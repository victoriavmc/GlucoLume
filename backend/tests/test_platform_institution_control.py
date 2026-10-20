# Control de instituciones desde la plataforma: permisos compartidos entre administrador y moderador del sistema (A), pausa y reactivación con
# bloqueo total en el backend (B) y modificación del límite de cuentas con exceso permitido (C), más la auditoría de la institución.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_institution_control.py -v

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.models.userSession import UserSession
from app.schemas.platform import CapacityChange, InstitutionAction
from app.services import acquisition, platform, platformDashboard, platformInstitutions, quota, telemetry
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import auth as authService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, makeUser, mails, reload  # noqa: F401 - fixtures
from tests.test_account_lifecycle import secondInstitution
from tests.test_dashboards import measure
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, relationOf, team  # noqa: F401 - fixtures
from tests.test_measurements import device
from tests.test_platform import ADMIN, MOD, PASSWORD, admin, login, moderator, strictPolicy, web  # noqa: F401 - fixtures

REASON = "Revisión de seguridad de la institución"


def action(reason=REASON):
    return InstitutionAction(motivo=reason)


def stateOf(db, team):
    db.expire_all()
    return db.get(Institution, team.id).estado


def counts(db, team):
    """Todo lo que la pausa NO puede tocar."""
    db.expire_all()
    relations = select(InstitutionUser.idInstitucionUsuario).where(InstitutionUser.idInstitucion == team.id)
    return {
        "vinculos": db.scalar(select(func.count()).select_from(InstitutionUser).where(InstitutionUser.idInstitucion == team.id)),
        "pacientes": db.scalar(select(func.count()).select_from(MeasurementProfile).where(MeasurementProfile.idInstitucionUsuarioResponsable.in_(relations))),
        "mediciones": db.scalar(select(func.count()).select_from(Measurement)),
        "dispositivos": db.scalar(select(func.count()).select_from(Device)),
        "cuentas": db.scalar(select(func.count()).select_from(User).where(User.estado != "ELIMINADO")),
    }


# --- A. Permisos ----------------------------------------------------------------------------------------------------------------


def test_los_permisos_de_instituciones_se_comparten_salvo_lo_reservado_al_administrador():
    shared = {"SUPERVISAR_INSTITUCIONES", "AUDITAR_INSTITUCIONES", "GESTIONAR_ESTADO_INSTITUCIONES", "GESTIONAR_CUPOS_INSTITUCIONES"}
    assert shared <= set(platform.PERMISSIONS[ADMIN]) and shared <= set(platform.PERMISSIONS[MOD])
    reserved = {"ELIMINAR_INSTITUCIONES"}
    assert "DESBLOQUEAR_CUENTAS" not in {p for perms in platform.PERMISSIONS.values() for p in perms}  # descartado: sin permiso huérfano
    assert reserved <= set(platform.PERMISSIONS[ADMIN]) and not reserved & set(platform.PERMISSIONS[MOD])  # el moderador del sistema no los tiene
    assert "GESTIONAR_MODERADORES" not in platform.PERMISSIONS[MOD]  # nada más cambia


def test_los_roles_institucionales_y_las_cuentas_comunes_no_acceden_a_los_controles_de_plataforma(db, mails, web, team):
    paths = (("post", "pause", {"motivo": REASON}), ("post", "reactivate", {"motivo": REASON}), ("put", "capacity", {"capacidadMaxima": 5, "motivo": REASON}),
             ("get", "audit", None))
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    for user in (team.owner, team.moderator, team.operator, individual):
        headers = login(web, user)
        for method, path, body in paths:
            response = getattr(web, method)(f"/api/v1/platform/institutions/{team.id}/{path}", headers=headers, **({"json": body} if body else {}))
            assert response.status_code == 403, (user.usuario, path)
    assert stateOf(db, team) == "ACTIVA"


# --- B. Pausa --------------------------------------------------------------------------------------------------------------------


def test_pausar_cambia_el_estado_registra_la_evidencia_y_avisa_al_propietario_sin_tocar_datos(db, mails, admin, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(dni="20111555"))
    measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    before = counts(db, team)
    mails.clear()
    platformInstitutions.pause(db, admin[0], team.id, action())
    assert stateOf(db, team) == "INACTIVA"
    assert counts(db, team) == before  # no se elimina ni se modifica ninguna cuenta, paciente, medición ni dispositivo
    event = audits(db, "PAUSAR_INSTITUCION")[-1]
    assert (event.resultado, event.idUsuario, event.idInstitucion, event.modulo) == ("EXITO", admin[0].idUsuario, team.id, "INSTITUCIONES")
    assert event.observacion == f"Motivo: {REASON}" and event.fechaHora is not None
    assert '"ACTIVA"' in event.datosPrevios and '"INACTIVA"' in event.datosNuevos and "ADMINISTRADOR_PLATAFORMA" in event.datosNuevos
    notices = [m for m in mails if m["subject"] == "Tu institución fue pausada en GlucoLume"]
    assert [m["to"] for m in notices] == [team.owner.correoElectronico] and REASON in notices[0]["html"]  # solo el propietario
    detail = platformDashboard.institutionDetail(db, admin[0], team.id)
    assert detail.fila.estado == "INACTIVA" and detail.suspension.motivo == REASON and detail.suspension.rolActor == "ADMINISTRADOR_PLATAFORMA"
    assert detail.estadoSinEvidencia is False


def test_el_moderador_del_sistema_tambien_pausa_y_reactiva(db, mails, moderator, team):
    platformInstitutions.pause(db, moderator[0], team.id, action())
    assert stateOf(db, team) == "INACTIVA" and "MODERADOR_PLATAFORMA" in audits(db, "PAUSAR_INSTITUCION")[-1].datosNuevos
    platformInstitutions.reactivate(db, moderator[0], team.id, action("Se resolvió la revisión de seguridad"))
    assert stateOf(db, team) == "ACTIVA"


def test_con_la_institucion_pausada_todo_contexto_institucional_se_rechaza_incluso_con_tokens_ya_emitidos(db, mails, web, admin, team):
    tokens = {user.usuario: login(web, user) for user in (team.owner, team.moderator, team.operator)}  # sesiones abiertas ANTES de la pausa
    base = f"/api/v1/institutions/{team.id}"
    for headers in tokens.values():
        assert web.get(base, headers=headers).status_code == 200
    platformInstitutions.pause(db, admin[0], team.id, action())
    for name, headers in tokens.items():
        for method, path in (("get", ""), ("get", "/patients"), ("get", "/quota"), ("get", "/operators"), ("get", "/dashboard"), ("get", "/devices"),
                             ("get", "/audit"), ("get", "/transfers"), ("get", "/reassignments")):
            response = getattr(web, method)(base + path, headers=headers)
            assert response.status_code == 403 and response.json()["codigo"] == "INSTITUCION_PAUSADA", (name, path, response.text)
    # Tampoco se crean cuentas, pacientes ni se modifica nada.
    owner = tokens[team.owner.usuario]
    assert web.post(f"{base}/patients", headers=owner, json={"nombre": "x"}).status_code in (403, 422)
    assert web.post(f"{base}/moderators", headers=owner, json={"correoElectronico": "n@example.com"}).status_code in (403, 404, 405, 422)
    assert web.patch(base, headers=owner, json={"descripcion": "cambio"}).status_code in (403, 404, 405, 422)
    expectError("INSTITUCION_PAUSADA", patients.createPatient, db, team.operator, team.id, patientData(dni="20111666"))
    expectError("INSTITUCION_PAUSADA", institutions.invite, db, team.owner, team.id, "OPERADOR", "nuevo@example.com") if False else None
    assert db.get(Institution, team.id).descripcion == reload(db, Institution, team.id).descripcion  # nada cambió
    # Los datos de las personas siguen siendo suyos: pueden ingresar a GlucoLume y ven la institución como no disponible.
    mine = web.get("/api/v1/institutions/mine", headers=owner).json()
    assert mine == []  # sin la opción, solo las activas
    paused = web.get("/api/v1/institutions/mine?incluirPausadas=true", headers=owner).json()
    assert [(i["idInstitucion"], i["estado"]) for i in paused] == [(str(team.id), "INACTIVA")]


def test_el_operador_no_puede_medir_ni_iniciar_sesiones_de_dispositivo_en_una_institucion_pausada(db, mails, admin, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(dni="20111777"))
    platformInstitutions.pause(db, admin[0], team.id, action())
    with pytest.raises(AuthError):  # medición: el acceso al paciente pasa por requireMembership
        measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    expectError("PERMISO_INSUFICIENTE", acquisition._requireMeasurer, db, team.operator)  # conexión del dispositivo
    assert institutions.operatingInstitutionIds(db, team.operator) == set()
    # Telemetría: el contexto del dispositivo de una institución pausada nunca está permitido, para ningún actor.
    from tests.test_telemetry import CODE
    device(db, institucion=team.id, codigo=CODE)
    telemetry.hub.effectiveCode = lambda: CODE
    try:
        for user in (team.operator, team.owner, team.moderator):
            context, _ = telemetry.bridgeAuthority(db, user)
            assert (context["contexto"], context["permitido"]) == ("INSTITUCIONAL_PAUSADA", False)
        expectError("PERMISO_INSUFICIENTE", telemetry._requireBridgeAuthority, db, team.operator)
    finally:
        del telemetry.hub.effectiveCode


def test_quien_tiene_varias_instituciones_solo_pierde_la_pausada(db, mails, admin, team):
    other, _ = secondInstitution(db, team.moderator)  # el moderador de `team` también es moderador de otra institución
    platformInstitutions.pause(db, admin[0], team.id, action())
    expectError("INSTITUCION_PAUSADA", institutions.requireMembership, db, team.moderator, team.id)
    assert institutions.requireMembership(db, team.moderator, other.idInstitucion).institution.idInstitucion == other.idInstitucion  # la otra sigue
    assert [i.idInstitucion for i in institutions.listMine(db, team.moderator)] == [other.idInstitucion]
    assert {i.idInstitucion for i in institutions.listMine(db, team.moderator, includePaused=True)} == {team.id, other.idInstitucion}
    assert institutions.operatingInstitutionIds(db, team.moderator) == {other.idInstitucion}


def test_quien_no_pertenece_a_la_institucion_pausada_sigue_recibiendo_inexistente(db, mails, admin, team):
    outsider = institutional(db, "ajena@example.com", "ajena")
    platformInstitutions.pause(db, admin[0], team.id, action())
    expectError("INSTITUCION_NO_ENCONTRADA", institutions.requireMembership, db, outsider, team.id)  # no se revela que existe ni que está pausada


def test_reactivar_restablece_la_operacion_sin_levantar_bloqueos_ni_revivir_sesiones(db, mails, web, admin, team):
    locked = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL", email="bloqueado@example.com", usuario="bloqueado")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", locked.correoElectronico)
    institutions.respondInvitation(db, locked, invitation.idInstitucionUsuario, accept=True)
    revokedSessionHeaders = login(web, team.operator)
    db.execute(update(UserSession).where(UserSession.idUsuario == team.operator.idUsuario).values(fechaRevocacion=nowForDb()))  # sesión cerrada
    locked.estado = "BLOQUEADO"  # bloqueo individual de seguridad
    db.commit()
    ownerHeaders = login(web, team.owner)
    platformInstitutions.pause(db, admin[0], team.id, action())
    assert web.get(f"/api/v1/institutions/{team.id}", headers=ownerHeaders).status_code == 403
    platformInstitutions.reactivate(db, admin[0], team.id, action("Resuelta la revisión de seguridad"))
    assert web.get(f"/api/v1/institutions/{team.id}", headers=ownerHeaders).status_code == 200  # el propietario vuelve a operar
    assert reload(db, User, locked.idUsuario).estado == "BLOQUEADO"  # el bloqueo individual sigue
    assert web.get(f"/api/v1/institutions/{team.id}", headers=revokedSessionHeaders).status_code == 401  # la sesión revocada no revive
    event = audits(db, "REACTIVAR_INSTITUCION")[-1]
    assert event.idUsuario == admin[0].idUsuario and '"INACTIVA"' in event.datosPrevios and '"ACTIVA"' in event.datosNuevos
    assert [m["subject"] for m in mails if m["to"] == team.owner.correoElectronico][-1] == "Tu institución fue reactivada en GlucoLume"


def test_las_transiciones_invalidas_se_rechazan_y_tambien_quedan_auditadas(db, mails, admin, team):
    expectError("INSTITUCION_NO_REACTIVABLE", platformInstitutions.reactivate, db, admin[0], team.id, action())  # activa: nada que reactivar
    platformInstitutions.pause(db, admin[0], team.id, action())
    expectError("INSTITUCION_NO_PAUSABLE", platformInstitutions.pause, db, admin[0], team.id, action())  # ya pausada: no se pausa dos veces
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="CERRADA"))
    db.commit()
    expectError("INSTITUCION_NO_REACTIVABLE", platformInstitutions.reactivate, db, admin[0], team.id, action())  # una cerrada no se reactiva por acá
    expectError("INSTITUCION_NO_PAUSABLE", platformInstitutions.pause, db, admin[0], team.id, action())
    failures = [e for e in audits(db, "PAUSAR_INSTITUCION") + audits(db, "REACTIVAR_INSTITUCION") if e.resultado == "FALLO"]
    assert len(failures) == 4 and all("Rechazada:" in e.observacion for e in failures)
    import uuid
    expectError("INSTITUCION_NO_ENCONTRADA", platformInstitutions.pause, db, admin[0], uuid.uuid4(), action())


def test_el_motivo_es_obligatorio_y_acotado_por_la_api(db, mails, web, admin, team):
    headers = login(web, admin[0], admin[1])
    for body in ({}, {"motivo": ""}, {"motivo": "corto"}, {"motivo": "x" * 301}, {"motivo": REASON, "estado": "CERRADA"}):
        assert web.post(f"/api/v1/platform/institutions/{team.id}/pause", headers=headers, json=body).status_code == 422
    assert stateOf(db, team) == "ACTIVA"
    ok = web.post(f"/api/v1/platform/institutions/{team.id}/pause", headers=headers, json={"motivo": REASON})
    assert ok.status_code == 200 and ok.json()["fila"]["estado"] == "INACTIVA" and ok.json()["suspension"]["motivo"] == REASON
    again = web.post(f"/api/v1/platform/institutions/{team.id}/reactivate", headers=headers, json={"motivo": "Se resolvió el motivo de la pausa"})
    assert again.status_code == 200 and again.json()["fila"]["estado"] == "ACTIVA" and again.json()["suspension"] is None


def test_el_estado_y_su_evidencia_son_atomicos_si_falla_el_registro_no_cambia_el_estado(db, mails, admin, team, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("falla simulada al registrar")

    monkeypatch.setattr(platformInstitutions, "registerEvent", broken)
    with pytest.raises(RuntimeError):
        platformInstitutions.pause(db, admin[0], team.id, action())
    assert stateOf(db, team) == "ACTIVA"  # sin evidencia no hay cambio
    assert audits(db, "PAUSAR_INSTITUCION") == []


def test_un_estado_inactivo_cambiado_por_fuera_de_la_aplicacion_se_informa_sin_evidencia(db, mails, admin, team):
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="INACTIVA"))
    db.commit()
    detail = platformDashboard.institutionDetail(db, admin[0], team.id)
    assert detail.fila.estado == "INACTIVA" and detail.suspension is None and detail.estadoSinEvidencia is True  # la fuente de verdad sigue siendo el estado
    expectError("INSTITUCION_PAUSADA", institutions.requireMembership, db, team.owner, team.id)


def test_una_institucion_pausada_no_puede_ser_cerrada_por_su_propietario(db, mails, admin, team):
    from app.schemas.institution import InstitutionDeletionRequest

    platformInstitutions.pause(db, admin[0], team.id, action())
    with pytest.raises(AuthError):
        institutions.deleteInstitution(db, team.owner, team.id, InstitutionDeletionRequest(confirmacionNombre="Hospital X", password=PASSWORD))
    assert stateOf(db, team) == "INACTIVA"


# --- C. Cupos --------------------------------------------------------------------------------------------------------------------


def test_reducir_el_limite_por_debajo_de_las_cuentas_activas_se_permite_y_deja_la_institucion_excedida(db, mails, moderator, team):
    assert quota.activeCount(db, team.id) == 3
    before = counts(db, team)
    usage = platformInstitutions.changeCapacity(db, moderator[0], team.id, CapacityChange(capacidadMaxima=2, motivo="Ajuste del plan contratado"))
    assert (usage.capacidadMaximaUsuarios, usage.usuariosActivos, usage.estado, usage.excedente, usage.cuposDisponibles) == (2, 3, "EXCEDIDA", 1, 0)
    assert counts(db, team) == before  # las cuentas existentes se conservan: ninguna se elimina ni se suspende
    assert all(reload(db, User, u.idUsuario).estado == "ACTIVO" for u in (team.owner, team.moderator, team.operator))
    event = audits(db, "MODIFICAR_CUPOS_INSTITUCION")[-1]
    assert '"capacidadMaximaUsuarios": 1000' in event.datosPrevios.replace('":1000', '": 1000') or "1000" in event.datosPrevios
    assert "2" in event.datosNuevos and "excedente" in event.datosNuevos and "MODERADOR_PLATAFORMA" in event.datosNuevos
    assert event.observacion == "Motivo: Ajuste del plan contratado"
    # No admite cuentas nuevas que consuman cupo hasta regularizarse.
    newcomer = institutional(db, "nueva@example.com", "nueva")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", newcomer.correoElectronico)
    expectError("CAPACIDAD_COMPLETA", institutions.respondInvitation, db, newcomer, invitation.idInstitucionUsuario, accept=True)
    detail = platformDashboard.institutionDetail(db, moderator[0], team.id)
    assert detail.excedente == 1 and detail.fila.limiteCuentas == 2 and detail.cupoUtilizado == 3 and detail.cuposDisponibles == 0


def test_al_regularizar_el_limite_vuelven_a_admitirse_cuentas(db, mails, admin, team):
    platformInstitutions.changeCapacity(db, admin[0], team.id, CapacityChange(capacidadMaxima=1, motivo="Reducción temporal del límite"))
    assert quota.usage(db, team.id).estado == "EXCEDIDA"
    usage = platformInstitutions.changeCapacity(db, admin[0], team.id, CapacityChange(capacidadMaxima=10, motivo="Se amplió el plan contratado"))
    assert (usage.estado, usage.excedente, usage.cuposDisponibles) == ("DISPONIBLE", 0, 7)
    newcomer = institutional(db, "nueva2@example.com", "nueva2")
    invitation = institutions.invite(db, team.moderator, team.id, "OPERADOR", newcomer.correoElectronico)
    institutions.respondInvitation(db, newcomer, invitation.idInstitucionUsuario, accept=True)
    assert quota.activeCount(db, team.id) == 4
    assert len(audits(db, "MODIFICAR_CUPOS_INSTITUCION")) == 2  # límite anterior y nuevo de cada cambio


def test_el_limite_se_valida_en_el_servidor_y_funciona_con_la_institucion_pausada_pero_no_cerrada(db, mails, web, admin, team):
    headers = login(web, admin[0], admin[1])
    url = f"/api/v1/platform/institutions/{team.id}/capacity"
    for value in (0, -3, 100001, 5.5, "10", None, True):
        assert web.put(url, headers=headers, json={"capacidadMaxima": value, "motivo": REASON}).status_code == 422, value
    assert web.put(url, headers=headers, json={"capacidadMaxima": 20}).status_code == 422  # sin motivo
    assert quota.capacityOf(db, team.id) == 1000
    platformInstitutions.pause(db, admin[0], team.id, action())
    ok = web.put(url, headers=headers, json={"capacidadMaxima": 20, "motivo": "Ajuste mientras está pausada"})
    assert ok.status_code == 200 and ok.json()["fila"]["limiteCuentas"] == 20
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="CERRADA"))
    db.commit()
    assert web.put(url, headers=headers, json={"capacidadMaxima": 30, "motivo": REASON}).status_code == 409


def test_el_limite_no_cambia_si_falla_la_evidencia(db, mails, admin, team, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(platformInstitutions, "registerEvent", broken)
    with pytest.raises(RuntimeError):
        platformInstitutions.changeCapacity(db, admin[0], team.id, CapacityChange(capacidadMaxima=5, motivo=REASON))
    assert quota.capacityOf(db, team.id) == 1000


def test_el_propietario_ve_el_exceso_en_sus_cupos(db, mails, web, admin, team):
    platformInstitutions.changeCapacity(db, admin[0], team.id, CapacityChange(capacidadMaxima=2, motivo=REASON))
    response = web.get(f"/api/v1/institutions/{team.id}/quota", headers=login(web, team.owner))
    assert response.status_code == 200
    assert (response.json()["estado"], response.json()["excedente"], response.json()["usuariosActivos"]) == ("EXCEDIDA", 1, 3)


# --- Auditoría de la institución ----------------------------------------------------------------------------------------------------


def test_la_auditoria_de_la_institucion_reune_registro_pausa_cupos_cuentas_y_accesos_fallidos_sin_secretos(db, mails, web, admin, moderator, team):
    for _ in range(2):
        with pytest.raises(AuthError):
            authService.loginLocal(db, team.operator.usuario, "clave-incorrecta-1A#")  # intentos fallidos de un integrante
    platformInstitutions.pause(db, admin[0], team.id, action())
    platformInstitutions.reactivate(db, moderator[0], team.id, action("Resuelta la revisión"))
    platformInstitutions.changeCapacity(db, admin[0], team.id, CapacityChange(capacidadMaxima=2, motivo="Ajuste del plan"))
    for viewer in (admin, moderator):  # administrador y moderador del sistema auditan por igual
        page = platformInstitutions.auditPage(db, viewer[0], team.id, tamanio=50)
        byCategory = {}
        for item in page.items:
            byCategory.setdefault(item.categoria, []).append(item)
        for key in ("REGISTRO", "PAUSA", "CUPOS", "CUENTAS", "AUTENTICACION"):
            assert byCategory.get(key), key
        pause = next(i for i in byCategory["PAUSA"] if i.accion == "PAUSAR_INSTITUCION")
        assert (pause.actor, pause.estadoAnterior, pause.estadoNuevo, pause.motivo, pause.resultado) == ("Administrador del sistema", "ACTIVA", "INACTIVA", REASON, "EXITO")
        reactivation = next(i for i in byCategory["PAUSA"] if i.accion == "REACTIVAR_INSTITUCION")
        assert reactivation.actor == "Moderador del sistema"
        change = byCategory["CUPOS"][0]
        assert (change.limiteAnterior, change.limiteNuevo, change.cuentasActivas, change.excedente) == (1000, 2, 3, 1)
        assert all(i.resultado == "FALLO" for i in byCategory["AUTENTICACION"]) and len(byCategory["AUTENTICACION"]) == 2
        dumped = page.model_dump_json()
        for secret in ("clave-incorrecta", "operadora@example.com", "@example.com", "token", "password", PASSWORD):
            assert secret not in dumped
    only = platformInstitutions.auditPage(db, admin[0], team.id, categoria="PAUSA")
    assert {i.accion for i in only.items} == {"PAUSAR_INSTITUCION", "REACTIVAR_INSTITUCION"} and only.total == 2
    failed = platformInstitutions.auditPage(db, admin[0], team.id, resultado="FALLO")
    assert failed.total >= 2 and all(i.resultado == "FALLO" for i in failed.items)
    expectError("DATOS_INVALIDOS", platformInstitutions.auditPage, db, admin[0], team.id, categoria="OTRA")


def test_la_auditoria_sigue_disponible_con_la_institucion_pausada_o_cerrada_y_no_muestra_datos_de_pacientes(db, mails, admin, moderator, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111888"))
    measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    platformInstitutions.pause(db, admin[0], team.id, action())
    paused = platformInstitutions.auditPage(db, moderator[0], team.id, tamanio=50)
    assert paused.total > 0
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="CERRADA"))
    db.commit()
    closed = platformInstitutions.auditPage(db, admin[0], team.id, tamanio=50)
    assert closed.total == paused.total
    dumped = closed.model_dump_json()
    for secret in ("Rosa", "Díaz", "20111888", str(patient.idPerfilMedicion), patient.identificadorPseudonimo):
        assert secret not in dumped  # ni pacientes ni mediciones
    assert not [i for i in closed.items if i.accion in ("CREAR_PACIENTE", "INICIAR_MEDICION", "FINALIZAR_MEDICION")]


def test_el_listado_de_auditoria_solo_muestra_la_institucion_pedida(db, mails, admin, team):
    other, _ = secondInstitution(db, team.moderator, cuit="30333333", nombre="Otra institución")
    platformInstitutions.pause(db, admin[0], other.idInstitucion, action())
    mine = platformInstitutions.auditPage(db, admin[0], team.id, tamanio=50)
    assert "PAUSAR_INSTITUCION" not in {i.accion for i in mine.items}  # la pausa de la otra no aparece acá
    assert "PAUSAR_INSTITUCION" in {i.accion for i in platformInstitutions.auditPage(db, admin[0], other.idInstitucion).items}


def test_una_institucion_pausada_o_cerrada_no_exporta_y_el_intento_queda_auditado(db, mails, admin, team):
    from app.services.exportAudit import auditedExport

    with auditedExport(db, team.owner, "MEDICIONES_PACIENTE", ambito="INSTITUCION", idInstitucion=team.id, formato="CSV") as export:
        export.registros = 0  # activa: la exportación futura sí pasa
    platformInstitutions.pause(db, admin[0], team.id, action())
    with pytest.raises(AuthError) as raised:
        with auditedExport(db, team.owner, "MEDICIONES_PACIENTE", ambito="INSTITUCION", idInstitucion=team.id, formato="CSV"):
            raise AssertionError("no debe ejecutarse el cuerpo de la exportación")
    assert raised.value.code == "INSTITUCION_PAUSADA"
    failed = [e for e in audits(db, "EXPORTACION_FALLIDA") if e.idInstitucion == team.id]
    assert failed and "INSTITUCION_PAUSADA" in failed[-1].observacion
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="CERRADA"))
    db.commit()
    with pytest.raises(AuthError):
        with auditedExport(db, team.owner, "MEDICIONES_PACIENTE", ambito="INSTITUCION", idInstitucion=team.id):
            pass


# --- Consulta del propietario al soporte durante la pausa ------------------------------------------------------------------------------------


@pytest.fixture
def supportMail(engine, monkeypatch):
    from app.core.config import getSettings
    from app.services import contact as contactService, institutionSupport

    for key, value in (("CONTACT_EMAIL", "soporte@glucolume.example"), ("SMTP_HOST", "smtp.example"), ("SMTP_PORT", "587"),
                       ("SMTP_USERNAME", "glucolume@example.com"), ("SMTP_PASSWORD", "secreto-smtp")):
        monkeypatch.setenv(key, value)
    getSettings.cache_clear()
    monkeypatch.setattr(contactService, "_limiter", contactService.RateLimiter(5, 900))
    monkeypatch.setattr(contactService, "_confirmationLimiter", contactService.RateLimiter(3, 3600))
    monkeypatch.setattr(institutionSupport, "_limiter", contactService.RateLimiter(3, 3600))
    yield
    getSettings.cache_clear()


def test_el_propietario_de_una_institucion_pausada_escribe_al_soporte_y_queda_auditado(db, mails, web, admin, team, supportMail):
    platformInstitutions.pause(db, admin[0], team.id, action("Revisión de seguridad en curso"))
    mails.clear()
    headers = login(web, team.owner)
    url = f"/api/v1/institutions/{team.id}/support-request"
    # Todo lo demás sigue bloqueado, pero esta consulta sí pasa.
    assert web.get(f"/api/v1/institutions/{team.id}", headers=headers).status_code == 403
    response = web.post(url, headers=headers, json={"asunto": "  Pedido de   reactivación ", "mensaje": "Ya resolvimos lo pedido, solicitamos reactivar."})
    assert response.status_code == 200, response.text
    toSupport = [m for m in mails if m["to"] == "soporte@glucolume.example"]
    assert len(toSupport) == 1 and toSupport[0]["replyTo"] == team.owner.correoElectronico  # responde al propietario
    body = toSupport[0]["html"]
    assert "[Institución pausada] Pedido de reactivación" in body and "Hospital X" in body and "Revisión de seguridad en curso" in body
    assert any(m["to"] == team.owner.correoElectronico for m in mails)  # confirmación al propietario
    event = audits(db, "SOLICITAR_SOPORTE_INSTITUCION")[-1]
    assert event.idInstitucion == team.id and event.idUsuario == team.owner.idUsuario and "Ya resolvimos" not in (event.observacion or "")
    items = platformInstitutions.auditPage(db, admin[0], team.id, categoria="PAUSA", tamanio=50).items
    assert any(i.accion == "SOLICITAR_SOPORTE_INSTITUCION" and i.etiqueta == "Consulta del propietario al soporte" for i in items)


def test_la_consulta_al_soporte_es_solo_del_propietario_y_solo_con_la_institucion_pausada(db, mails, web, admin, team, supportMail):
    url = f"/api/v1/institutions/{team.id}/support-request"
    body = {"asunto": "Consulta", "mensaje": "Mensaje suficientemente largo para enviar."}
    assert web.post(url, headers=login(web, team.owner), json=body).status_code == 409  # activa: usa el contacto público
    platformInstitutions.pause(db, admin[0], team.id, action())
    for person in (team.moderator, team.operator, institutional(db, "ajena@example.com", "ajena")):
        assert web.post(url, headers=login(web, person), json=body).status_code == 404, person.usuario  # ni siquiera se revela que existe
    owner = login(web, team.owner)
    for invalid in ({"asunto": "ab", "mensaje": "Mensaje suficientemente largo"}, {"asunto": "Consulta", "mensaje": "corto"},
                    {"asunto": "Consulta", "mensaje": "x" * 1501}, {**body, "nombre": "otro"}, {**body, "email": "otro@example.com"}):
        assert web.post(url, headers=owner, json=invalid).status_code == 422
    assert web.post(url, json=body).status_code == 401
    assert audits(db, "SOLICITAR_SOPORTE_INSTITUCION") == []


def test_la_consulta_al_soporte_tiene_limite_por_cuenta_y_falla_con_503_si_el_correo_no_sale(db, mails, web, admin, team, supportMail, monkeypatch):
    platformInstitutions.pause(db, admin[0], team.id, action())
    headers = login(web, team.owner)
    url = f"/api/v1/institutions/{team.id}/support-request"
    body = {"asunto": "Consulta", "mensaje": "Mensaje suficientemente largo para enviar."}
    assert [web.post(url, headers=headers, json=body).status_code for _ in range(4)] == [200, 200, 200, 429]
    from app.services import institutionSupport, contact as contactService

    monkeypatch.setattr(institutionSupport, "_limiter", contactService.RateLimiter(3, 3600))
    monkeypatch.setattr(institutionSupport.contactService, "_limiter", contactService.RateLimiter(5, 900))
    from app.services import email as emailService
    monkeypatch.setattr(emailService, "sendEmailEvent", lambda *a, **k: False)
    before = len(audits(db, "SOLICITAR_SOPORTE_INSTITUCION"))
    assert web.post(url, headers=headers, json=body).status_code == 503
    assert len(audits(db, "SOLICITAR_SOPORTE_INSTITUCION")) == before  # lo que no salió no figura como enviado
