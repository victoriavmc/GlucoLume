# Envío del resultado de una medición por correo (RESULTADO_MEDICION): cuenta individual (a su propio correo) y
# paciente institucional (al correo que el paciente informa al operador, sin guardarlo).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_result_email.py -v

import pytest
from sqlalchemy import select

from app.models.audit import Audit
from app.models.resultDelivery import ResultDelivery
from app.schemas.resultDelivery import ResultSendRequest
from app.services import email as emailService
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import measure
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import completeOximetry, consumer, device, oximetry  # noqa: F401
from tests.test_patient_result_email import confirmationToken
from app.services import resultEmailConfirmation as confirmation

PATIENT_MAIL = "paciente.rosa@example.com"


def deliveries(db, idMedicion):
    db.expire_all()
    return list(db.scalars(select(ResultDelivery).where(ResultDelivery.idMedicion == idMedicion)))


def test_la_cuenta_individual_se_envia_el_resultado_a_su_propio_correo(db, mails, consumer):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db), spo2="97", hr=72)
    answer = measurements.sendResultByEmail(db, user, done.idMedicion, ResultSendRequest())
    assert answer.estadoEnvio == "ENVIADO" and PATIENT_MAIL not in answer.correoEnmascarado
    assert mails[-1]["to"] == user.correoElectronico and "SpO₂" in mails[-1]["html"]
    assert f"/app/mediciones/{done.idMedicion}" in mails[-1]["html"]
    [row] = deliveries(db, done.idMedicion)
    assert row.estadoEnvio == "ENVIADO" and row.correoDestino is None and row.fechaEnvio is not None
    entry = audits(db, "ENVIAR_RESULTADO_MEDICION")[0]
    assert entry.resultado == "EXITO" and user.correoElectronico not in f"{entry.datosNuevos}{entry.observacion}"


def test_una_cuenta_individual_no_puede_dirigirlo_a_otro_correo(db, mails, consumer):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    measurements.sendResultByEmail(db, user, done.idMedicion, ResultSendRequest(correoDestino="otro@example.com"))
    assert [m["to"] for m in mails] == [user.correoElectronico]


def test_solo_se_envian_mediciones_completadas(db, mails, consumer):
    user, profileId = consumer
    pending = oximetry(db, user, profileId, device(db))
    expectError("MEDICION_NO_COMPLETADA", measurements.sendResultByEmail, db, user, pending.idMedicion, ResultSendRequest())
    assert not mails


def test_el_paciente_institucional_recibe_el_resultado_en_el_correo_que_informo(db, mails, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))
    done = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    mails.clear()
    expectError("CORREO_DESTINO_REQUERIDO", measurements.sendResultByEmail, db, team.operator, done.idMedicion, ResultSendRequest())
    expectError("AUTORIZACION_PACIENTE_REQUERIDA", measurements.sendResultByEmail, db, team.operator, done.idMedicion,
                ResultSendRequest(correoDestino=PATIENT_MAIL))
    assert not mails
    answer = measurements.sendResultByEmail(db, team.operator, done.idMedicion, ResultSendRequest(correoDestino=PATIENT_MAIL, pacienteAutoriza=True))
    # Una dirección que el paciente no confirmó no recibe el resultado: recibe un pedido de confirmación (GL-08).
    [request] = mails
    assert answer.estadoEnvio == "CONFIRMACION_PENDIENTE" and request["to"] == PATIENT_MAIL and "SpO₂" not in request["html"]
    assert not deliveries(db, done.idMedicion)
    mails.clear()
    token = confirmationToken([request], PATIENT_MAIL)
    result = confirmation.confirm(db, token)
    assert result["resultadoEnviado"] and not result["correoGuardado"]  # envío puntual: el correo no se guarda
    assert confirmation.confirm(db, token)["resultadoEnviado"] is False  # el mismo enlace no lo reenvía
    [sent] = mails
    assert sent["to"] == PATIENT_MAIL and "SpO₂" in sent["html"] and "iniciá sesión" not in sent["html"]
    assert "/app/mediciones" not in sent["html"]  # el paciente no tiene cuenta: no hay enlace
    [row] = deliveries(db, done.idMedicion)
    assert row.estadoEnvio == "ENVIADO" and row.correoDestino is None  # el correo del paciente no se conserva
    entry = audits(db, "ENVIAR_RESULTADO_MEDICION")[0]
    assert entry.idInstitucion == team.id and PATIENT_MAIL not in f"{entry.datosNuevos}{entry.datosPrevios}{entry.observacion}{entry.detalle}"


def test_solo_el_operador_a_cargo_puede_enviar_el_resultado_de_un_paciente(db, mails, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    done = measure(db, team.operator, patient.idPerfilMedicion, dev)
    other = addOperator(db, team)
    otherUser = db.get(type(team.operator), other.idUsuarioInvitado)
    body = ResultSendRequest(correoDestino=PATIENT_MAIL, pacienteAutoriza=True)
    for actor in (otherUser, team.moderator, team.owner):
        with pytest.raises(Exception) as error:
            measurements.sendResultByEmail(db, actor, done.idMedicion, body)
        assert getattr(error.value, "code", "") in ("MEDICION_NO_ENCONTRADA", "PERMISO_INSUFICIENTE", "MEDICIONES_NO_AUTORIZADAS")
    assert not [m for m in mails if m["to"] == PATIENT_MAIL]


def test_limite_de_envios_por_hora_y_fallo_de_smtp(db, mails, consumer, monkeypatch):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    for _ in range(measurements.RESULT_SEND_LIMIT):
        measurements.sendResultByEmail(db, user, done.idMedicion, ResultSendRequest())
    expectError("ENVIO_RESULTADO_LIMITE", measurements.sendResultByEmail, db, user, done.idMedicion, ResultSendRequest())

    other = completeOximetry(db, user, profileId, device(db))

    def broken(*args, **kwargs):
        raise OSError("smtp caído")

    monkeypatch.setattr(emailService.sender, "sendHtmlEmail", broken)
    expectError("ENVIO_CORREO_FALLIDO", measurements.sendResultByEmail, db, user, other.idMedicion, ResultSendRequest())
    [row] = deliveries(db, other.idMedicion)
    assert row.estadoEnvio == "FALLIDO" and row.correoDestino is None
    failed = [a for a in db.scalars(select(Audit).where(Audit.accion == "ENVIAR_RESULTADO_MEDICION")) if a.resultado != "EXITO"]
    assert failed
