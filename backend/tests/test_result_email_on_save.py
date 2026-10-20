# El resultado se envía por correo AL GUARDAR la medición con el dispositivo (flujo real: sesión de telemetría), no solo cuando se llama al envío
# a mano: paciente institucional con correo cargado y vigente, DEMO y experimentales, sin correo no se envía y un fallo no deshace la medición.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_result_email_on_save.py -v

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.resultDelivery import ResultDelivery
from app.schemas.acquisition import DeviceConnectConfirm
from app.schemas.measurementProfile import PatientResultEmailRequest
from app.services import deviceConnection
from app.services import institutionPatients as patients
from app.services import patientResultEmail as resultEmail
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_institution_patients import patientData
from tests.test_institutions import freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401
from tests.test_patient_result_email import loadEmail
from tests.test_telemetry import CODE, bridge, clock, freshHub, startFor  # noqa: F401

MAIL = "paciente.rosa@example.com"


def deliveries(db, idMedicion):
    db.expire_all()
    return list(db.scalars(select(ResultDelivery).where(ResultDelivery.idMedicion == idMedicion)))


def measureAndSave(db, team, patient, bridge, **readings):
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=dev.idDispositivo))  # firmware sin ID propio
    startFor(db, team.operator, patient.idPerfilMedicion, dev)
    bridge.seconds(9, **readings)
    return telemetryService.saveSession(db, team.operator)


@pytest.fixture
def patient(db, team):
    return patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))


def test_al_guardar_una_medicion_demo_se_envia_el_correo_identificada_como_simulada(db, team, patient, bridge, mails):
    loadEmail(db, mails, team, patient.idPerfilMedicion, MAIL)
    mails.clear()
    saved = measureAndSave(db, team, patient, bridge, origen="DEMO", glu="117.0")
    assert saved.envioAutomatico == "ENVIADO"  # el guardado informa el resultado del envío
    assert [m["to"] for m in mails] == [MAIL] and "simulad" in mails[0]["text"].lower()
    assert [d.estadoEnvio for d in deliveries(db, saved.idMedicion)] == ["ENVIADO"]


def test_al_guardar_una_medicion_experimental_tambien_se_envia(db, team, patient, bridge, mails):
    loadEmail(db, mails, team, patient.idPerfilMedicion, MAIL)
    mails.clear()
    saved = measureAndSave(db, team, patient, bridge, origen="EXPERIMENTAL", glu="105.0")
    assert saved.envioAutomatico == "ENVIADO" and [m["to"] for m in mails] == [MAIL]


def test_sin_correo_cargado_no_se_envia_nada(db, team, patient, bridge, mails):
    mails.clear()
    saved = measureAndSave(db, team, patient, bridge, origen="DEMO", glu="117.0")
    assert saved.envioAutomatico is None and not mails and deliveries(db, saved.idMedicion) == []


def test_cada_medicion_completada_por_la_via_del_servidor_tambien_envia_su_resultado(db, team, patient, mails):
    """La otra vía que completa mediciones (muestras procesadas por el servidor) también envía: cada medición del paciente con correo cargado."""
    from app.services import measurement as measurements
    from tests.test_dashboards import measure
    loadEmail(db, mails, team, patient.idPerfilMedicion, MAIL)
    mails.clear()
    dev = device(db, institucion=team.id)
    first = measure(db, team.operator, patient.idPerfilMedicion, dev, "97", 70)
    second = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 75)
    assert first.envioAutomatico == "ENVIADO" and second.envioAutomatico == "ENVIADO"  # una por cada medición
    assert [m["to"] for m in mails] == [MAIL, MAIL]
    assert all(d.estadoEnvio == "ENVIADO" for idMedicion in (first.idMedicion, second.idMedicion) for d in deliveries(db, idMedicion))
    # Sin correo no se envía y la medición queda guardada igual.
    from app.services import resultEmailStore
    resultEmailStore.clear(db, patient.idPerfilMedicion)
    db.commit()
    mails.clear()
    third = measure(db, team.operator, patient.idPerfilMedicion, dev, "95", 72)
    assert third.estadoMedicion == "COMPLETADA" and third.envioAutomatico is None and not mails
