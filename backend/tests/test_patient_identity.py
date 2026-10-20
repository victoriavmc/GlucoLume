# Nombre y apellido del paciente en transferencias y auditoría: solo con autorización, nunca reconstruidos si fueron
# depurados y siempre dentro de la institución del perfil.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_identity.py -v

from sqlalchemy import update

from app.models.measurementProfile import MeasurementProfile
from app.services import auditQuery
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import admin  # noqa: F401 - fixture
from tests.test_audit_names import named
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import freshLookupLimiter, institutional, relationOf, team  # noqa: F401
from tests.test_transfer_detail import auditItems, scenario


def patientOf(db, patient):
    db.expire_all()
    return db.get(MeasurementProfile, patient.idPerfilMedicion)


def requested(db, team):
    second, secondUser, patient = scenario(db, team)
    sent = transfers.requestTransfer(db, team.operator, team.id, patient.idPerfilMedicion, second.idInstitucionUsuario, None)
    return second, secondUser, patient, sent


def test_el_nombre_sale_de_perfil_medicion_y_no_del_operador(db, mails, team):
    _, _, patient, sent = requested(db, team)
    detail = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert (detail.paciente.nombre, detail.paciente.apellido) == ("Rosa", "Díaz")
    assert detail.origen.nombre == "Juan" and detail.destino.nombre == "María"
    audit = auditQuery.detailInstitution(db, team.owner, team.id, auditItems(db, team, "SOLICITAR_TRANSFERENCIA_PERFIL")[0].idAuditoria)
    assert audit.transferencia.paciente.nombreCompleto == "Rosa Díaz"
    assert audit.transferencia.paciente.identificador == patient.identificadorPseudonimo


def test_el_moderador_ve_el_nombre_y_el_operador_destinatario_solo_el_codigo(db, mails, team):
    _, secondUser, _, sent = requested(db, team)
    assert transfers.getTransfer(db, team.moderator, team.id, sent.idTransferenciaPerfil).paciente.nombre == "Rosa"
    asRecipient = transfers.getTransfer(db, secondUser, team.id, sent.idTransferenciaPerfil)
    assert asRecipient.paciente.nombre is None and asRecipient.paciente.datosIdentificativos is None
    assert "Rosa" not in asRecipient.descripcion and asRecipient.paciente.identificadorPseudonimo in asRecipient.descripcion


def test_la_auditoria_global_no_muestra_nombres_de_pacientes(db, mails, team, admin):
    requested(db, team)
    page = auditQuery.listGlobal(db, admin, accion="SOLICITAR_TRANSFERENCIA_PERFIL")
    detail = auditQuery.detailGlobal(db, admin, page.items[0].idAuditoria)
    assert detail.transferencia.paciente.nombreCompleto is None and detail.transferencia.paciente.datosIdentificativos is None
    assert "Rosa" not in detail.resumen and detail.transferencia.paciente.identificador in detail.resumen


def test_datos_depurados_o_sin_nombre_no_se_reconstruyen(db, mails, team):
    _, _, patient, sent = requested(db, team)
    db.execute(update(MeasurementProfile).where(MeasurementProfile.idPerfilMedicion == patient.idPerfilMedicion)
               .values(nombre=None, apellido=None, fechaDepuracionDatosPersonales=nowForDb(),
                       fechaExpiracionDatosPersonales=nowForDb()))
    db.commit()
    detail = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert detail.paciente.nombre is None and detail.paciente.datosIdentificativos is None and not detail.paciente.puedeVerPerfil
    assert detail.paciente.identificadorPseudonimo == patient.identificadorPseudonimo  # la trazabilidad se conserva
    audit = auditQuery.detailInstitution(db, team.owner, team.id, auditItems(db, team, "SOLICITAR_TRANSFERENCIA_PERFIL")[0].idAuditoria)
    assert audit.transferencia.paciente.nombreCompleto is None and audit.transferencia.paciente.datosIdentificativos is False
    assert "Rosa" not in audit.resumen


def test_autorizado_pero_sin_nombre_registrado_informa_que_no_esta_disponible(db, mails, team):
    _, _, patient, sent = requested(db, team)
    db.execute(update(MeasurementProfile).where(MeasurementProfile.idPerfilMedicion == patient.idPerfilMedicion)
               .values(nombre=None, apellido=None))
    db.commit()
    detail = transfers.getTransfer(db, team.owner, team.id, sent.idTransferenciaPerfil)
    assert detail.paciente.datosIdentificativos is False and detail.paciente.nombre is None
    listed = transfers.listTransfers(db, team.owner, team.id).items[0]
    assert listed.paciente.datosIdentificativos is False
