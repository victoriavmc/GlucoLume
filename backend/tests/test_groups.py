# Pruebas del módulo Grupo familiar: un grupo activo por cuenta, invitaciones con aceptación, administración y,
# sobre todo, los permisos personales de compartición verificados en cada consulta.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_groups.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py.

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.group import FamilyGroupCreateRequest, FamilyGroupUpdateRequest, SharingSettings
from app.integrations.email import sender
from app.services import dashboard as dashboards
from app.services import group as groups
from app.services import notifications
from app.services.contact import RateLimiter
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    addMeasurement,
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)


@pytest.fixture(autouse=True)
def freshLimiter(monkeypatch):
    monkeypatch.setattr(groups, "_lookupLimiter", RateLimiter(100, 600))


def expectError(code, fn, *args, **kwargs) -> AuthError:
    with pytest.raises(AuthError) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.message
    return error.value


def person(db, name, **kwargs) -> User:
    return makeUser(db, email=f"{name}@example.com", usuario=name, **kwargs)


def create(db, user, nombre="Familia Pérez"):
    return groups.createGroup(db, user, FamilyGroupCreateRequest(nombre=nombre, descripcion="Nuestro grupo"))


def join(db, admin, idGrupo, user):
    invitation = groups.invite(db, admin, idGrupo, user.correoElectronico)
    return groups.respondInvitation(db, user, invitation.idGrupoUsuario, accept=True)


def share(db, user, idGrupo, **flags):
    return groups.updateMySharing(db, user, idGrupo, SharingSettings(**flags))


def relationOf(db, idGrupo, user) -> GroupUser:
    db.expire_all()
    return db.scalar(select(GroupUser).where(GroupUser.idGrupo == idGrupo, GroupUser.idUsuario == user.idUsuario,
                                             GroupUser.estadoRelacion != "BAJA"))


def addReading(db, profile, daysAgo, spo2):
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
    db.add(device)
    db.flush()
    db.add(Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=36, sexoModelo="FEMENINO",
        condicionComida="AYUNO", fechaHoraInicio=nowForDb() - timedelta(days=daysAgo, hours=1),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=daysAgo, hours=10), spo2=spo2, frecuenciaCardiaca=70,
        modeloSensorAlMomento="MAX30102",
    ))
    db.commit()


@pytest.fixture
def family(db, mails):
    """Ana administra; Beto es miembro con perfil y 3 mediciones; ninguno comparte nada todavía."""
    ana, beto = person(db, "ana"), person(db, "beto")
    group = create(db, ana)
    join(db, ana, group.idGrupo, beto)
    profile, _ = addMeasurement(db, beto)  # medición de hace 3 días
    addReading(db, profile, 2, 96)
    addReading(db, profile, 0, 98)
    mails.clear()

    class Family:
        pass

    family = Family()
    family.ana, family.beto, family.id, family.profile = ana, beto, group.idGrupo, profile
    family.betoLink = relationOf(db, group.idGrupo, beto).idGrupoUsuario
    family.anaLink = relationOf(db, group.idGrupo, ana).idGrupoUsuario
    return family


# --- 1-3. Creación y un solo grupo activo ----------------------------------------------------


def test_un_usuario_individual_crea_un_grupo_y_queda_administrador(db, mails):
    ana = person(db, "ana")
    group = create(db, ana)
    assert (group.miRol, group.cantidadIntegrantes, group.administrador) == ("ADMINISTRADOR", 1, "Victoria Cortés")
    stored = db.get(Group, group.idGrupo)
    assert stored.estado == "ACTIVO" and stored.fechaCreacion is not None
    sharing = groups.getMySharing(db, ana, group.idGrupo)
    assert not any(getattr(sharing, f) for f in groups.SHARING_FIELDS)  # el administrador tampoco comparte nada
    assert groups.getMine(db, ana).idGrupo == group.idGrupo


def test_una_cuenta_institucional_no_crea_ni_se_incorpora(db, mails):
    inst = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL", email="inst@example.com", usuario="inst")
    expectError("PERMISO_INSUFICIENTE", create, db, inst)
    ana = person(db, "ana")
    group = create(db, ana)
    error = expectError("CUENTA_NO_INDIVIDUAL", groups.invite, db, ana, group.idGrupo, "inst@example.com")
    assert "cuenta institucional" in error.message


def test_no_puede_tener_dos_grupos_activos(db, mails):
    ana, beto = person(db, "ana"), person(db, "beto")
    group = create(db, ana)
    error = expectError("YA_PERTENECE_A_GRUPO", create, db, ana, "Otro")
    assert error.message == groups.ALREADY_IN_GROUP_MESSAGE
    other = create(db, beto, "Familia Gómez")
    error = expectError("YA_PERTENECE_A_GRUPO", groups.invite, db, ana, group.idGrupo, "beto@example.com")
    assert error.message == "El usuario no puede incorporarse porque ya pertenece a otro grupo."
    assert other.idGrupo != group.idGrupo
    # La base también lo impide aunque se saltee el servicio.
    db.add(GroupUser(idGrupo=group.idGrupo, idUsuario=beto.idUsuario, rolGrupo="MIEMBRO", estadoRelacion="ACTIVO",
                     fechaIncorporacion=nowForDb()))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# --- 4-9. Invitaciones ------------------------------------------------------------------------


def test_invitacion_no_incorpora_hasta_aceptar(db, mails):
    ana, beto = person(db, "ana"), person(db, "beto")
    group = create(db, ana)
    assert groups.lookupCandidate(db, ana, group.idGrupo, "beto@example.com").model_dump() == {
        "nombre": "Victoria", "apellido": "Cortés"}
    invitation = groups.invite(db, ana, group.idGrupo, "beto@example.com")
    assert mails[-1]["to"] == "beto@example.com" and "/app/grupo" in mails[-1]["html"]
    # Pendiente: no es integrante ni ve el grupo.
    assert groups.getMine(db, beto) is None
    expectError("GRUPO_NO_ENCONTRADO", groups.getDetail, db, beto, group.idGrupo)
    assert [m.nombre for m in groups.listMembers(db, ana, group.idGrupo)] == ["Victoria"]
    [received] = groups.listReceivedInvitations(db, beto)
    assert (received.nombreGrupo, received.nombreAdministrador, received.estado) == (
        "Familia Pérez", "Victoria Cortés", "PENDIENTE")
    [sent] = groups.listSentInvitations(db, ana, group.idGrupo)
    assert sent.idGrupoUsuario == invitation.idGrupoUsuario

    detail = groups.respondInvitation(db, beto, invitation.idGrupoUsuario, accept=True)
    assert (detail.miRol, detail.cantidadIntegrantes) == ("MIEMBRO", 2)
    assert not any(getattr(groups.getMySharing(db, beto, group.idGrupo), f) for f in groups.SHARING_FIELDS)


def test_rechazar_registra_y_no_crea_vinculo(db, mails):
    ana, beto = person(db, "ana"), person(db, "beto")
    group = create(db, ana)
    invitation = groups.invite(db, ana, group.idGrupo, "beto@example.com")
    assert groups.respondInvitation(db, beto, invitation.idGrupoUsuario, accept=False) is None
    assert reload(db, GroupUser, invitation.idGrupoUsuario).estadoRelacion == "BAJA"
    assert audits(db, "RECHAZAR_INVITACION_GRUPO")
    assert groups.getMine(db, beto) is None


def test_mensajes_de_invitacion(db, mails):
    ana = person(db, "ana")
    group = create(db, ana)
    error = expectError("USUARIO_NO_ENCONTRADO", groups.invite, db, ana, group.idGrupo, "nadie@example.com")
    assert error.message.startswith("No existe una cuenta individual registrada con este correo.")
    pendiente = person(db, "pendiente")
    pendiente.estado = "PENDIENTE"  # correo sin verificar
    db.commit()
    expectError("USUARIO_NO_ENCONTRADO", groups.invite, db, ana, group.idGrupo, "pendiente@example.com")
    person(db, "beto")
    groups.invite(db, ana, group.idGrupo, "beto@example.com")
    expectError("INVITACION_PENDIENTE", groups.invite, db, ana, group.idGrupo, "beto@example.com")


def test_aceptar_invalida_las_demas_invitaciones(db, mails):
    ana, beto, carla = person(db, "ana"), person(db, "beto"), person(db, "carla")
    g1, g2 = create(db, ana), create(db, carla, "Familia Gómez")
    i1 = groups.invite(db, ana, g1.idGrupo, "beto@example.com")
    i2 = groups.invite(db, carla, g2.idGrupo, "beto@example.com")
    groups.respondInvitation(db, beto, i1.idGrupoUsuario, accept=True)
    assert reload(db, GroupUser, i2.idGrupoUsuario).estadoRelacion == "BAJA"
    expectError("INVITACION_NO_ENCONTRADA", groups.respondInvitation, db, beto, i2.idGrupoUsuario, True)


def test_aceptaciones_simultaneas_no_generan_doble_pertenencia(engine, db, mails):
    ana, beto, carla = person(db, "ana"), person(db, "beto"), person(db, "carla")
    g1, g2 = create(db, ana), create(db, carla, "Familia Gómez")
    invitations = [groups.invite(db, ana, g1.idGrupo, "beto@example.com"),
                   groups.invite(db, carla, g2.idGrupo, "beto@example.com")]
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def accept(idGrupoUsuario):
        session = makeSession()
        try:
            user = session.get(User, beto.idUsuario)
            barrier.wait()
            groups.respondInvitation(session, user, idGrupoUsuario, accept=True)
            results.append("OK")
        except AuthError as error:
            results.append(error.code)
        except Exception as error:  # pragma: no cover - diagnóstico
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=accept, args=(i.idGrupoUsuario,)) for i in invitations]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert results.count("OK") == 1
    db.expire_all()
    active = db.scalar(select(func.count()).select_from(GroupUser).where(
        GroupUser.idUsuario == beto.idUsuario, GroupUser.estadoRelacion == "ACTIVO"))
    assert active == 1


def test_un_miembro_no_tiene_funciones_administrativas(db, mails, family):
    carla = person(db, "carla")
    expectError("PERMISO_INSUFICIENTE", groups.invite, db, family.beto, family.id, "carla@example.com")
    expectError("PERMISO_INSUFICIENTE", groups.listSentInvitations, db, family.beto, family.id)
    expectError("PERMISO_INSUFICIENTE", groups.removeMember, db, family.beto, family.id, family.anaLink)
    expectError("PERMISO_INSUFICIENTE", groups.updateGroup, db, family.beto, family.id,
                FamilyGroupUpdateRequest(nombre="Otro"))
    expectError("PERMISO_INSUFICIENTE", groups.deleteGroup, db, family.beto, family.id, "Familia Pérez")
    assert carla.idUsuario


def test_grupos_ajenos_no_se_consultan(db, mails, family):
    carla = person(db, "carla")
    create(db, carla, "Familia Gómez")
    expectError("GRUPO_NO_ENCONTRADO", groups.getDetail, db, carla, family.id)
    expectError("GRUPO_NO_ENCONTRADO", groups.sharedLatest, db, carla, family.id, family.betoLink)


# --- 10-15. Permisos de compartición ----------------------------------------------------------


def test_permisos_desactivados_por_defecto_y_sin_acceso(db, mails, family):
    summary = {m.idGrupoUsuario: m for m in groups.sharedMembers(db, family.ana, family.id)}[family.betoLink]
    assert not any(getattr(summary, f) for f in groups.SHARING_FIELDS) and summary.tienePerfil
    for fn in (groups.sharedProfile, groups.sharedLatest, groups.sharedHistory, groups.sharedStatistics):
        expectError("DATOS_NO_COMPARTIDOS", fn, db, family.ana, family.id, family.betoLink)  # ni el administrador


def test_cada_integrante_modifica_solo_sus_permisos_y_queda_el_consentimiento(db, mails, family):
    mine = share(db, family.beto, family.id, comparteUltimaMedicion=True)
    assert (mine.comparteUltimaMedicion, mine.comparteHistorial) == (True, False)
    assert mine.idPerfilMedicion == family.profile.idPerfilMedicion
    # El administrador cambia los suyos, no los de Beto (no existe forma de indicar otro vínculo).
    share(db, family.ana, family.id, compartePerfil=True)
    assert groups.getMySharing(db, family.beto, family.id).compartePerfil is False
    [consent] = [a for a in audits(db, "CONSENTIMIENTO_COMPARTICION_GRUPO") if a.idUsuario == family.beto.idUsuario]
    assert '"comparteUltimaMedicion": true' in consent.datosNuevos and consent.fechaHora is not None


def test_ultima_medicion_no_habilita_el_historial(db, mails, family):
    share(db, family.beto, family.id, comparteUltimaMedicion=True)
    latest = groups.sharedLatest(db, family.ana, family.id, family.betoLink)
    assert float(latest.medicion.spo2) == 98.0  # la más reciente
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, family.ana, family.id, family.betoLink)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedStatistics, db, family.ana, family.id, family.betoLink)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedProfile, db, family.ana, family.id, family.betoLink)


def test_cada_permiso_expone_solo_lo_suyo(db, mails, family):
    share(db, family.beto, family.id, compartePerfil=True, comparteHistorial=True)  # el historial habilita gráficos
    profile = groups.sharedProfile(db, family.ana, family.id, family.betoLink)
    assert set(profile.model_dump()) == {"edad", "sexoModelo"}  # sin documento ni fecha de nacimiento
    history = groups.sharedHistory(db, family.ana, family.id, family.betoLink)
    assert history.total == 3 and [float(m.spo2) for m in history.items] == [98.0, 96.0, 97.0]
    stats = groups.sharedStatistics(db, family.ana, family.id, family.betoLink, dias=7)
    assert stats.cantidadMediciones == 3 and stats.spo2.minimo == 96.0 and stats.spo2.maximo == 98.0
    # Tres mediciones en días distintos, salvo cerca de la medianoche (la de hace 1 h cae en el día anterior).
    assert len(stats.serieDiaria) in (2, 3) and "items" not in stats.model_dump()
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedLatest, db, family.ana, family.id, family.betoLink)
    expectError("PERIODO_INVALIDO", groups.sharedStatistics, db, family.ana, family.id, family.betoLink, dias=365)


def markDemo(db, profile, *, glucoseMode=False):
    """Todas las mediciones del perfil quedan como datos de prueba del dispositivo (origen DEMO), como las reales del proyecto."""
    db.execute(update(Measurement).where(Measurement.idPerfilMedicion == profile.idPerfilMedicion).values(
        origenGlucosa="DEMO", glucosaDispositivo=114, unidadGlucosa="mg/dL"))
    if glucoseMode:
        latest = db.scalar(select(Measurement).where(Measurement.idPerfilMedicion == profile.idPerfilMedicion)
                           .order_by(Measurement.fechaHoraInicio.desc()).limit(1))
        latest.modoMedicion = "GLUCOSA_EXPERIMENTAL"
    db.commit()


def test_las_mediciones_demo_o_de_prueba_se_comparten_identificadas(db, mails, family):
    """Todas las mediciones del proyecto son experimentales o de prueba: el grupo las muestra, identificadas, no las oculta."""
    markDemo(db, family.profile, glucoseMode=True)
    share(db, family.beto, family.id, comparteUltimaMedicion=True, comparteHistorial=True)
    latest = groups.sharedLatest(db, family.ana, family.id, family.betoLink).medicion
    assert latest is not None and latest.esDemo is True and latest.origenGlucosa == "DEMO"
    # Modo glucosa: el valor sintético vive en glucosaDispositivo (glucosaEstimada queda vacía por restricción) y se informa.
    assert latest.modoMedicion == "GLUCOSA_EXPERIMENTAL" and float(latest.glucosa) == 114.0 and latest.glucosaEstimada is None
    history = groups.sharedHistory(db, family.ana, family.id, family.betoLink)
    assert history.total == 3 and all(m.esDemo for m in history.items)
    # El orden es de la más reciente a la más antigua y se respeta la clasificación original (oximetría no informa glucosa).
    moments = [m.fechaHoraInicio for m in history.items]
    assert moments == sorted(moments, reverse=True)
    assert [m.modoMedicion for m in history.items] == ["GLUCOSA_EXPERIMENTAL", "OXIMETRIA", "OXIMETRIA"]
    assert [m.glucosa for m in history.items][1:] == [None, None]


def test_aviso_de_medicion_solo_muestra_fecha_y_hora_y_es_independiente(db, mails, family):
    markDemo(db, family.profile)
    share(db, family.beto, family.id, notificaMedicion=True)  # solo el aviso
    notices = groups.sharedNotices(db, family.ana, family.id, family.betoLink)
    assert notices.total == 3 and len(notices.items) == 3
    moments = [item.fechaHoraInicio for item in notices.items]
    assert moments == sorted(moments, reverse=True)
    # Ni un solo dato de salud ni identificador: únicamente cuándo.
    assert all(set(item.model_dump()) == {"fechaHoraInicio"} for item in notices.items)
    for fn in (groups.sharedProfile, groups.sharedLatest, groups.sharedHistory, groups.sharedStatistics):
        expectError("DATOS_NO_COMPARTIDOS", fn, db, family.ana, family.id, family.betoLink)
    # Revocar corta el aviso en la consulta siguiente y no borra las mediciones.
    share(db, family.beto, family.id)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedNotices, db, family.ana, family.id, family.betoLink)
    assert db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idPerfilMedicion == family.profile.idPerfilMedicion)) == 3


def test_los_avisos_se_pueden_paginar_para_ver_todos_los_de_una_persona(db, mails, family):
    share(db, family.beto, family.id, notificaMedicion=True)
    first = groups.sharedNotices(db, family.ana, family.id, family.betoLink, limite=2, pagina=1)
    second = groups.sharedNotices(db, family.ana, family.id, family.betoLink, limite=2, pagina=2)
    assert first.total == second.total == 3 and len(first.items) == 2 and len(second.items) == 1
    moments = [item.fechaHoraInicio for item in first.items + second.items]
    assert moments == sorted(moments, reverse=True) and len(set(moments)) == 3  # todos, sin repetir, del más nuevo al más viejo


def test_cada_permiso_funciona_solo_para_su_propia_consulta(db, mails, family):
    consultas = {
        "compartePerfil": groups.sharedProfile, "comparteUltimaMedicion": groups.sharedLatest,
        "comparteHistorial": groups.sharedHistory, "notificaMedicion": groups.sharedNotices,
    }
    markDemo(db, family.profile)
    for permiso, consulta in consultas.items():
        share(db, family.beto, family.id, **{permiso: True})
        assert consulta(db, family.ana, family.id, family.betoLink) is not None
        for otro, otraConsulta in consultas.items():
            if otro != permiso:
                expectError("DATOS_NO_COMPARTIDOS", otraConsulta, db, family.ana, family.id, family.betoLink)
    share(db, family.beto, family.id)  # ninguno: nada privado
    for consulta in consultas.values():
        expectError("DATOS_NO_COMPARTIDOS", consulta, db, family.ana, family.id, family.betoLink)


def test_los_avisos_no_se_consultan_desde_fuera_del_grupo(db, mails, family):
    share(db, family.beto, family.id, notificaMedicion=True)
    carla = person(db, "carla")
    create(db, carla, "Familia Gómez")
    expectError("GRUPO_NO_ENCONTRADO", groups.sharedNotices, db, carla, family.id, family.betoLink)
    expectError("MIEMBRO_NO_ENCONTRADO", groups.sharedNotices, db, family.ana, family.id, family.anaLink)  # los propios, no


def test_la_actividad_del_dashboard_del_grupo_incluye_mediciones_demo(db, mails, family):
    markDemo(db, family.profile)
    share(db, family.beto, family.id, comparteUltimaMedicion=True)
    data = dashboards.groupDashboard(db, family.ana, family.id)
    assert [item.idGrupoUsuario for item in data.actividadReciente] == [family.betoLink]
    assert data.actividadReciente[0].medicion.esDemo is True


def test_la_actividad_incluye_el_aviso_de_medicion_sin_valores(db, mails, family):
    # Solo aviso: aparece la medición completada con su fecha y hora, pero SIN medición (ningún valor ni dato clínico).
    share(db, family.beto, family.id, notificaMedicion=True)
    data = dashboards.groupDashboard(db, family.ana, family.id)
    avisos = [item for item in data.actividadReciente if item.idGrupoUsuario == family.betoLink]
    assert avisos and all(item.tipo == "AVISO" and item.medicion is None and item.fechaHoraInicio is not None for item in avisos)
    dumped = [item.model_dump() for item in avisos]
    assert all(set(item) == {"idGrupoUsuario", "nombre", "apellido", "tipo", "fechaHoraInicio", "medicion"} and item["medicion"] is None for item in dumped)
    # Aviso + última medición: la última trae sus valores y el resto del cupo figura como aviso, sin repetirla.
    share(db, family.beto, family.id, notificaMedicion=True, comparteUltimaMedicion=True)
    mixed = [item for item in dashboards.groupDashboard(db, family.ana, family.id).actividadReciente if item.idGrupoUsuario == family.betoLink]
    assert [item.tipo for item in mixed] == ["MEDICION", "AVISO"]
    assert mixed[0].medicion is not None and mixed[0].fechaHoraInicio > mixed[1].fechaHoraInicio
    # Sin ningún permiso, no hay actividad.
    share(db, family.beto, family.id)
    assert not [item for item in dashboards.groupDashboard(db, family.ana, family.id).actividadReciente if item.idGrupoUsuario == family.betoLink]


def test_la_actividad_toma_un_cupo_por_integrante_y_luego_ordena_todo_junto(db, mails, family):
    """Cada persona aporta como máximo ACTIVITY_PER_MEMBER actividades (aunque tenga más); después se ordena todo por fecha y hora."""
    # Ana comparte todo y tiene 4 mediciones; Beto (3 mediciones) comparte solo el aviso. Quedan intercaladas en el tiempo.
    anaProfile, _ = addMeasurement(db, family.ana)  # hace 3 días
    for daysAgo in (1.5, 0.5, 0.25):
        addReading(db, anaProfile, daysAgo, 97)
    share(db, family.ana, family.id, compartePerfil=True, comparteUltimaMedicion=True, comparteHistorial=True, notificaMedicion=True)
    share(db, family.beto, family.id, notificaMedicion=True)
    feed = dashboards.groupDashboard(db, family.ana, family.id).actividadReciente
    cupo = dashboards.ACTIVITY_PER_MEMBER
    assert cupo == 2
    porPersona = {link: [item for item in feed if item.idGrupoUsuario == link] for link in (family.anaLink, family.betoLink)}
    assert [len(items) for items in porPersona.values()] == [cupo, cupo]  # ni 4 de Ana ni 3 de Beto: nadie monopoliza la lista
    assert len(feed) == 2 * cupo
    # Orden global descendente, mezclando a las dos personas (no «todo Ana y luego todo Beto»).
    assert [item.fechaHoraInicio for item in feed] == sorted((item.fechaHoraInicio for item in feed), reverse=True)
    assert [item.idGrupoUsuario for item in feed] == [family.betoLink, family.anaLink, family.anaLink, family.betoLink]
    # Ana comparte el historial: sus actividades traen valores. Beto solo el aviso: ninguno.
    assert all(item.tipo == "MEDICION" and item.medicion is not None for item in porPersona[family.anaLink])
    assert all(item.tipo == "AVISO" and item.medicion is None for item in porPersona[family.betoLink])


def test_revocar_bloquea_la_consulta_siguiente(db, mails, family):
    share(db, family.beto, family.id, comparteHistorial=True)
    groups.sharedHistory(db, family.ana, family.id, family.betoLink)
    share(db, family.beto, family.id)  # todo en false
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, family.ana, family.id, family.betoLink)
    assert audits(db, "REVOCAR_COMPARTICION_GRUPO")
    assert any(a.resultado == "FALLO" for a in audits(db, "CONSULTAR_DATOS_GRUPO"))


def test_no_se_exponen_perfiles_institucionales(db, mails, family):
    # Un perfil INSTITUCIONAL nunca es el "perfil propio" que se comparte.
    profile = groups._ownProfile(db, family.beto.idUsuario)
    assert profile.tipoPerfil == "CONSUMIDOR_FINAL"


# --- 16-19. Salida, transferencia, eliminación --------------------------------------------------


def test_abandonar_conserva_mediciones_y_corta_el_acceso(db, mails, family):
    share(db, family.beto, family.id, comparteHistorial=True)
    groups.leaveGroup(db, family.beto, family.id)
    assert reload(db, GroupUser, family.betoLink).estadoRelacion == "BAJA"
    assert reload(db, GroupUser, family.betoLink).comparteHistorial is False
    expectError("MIEMBRO_NO_ENCONTRADO", groups.sharedHistory, db, family.ana, family.id, family.betoLink)
    expectError("GRUPO_NO_ENCONTRADO", groups.getDetail, db, family.beto, family.id)
    count = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.idPerfilMedicion == family.profile.idPerfilMedicion))
    assert count == 3 and reload(db, MeasurementProfile, family.profile.idPerfilMedicion) is not None
    # Puede crear otro grupo.
    assert create(db, family.beto, "Nuevo").miRol == "ADMINISTRADOR"


def test_el_administrador_transfiere_antes_de_abandonar(db, mails, family):
    expectError("TRANSFERENCIA_REQUERIDA", groups.leaveGroup, db, family.ana, family.id)
    detail = groups.transferAdmin(db, family.ana, family.id, family.betoLink)
    assert detail.miRol == "MIEMBRO" and detail.administrador == "Victoria Cortés"
    assert groups.getDetail(db, family.beto, family.id).miRol == "ADMINISTRADOR"
    admins = db.scalar(select(func.count()).select_from(GroupUser).where(
        GroupUser.idGrupo == family.id, GroupUser.rolGrupo == "PROPIETARIO", GroupUser.estadoRelacion == "ACTIVO"))
    assert admins == 1
    groups.leaveGroup(db, family.ana, family.id)
    expectError("ELIMINACION_REQUERIDA", groups.leaveGroup, db, family.beto, family.id)


def test_eliminar_grupo_conserva_cuentas_y_mediciones(db, mails, family):
    carla = person(db, "carla")
    pending = groups.invite(db, family.ana, family.id, "carla@example.com")
    share(db, family.beto, family.id, comparteHistorial=True)
    mails.clear()
    expectError("CONFIRMACION_INVALIDA", groups.deleteGroup, db, family.ana, family.id, "Familia")
    groups.deleteGroup(db, family.ana, family.id, "familia pérez")
    assert reload(db, Group, family.id).estado == "CERRADO"
    links = db.scalars(select(GroupUser).where(GroupUser.idGrupo == family.id)).all()
    assert {link.estadoRelacion for link in links} == {"BAJA"} and not any(link.comparteHistorial for link in links)
    for user in (family.ana, family.beto, carla):
        assert reload(db, User, user.idUsuario).estado == "ACTIVO"
    assert db.scalar(select(func.count()).select_from(Measurement)) == 3
    expectError("GRUPO_NO_ENCONTRADO", groups.sharedHistory, db, family.ana, family.id, family.betoLink)
    assert reload(db, GroupUser, pending.idGrupoUsuario).estadoRelacion == "BAJA"
    # Beto (integrante activo) recibe el aviso de eliminación; Ana (quien lo eliminó) recibe su propia confirmación.
    bySubject = {m["to"]: m["subject"] for m in mails}
    assert bySubject == {"beto@example.com": "El grupo fue eliminado", "ana@example.com": "Eliminaste el grupo con éxito"}
    confirmation = next(m for m in mails if m["to"] == "ana@example.com")
    assert "Familia Pérez" in confirmation["text"] and "1" in confirmation["text"]
    # Todos pueden formar nuevos grupos.
    create(db, family.ana, "Otra familia")
    assert db.scalar(select(Audit).where(Audit.accion == "ELIMINAR_GRUPO")) is not None


def test_un_desvinculado_puede_incorporarse_a_otro_grupo(db, mails, family):
    groups.removeMember(db, family.ana, family.id, family.betoLink)
    assert mails[-1]["to"] == "beto@example.com"
    carla = person(db, "carla")
    other = create(db, carla, "Familia Gómez")
    assert join(db, carla, other.idGrupo, family.beto).miRol == "MIEMBRO"


# --- Confirmación de creación por correo ----------------------------------------------------------


def test_crear_grupo_notifica_al_creador_despues_del_commit(db, mails, engine, monkeypatch):
    seen = []
    original = sender.sendHtmlEmail

    def checkCommitted(recipient, subject, *args, **kwargs):
        with engine.connect() as connection:  # conexión independiente: solo ve lo confirmado
            seen.append(connection.execute(text("SELECT COUNT(*) FROM dbo.Grupo")).scalar())
        return original(recipient, subject, *args, **kwargs)

    monkeypatch.setattr(sender, "sendHtmlEmail", checkCommitted)
    ana = person(db, "ana")
    group = create(db, ana, nombre="Los Pérez")
    assert seen == [1]  # el grupo ya estaba confirmado al enviar
    [mail] = mails
    assert mail["to"] == "ana@example.com"
    assert mail["subject"] == "GlucoLume — Tu grupo fue creado correctamente"
    for fragment in ("Los Pérez", "Victoria Cortés", "Propietario/a", f"/app/grupo/{group.idGrupo}"):
        assert fragment in mail["html"], fragment
    [notice] = audits(db, notifications.ACCION_GRUPO)
    assert notice.resultado == "EXITO" and notice.idRegistro == group.idGrupo
    assert "ana@example.com" not in (notice.observacion or "") + (notice.datosNuevos or "")


def test_fallo_smtp_no_revierte_el_grupo_y_permite_reintentar_sin_duplicar(db, mails, monkeypatch):
    original = sender.sendHtmlEmail

    def failing(*args, **kwargs):
        raise OSError("SMTP caído")

    monkeypatch.setattr(sender, "sendHtmlEmail", failing)
    ana = person(db, "ana")
    group = create(db, ana)  # responde bien aunque el correo falle
    assert db.get(Group, group.idGrupo).estado == "ACTIVO"
    assert [a.resultado for a in audits(db, notifications.ACCION_GRUPO)] == ["FALLO"]

    monkeypatch.setattr(sender, "sendHtmlEmail", original)
    groups.resendCreationNotice(db, ana, group.idGrupo)
    assert len(mails) == 1
    expectError("NOTIFICACION_YA_ENVIADA", groups.resendCreationNotice, db, ana, group.idGrupo)
    assert len(mails) == 1  # el reintento no duplica


def test_un_miembro_no_reenvia_la_confirmacion(db, mails, family):
    expectError("PERMISO_INSUFICIENTE", groups.resendCreationNotice, db, family.beto, family.id)


# --- Visibilidad de permisos y gráficos derivados del historial -----------------------------------


def test_el_permiso_de_estadisticas_ya_no_existe():
    assert set(SharingSettings.model_fields) == {
        "compartePerfil", "comparteUltimaMedicion", "comparteHistorial", "notificaMedicion"}  # 4.º: aviso, no da acceso a datos
    assert not hasattr(GroupUser, "comparteEstadisticas")
    with pytest.raises(ValueError):
        SharingSettings(comparteEstadisticas=True)


def test_todos_los_integrantes_ven_que_comparte_cada_uno(db, mails, family):
    share(db, family.beto, family.id, comparteUltimaMedicion=True)
    for viewer in (family.ana, family.beto):
        members = {m.idGrupoUsuario: m for m in groups.listMembers(db, viewer, family.id)}
        beto, ana = members[family.betoLink], members[family.anaLink]
        assert (beto.compartePerfil, beto.comparteUltimaMedicion, beto.comparteHistorial) == (False, True, False)
        assert (ana.compartePerfil, ana.comparteUltimaMedicion, ana.comparteHistorial) == (False, False, False)
        assert beto.tienePerfil is True
        dumped = beto.model_dump()
        assert "spo2" not in dumped and "medicion" not in dumped  # el listado muestra permisos, nunca datos


def test_juan_comparte_historial_y_pepe_ve_sus_graficos(db, mails):
    juan, pepe = person(db, "juan"), person(db, "pepe")
    group = create(db, juan)
    join(db, juan, group.idGrupo, pepe)
    profile, _ = addMeasurement(db, juan)
    addReading(db, profile, 1, 95)
    juanLink = relationOf(db, group.idGrupo, juan).idGrupoUsuario
    share(db, juan, group.idGrupo, comparteHistorial=True)
    assert groups.sharedHistory(db, pepe, group.idGrupo, juanLink).total == 2
    assert groups.sharedStatistics(db, pepe, group.idGrupo, juanLink, dias=7).cantidadMediciones == 2
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedProfile, db, pepe, group.idGrupo, juanLink)


def test_pepe_no_comparte_nada_y_juan_no_ve_sus_datos(db, mails):
    juan, pepe = person(db, "juan"), person(db, "pepe")
    group = create(db, juan)
    join(db, juan, group.idGrupo, pepe)
    addMeasurement(db, pepe)
    pepeLink = relationOf(db, group.idGrupo, pepe).idGrupoUsuario
    [row] = [m for m in groups.listMembers(db, juan, group.idGrupo) if m.idGrupoUsuario == pepeLink]
    assert not (row.compartePerfil or row.comparteUltimaMedicion or row.comparteHistorial)
    for fn in (groups.sharedProfile, groups.sharedLatest, groups.sharedHistory, groups.sharedStatistics):
        expectError("DATOS_NO_COMPARTIDOS", fn, db, juan, group.idGrupo, pepeLink)


def test_revocar_historial_bloquea_tambien_los_graficos(db, mails, family):
    share(db, family.beto, family.id, comparteHistorial=True)
    groups.sharedStatistics(db, family.ana, family.id, family.betoLink, dias=7)
    share(db, family.beto, family.id, comparteHistorial=False)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedStatistics, db, family.ana, family.id, family.betoLink)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, family.ana, family.id, family.betoLink)
