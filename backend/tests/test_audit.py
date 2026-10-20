# Pruebas de la auditoría integral: registro automático en todos los módulos y consulta con control de acceso por
# ámbito (administrador del sistema: todo; propietario: solo su institución; nadie más).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit.py -v
#
# Las consultas por HTTP usan TestClient con la base SQLite temporal; la identidad se inyecta por la dependencia de
# sesión y el usuario se vuelve a leer de la base en cada pedido (como hace la aplicación real).

import json
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import AuthContext, getAuthContext
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.main import app
from app.models.audit import Audit
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.group import FamilyGroupCreateRequest
from app.schemas.matrix import MatrixCreateRequest, MatrixRuleInput
from app.services import audit as auditService
from app.services import auditQuery
from app.services import auth as authService
from app.services import group as groups
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import matrix as matrices
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from tests.test_account_deletion import PASSWORD, audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)
from tests.test_matrices import north, rule  # noqa: F401 - fixtures
from tests.test_measurements import device, samples
from app.schemas.measurement import MeasurementFinish, MeasurementStart


@pytest.fixture
def admin(db, mails):
    return makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin@example.com", usuario="admin")


def listing(db, actor, **kwargs):
    return auditQuery.listGlobal(db, actor, **kwargs)


def ofInstitution(db, idInstitucion):
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.idInstitucion == idInstitucion)))


# --- Consulta: quién puede y quién no ---------------------------------------------------------------------


def test_el_administrador_consulta_la_auditoria_general_de_todos_los_modulos(db, mails, team, north, admin):
    groups.createGroup(db, makeUser(db, email="familia@example.com", usuario="familia"),
                       FamilyGroupCreateRequest(nombre="Familia Pérez"))
    page = listing(db, admin, tamanioPagina=100)
    assert page.total >= 6
    modules = {item.modulo for item in page.items}
    assert {"INSTITUCIONES", "GRUPOS"} <= modules
    institutionsSeen = {item.idInstitucion for item in page.items if item.idInstitucion}
    assert institutionsSeen == {team.id, north.id}  # eventos de todas las instituciones
    assert any(item.idInstitucion is None for item in page.items)  # y los globales, sin contexto institucional
    assert all(item.nombreInstitucion for item in page.items if item.idInstitucion)
    stamps = [item.fechaHora for item in page.items]
    assert stamps == sorted(stamps, reverse=True)
    summary = auditQuery.summaryGlobal(db, admin)
    assert summary.total == page.total and summary.exitosos + summary.fallidos == summary.total
    assert {c.nombre for c in summary.porInstitucion} == {"Hospital X", "Clínica Norte"}
    assert sum(c.total for c in summary.porModulo) == summary.total


def test_el_administrador_filtra_por_institucion_modulo_accion_resultado_usuario_y_periodo(db, mails, team, north, admin):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz X"))
    matrices.addRule(db, team.owner, created.idMatriz, rule())
    with pytest.raises(AuthError):
        matrices.activate(db, team.operator, created.idMatriz)  # rechazada: queda como FALLO
    matrices.activate(db, team.owner, created.idMatriz)  # operación crítica
    only = listing(db, admin, idInstitucion=team.id, tamanioPagina=100)
    assert only.total > 0 and {i.idInstitucion for i in only.items} == {team.id}
    assert {i.modulo for i in listing(db, admin, modulo="MATRICES", tamanioPagina=100).items} == {"MATRICES"}
    assert {i.accion for i in listing(db, admin, accion="regla", tamanioPagina=100).items} == {"CREAR_REGLA_MATRIZ"}
    failed = listing(db, admin, resultado="FALLO", idInstitucion=team.id, tamanioPagina=100)
    assert failed.total >= 1 and {i.resultado for i in failed.items} == {"FALLO"}
    byUser = listing(db, admin, usuario="duenia", tamanioPagina=100)
    assert byUser.total > 0 and {i.usuario for i in byUser.items} == {"Victoria Cortés"}
    today = date.today()
    assert listing(db, admin, desde=today, hasta=today).total == listing(db, admin).total  # todo ocurrió hoy (UTC o Argentina)
    assert listing(db, admin, hasta=today - timedelta(days=2)).total == 0
    assert listing(db, admin, desde=today + timedelta(days=2)).total == 0
    expectError("PERIODO_INVALIDO", listing, db, admin, desde=today, hasta=today - timedelta(days=1))
    expectError("DATOS_INVALIDOS", listing, db, admin, modulo="INVENTADO")
    critical = listing(db, admin, critica=True, tamanioPagina=100)
    assert critical.total >= 1 and all(i.critica for i in critical.items)


def test_paginacion_desde_la_consulta(db, mails, team, admin):
    total = listing(db, admin).total
    first = listing(db, admin, tamanioPagina=3, pagina=1)
    second = listing(db, admin, tamanioPagina=3, pagina=2)
    assert len(first.items) == 3 and first.total == total and first.tamanioPagina == 3
    assert {i.idAuditoria for i in first.items}.isdisjoint({i.idAuditoria for i in second.items})
    assert len(listing(db, admin, tamanioPagina=10000).items) <= auditQuery.MAX_PAGE_SIZE  # tope


def test_el_propietario_consulta_solo_los_eventos_de_su_institucion(db, mails, team, north):
    page = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    assert page.total > 0 and {i.idInstitucion for i in page.items} == {team.id}
    assert all(i.nombreInstitucion is None for i in page.items)  # ya está acotada a una institución
    # Incluye lo que hicieron el moderador y la operadora (no solo el propietario).
    institutions.invite(db, team.moderator, team.id, "OPERADOR", "nuevo@example.com", nombre="Pía", apellido="Gómez")
    patients.createPatient(db, team.operator, team.id, patientData())
    users = {i.usuario for i in auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items}
    assert {"Victoria Cortés"} <= users and len(ofInstitution(db, team.id)) == len(
        auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items)
    summary = auditQuery.summaryInstitution(db, team.owner, team.id)
    assert summary.total == len(ofInstitution(db, team.id)) and summary.porInstitucion == []


def test_el_propietario_no_ve_eventos_de_otra_institucion(db, mails, team, north):
    foreign = ofInstitution(db, north.id)[0]
    expectError("INSTITUCION_NO_ENCONTRADA", auditQuery.listInstitution, db, team.owner, north.id)
    expectError("INSTITUCION_NO_ENCONTRADA", auditQuery.summaryInstitution, db, team.owner, north.id)
    expectError("INSTITUCION_NO_ENCONTRADA", auditQuery.detailInstitution, db, team.owner, north.id, foreign.idAuditoria)
    # Pidiendo un evento ajeno por la ruta de la propia institución tampoco existe.
    expectError("EVENTO_NO_ENCONTRADO", auditQuery.detailInstitution, db, team.owner, team.id, foreign.idAuditoria)
    mine = {i.idAuditoria for i in auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items}
    assert foreign.idAuditoria not in mine
    # El filtro por institución no existe en la consulta institucional: no hay parámetro que cambie el ámbito.
    with pytest.raises(TypeError):
        auditQuery.listInstitution(db, team.owner, team.id, idInstitucion=north.id)


def test_quien_no_es_administrador_ni_propietario_recibe_403_y_el_intento_queda_registrado(db, mails, team, admin):
    consumer = makeUser(db, email="persona@example.com", usuario="persona")
    platformModerator = makeUser(db, tipoCuenta="MODERADOR_PLATAFORMA", email="mod@example.com", usuario="mod")
    for actor in (team.owner, team.moderator, team.operator, consumer, platformModerator):
        expectError("PERMISO_INSUFICIENTE", auditQuery.listGlobal, db, actor)  # ni siquiera el propietario: no es global
        expectError("PERMISO_INSUFICIENTE", auditQuery.summaryGlobal, db, actor)
    for actor in (team.moderator, team.operator):
        expectError("PERMISO_INSUFICIENTE", auditQuery.listInstitution, db, actor, team.id)
        expectError("PERMISO_INSUFICIENTE", auditQuery.summaryInstitution, db, actor, team.id)
    expectError("PERMISO_INSUFICIENTE", auditQuery.listInstitution, db, consumer, team.id)  # cuenta individual
    denied = [a for a in audits(db, "CONSULTAR_AUDITORIA") if a.resultado == "FALLO"]
    assert len(denied) == 5 * 2 + 2 * 2 + 1  # un alta por intento (incluida la cuenta individual), sin recursión
    assert {a.modulo for a in denied} == {"AUDITORIA"}
    # Los intentos de moderador/operador sobre su institución los ve el propietario; los globales, el administrador.
    ownerView = auditQuery.listInstitution(db, team.owner, team.id, accion="CONSULTAR_AUDITORIA", tamanioPagina=100)
    assert ownerView.total == 4 and {i.resultado for i in ownerView.items} == {"FALLO"}
    adminView = listing(db, admin, accion="CONSULTAR_AUDITORIA", tamanioPagina=100)
    assert adminView.total == len(denied)


def test_consultar_con_exito_no_genera_nuevos_eventos(db, mails, team, admin):
    before = db.scalar(select(func.count()).select_from(Audit))
    listing(db, admin)
    auditQuery.summaryGlobal(db, admin)
    auditQuery.listInstitution(db, team.owner, team.id)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Audit)) == before  # sin ciclos ni ruido


# --- HTTP: códigos de estado y ausencia de operaciones de escritura ----------------------------------------


@pytest.fixture
def api(engine):
    """Cliente HTTP; `as_(user)` fija la identidad. El usuario se relee de la base en cada pedido."""
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    current = {}

    def getTestDb():
        session = makeSession()
        try:
            yield session
        finally:
            session.close()

    def fakeAuth(session=__import__("fastapi").Depends(getTestDb)):
        return AuthContext(user=session.get(User, current["id"]), session=None)

    app.dependency_overrides[getDb] = getTestDb
    app.dependency_overrides[getAuthContext] = fakeAuth
    client = TestClient(app, raise_server_exceptions=False)

    def as_(user):
        current["id"] = user.idUsuario
        return client

    yield as_
    app.dependency_overrides.clear()


def test_codigos_http_de_la_consulta(db, mails, team, north, admin, api):
    consumer = makeUser(db, email="persona@example.com", usuario="persona")
    assert api(admin).get("/api/v1/audit").status_code == 200
    assert api(admin).get(f"/api/v1/audit?idInstitucion={team.id}").json()["total"] > 0
    assert api(admin).get("/api/v1/audit/summary").status_code == 200
    first = api(admin).get("/api/v1/audit").json()["items"][0]
    assert api(admin).get(f"/api/v1/audit/events/{first['idAuditoria']}").status_code == 200
    assert api(team.owner).get(f"/api/v1/institutions/{team.id}/audit").status_code == 200
    # 403: moderador, operador, individual y el propietario en la ruta global.
    for actor, path in ((team.moderator, f"/institutions/{team.id}/audit"), (team.operator, f"/institutions/{team.id}/audit"),
                        (consumer, "/audit"), (team.owner, "/audit"), (team.moderator, "/audit"), (team.operator, "/audit/summary")):
        assert api(actor).get(f"/api/v1{path}").status_code == 403, (actor.usuario, path)
    # 404: propietario de otra institución (no se revela qué instituciones existen). La cuenta individual: 403.
    assert api(team.owner).get(f"/api/v1/institutions/{north.id}/audit").status_code == 404
    assert api(consumer).get(f"/api/v1/institutions/{team.id}/audit").status_code == 403


def test_un_propietario_no_se_convierte_en_administrador_cambiando_parametros(db, mails, team, north, api):
    owner = api(team.owner)
    ids = {i["idInstitucion"] for i in owner.get(f"/api/v1/institutions/{team.id}/audit?idInstitucion={north.id}").json()["items"]}
    assert ids == {str(team.id)}  # el parámetro se ignora: el ámbito sale de la ruta validada
    assert owner.get("/api/v1/audit?idInstitucion=" + str(team.id)).status_code == 403
    assert owner.get(f"/api/v1/institutions/{team.id}/audit?modulo=INVENTADO").status_code == 422


def test_la_auditoria_es_de_solo_lectura_por_la_api(admin, api):
    for route in app.routes:
        path = getattr(route, "path", "")
        if "/audit" in path and path.startswith("/api/v1/audit") or "/audit" in path and "/institutions/" in path and path.endswith(("/audit", "/summary", "/events/{idAuditoria}")):
            assert set(route.methods) <= {"GET", "HEAD", "OPTIONS"}, path
    client = api(admin)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/v1/audit").status_code in (404, 405)


# --- Registro automático ----------------------------------------------------------------------------------


def test_la_creacion_de_instituciones_y_grupos_genera_eventos(db, mails, team):
    owner = institutional(db, "otra@example.com", "otra")
    other = newInstitution(db, owner, "87654321", "Consultorio San José")
    created = [a for a in audits(db, "CREAR_INSTITUCION") if a.idRegistro == other.idInstitucion]
    assert len(created) == 1 and created[0].modulo == "INSTITUCIONES" and created[0].idInstitucion == other.idInstitucion
    assert created[0].resultado == "EXITO" and created[0].idUsuario == owner.idUsuario and created[0].fechaHora is not None
    group = groups.createGroup(db, makeUser(db, email="familia@example.com", usuario="familia"),
                               FamilyGroupCreateRequest(nombre="Familia Gómez"))
    [event] = [a for a in audits(db, "CREAR_GRUPO") if a.idRegistro == group.idGrupo]
    assert event.modulo == "GRUPOS" and event.idInstitucion is None  # los grupos no pertenecen a una institución
    assert {a.accion for a in audits(db, "NOTIFICAR_CREACION_INSTITUCION")} == {"NOTIFICAR_CREACION_INSTITUCION"}


def test_las_acciones_de_moderadores_y_operadores_quedan_registradas_aunque_no_puedan_consultar(db, mails, team):
    institutions.invite(db, team.moderator, team.id, "OPERADOR", "nuevo@example.com", nombre="Pía", apellido="Gómez")
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    invited = [a for a in audits(db, "INVITAR_MIEMBRO_INSTITUCION") if a.idUsuario == team.moderator.idUsuario]
    created = [a for a in audits(db, "CREAR_PACIENTE") if a.idRegistro == patient.idPerfilMedicion]
    assert invited and created
    assert created[0].idUsuario == team.operator.idUsuario and created[0].idInstitucion == team.id
    assert created[0].modulo == "PERFILES" and invited[-1].idInstitucion == team.id
    for actor in (team.moderator, team.operator):  # generan eventos, pero no los consultan
        expectError("PERMISO_INSUFICIENTE", auditQuery.listInstitution, db, actor, team.id)


def test_las_modificaciones_de_matrices_generan_eventos(db, mails, team):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz X"))
    added = matrices.addRule(db, team.moderator, created.idMatriz, rule())
    matrices.updateDraft(db, team.owner, created.idMatriz, __import__("app.schemas.matrix", fromlist=["x"]).MatrixDraftUpdateRequest(descripcion="d"))
    matrices.activate(db, team.moderator, created.idMatriz)
    matrices.deactivate(db, team.owner, created.idMatriz)
    matrices.newVersion(db, team.owner, created.idMatriz)
    matrices.archive(db, team.owner, created.idMatriz)
    trail = auditQuery.listInstitution(db, team.owner, team.id, modulo="MATRICES", tamanioPagina=100)
    actions = {i.accion for i in trail.items}
    assert {"CREAR_MATRIZ", "CREAR_REGLA_MATRIZ", "MODIFICAR_MATRIZ", "ACTIVAR_MATRIZ", "DESACTIVAR_MATRIZ",
            "CREAR_VERSION_MATRIZ", "ARCHIVAR_MATRIZ"} <= actions
    assert {i.idInstitucion for i in trail.items} == {team.id}
    assert next(i for i in trail.items if i.accion == "ACTIVAR_MATRIZ").critica


def test_las_transferencias_de_perfiles_generan_eventos(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    second = addOperator(db, team)
    secondUser = db.get(User, second.idUsuarioInvitado)
    first = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.rejectTransfer(db, secondUser, team.id, first.idTransferenciaPerfil)
    again = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.cancelTransfer(db, team.operator, team.id, again.idTransferenciaPerfil)
    last = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, secondUser, team.id, last.idTransferenciaPerfil)
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="PERFILES", tamanioPagina=100)
    actions = [i.accion for i in page.items]
    for expected in ("SOLICITAR_TRANSFERENCIA_PERFIL", "RECHAZAR_TRANSFERENCIA_PERFIL", "CANCELAR_TRANSFERENCIA_PERFIL",
                     "ACEPTAR_TRANSFERENCIA_PERFIL", "CAMBIAR_RESPONSABLE_PERFIL"):
        assert expected in actions, expected
    assert actions.count("SOLICITAR_TRANSFERENCIA_PERFIL") == 3
    assert {i.idInstitucion for i in page.items} == {team.id}


def test_el_ciclo_de_una_medicion_se_registra_y_se_asocia_a_la_institucion_del_perfil(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    started = measurements.startMeasurement(db, team.operator, MeasurementStart(
        idPerfilMedicion=patient.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    measurements.addSamples(db, team.operator, started.idMedicion, samples())
    measurements.finishMeasurement(db, team.operator, started.idMedicion, MeasurementFinish())  # sin resultados: inválida
    other = measurements.startMeasurement(db, team.operator, MeasurementStart(
        idPerfilMedicion=patient.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    measurements.cancelMeasurement(db, team.operator, other.idMedicion)
    page = auditQuery.listInstitution(db, team.owner, team.id, modulo="MEDICIONES", tamanioPagina=100)
    actions = [i.accion for i in page.items]
    assert actions.count("INICIAR_MEDICION") == 2 and "CANCELAR_MEDICION" in actions and "FINALIZAR_MEDICION" in actions
    failure = next(i for i in page.items if i.accion == "FINALIZAR_MEDICION")
    assert failure.resultado == "FALLO" and "SpO" in (failure.descripcion or "")  # error de procesamiento
    assert {i.idInstitucion for i in page.items} == {team.id}


def test_una_cuenta_en_dos_instituciones_genera_eventos_en_la_institucion_donde_opera(db, mails, team, north):
    # Juan (operador de Hospital X) también es operador de Clínica Norte.
    invitation = institutions.invite(db, north.moderator, north.id, "OPERADOR", team.operator.correoElectronico)
    institutions.respondInvitation(db, team.operator, invitation.idInstitucionUsuario, accept=True)
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    started = measurements.startMeasurement(db, team.operator, MeasurementStart(
        idPerfilMedicion=patient.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    juan = [a for a in audits(db, "INICIAR_MEDICION") if a.idRegistro == started.idMedicion]
    assert [a.idInstitucion for a in juan] == [team.id] and juan[0].idUsuario == team.operator.idUsuario
    northIds = {i.idAuditoria for i in auditQuery.listInstitution(db, north.owner, north.id, tamanioPagina=100).items}
    assert juan[0].idAuditoria not in northIds  # el propietario de Clínica Norte no lo ve
    expectError("EVENTO_NO_ENCONTRADO", auditQuery.detailInstitution, db, north.owner, north.id, juan[0].idAuditoria)
    ownerIds = {i.idAuditoria for i in auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items}
    assert juan[0].idAuditoria in ownerIds
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin@example.com", usuario="admin")
    assert juan[0].idAuditoria in {i.idAuditoria for i in listing(db, admin, tamanioPagina=100).items}  # el administrador sí


def test_un_propietario_de_varias_instituciones_elige_el_contexto(db, mails, team):
    second = newInstitution(db, team.owner, "87654321", "Clínica Sur")
    patients_ = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    sur = auditQuery.listInstitution(db, team.owner, second.idInstitucion, tamanioPagina=100)
    assert {i.idInstitucion for i in patients_.items} == {team.id}
    assert {i.idInstitucion for i in sur.items} == {second.idInstitucion}
    assert {i.idAuditoria for i in patients_.items}.isdisjoint({i.idAuditoria for i in sur.items})


def test_un_intento_rechazado_de_una_operacion_relevante_queda_registrado(db, mails, team):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz X"))
    before = db.scalar(select(func.count()).select_from(Audit).where(Audit.resultado == "FALLO"))
    with pytest.raises(AuthError):
        matrices.activate(db, team.operator, created.idMatriz)
    db.expire_all()
    failures = [a for a in audits(db, "ACCEDER_MATRIZ") if a.resultado == "FALLO"]
    assert len(failures) == 1 and failures[0].idUsuario == team.operator.idUsuario and failures[0].idInstitucion == team.id
    assert db.scalar(select(func.count()).select_from(Audit).where(Audit.resultado == "FALLO")) == before + 1


def test_registerfailure_deja_el_evento_aunque_la_operacion_se_deshaga(db, mails, team):
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    profile = db.get(__import__("app.models.measurementProfile", fromlist=["x"]).MeasurementProfile, patient.idPerfilMedicion)
    profile.nombre = "CAMBIO_SIN_CONFIRMAR"  # trabajo pendiente de la operación principal
    auditService.registerFailure(db, "CRUD", "MODIFICAR_PACIENTE", team.operator.idUsuario, "PerfilMedicion",
                                 patient.idPerfilMedicion, "Motivo: prueba")
    db.expire_all()
    assert db.get(profile.__class__, patient.idPerfilMedicion).nombre != "CAMBIO_SIN_CONFIRMAR"  # la operación se deshizo
    [event] = [a for a in audits(db, "MODIFICAR_PACIENTE") if a.resultado == "FALLO"]
    assert event.idInstitucion == team.id and event.modulo == "PERFILES"


# --- Qué no se registra ni se expone -----------------------------------------------------------------------


SECRET_VALUES = (PASSWORD, "Contraseña#Secreta2026", "123456", "secreto-mfa")


def test_los_registros_no_incluyen_credenciales_ni_secretos(db, mails, team):
    authService.registerLocal(db, RegisterRequest(aceptaPoliticaPrivacidad=True, 
        nombre="Laura", apellido="Díaz", correoElectronico="laura@example.com", usuario="laura",
        password="Contraseña#Secreta2026", tipoCuenta="CONSUMIDOR_FINAL"))
    patients.createPatient(db, team.operator, team.id, patientData())
    db.expire_all()
    for row in db.scalars(select(Audit)):
        blob = " ".join(str(v) for v in (row.accion, row.observacion, row.datosPrevios, row.datosNuevos, row.detalle) if v)
        for secret in SECRET_VALUES:
            assert secret not in blob, (row.accion, secret)
        for personal in ("Juan", "Pérez", "20111222", "1980-01-02"):
            assert personal not in blob, (row.accion, personal)


def test_el_servicio_descarta_las_claves_sensibles_antes_de_guardar(db, mails):
    auditService.registerEvent(db, "CRUD", "PRUEBA_SANITIZACION", True, None, datosNuevos={
        "password": "x1", "refreshToken": "x2", "secretoMfa": "x3", "codigo": "123456", "campos": ["a"],
        "codigoRegla": "R-001", "anidado": {"tokenHash": "x4", "ok": 1}})
    db.commit()
    stored = json.loads(audits(db, "PRUEBA_SANITIZACION")[0].datosNuevos)
    assert stored["campos"] == ["a"] and stored["codigoRegla"] == "R-001" and stored["anidado"]["ok"] == 1
    for key in ("password", "refreshToken", "secretoMfa", "codigo"):
        assert stored[key] == "[omitido]"
    assert stored["anidado"]["tokenHash"] == "[omitido]"


def test_el_detalle_devuelve_los_valores_sin_datos_sensibles(db, mails, team, admin):
    created = matrices.createMatrix(db, team.owner, MatrixCreateRequest(ambito="INSTITUCION", idInstitucion=team.id, nombre="Matriz X"))
    event = next(i for i in listing(db, admin, accion="CREAR_MATRIZ").items)
    detail = auditQuery.detailGlobal(db, admin, event.idAuditoria)
    assert detail.valoresNuevos["ambito"] == "INSTITUCION" and detail.tipoEntidad == "Matriz" and detail.idEntidad == created.idMatriz
    dumped = detail.model_dump_json()
    for forbidden in ("password", "passwordHash", "tokenHash"):
        assert forbidden not in dumped


# --- Consulta resuelta en SQL --------------------------------------------------------------------------


def test_filtros_aislamiento_y_paginacion_se_aplican_en_la_consulta_sql(db, mails, team, north, admin):
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine_ = db.get_bind()
    event.listen(engine_, "before_cursor_execute", capture)
    try:
        auditQuery.listInstitution(db, team.owner, team.id, modulo="MATRICES", resultado="FALLO", tamanioPagina=5)
    finally:
        event.remove(engine_, "before_cursor_execute", capture)
    audit_queries = [s for s in statements if 'FROM dbo."Auditoria"' in s or "FROM dbo.Auditoria" in s]
    assert audit_queries, "la consulta debe leer de Auditoria"
    page = next(s for s in audit_queries if "LIMIT" in s.upper() or "FETCH" in s.upper())
    for fragment in ("idInstitucion", "modulo", "resultado"):
        assert fragment in page, f"el filtro por {fragment} debe estar en el SQL"
    assert "LIMIT" in page.upper()  # paginación en la base, no en Python
    # El propietario de otra institución recibe un conjunto disjunto, nunca una unión filtrada después.
    mine = {i.idAuditoria for i in auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items}
    theirs = {i.idAuditoria for i in auditQuery.listInstitution(db, north.owner, north.id, tamanioPagina=100).items}
    assert mine and theirs and mine.isdisjoint(theirs)


def test_cada_evento_resuelve_su_modulo_y_su_institucion_desde_la_entidad(db, mails, team, north):
    modules = {a.tablaAfectada: a.modulo for a in db.scalars(select(Audit)) if a.tablaAfectada}
    assert modules.get("Institucion") == "INSTITUCIONES" and modules.get("InstitucionUsuario") == "INSTITUCIONES"
    assert auditService.moduleFor("LOGIN", None) == "CUENTA" and auditService.moduleFor("CRUD", "Matriz") == "MATRICES"
    assert auditService.moduleFor("CRUD", "Dispositivo") == "DISPOSITIVOS" and auditService.moduleFor("CRUD", "Algo") == "SISTEMA"
    # Un evento de cuenta no se asocia a ninguna institución aunque el usuario pertenezca a una.
    auditService.registerEvent(db, "LOGIN", "LOGIN_LOCAL", True, team.operator.idUsuario)
    db.commit()
    login = audits(db, "LOGIN_LOCAL")[-1]
    assert login.idInstitucion is None and login.modulo == "CUENTA"
    # La institución del evento no cambia si el usuario cambia de institución: sale de la entidad.
    assert all(a.idInstitucion in (team.id, north.id, None) for a in db.scalars(select(Audit)))
