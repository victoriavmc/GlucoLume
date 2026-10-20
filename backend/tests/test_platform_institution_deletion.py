# Eliminación ADMINISTRATIVA de instituciones (etapa D): cierre lógico con marca de cierre administrativo (columnas del esquema v5).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_institution_deletion.py -v
#
# Las pruebas de SQLite usan el esquema de los modelos (ya con las columnas de 033); «sin migración» se simula con
# schemaCompat.administrativeClosureReady = False, que es lo que ve el backend contra SQL Server sin el script.

import pytest
from sqlalchemy import event, func, select, update

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.platform import InstitutionAction, InstitutionDeletion, Reauthentication
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import platformDashboard, platformInstitutions, schemaCompat
from tests.test_account_deletion import audits, db, engine, makeUser, mails, reload  # noqa: F401 - fixtures
from tests.test_account_lifecycle import secondInstitution
from tests.test_dashboards import measure
from tests.test_institution_patients import patientData
from tests.test_institution_reopen import close, reopenData
from tests.test_institutions import cuit, expectError, freshLookupLimiter, institutional, team  # noqa: F401 - fixtures
from tests.test_measurements import device
from tests.test_platform import ADMIN, MOD, PASSWORD, admin, code, login, moderator, reauth, strictPolicy, web  # noqa: F401 - fixtures

REASON = "Cierre definitivo por incumplimiento de condiciones"


def deletion(db, user, secret, *, name="Hospital X", reason=REASON, **overrides) -> InstitutionDeletion:
    data = {"motivo": reason, "confirmacionNombre": name, "reautenticacion": reauth(db, user, secret)}
    return InstitutionDeletion(**{**data, **overrides})


def institution(db, team) -> Institution:
    db.expire_all()
    return db.get(Institution, team.id)


def adminFlag(db, team):
    db.expire_all()
    table = Institution.__table__
    return db.execute(select(table.c.cierreAdministrativo, table.c.fechaCierreAdministrativo, table.c.idUsuarioCierreAdministrativo,
                             table.c.motivoCierreAdministrativo).where(table.c.idInstitucion == team.id)).one()


def activeLinks(db, team):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(InstitutionUser).where(InstitutionUser.idInstitucion == team.id,
                                                                              InstitutionUser.estadoRelacion == "ACTIVO"))


# --- Permisos y reautenticación ----------------------------------------------------------------------------------------------------


def test_solo_el_administrador_puede_eliminar_y_el_moderador_del_sistema_y_los_roles_institucionales_no(db, mails, web, admin, moderator, team):
    user, secret = moderator
    expectError("PERMISO_INSUFICIENTE", platformInstitutions.deleteInstitution, db, user, team.id, deletion(db, user, secret))
    body = {"motivo": REASON, "confirmacionNombre": "Hospital X", "reautenticacion": {"password": PASSWORD, "codigo": code(db, user, secret)}}
    for person in (user, team.owner, team.moderator, team.operator):
        headers = login(web, person, secret if person is user else None)
        assert web.post(f"/api/v1/platform/institutions/{team.id}/delete", headers=headers, json=body).status_code == 403, person.usuario
    assert institution(db, team).estado == "ACTIVA" and activeLinks(db, team) == 3
    assert not adminFlag(db, team).cierreAdministrativo


def test_exige_reautenticacion_reforzada_nombre_exacto_y_motivo_y_nada_cambia_si_falla(db, mails, web, admin, team):
    user, secret = admin
    wrongPassword = InstitutionDeletion(motivo=REASON, confirmacionNombre="Hospital X",
                                        reautenticacion=Reauthentication(password="incorrecta", codigo=code(db, user, secret)))
    expectError("REAUTENTICACION_INVALIDA", platformInstitutions.deleteInstitution, db, user, team.id, wrongPassword)
    noCode = InstitutionDeletion(motivo=REASON, confirmacionNombre="Hospital X", reautenticacion=Reauthentication(password=PASSWORD))
    expectError("REAUTENTICACION_INVALIDA", platformInstitutions.deleteInstitution, db, user, team.id, noCode)
    expectError("CONFIRMACION_INVALIDA", platformInstitutions.deleteInstitution, db, user, team.id, deletion(db, user, secret, name="Otra institución"))
    assert institution(db, team).estado == "ACTIVA" and activeLinks(db, team) == 3
    assert len(audits(db, "REAUTENTICACION_FALLIDA")) == 2  # los fallos de reautenticación quedan registrados
    headers = login(web, user, secret)
    url = f"/api/v1/platform/institutions/{team.id}/delete"
    reauthBody = {"password": PASSWORD, "codigo": code(db, user, secret)}
    for body in ({"confirmacionNombre": "Hospital X", "reautenticacion": reauthBody}, {"motivo": "corto", "confirmacionNombre": "Hospital X", "reautenticacion": reauthBody},
                 {"motivo": REASON, "reautenticacion": reauthBody}, {"motivo": REASON, "confirmacionNombre": "Hospital X"},
                 {"motivo": REASON, "confirmacionNombre": "Hospital X", "reautenticacion": reauthBody, "estado": "CERRADA"}):
        assert web.post(url, headers=headers, json=body).status_code == 422
    assert institution(db, team).estado == "ACTIVA"


def test_un_codigo_mfa_ya_usado_no_se_acepta_otra_vez(db, mails, admin, team):
    user, secret = admin
    first = deletion(db, user, secret, name="Otra")  # nombre incorrecto: la reautenticación se evalúa después y no se consume
    expectError("CONFIRMACION_INVALIDA", platformInstitutions.deleteInstitution, db, user, team.id, first)
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institution(db, team).estado == "CERRADA"


# --- Efectos --------------------------------------------------------------------------------------------------------------------------


def test_la_eliminacion_administrativa_cierra_con_la_marca_conserva_los_datos_audita_y_avisa(db, mails, admin, team):
    user, secret = admin
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(dni="20111999"))
    measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    profiles = db.scalar(select(func.count()).select_from(MeasurementProfile))
    measurements = db.scalar(select(func.count()).select_from(Measurement))
    mails.clear()
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institution(db, team).estado == "CERRADA" and activeLinks(db, team) == 0
    flag = adminFlag(db, team)
    assert flag.cierreAdministrativo in (True, 1) and flag.idUsuarioCierreAdministrativo == user.idUsuario and flag.motivoCierreAdministrativo == REASON
    assert flag.fechaCierreAdministrativo is not None
    # No se destruyen datos clínicos: pacientes y mediciones siguen, con su plazo de conservación.
    assert db.scalar(select(func.count()).select_from(MeasurementProfile)) == profiles
    assert db.scalar(select(func.count()).select_from(Measurement)) == measurements
    assert reload(db, MeasurementProfile, patient.idPerfilMedicion).fechaExpiracionDatosPersonales is not None
    event = audits(db, "ELIMINAR_INSTITUCION_ADMINISTRATIVA")[-1]
    assert (event.resultado, event.idUsuario, event.idInstitucion, event.modulo) == ("EXITO", user.idUsuario, team.id, "INSTITUCIONES")
    assert event.observacion == f"Motivo: {REASON}" and '"ACTIVA"' in event.datosPrevios and '"CERRADA"' in event.datosNuevos
    assert "ADMINISTRADOR_PLATAFORMA" in event.datosNuevos and "cierreAdministrativo" in event.datosNuevos
    notices = [m for m in mails if m["subject"] == "La institución fue cerrada por la administración de GlucoLume"]
    assert {m["to"] for m in notices} == {team.owner.correoElectronico, team.moderator.correoElectronico, team.operator.correoElectronico}
    assert REASON not in notices[0]["html"]  # el motivo administrativo no se difunde a todo el equipo
    detail = platformDashboard.institutionDetail(db, user, team.id)
    assert detail.fila.estado == "CERRADA" and detail.cierreAdministrativo.motivo == REASON and detail.cierreAdministrativo.rolActor == ADMIN
    assert detail.eliminacionDisponible is True
    assert any(i.accion == "ELIMINAR_INSTITUCION_ADMINISTRATIVA" and i.categoria == "CIERRE"
               for i in platformInstitutions.auditPage(db, user, team.id, tamanio=50).items)  # la auditoría sigue disponible con la institución cerrada


def test_tambien_se_puede_eliminar_una_institucion_pausada(db, mails, admin, team):
    user, secret = admin
    platformInstitutions.pause(db, user, team.id, InstitutionAction(motivo="Revisión de seguridad en curso"))
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institution(db, team).estado == "CERRADA" and adminFlag(db, team).cierreAdministrativo in (True, 1)
    assert '"INACTIVA"' in audits(db, "ELIMINAR_INSTITUCION_ADMINISTRATIVA")[-1].datosPrevios


def test_no_afecta_a_las_otras_instituciones_de_quienes_pertenecian_a_la_eliminada(db, mails, admin, team):
    user, secret = admin
    other, _ = secondInstitution(db, team.moderator)  # el moderador de `team` también es moderador de otra institución
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institutions.requireMembership(db, team.moderator, other.idInstitucion).institution.estado == "ACTIVA"
    assert reload(db, User, team.moderator.idUsuario).estado == "ACTIVO"
    assert db.get(Institution, other.idInstitucion).estado == "ACTIVA"


def test_una_institucion_ya_cerrada_no_se_elimina_y_el_intento_queda_auditado(db, mails, admin, team):
    user, secret = admin
    close(db, team.owner, team.id)  # la cerró su propietario
    expectError("INSTITUCION_NO_ELIMINABLE", platformInstitutions.deleteInstitution, db, user, team.id, deletion(db, user, secret))
    assert not adminFlag(db, team).cierreAdministrativo  # no se convierte en administrativa
    failed = [e for e in audits(db, "ELIMINAR_INSTITUCION_ADMINISTRATIVA") if e.resultado == "FALLO"]
    assert len(failed) == 1 and "INSTITUCION_NO_ELIMINABLE" in failed[0].observacion
    import uuid
    expectError("INSTITUCION_NO_ENCONTRADA", platformInstitutions.deleteInstitution, db, user, uuid.uuid4(), deletion(db, user, secret))


def test_estado_marca_y_auditoria_son_atomicos_si_falla_el_registro_no_cambia_nada(db, mails, admin, team, monkeypatch):
    user, secret = admin

    def broken(*args, **kwargs):
        raise RuntimeError("falla simulada al registrar")

    monkeypatch.setattr(platformInstitutions, "registerEvent", broken)
    with pytest.raises(RuntimeError):
        platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institution(db, team).estado == "ACTIVA" and activeLinks(db, team) == 3
    assert not adminFlag(db, team).cierreAdministrativo and adminFlag(db, team).motivoCierreAdministrativo is None


# --- Reapertura ----------------------------------------------------------------------------------------------------------------------


def test_el_propietario_no_puede_reabrir_una_institucion_eliminada_por_la_administracion(db, mails, admin, team):
    user, secret = admin
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    assert institutions.canReopen(db, team.owner, institution(db, team)) is False
    status = institutions.checkLegalId(db, team.owner, "CUIT", cuit())
    assert (status.estado, status.puedeReabrir, status.institucion) == ("CERRADA", False, None) and "administración de GlucoLume" in status.mensaje
    expectError("INSTITUCION_CERRADA_ADMINISTRATIVAMENTE", institutions.reopenInstitution, db, team.owner, reopenData())
    expectError("INSTITUCION_CERRADA_ADMINISTRATIVAMENTE", institutions.createInstitution, db, team.owner, reopenData())  # tampoco creando otra con el CUIT
    assert institution(db, team).estado == "CERRADA" and activeLinks(db, team) == 0 and institution(db, team).cantidadReaperturas == 0
    failed = [e for e in audits(db, "REABRIR_INSTITUCION") if e.resultado == "FALLO"]
    assert failed and "CIERRE_ADMINISTRATIVO" in failed[-1].observacion


def test_a_una_cuenta_ajena_no_se_le_revela_que_el_cierre_fue_administrativo(db, mails, admin, team):
    user, secret = admin
    platformInstitutions.deleteInstitution(db, user, team.id, deletion(db, user, secret))
    stranger = institutional(db, "ajena@example.com", "ajena")
    status = institutions.checkLegalId(db, stranger, "CUIT", cuit())
    assert status.estado == "CERRADA" and status.puedeReabrir is False and "administración" not in status.mensaje  # igual que cualquier cerrada ajena
    expectError("INSTITUCION_CERRADA", institutions.createInstitution, db, stranger, reopenData())
    expectError("REPRESENTACION_NO_VERIFICADA", institutions.reopenInstitution, db, stranger, reopenData(password=PASSWORD))


def test_el_cierre_y_la_reapertura_legitimos_del_propietario_siguen_funcionando_sin_marca(db, mails, team):
    close(db, team.owner, team.id)
    assert not adminFlag(db, team).cierreAdministrativo
    assert institutions.isAdministrativeClosure(db, institution(db, team)) is False
    assert institutions.canReopen(db, team.owner, institution(db, team)) is True
    reopened = institutions.reopenInstitution(db, team.owner, reopenData())
    assert reopened.estado == "ACTIVA" and reopened.cantidadReaperturas == 1
    assert platformInstitutions.administrativeClosure(db, reopened) is None


# --- Compatibilidad: base sin el script 033 --------------------------------------------------------------------------------------------


def test_sin_el_script_033_la_eliminacion_administrativa_no_esta_disponible_y_el_resto_no_cambia(db, mails, admin, team, monkeypatch):
    user, secret = admin
    monkeypatch.setattr(schemaCompat, "administrativeClosureReady", lambda session: False)
    expectError("ELIMINACION_ADMINISTRATIVA_NO_DISPONIBLE", platformInstitutions.deleteInstitution, db, user, team.id, deletion(db, user, secret))
    assert institution(db, team).estado == "ACTIVA" and activeLinks(db, team) == 3 and audits(db, "ELIMINAR_INSTITUCION_ADMINISTRATIVA") == []
    detail = platformDashboard.institutionDetail(db, user, team.id)
    assert detail.eliminacionDisponible is False and detail.cierreAdministrativo is None
    # El cierre y la reapertura del propietario siguen exactamente igual.
    close(db, team.owner, team.id)
    assert institutions.canReopen(db, team.owner, institution(db, team)) is True
    assert institutions.reopenInstitution(db, team.owner, reopenData()).estado == "ACTIVA"


def test_el_backend_no_pide_ni_escribe_las_columnas_nuevas_salvo_en_la_eliminacion_administrativa(db, engine, mails, team):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        owner = institutional(db, "otro@example.com", "otrodue")
        institutions.createInstitution(db, owner, _newData())
        institutions.requireMembership(db, team.owner, team.id)
        institutions.listMine(db, team.owner)
        close(db, team.owner, team.id)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    touching = [s for s in statements if "cierreAdministrativo" in s or "motivoCierreAdministrativo" in s]
    assert touching == [], [t[:2000] for t in touching]  # ni SELECT de Institucion, ni INSERT, ni el cierre del propietario las mencionan


def _newData():
    from app.schemas.institution import InstitutionCreateRequest

    return InstitutionCreateRequest(nombre="Clínica Nueva", tipoInstitucion="CLINICA", tipoIdentificadorLegal="CUIT", identificadorLegal=cuit(number="71234568"))


def test_el_esquema_consolidado_incluye_el_cierre_administrativo_como_el_modelo(referenceSchema):
    """DEC-02: la regla del antiguo script 033 (cierre administrativo de una institución) vive en GlucoLume_DB_v5.sql."""
    import re

    table = Institution.__table__
    expected = {"cierreAdministrativo": r"\[bit\] NOT NULL", "fechaCierreAdministrativo": r"\[datetime2\]\(3\) NULL",
                "idUsuarioCierreAdministrativo": r"\[uniqueidentifier\] NULL", "motivoCierreAdministrativo": r"\[nvarchar\]\(300\) NULL"}
    for column, definition in expected.items():
        assert column in table.c and re.search(rf"^\t\[{column}\] {definition}", referenceSchema, re.M), column
    names = {constraint.name for constraint in table.constraints} | {key.name for key in table.foreign_keys}
    for name in ("CK_Institucion_cierreAdministrativo", "FK_Institucion_cierreAdministrativo_Usuario"):
        assert name in names and f"CONSTRAINT [{name}]" in referenceSchema
    assert re.search(r"CONSTRAINT \[FK_Institucion_cierreAdministrativo_Usuario\] FOREIGN KEY\(\[idUsuarioCierreAdministrativo\]\)\s*"
                     r"REFERENCES \[dbo\]\.\[Usuario\]", referenceSchema)
