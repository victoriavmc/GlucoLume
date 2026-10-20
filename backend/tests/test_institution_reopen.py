# Pruebas de la validación de CUIT por estado y de la reapertura de instituciones cerradas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_institution_reopen.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py y el escenario `team` de test_institutions.py.

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.schemas.institution import InstitutionDeletionRequest, InstitutionReopenRequest
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurement as measurementService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    PASSWORD,
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    cuit,
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)


def close(db, owner, idInstitucion, nombre="Hospital X"):
    institutions.deleteInstitution(db, owner, idInstitucion,
                                   InstitutionDeletionRequest(confirmacionNombre=nombre, password=PASSWORD))


def reopenData(**overrides) -> InstitutionReopenRequest:
    data = {"nombre": "Hospital X Reabierto", "tipoInstitucion": "CLINICA", "identificadorLegal": cuit(),
            "descripcion": "Nueva etapa", "password": PASSWORD}
    return InstitutionReopenRequest(**{**data, **overrides})


def ownerRelations(db, idInstitucion):
    db.expire_all()
    return db.scalars(
        select(InstitutionUser)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == "PROPIETARIO")
        .order_by(InstitutionUser.fechaIncorporacion)
    ).all()


# --- Estado del CUIT: casos A, B y C ---------------------------------------------------------


def test_cuit_nuevo_crea_institucion_con_contador_en_cero(db, mails):
    owner = institutional(db, "duenia@example.com", "duenia")
    assert institutions.checkLegalId(db, owner, "CUIT", cuit()).estado == "DISPONIBLE"
    created = newInstitution(db, owner)
    institution = reload(db, Institution, created.idInstitucion)
    assert institution.cantidadReaperturas == 0 and institution.fechaUltimaReapertura is None
    assert institutions.getDetail(db, owner, created.idInstitucion).cantidadReaperturas == 0


def test_cuit_activo_se_rechaza(db, mails, team):
    other = institutional(db, "otra@example.com", "otra")
    status = institutions.checkLegalId(db, other, "CUIT", cuit())
    assert status.estado == "ACTIVA" and status.institucion is None
    error = expectError("INSTITUCION_REGISTRADA", newInstitution, db, other)
    assert error.message == "Ya existe una institución activa registrada con este CUIT."
    expectError("INSTITUCION_REGISTRADA", institutions.reopenInstitution, db, team.owner, reopenData())
    assert db.scalar(select(func.count()).select_from(Institution)) == 1


def test_cuit_cerrado_informa_la_reapertura_solo_al_autorizado(db, mails, team):
    close(db, team.owner, team.id)
    status = institutions.checkLegalId(db, team.owner, "CUIT", cuit())
    assert (status.estado, status.puedeReabrir) == ("CERRADA", True)
    assert status.mensaje == "Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla."
    assert status.institucion.nombre == "Hospital X" and status.institucion.cantidadReaperturas == 0
    # Otra cuenta institucional no ve sus datos ni puede reabrirla.
    stranger = institutional(db, "ajena@example.com", "ajena")
    status = institutions.checkLegalId(db, stranger, "CUIT", cuit())
    assert (status.estado, status.puedeReabrir, status.institucion) == ("CERRADA", False, None)
    # Crear con ese CUIT no duplica: indica que corresponde reabrir.
    error = expectError("INSTITUCION_CERRADA", newInstitution, db, team.owner)
    assert error.message == "Esta institución se encuentra cerrada. Completá sus nuevos datos para reabrirla."
    assert db.scalar(select(func.count()).select_from(Institution)) == 1


# --- Reapertura ---------------------------------------------------------------------------


def test_reapertura_conserva_el_registro_y_actualiza_los_datos(db, mails, team):
    before = reload(db, Institution, team.id)
    fechaCreacion, identificador = before.fechaCreacion, before.identificadorLegal
    close(db, team.owner, team.id)

    reopened = institutions.reopenInstitution(db, team.owner, reopenData())
    institution = reload(db, Institution, team.id)
    assert reopened.idInstitucion == team.id  # mismo UUID: no se duplica el registro
    assert (institution.estado, institution.cantidadReaperturas) == ("ACTIVA", 1)
    assert (institution.nombre, institution.tipoInstitucion, institution.descripcion) == (
        "Hospital X Reabierto", "CLINICA", "Nueva etapa")
    assert (institution.fechaCreacion, institution.identificadorLegal) == (fechaCreacion, identificador)
    assert institution.fechaUltimaReapertura is not None
    assert db.scalar(select(func.count()).select_from(Institution)) == 1

    # Historial del propietario: el vínculo anterior queda en BAJA y hay uno nuevo ACTIVO.
    relations = ownerRelations(db, team.id)
    assert [r.estadoRelacion for r in relations] == ["BAJA", "ACTIVO"]
    assert {r.idUsuarioInvitado for r in relations} == {team.owner.idUsuario}
    # Auditoría de cierre y reapertura (historial disponible).
    assert [a.accion for a in audits(db) if a.accion in ("CREAR_INSTITUCION", "ELIMINAR_INSTITUCION",
                                                         "REABRIR_INSTITUCION") and a.resultado == "EXITO"] == [
        "CREAR_INSTITUCION", "ELIMINAR_INSTITUCION", "REABRIR_INSTITUCION"]
    detail = institutions.getDetail(db, team.owner, team.id)
    assert detail.cantidadReaperturas == 1 and detail.rolInstitucion == "PROPIETARIO"


def test_contador_cuenta_cada_reapertura_y_no_se_reinicia_al_cerrar(db, mails, team):
    counts = []
    for round_ in range(3):
        nombre = "Hospital X" if round_ == 0 else "Hospital X Reabierto"
        close(db, team.owner, team.id, nombre)
        counts.append(reload(db, Institution, team.id).cantidadReaperturas)  # tras cerrar
        institutions.reopenInstitution(db, team.owner, reopenData())
        counts.append(reload(db, Institution, team.id).cantidadReaperturas)  # tras reabrir
    assert counts == [0, 1, 1, 2, 2, 3]


def test_los_integrantes_anteriores_no_recuperan_acceso(db, mails, team):
    nueva = institutional(db, "nueva@example.com", "nueva")
    pending = institutions.invite(db, team.moderator, team.id, "OPERADOR", "nueva@example.com")
    close(db, team.owner, team.id)
    institutions.reopenInstitution(db, team.owner, reopenData())

    for user in (team.moderator, team.operator):
        assert institutions.listMine(db, user) == []
        expectError("INSTITUCION_NO_ENCONTRADA", institutions.getDetail, db, user, team.id)
    expectError("INVITACION_NO_ENCONTRADA", institutions.respondInvitation, db, nueva, pending.idInstitucionUsuario, True)
    detail = institutions.getDetail(db, team.owner, team.id)
    assert (detail.cantidadModeradores, detail.cantidadOperadores) == (0, 0)
    # Se pueden volver a incorporar, pero solo por los flujos autorizados (invitación aceptada).
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", team.moderator.correoElectronico)
    assert invitation.estadoRelacion == "PENDIENTE"


def test_pacientes_y_mediciones_anteriores_se_conservan_archivados(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
    db.add(device)
    db.flush()
    measurement = Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=created.idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=46, sexoModelo="MASCULINO",
        condicionComida="POSTPRANDIAL", fechaHoraInicio=nowForDb() - timedelta(days=2),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=2, hours=2), spo2=97, frecuenciaCardiaca=72,
        modeloSensorAlMomento="MAX30102",
    )
    db.add(measurement)
    db.commit()
    close(db, team.owner, team.id)
    retentionEnd = reload(db, MeasurementProfile, created.idPerfilMedicion).fechaExpiracionDatosPersonales
    assert retentionEnd is not None

    institutions.reopenInstitution(db, team.owner, reopenData())

    # La reapertura no toca la conservación programada ni los datos ni las mediciones.
    profile = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert profile.fechaExpiracionDatosPersonales == retentionEnd and profile.fechaDepuracionDatosPersonales is None
    assert (profile.nombre, profile.dni) == ("Juan", "20111222")
    assert reload(db, Measurement, measurement.idMedicion).idPerfilMedicion == created.idPerfilMedicion
    # Pero quedan archivados: el nuevo período no accede a los pacientes anteriores.
    assert patients.listPatients(db, team.owner, team.id).total == 0
    assert patients.listPatients(db, team.owner, team.id, estado="BAJA").total == 0
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, team.owner, team.id, created.idPerfilMedicion)
    expectError("PACIENTE_NO_ENCONTRADO", measurementService.listPatientHistory, db, team.owner, team.id, created.idPerfilMedicion)
    assert institutions.getDetail(db, team.owner, team.id).cantidadPacientes == 0


def test_pacientes_del_nuevo_periodo_si_se_gestionan(db, mails, team):
    close(db, team.owner, team.id)
    institutions.reopenInstitution(db, team.owner, reopenData())
    moderator = institutional(db, "mod2@example.com", "mod2")
    invitation = institutions.invite(db, team.owner, team.id, "MODERADOR", "mod2@example.com")
    institutions.respondInvitation(db, moderator, invitation.idInstitucionUsuario, accept=True)
    team.moderator = moderator
    operator = addOperator(db, team, "op2@example.com", "op2")
    created = patients.createPatient(db, team.moderator, team.id, patientData(
        idInstitucionUsuarioResponsable=operator.idInstitucionUsuario))
    assert [p.idPerfilMedicion for p in patients.listPatients(db, team.owner, team.id).items] == [created.idPerfilMedicion]


# --- Autorización ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["stranger", "moderator", "operator"])
def test_solo_el_ultimo_propietario_puede_reabrir(db, mails, team, who):
    close(db, team.owner, team.id)
    actor = institutional(db, "ajena@example.com", "ajena") if who == "stranger" else getattr(team, who)
    error = expectError("REPRESENTACION_NO_VERIFICADA", institutions.reopenInstitution, db, actor, reopenData())
    assert "conocer el CUIT no alcanza" in error.message
    institution = reload(db, Institution, team.id)
    assert (institution.estado, institution.cantidadReaperturas) == ("CERRADA", 0)
    assert any(a.accion == "REABRIR_INSTITUCION" and a.resultado == "FALLO" for a in audits(db))


def test_cuenta_individual_no_puede_reabrir(db, mails, team):
    close(db, team.owner, team.id)
    expectError("PERMISO_INSUFICIENTE", institutions.reopenInstitution, db, makeUser(db), reopenData())


def test_reapertura_exige_reautenticacion(db, mails, team):
    close(db, team.owner, team.id)
    expectError("PASSWORD_REQUERIDA", institutions.reopenInstitution, db, team.owner, reopenData(password=None))
    expectError("PASSWORD_INCORRECTA", institutions.reopenInstitution, db, team.owner, reopenData(password="OtraClave#2026"))
    assert reload(db, Institution, team.id).estado == "CERRADA"


# --- Concurrencia y atomicidad ----------------------------------------------------------------


def test_dos_reaperturas_simultaneas_incrementan_una_sola_vez(engine, db, mails, team):
    close(db, team.owner, team.id)
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results, errors = [], []

    def attempt():
        session = makeSession()
        try:
            owner = session.get(type(team.owner), team.owner.idUsuario)
            barrier.wait()
            institutions.reopenInstitution(session, owner, reopenData())
            results.append("OK")
        except AuthError as error:
            results.append(error.code)
        except Exception as error:  # pragma: no cover - diagnóstico
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(results) == ["INSTITUCION_REGISTRADA", "OK"]
    institution = reload(db, Institution, team.id)
    assert (institution.estado, institution.cantidadReaperturas) == ("ACTIVA", 1)
    assert [r.estadoRelacion for r in ownerRelations(db, team.id)] == ["BAJA", "ACTIVO"]


def test_transaccion_fallida_no_modifica_estado_ni_contador(db, mails, team, monkeypatch):
    close(db, team.owner, team.id)
    original = institutions.registerEvent

    def failingAudit(db_, tipo, accion, exito, *args, **kwargs):
        if accion == "REABRIR_INSTITUCION" and exito:
            raise RuntimeError("falla simulada al auditar")
        return original(db_, tipo, accion, exito, *args, **kwargs)

    monkeypatch.setattr(institutions, "registerEvent", failingAudit)
    with pytest.raises(RuntimeError):
        institutions.reopenInstitution(db, team.owner, reopenData())
    institution = reload(db, Institution, team.id)
    assert (institution.estado, institution.cantidadReaperturas, institution.nombre) == ("CERRADA", 0, "Hospital X")
    assert institution.fechaUltimaReapertura is None
    assert [r.estadoRelacion for r in ownerRelations(db, team.id)] == ["BAJA"]


def test_reapertura_directa_sin_estados_pendientes(db, mails, team):
    """Una sola operación: no quedan solicitudes ni vínculos PENDIENTES; el propietario queda ACTIVO de inmediato."""
    close(db, team.owner, team.id)
    institutions.reopenInstitution(db, team.owner, reopenData())
    db.expire_all()
    pending = db.scalars(select(InstitutionUser).where(InstitutionUser.idInstitucion == team.id,
                                                       InstitutionUser.estadoRelacion == "PENDIENTE")).all()
    assert pending == []
    assert institutions.getDetail(db, team.owner, team.id).estado == "ACTIVA"
