# Dashboard general del Administrador de Plataforma: indicadores de cuentas, instituciones, dispositivos, mediciones operativas, seguridad y
# estado de los componentes, más el listado y el detalle de instituciones. Todo con datos sintéticos y consultas reales.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_dashboard.py -v

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select, update

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.institution import Institution
from app.models.measurement import Measurement
from app.models.technicalAudit import TechnicalAudit
from app.models.user import User
from app.services import auth as authService
from app.services import institutionPatients as patients
from app.services import platformDashboard
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, makeUser, mails, reload  # noqa: F401 - fixtures
from tests.test_account_lifecycle import secondInstitution
from tests.test_dashboards import measure
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, institutional, newInstitution, team  # noqa: F401 - fixtures
from tests.test_measurements import device
from tests.test_platform import ADMIN, MOD, PASSWORD, admin, login, moderator, strictPolicy, web  # noqa: F401 - fixtures


def stats(db, actor, dias=30):
    return platformDashboard.dashboard(db, actor, dias)


# --- Cuentas ------------------------------------------------------------------------------------------------------------------


def test_cada_cuenta_cuenta_una_vez_y_las_internas_no_se_repiten_por_roles(db, mails, admin, moderator, team):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    secondInstitution(db, team.moderator)  # el moderador institucional pasa a tener un segundo vínculo en otra institución
    data = stats(db, admin[0]).usuarios
    assert data.total == data.individuales + data.institucionales + data.plataforma  # sin doble conteo
    assert data.individuales == 1 and data.plataforma == 2 and individual is not None
    bonded = db.scalar(select(func.count(func.distinct(InstitutionUserAlias.idUsuarioInvitado))).where(InstitutionUserAlias.estadoRelacion == "ACTIVO"))
    assert data.conVinculoInstitucional == bonded  # personas distintas, no vínculos
    assert data.institucionalesSinVinculo == data.institucionales - data.conVinculoInstitucional
    assert data.activas + data.inactivas >= data.total - 0


def test_los_registros_recientes_se_cuentan_por_fecha_de_alta(db, mails, admin):
    old = makeUser(db, email="vieja@example.com", usuario="vieja")
    db.execute(update(User).where(User.idUsuario == old.idUsuario).values(fechaCreacion=nowForDb() - timedelta(days=40)))
    makeUser(db, email="nueva@example.com", usuario="nueva")
    db.commit()
    data = stats(db, admin[0]).usuarios
    assert data.registradas7Dias >= 2 and data.registradasPeriodo >= 2  # la nueva y el administrador del escenario
    assert data.total - data.registradasPeriodo >= 1  # la antigua queda fuera del período de 30 días


# --- Instituciones ------------------------------------------------------------------------------------------------------------


def test_estados_de_las_instituciones_y_personal_activo(db, mails, admin, team):
    other, _ = secondInstitution(db, team.moderator, cuit="30111111", nombre="Clínica Sur")
    third, _ = secondInstitution(db, team.operator, cuit="30222222", nombre="Centro Este")
    db.execute(update(Institution).where(Institution.idInstitucion == other.idInstitucion).values(estado="CERRADA"))
    db.execute(update(Institution).where(Institution.idInstitucion == third.idInstitucion).values(estado="INACTIVA"))
    db.commit()
    data = stats(db, admin[0]).instituciones
    assert (data.total, data.activas, data.cerradas, data.inactivas) == (3, 1, 1, 1)


def test_el_listado_trae_conteos_estado_fechas_y_filtros_sin_consultas_por_fila(db, mails, admin, team):
    page = platformDashboard.listInstitutions(db, admin[0])
    [row] = page.items
    assert (row.idInstitucion, row.estado, row.propietarios, row.moderadores, row.operadores) == (team.id, "ACTIVA", 1, 1, 1)
    assert row.cuentasInternas == 3 and row.limiteCuentas and row.fechaInicio and row.fechaFin is None
    # Filtros por nombre (con comodines escapados) y por estado.
    for n in range(5):
        inst, _ = secondInstitution(db, team.moderator, cuit=f"3099{n:04d}", nombre=f"Centro_{n}%")
        if n % 2:
            db.execute(update(Institution).where(Institution.idInstitucion == inst.idInstitucion).values(estado="CERRADA"))
    db.commit()
    assert platformDashboard.listInstitutions(db, admin[0], busqueda="Centro_").total == 5
    assert platformDashboard.listInstitutions(db, admin[0], busqueda="%").total == 5  # el comodín no coincide con todo: se busca literal
    assert platformDashboard.listInstitutions(db, admin[0], busqueda="centro", estado="CERRADA").total == 2
    full = platformDashboard.listInstitutions(db, admin[0])
    assert full.total == 6 and sum(full.porEstado.values()) == 6
    closed = [r for r in full.items if r.estado == "CERRADA"]
    assert closed and all(r.fechaFin is not None for r in closed)  # el cierre informa su fecha
    paged = platformDashboard.listInstitutions(db, admin[0], pagina=2, tamanio=4)
    assert len(paged.items) == 2 and paged.total == 6
    expectError("DATOS_INVALIDOS", platformDashboard.listInstitutions, db, admin[0], estado="OTRO")
    # Cantidad de consultas constante: no crece con las instituciones (sin N+1).
    seen = []
    listener = lambda conn, cursor, statement, *args: seen.append(statement)  # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        platformDashboard.listInstitutions(db, admin[0], tamanio=2)
        small = len(seen)
        seen.clear()
        platformDashboard.listInstitutions(db, admin[0], tamanio=6)
        assert len(seen) == small
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)


def test_el_detalle_es_administrativo_sin_pacientes_ni_valores_clinicos(db, mails, admin, team):
    dev = device(db, institucion=team.id)
    other = device(db, institucion=team.id, estado="EN_MANTENIMIENTO")
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", dni="20111222"))
    done = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    bad = measure(db, team.operator, patient.idPerfilMedicion, dev, "90", 60)
    db.execute(update(Measurement).where(Measurement.idMedicion == bad.idMedicion).values(estadoMedicion="INVALIDA", spo2=None, frecuenciaCardiaca=None))
    db.commit()
    detail = platformDashboard.institutionDetail(db, admin[0], team.id)
    assert (detail.pacientesActivos, detail.pacientesRegistrados) == (1, 1)
    assert (detail.medicionesTotal, detail.completadas, detail.invalidas, detail.canceladas) == (2, 1, 1, 0) and done is not None
    states = {d.codigoDispositivo: (d.estado, d.lecturasInvalidasRecientes) for d in detail.dispositivosAsignados}
    assert states[dev.codigoDispositivo] == ("OPERATIVO", 1) and states[other.codigoDispositivo] == ("EN_MANTENIMIENTO", 0)
    assert detail.fila.dispositivos == 2 and detail.cupoUtilizado == 3 and detail.cuposDisponibles is not None
    dumped = detail.model_dump_json()
    for secret in ("Rosa", "Díaz", "20111222", "@example.com", str(patient.idPerfilMedicion), "spo2", "glucosa", "frecuencia"):
        assert secret not in dumped
    expectError("INSTITUCION_NO_ENCONTRADA", platformDashboard.institutionDetail, db, admin[0], uuid.uuid4())


def test_administrador_y_moderador_del_sistema_supervisan_instituciones_y_nadie_mas(db, mails, web, admin, moderator, team):
    adminHeaders = login(web, admin[0], admin[1])
    modHeaders = login(web, moderator[0], moderator[1])
    for headers in (adminHeaders, modHeaders):  # ambos roles de plataforma consultan listado y detalle
        assert web.get("/api/v1/platform/institutions", headers=headers).status_code == 200
        assert web.get(f"/api/v1/platform/institutions/{team.id}", headers=headers).status_code == 200
    for path in ("/platform/institutions", f"/platform/institutions/{team.id}"):
        for user in (team.owner, team.moderator, team.operator):  # los roles institucionales NO son roles de plataforma
            assert web.get(f"/api/v1{path}", headers=login(web, user)).status_code == 403, path
    assert web.get("/api/v1/platform/institutions?estado=NOPE", headers=adminHeaders).status_code in (400, 422)


# --- Dispositivos y mediciones ------------------------------------------------------------------------------------------------


def test_los_dispositivos_distinguen_estado_tecnico_de_resultados_de_medicion(db, mails, admin, team):
    good = device(db, institucion=team.id)
    flaky = device(db, institucion=team.id)
    device(db, estado="FUERA_DE_SERVICIO")
    patient = patients.createPatient(db, team.operator, team.id, patientData(dni="20111333"))
    cancelled = measure(db, team.operator, patient.idPerfilMedicion, good, "95", 70)
    invalid = measure(db, team.operator, patient.idPerfilMedicion, flaky, "90", 60)
    db.execute(update(Measurement).where(Measurement.idMedicion == cancelled.idMedicion).values(estadoMedicion="CANCELADA", spo2=None, frecuenciaCardiaca=None,
                                                                                                 fechaHoraFin=nowForDb() + timedelta(minutes=1)))
    db.execute(update(Measurement).where(Measurement.idMedicion == invalid.idMedicion).values(estadoMedicion="INVALIDA", spo2=None, frecuenciaCardiaca=None))
    db.commit()
    data = stats(db, admin[0]).dispositivos
    assert (data.total, data.operativos, data.fueraDeServicio, data.asignados, data.sinAsignar) == (3, 2, 1, 2, 1)
    assert data.conLecturasInvalidasRecientes == 1  # solo el de la lectura inválida: una cancelada no cuenta como falla del equipo
    assert data.desconectados is None and data.conexionVerificable is False  # no se inventa una conexión que el sistema no registra


def test_las_mediciones_son_volumen_operativo_con_errores_tecnicos_y_demo_aparte(db, mails, admin, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(dni="20111444"))
    real = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    demo = measure(db, team.operator, patient.idPerfilMedicion, dev, "97", 72)
    db.execute(update(Measurement).where(Measurement.idMedicion == demo.idMedicion).values(origenGlucosa="DEMO", glucosaDispositivo=110, unidadGlucosa="mg/dL"))
    db.add_all([TechnicalAudit(idEvento=uuid.uuid4(), fechaHora=nowForDb().replace(minute=0, second=0, microsecond=0), tipoOperacion="MEDICION",
                               estadoFinal="INVALIDA", motivo="LECTURA_NO_VALIDA") for _ in range(3)])
    db.add(TechnicalAudit(idEvento=uuid.uuid4(), fechaHora=nowForDb().replace(minute=0, second=0, microsecond=0), tipoOperacion="SESION_DISPOSITIVO",
                          estadoFinal="CANCELADA", motivo="SESION_EXPIRADA"))
    db.commit()
    data = stats(db, admin[0]).mediciones
    assert (data.total, data.completadas, data.demo) == (1, 1, 1) and real is not None  # las DEMO no inflan el volumen real
    assert data.erroresTecnicos == 4 and {m.clave: m.total for m in data.motivosTecnicos} == {"LECTURA_NO_VALIDA": 3, "SESION_EXPIRADA": 1}
    for forbidden in ("spo2", "glucosa", "frecuenciaCardiaca"):
        assert forbidden not in data.model_dump_json().replace("glucosaExperimental", "")


# --- Seguridad ----------------------------------------------------------------------------------------------------------------


def test_el_resumen_de_seguridad_sale_de_la_auditoria_y_del_estado_real_de_las_cuentas(db, mails, admin):
    target = makeUser(db, email="objetivo@example.com", usuario="objetivo")
    for _ in range(4):  # 4 contraseñas incorrectas: bloqueo temporal
        with pytest.raises(AuthError):
            authService.loginLocal(db, "objetivo", "incorrecta-1A#")
    with pytest.raises(AuthError):
        authService.loginLocal(db, "nadie-existe", "incorrecta-1A#")
    authService.loginLocal(db, "adminsys", PASSWORD, acceso=authService.ACCESO_PLATAFORMA)  # solo el primer paso (pide MFA): todavía no es un ingreso
    makeUser(db, email="entra@example.com", usuario="entra")
    authService.loginLocal(db, "entra", PASSWORD)  # un ingreso correcto
    blocked = makeUser(db, email="bloqueada@example.com", usuario="bloqueada")
    blocked.estado = "BLOQUEADO"
    db.commit()
    data = stats(db, admin[0]).seguridad
    assert data.loginsFallidos >= 4 and data.loginsExitosos == 1
    assert data.motivosFallo and all(m.total >= 1 for m in data.motivosFallo)
    assert data.cuentasBloqueadas == 1 and data.bloqueosTemporales == 1 and target is not None
    assert data.cuentasConFallosRepetidos == 1  # una sola cuenta superó 3 fallos
    assert data.exportaciones == 0  # no hay función de exportación: nada que informar
    dumped = data.model_dump_json()
    for secret in ("objetivo", "@example.com", "nadie-existe"):
        assert secret not in dumped  # solo conteos y motivos genéricos


def test_el_moderador_del_sistema_solo_ve_la_parte_tecnica(db, mails, admin, moderator):
    technical = stats(db, moderator[0])
    assert technical.alcance == "TECNICO" and technical.usuarios is None and technical.seguridad is None and technical.instituciones is None
    assert technical.dispositivos.total == 0 and technical.mediciones.total == 0


# --- Estado de los componentes: verificaciones reales -------------------------------------------------------------------------------


def componentOf(status, name):
    return next(c for c in status.componentes if c.nombre.startswith(name))


def test_los_componentes_informan_verificaciones_reales_y_estados_diferenciados(db, mails, admin, monkeypatch):
    from app.core.config import getSettings

    monkeypatch.setenv("SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    getSettings.cache_clear()
    calls = []

    def fakeTcp(host, port):
        calls.append((host, port))
        return (False, None, "TimeoutError") if host == "smtp.example.invalid" else (True, 12, None)

    monkeypatch.setattr(platformDashboard, "_tcp", fakeTcp)
    status = platformDashboard.systemStatus(db, admin[0])
    assert {c.estado for c in status.componentes} <= {"OPERATIVO", "DEGRADADO", "NO_DISPONIBLE", "DESCONOCIDO"}
    smtp = componentOf(status, "Correo")
    assert smtp.estado == "NO_DISPONIBLE" and "TimeoutError" in smtp.detalle and smtp.verificacion == "Conexión TCP al servidor SMTP"
    assert ("smtp.example.invalid", 587) in calls
    database = componentOf(status, "Base de datos")
    assert database.estado == "OPERATIVO" and database.latenciaMs is not None and database.verificacion
    assert componentOf(status, "Verificación en dos pasos").estado == "OPERATIVO"
    assert componentOf(status, "Matriz global").estado == "NO_DISPONIBLE"  # sin matriz global activa en este escenario
    monkeypatch.setattr(platformDashboard, "_tcp", lambda host, port: (True, 8, None))
    assert componentOf(platformDashboard.systemStatus(db, admin[0]), "Correo").estado == "OPERATIVO"
    getSettings.cache_clear()


def test_una_base_lenta_se_marca_degradada(db, mails, admin, monkeypatch):
    monkeypatch.setattr(platformDashboard, "SLOW_DB_MS", -1)
    assert componentOf(platformDashboard.systemStatus(db, admin[0]), "Base de datos").estado == "DEGRADADO"


from app.models.institutionUser import InstitutionUser as InstitutionUserAlias  # noqa: E402
