# Autorización del dispositivo según su contexto: individual (pool sin institución), institucional propio y institucional ajeno.
#
#     python -m pytest tests/test_device_context_authority.py -v
#
# Una cuenta individual conecta, se registra y mide con su Arduino SIN operador institucional; la autoridad de un operador solo rige para un
# dispositivo que pertenece a una institución. Un dispositivo de otra institución sigue bloqueado y no se reasigna. Datos sintéticos, SQLite temporal.

from sqlalchemy import select

from app.acquisition.telemetry import ABANDON_SECONDS
from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.measurement import Measurement
from app.schemas.acquisition import DeviceConnectConfirm
from app.services import deviceConnection
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401
from tests.test_bridge_command_authority import COMMAND, CONTROL, refused
from tests.test_bridge_diagnostics import steps
from tests.test_device_connection import ARDUINO, connect, link, makeDevice
from tests.test_groups import family  # noqa: F401 - fixture
from tests.test_institution_patients import patientData
from tests.test_institutions import team  # noqa: F401
from tests.test_matrices import north  # noqa: F401
from tests.test_measurements import consumer, device, expectError  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, freshHub, startFor  # noqa: F401


def owner(db, code=CODE):
    db.expire_all()
    return db.scalar(select(Device.idInstitucionAsignada).where(Device.codigoDispositivo == code))


# --- Individual -----------------------------------------------------------------------------------------------------------------


def test_individual_con_dispositivo_propio_conecta_ordena_y_mide_sin_operador(db, mails, consumer, bridge, api):
    user, profileId = consumer
    bridge.seconds(17)  # el dispositivo se registra solo, sin institución
    assert owner(db) is None
    readiness = telemetryService.readiness(db, user, profileId)
    assert readiness["listo"] and readiness["ordenesPuente"] == {"contexto": "PERSONAL", "permitido": True, "motivo": None}
    assert steps(readiness)["ASOCIADO"]["estado"] == "OK"
    assert api(user).post(CONTROL).status_code == 200  # «Usar dispositivo»
    response = api(user).post(COMMAND, json={"accion": "PAUSAR"})
    assert response.status_code == 200, response.text
    assert not refused(db)


def test_individual_sin_dispositivo_vinculado_todavia_no_pide_un_operador(db, mails, consumer, bridge):
    """Nada conectado ni registrado: el diagnóstico queda pendiente, sin exigir autoridad institucional."""
    user, profileId = consumer
    readiness = telemetryService.readiness(db, user, profileId)
    assert not readiness["listo"] and readiness["dispositivo"] is None
    assert readiness["ordenesPuente"]["permitido"] is True


def test_la_medicion_individual_se_guarda_en_el_perfil_de_quien_mide(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    session = startFor(db, user, profileId, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)
    assert saved.estadoMedicion == "COMPLETADA" and session.idMedicion == saved.idMedicion
    db.expire_all()
    assert db.get(Measurement, saved.idMedicion).idPerfilMedicion == profileId


def test_una_cuenta_no_mide_en_el_perfil_de_otra_aunque_comparta_el_dispositivo(db, mails, consumer, bridge):
    """Compartir el equipo no comparte historiales: cada cuenta mide solo su propio perfil."""
    user, profileId = consumer
    other = makeUser(db, email="otra@example.com", usuario="otra")
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    expectError("PERFIL_NO_ENCONTRADO", startFor, db, other, profileId, dev)


# --- Institucional --------------------------------------------------------------------------------------------------------------


def test_operador_de_la_institucion_duena_conserva_su_autorizacion(db, mails, team, bridge):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    authority, _ = telemetryService.bridgeAuthority(db, team.operator)
    assert authority == {"contexto": "INSTITUCIONAL_PROPIA", "permitido": True, "motivo": None}


def test_individual_frente_a_un_dispositivo_de_una_institucion_sigue_bloqueado_con_su_explicacion(db, mails, consumer, team, bridge, api, deviceMode):
    deviceMode(False)  # modo restringido por asignación (DEC-01)
    user, profileId = consumer
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)  # físicamente conectado, con telemetría
    readiness = telemetryService.readiness(db, user, profileId)
    authority = readiness["ordenesPuente"]
    assert authority["contexto"] == "INSTITUCIONAL_AJENA" and authority["permitido"] is False
    assert "una cuenta individual" in authority["motivo"] and "operador de la institución" not in authority["motivo"]
    assert not readiness["listo"] and steps(readiness)["ASOCIADO"]["estado"] == "ERROR"
    assert "administración" not in steps(readiness)["ASOCIADO"]["solucion"]
    response = api(user).post(COMMAND, json={"accion": "DETENER"})
    assert response.status_code == 403 and response.json()["codigo"] == "PERMISO_INSUFICIENTE"
    assert len(refused(db)) == 1  # intento auditado
    expectError("DISPOSITIVO_NO_DISPONIBLE", startFor, db, user, profileId, db.scalar(select(Device)))
    assert owner(db) == team.id  # nunca se reasigna ni se libera solo


def test_operador_de_otra_institucion_conserva_el_mensaje_institucional(db, mails, team, north, bridge):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    authority, _ = telemetryService.bridgeAuthority(db, north.operator)
    assert authority["contexto"] == "INSTITUCIONAL_AJENA" and not authority["permitido"]
    assert authority["motivo"].startswith("Solo un operador de la institución")


# --- Interruptor transitorio: un único equipo compartido ------------------------------------------------------------------------


def test_con_el_interruptor_la_cuenta_individual_mide_con_el_equipo_de_la_institucion_sin_cambiar_su_propiedad(
        db, mails, consumer, team, bridge, api, deviceMode):
    deviceMode(True)
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    readiness = telemetryService.readiness(db, user, profileId)
    assert readiness["listo"] and readiness["ordenesPuente"]["permitido"] is True
    assert api(user).post(CONTROL).status_code == 200
    assert api(user).post(COMMAND, json={"accion": "PAUSAR"}).status_code == 200
    session = startFor(db, user, profileId, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)
    assert saved.estadoMedicion == "COMPLETADA" and session.idMedicion == saved.idMedicion
    assert owner(db) == team.id  # la propiedad no cambia
    deviceMode(False)  # modo restringido: vuelve el bloqueo
    assert telemetryService.readiness(db, user, profileId)["ordenesPuente"]["permitido"] is False


# --- Modo compartido (DEC-01, ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE=true) ------------------------------------------------------
# Un único equipo experimental lo usan cuentas individuales, integrantes de grupos familiares y operadores de la institución titular.
# Compartir el hardware NO comparte mediciones, datos personales ni el control de una sesión ajena.


def code(fn, *args):
    try:
        fn(*args)
    except AuthError as error:
        return error.code
    return "OK"


def measure(db, bridge, actor, profileId, dev):
    session = startFor(db, actor, profileId, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, actor)
    assert saved.estadoMedicion == "COMPLETADA" and saved.idMedicion == session.idMedicion
    return saved


def operatorReady(db, team, dev):
    """Paciente de la operadora y confirmación manual del Arduino (el puente de prueba no informa un ID propio)."""
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=dev.idDispositivo))
    return patient


def test_compartido_individual_familiar_y_operador_miden_con_el_mismo_equipo_cada_uno_en_su_perfil(
        db, mails, consumer, family, team, bridge, deviceMode):
    deviceMode(True)
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    mine = measure(db, bridge, user, profileId, dev)  # cuenta individual
    betoProfile = measurements.getOwnProfile(db, family.beto).idPerfilMedicion
    beto = measure(db, bridge, family.beto, betoProfile, dev)  # integrante de un grupo familiar
    patient = operatorReady(db, team, dev)
    clinical = measure(db, bridge, team.operator, patient.idPerfilMedicion, dev)  # operadora de la institución titular
    assert (mine.idPerfilMedicion, beto.idPerfilMedicion, clinical.idPerfilMedicion) == (profileId, betoProfile, patient.idPerfilMedicion)
    assert owner(db) == team.id  # el uso compartido no transfiere la titularidad
    # Ninguna cuenta lee las mediciones de otro contexto.
    assert code(measurements.getMeasurement, db, team.operator, mine.idMedicion) == "MEDICION_NO_ENCONTRADA"
    assert code(measurements.getMeasurement, db, user, beto.idMedicion) == "MEDICION_NO_ENCONTRADA"
    assert code(measurements.getMeasurement, db, family.beto, clinical.idMedicion) == "MEDICION_NO_ENCONTRADA"
    assert code(measurements.getMeasurement, db, user, clinical.idMedicion) == "MEDICION_NO_ENCONTRADA"


def test_compartido_nadie_interrumpe_ni_ve_la_sesion_activa_de_otra_cuenta(db, mails, consumer, team, bridge, api, deviceMode):
    deviceMode(True)
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    session = startFor(db, user, profileId, dev)
    other = makeUser(db, email="otra@example.com", usuario="otra")
    otherProfile = measurements.getOwnProfile(db, other).idPerfilMedicion
    patient = operatorReady(db, team, dev)
    for intruder, intruderProfile in ((other, otherProfile), (team.operator, patient.idPerfilMedicion)):
        snap = telemetryService.status(db, intruder)
        assert snap["ocupado"] is True and snap.get("lectura") is None  # ni las lecturas de quien mide
        assert code(startFor, db, intruder, intruderProfile, dev) == "DISPOSITIVO_EN_USO"
        assert code(telemetryService.saveSession, db, intruder) == "DISPOSITIVO_EN_USO"
        assert code(telemetryService.cancelSession, db, intruder) == "DISPOSITIVO_EN_USO"
        for payload in ({"accion": "DETENER"}, {"accion": "REINICIAR"}, {"accion": "PAUSAR"},
                        {"accion": "CONFIGURAR", "puerto": "COM4", "medio": "BLUETOOTH"}):
            assert api(intruder).post(COMMAND, json=payload).json()["codigo"] == "DISPOSITIVO_EN_USO"  # el control es de otra cuenta
        assert api(intruder).post(CONTROL).json()["codigo"] == "DISPOSITIVO_EN_USO"  # tampoco puede tomarlo
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)  # la sesión de su dueña sigue intacta
    assert saved.idMedicion == session.idMedicion and saved.estadoMedicion == "COMPLETADA"
    measure(db, bridge, team.operator, patient.idPerfilMedicion, dev)  # liberado, la operadora lo usa enseguida


def test_compartido_una_sesion_abandonada_se_libera_y_otra_cuenta_toma_el_equipo(db, mails, consumer, team, bridge, clock, deviceMode):
    deviceMode(True)
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    abandoned = startFor(db, user, profileId, dev)
    clock.advance(ABANDON_SECONDS + 1)  # la dueña dejó de consultar (cerró la pestaña o perdió la conexión)
    bridge.seconds(1)
    patient = operatorReady(db, team, dev)
    taken = startFor(db, team.operator, patient.idPerfilMedicion, dev)  # libera la reserva vencida y toma el equipo
    assert taken.idMedicion != abandoned.idMedicion
    db.expire_all()
    assert db.get(Measurement, abandoned.idMedicion).estadoMedicion == "CANCELADA"  # la abandonada se cierra, no se reasigna
    assert code(telemetryService.saveSession, db, user) == "DISPOSITIVO_EN_USO"  # la dueña anterior ya no controla el equipo


def test_compartido_vincular_el_equipo_a_la_institucion_no_lo_quita_de_las_cuentas_individuales(db, mails, team, consumer, bridge, deviceMode):
    deviceMode(True)
    user, profileId = consumer
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    startFor(db, user, profileId, shared)
    telemetryService.cancelSession(db, user)
    link(db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True)
    connect(bridge)
    session = startFor(db, user, profileId, shared)  # con TRUE la cuenta individual lo sigue usando
    assert session.idPerfilMedicion == profileId and owner(db, ARDUINO) == team.id


def test_compartido_operadora_de_otra_institucion_mide_a_su_paciente_sin_cambiar_la_titularidad(db, mails, team, north, bridge, deviceMode):
    dev = device(db, institucion=team.id, codigo=CODE)  # el único equipo, asignado a la institución «team»
    bridge.seconds(1)
    patient = patients.createPatient(db, north.operator, north.id, patientData())
    deviceMode(False)  # restringido: la operadora de otra institución no lo usa ni lo ve
    assert code(deviceConnection.confirm, db, north.operator,
                DeviceConnectConfirm(idInstitucion=north.id, idDispositivo=dev.idDispositivo)) == "DISPOSITIVO_NO_ENCONTRADO"
    assert code(startFor, db, north.operator, patient.idPerfilMedicion, dev) == "DISPOSITIVO_NO_DISPONIBLE"
    deviceMode(True)  # compartido: la usa sin vincularla ni cambiar su titularidad
    deviceConnection.confirm(db, north.operator, DeviceConnectConfirm(idInstitucion=north.id, idDispositivo=dev.idDispositivo))
    readiness = telemetryService.readiness(db, north.operator, None, north.id)
    assert steps(readiness)["REGISTRADO"]["estado"] == "OK" and readiness["ordenesPuente"]["contexto"] == "COMPARTIDO"
    saved = measure(db, bridge, north.operator, patient.idPerfilMedicion, dev)
    assert saved.idPerfilMedicion == patient.idPerfilMedicion and owner(db) == team.id
    assert code(measurements.getMeasurement, db, team.operator, saved.idMedicion) == "MEDICION_NO_ENCONTRADA"  # ni la titular la ve
    teamPatient = operatorReady(db, team, dev)
    clinical = measure(db, bridge, team.operator, teamPatient.idPerfilMedicion, dev)
    assert code(measurements.getMeasurement, db, north.operator, clinical.idMedicion) == "MEDICION_NO_ENCONTRADA"

