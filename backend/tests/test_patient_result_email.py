# Correo del paciente institucional para recibir sus resultados: carga con autorización, plazo de 12 meses, cambio, borrado, envío
# automático al guardar (nunca DEMO) y retención. El correo no se registra en la auditoría ni en EnvioResultado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_patient_result_email.py -v

import re
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.models.measurement import Measurement
from app.models.resultDelivery import ResultDelivery
from app.schemas.measurementProfile import PatientResultEmailRequest
from app.schemas.resultDelivery import ResultSendRequest
from app.services import email as emailService
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import patientResultEmail as resultEmail
from app.services import resultEmailConfirmation as confirmation
from app.services import resultEmailStore
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_dashboards import measure
from tests.test_institution_patients import addOperator, patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import consumer, device  # noqa: F401

MAIL = "paciente.rosa@example.com"
OTHER = "rosa.nueva@example.com"


def body(correo=MAIL, autoriza=True):
    return PatientResultEmailRequest(correo=correo, pacienteAutoriza=autoriza)


def confirmationToken(mails, to):
    """Token del último pedido de confirmación que recibió `to` (el enlace lleva el token en el fragmento #token=)."""
    for mail in reversed(mails):
        if mail["to"] == to and "#token=" in mail["html"]:
            return re.search(r"#token=([A-Za-z0-9_.\-]+)", mail["html"]).group(1)
    raise AssertionError(f"No llegó el pedido de confirmación a {to}")


def loadEmail(db, mails, team, idPerfilMedicion, correo=MAIL):
    """El operador carga el correo y el paciente lo confirma desde el enlace (GL-08)."""
    resultEmail.setResultEmail(db, team.operator, team.id, idPerfilMedicion, body(correo))
    return confirmation.confirm(db, confirmationToken(mails, correo))


def deliveries(db, idMedicion):
    db.expire_all()
    return list(db.scalars(select(ResultDelivery).where(ResultDelivery.idMedicion == idMedicion)))


@pytest.fixture
def patient(db, team):
    return patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz"))


def test_cargar_el_correo_exige_autorizacion_y_la_confirmacion_del_paciente_y_vence_a_los_12_meses(db, mails, team, patient):
    expectError("AUTORIZACION_PACIENTE_REQUERIDA", resultEmail.setResultEmail, db, team.operator, team.id, patient.idPerfilMedicion, body(autoriza=False))
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None
    read = resultEmail.setResultEmail(db, team.operator, team.id, patient.idPerfilMedicion, body())
    assert read.correoResultados is None and read.correoResultadosPendiente.endswith("@example.com")  # enmascarado y pendiente
    assert MAIL not in read.correoResultadosPendiente
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None  # el operador solo no alcanza: falta el paciente
    token = confirmationToken(mails, MAIL)
    expectError("ENLACE_INVALIDO", confirmation.confirm, db, token[:-4] + "abcd")  # un enlace alterado no confirma nada
    result = confirmation.confirm(db, token)
    assert result["confirmado"] and result["correoGuardado"] and result["resultadoEnCamino"] is False
    found = resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb())
    expected = nowForDb() + timedelta(days=365)
    assert found[0] == MAIL and abs((found[1] - expected).total_seconds()) < 3 * 86400
    assert confirmation.confirm(db, token)["correoGuardado"] is False  # repetir el enlace no vuelve a hacer nada
    for action in ("SOLICITAR_CONFIRMACION_CORREO_RESULTADOS", "CARGAR_CORREO_RESULTADOS_PACIENTE"):
        entry = audits(db, action)[0]
        assert MAIL not in f"{entry.datosNuevos}{entry.datosPrevios}{entry.observacion}{entry.detalle}"


def test_un_correo_que_no_existe_se_rechaza_al_cargarlo_y_no_se_dice_que_sale(db, mails, team, patient, monkeypatch):
    from app.integrations.email.mailboxCheck import ResultadoBuzon, Veredicto
    monkeypatch.setattr(emailService, "verificarDestinatario", lambda correo: ResultadoBuzon(Veredicto.NO_EXISTE, "BUZON_NO_ENCONTRADO"))
    expectError("CORREO_NO_ENCONTRADO", resultEmail.setResultEmail, db, team.operator, team.id, patient.idPerfilMedicion, body("nadie@example.com"))
    assert not [mail for mail in mails if mail["to"] == "nadie@example.com"]  # ni se envía el enlace de confirmación
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None


def test_cambiar_el_correo_lo_reemplaza_y_renueva_el_plazo_y_quitarlo_lo_borra(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    # El plazo se había cargado «hace 6 meses»: al cambiar el correo vuelve a contar 12 meses desde hoy.
    db.execute(resultEmailStore._T.update().where(resultEmailStore._T.c.idPerfilMedicion == patient.idPerfilMedicion)
               .values(fechaExpiracionCorreo=nowForDb() + timedelta(days=180)))
    db.commit()
    resultEmail.setResultEmail(db, team.operator, team.id, patient.idPerfilMedicion, body(OTHER))
    assert resultEmailStore.recipient(db, patient.idPerfilMedicion, nowForDb()) == MAIL  # hasta que el paciente confirme, sigue el anterior
    confirmation.confirm(db, confirmationToken(mails, OTHER))
    assert resultEmailStore.recipient(db, patient.idPerfilMedicion, nowForDb()) == OTHER
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb())[1] > nowForDb() + timedelta(days=360)
    assert audits(db, "CAMBIAR_CORREO_RESULTADOS_PACIENTE")
    read = resultEmail.clearResultEmail(db, team.operator, team.id, patient.idPerfilMedicion)
    assert read.correoResultados is None and resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None
    assert audits(db, "QUITAR_CORREO_RESULTADOS_PACIENTE")


def test_solo_el_operador_responsable_administra_el_correo(db, team, patient):
    other = addOperator(db, team)
    otherUser = db.get(type(team.operator), other.idUsuarioInvitado)
    for actor in (otherUser, team.moderator, team.owner):
        with pytest.raises(Exception) as error:
            resultEmail.setResultEmail(db, actor, team.id, patient.idPerfilMedicion, body())
        assert getattr(error.value, "code", "") in ("PERMISO_INSUFICIENTE", "PACIENTE_NO_ENCONTRADO")
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None


def test_al_guardar_una_medicion_real_se_envia_sola_con_el_lugar_y_los_valores(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    mails.clear()
    done = measure(db, team.operator, patient.idPerfilMedicion, device(db, institucion=team.id), "96", 70)
    assert done.envioAutomatico == "PENDIENTE"  # el correo sale en segundo plano: la medición no espera al servidor de correo
    [sent] = mails
    assert sent["to"] == MAIL and "SpO₂" in sent["html"] and "Lugar de la medición" in sent["html"]
    [row] = deliveries(db, done.idMedicion)
    assert row.estadoEnvio == "ENVIADO" and row.correoDestino is None  # EnvioResultado no conserva el correo
    entry = audits(db, "ENVIAR_RESULTADO_MEDICION")[0]
    assert MAIL not in f"{entry.datosNuevos}{entry.observacion}" and "AUTOMATICO" in entry.datosNuevos


def test_sin_correo_o_con_el_correo_vencido_no_se_envia_nada(db, mails, team, patient):
    dev = device(db, institucion=team.id)
    done = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    mails.clear()
    assert measurements.autoSendResult(db, team.operator, done.idMedicion) is None  # sin correo cargado
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    mails.clear()  # solo el pedido de confirmación
    db.execute(resultEmailStore._T.update().where(resultEmailStore._T.c.idPerfilMedicion == patient.idPerfilMedicion)
               .values(fechaExpiracionCorreo=nowForDb() - timedelta(days=1)))
    db.commit()
    assert measurements.autoSendResult(db, team.operator, done.idMedicion) is None  # vencido: no se usa aunque no se haya purgado
    assert not mails


def test_el_envio_manual_usa_el_correo_cargado_si_no_se_escribe_otro(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    done = measure(db, team.operator, patient.idPerfilMedicion, device(db, institucion=team.id), "96", 70)
    mails.clear()
    measurements.sendResultByEmail(db, team.operator, done.idMedicion, ResultSendRequest())
    assert [m["to"] for m in mails] == [MAIL]


def test_la_baja_y_el_vencimiento_borran_el_correo(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    patients.dischargePatient(db, team.owner, team.id, patient.idPerfilMedicion)
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None  # la baja lo borra

    second = patients.createPatient(db, team.operator, team.id, patientData(nombre="luis", apellido="paz", dni="30111222"))
    loadEmail(db, mails, team, second.idPerfilMedicion, OTHER)
    assert resultEmailStore.purgeExpired(db, nowForDb()) == 0  # vigente: no se toca
    assert resultEmailStore.purgeExpired(db, nowForDb() + timedelta(days=366)) == 1  # vencido: el job lo borra
    assert resultEmailStore.stored(db, second.idPerfilMedicion, nowForDb()) is None


def _withDeviceGlucose(db, idMedicion, origin, value, mode="OXIMETRIA"):
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion)
               .values(origenGlucosa=origin, glucosaDispositivo=value, unidadGlucosa="mg/dL", modoMedicion=mode))
    db.commit()
    db.expire_all()


def test_las_pruebas_demo_tambien_se_envian_identificadas_como_simuladas(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    done = measure(db, team.operator, patient.idPerfilMedicion, device(db, institucion=team.id), "96", 70)
    _withDeviceGlucose(db, done.idMedicion, "DEMO", 114)
    mails.clear()
    assert measurements.autoSendResult(db, team.operator, done.idMedicion) == "PENDIENTE"
    [sent] = mails
    assert sent["to"] == MAIL
    assert "PRUEBA (DEMO)" in sent["html"] and "simulados" in sent["html"] and "no es una glucemia" in sent["html"]
    assert "114" in sent["html"] and "SpO₂" in sent["html"]
    assert "Glucosa experimental (estimación" not in sent["html"]  # la glucosa DEMO nunca se presenta como experimental


def test_glucosa_experimental_y_oximetria_se_envian_con_su_modo_y_sin_marca_demo(db, mails, team, patient):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    dev = device(db, institucion=team.id)
    oxi = measure(db, team.operator, patient.idPerfilMedicion, dev, "96", 70)
    glu = measure(db, team.operator, patient.idPerfilMedicion, dev, "97", 72)
    _withDeviceGlucose(db, glu.idMedicion, "EXPERIMENTAL", 118, mode="GLUCOSA_EXPERIMENTAL")
    mails.clear()
    assert measurements.autoSendResult(db, team.operator, oxi.idMedicion) == "PENDIENTE"
    assert measurements.autoSendResult(db, team.operator, glu.idMedicion) == "PENDIENTE"
    first, second = mails
    assert "Oximetría" in first["html"] and "DEMO" not in first["html"] and "Glucosa experimental" not in first["html"]
    assert "Glucosa experimental" in second["html"] and "118" in second["html"] and "no es un diagnóstico" in second["html"]
    assert "PRUEBA (DEMO)" not in second["html"]


def test_una_cuenta_individual_sigue_sin_recibir_pruebas_demo(db, mails, consumer):
    from tests.test_measurements import completeOximetry  # noqa: PLC0415
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    _withDeviceGlucose(db, done.idMedicion, "DEMO", 114)
    expectError("RESULTADO_DEMO_NO_ENVIABLE", measurements.sendResultByEmail, db, user, done.idMedicion, ResultSendRequest())


def user_mail_absent(entry):
    return MAIL not in f"{entry.datosNuevos}{entry.observacion}"


class Deferred:
    """Ejecutor que guarda las tareas en vez de correrlas: así se ve qué ocurre antes de que el correo salga (segundo plano)."""

    def __init__(self):
        self.tasks = []

    def submit(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def run(self):
        while self.tasks:
            fn, args, kwargs = self.tasks.pop(0)
            fn(*args, **kwargs)


def test_el_guardado_no_espera_al_correo_del_resultado(db, mails, team, patient, monkeypatch):
    loadEmail(db, mails, team, patient.idPerfilMedicion)
    mails.clear()
    queue = Deferred()
    monkeypatch.setattr(emailService, "_executor", queue)
    done = measure(db, team.operator, patient.idPerfilMedicion, device(db, institucion=team.id), "96", 70)
    assert done.envioAutomatico == "PENDIENTE" and not mails  # la respuesta vuelve sin esperar al servidor de correo
    [row] = deliveries(db, done.idMedicion)
    assert row.estadoEnvio == "PENDIENTE" and row.correoDestino == MAIL  # el correo queda solo mientras sale
    assert measurements.getMeasurement(db, team.operator, done.idMedicion).envioResultadoEstado == "PENDIENTE"
    queue.run()  # lo que hace el hilo auxiliar
    assert [m["to"] for m in mails] == [MAIL]
    [row] = deliveries(db, done.idMedicion)
    assert row.estadoEnvio == "ENVIADO" and row.correoDestino is None
    assert measurements.getMeasurement(db, team.operator, done.idMedicion).envioResultadoEstado == "ENVIADO"
    [entry] = [a for a in audits(db, "ENVIAR_RESULTADO_MEDICION") if a.idRegistro == done.idMedicion]
    assert "AUTOMATICO" in str(entry.datosNuevos) and user_mail_absent(entry)


def test_el_correo_de_confirmacion_sale_en_segundo_plano(db, mails, team, patient, monkeypatch):
    mails.clear()
    queue = Deferred()
    monkeypatch.setattr(emailService, "_executor", queue)
    read = resultEmail.setResultEmail(db, team.operator, team.id, patient.idPerfilMedicion, body())
    assert read.correoResultadosPendiente.endswith("@example.com") and not mails  # la respuesta no espera al correo
    assert resultEmailStore.stored(db, patient.idPerfilMedicion, nowForDb()) is None  # y sigue sin guardarse hasta la confirmación
    queue.run()
    assert [m["to"] for m in mails] == [MAIL]
    [entry] = audits(db, "SOLICITAR_CONFIRMACION_CORREO_RESULTADOS")
    assert entry.resultado == "EXITO" and MAIL not in f"{entry.datosNuevos}{entry.observacion}"


def test_un_fallo_del_correo_de_confirmacion_queda_en_la_auditoria(db, mails, team, patient, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("smtp caído")

    mails.clear()
    monkeypatch.setattr(emailService.sender, "sendHtmlEmail", broken)
    resultEmail.setResultEmail(db, team.operator, team.id, patient.idPerfilMedicion, body())  # no levanta: el envío es en segundo plano
    [entry] = audits(db, "SOLICITAR_CONFIRMACION_CORREO_RESULTADOS")
    assert entry.resultado != "EXITO" and not mails
