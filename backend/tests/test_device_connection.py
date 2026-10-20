# Registro de dispositivos desde la conexión de un operador: un único inventario institucional, alimentado por el flujo de conexión.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_device_connection.py -v
#
# Sin Arduino ni puerto COM: `FakeBridge` (tests/test_telemetry.py) hace lo que el puente real —latidos y líneas hacia ingest()— y
# `idLine` imprime la línea de identificación EXACTA que escribe el firmware (`GLUCOLUME,ID=<uuid>,SENSOR=MAX30100,FW=<ver>,SR=50`).
# Escenarios: 1 primer operador registra · 2 segundo operador reconoce · 3 otro puerto COM · 4 desconexión y reconexión · 5 el propietario
# lo consulta · 6 el propietario lo edita y cambia su estado · 7 existe pero está desconectado · 8 el puerto existe y el Arduino no responde ·
# 9 dispositivo de otra institución · 10 simultaneidad (alta y uso).

import uuid

import pytest
from sqlalchemy import func, select

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.device import Device
from app.schemas.acquisition import DeviceConnectConfirm, DeviceConnectLink, DeviceConnectRegister
from app.schemas.device import DeviceEditRequest
from app.services import device as devices
from app.services import deviceConnection
from app.services import institutionPatients as patients
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import freshLookupLimiter, relationOf, team  # noqa: F401 - fixtures
from tests.test_measurements import consumer  # noqa: F401 - fixture
from tests.test_measurements import device as makeDevice
from tests.test_telemetry import CODE, FakeBridge, bridge, clock, freshHub, line, startFor  # noqa: F401 - fixtures

ARDUINO = "3f2a9c1e-5b7d-4e21-8a9f-0123456789ab"


def idLine(code=ARDUINO, firmware="1.1.0") -> str:
    return f"GLUCOLUME,ID={code},SENSOR=MAX30100,FW={firmware},SR=50"


def connect(bridge, code=ARDUINO, seconds=1):
    """El Arduino se comunica: informa su ID persistente y sigue enviando lecturas."""
    bridge.send([idLine(code)])
    bridge.seconds(seconds)


def register(db, actor, team_, nombre="Arduino Consultorio 1"):
    return deviceConnection.register(db, actor, DeviceConnectRegister(idInstitucion=team_.id, nombre=nombre))


def inventory(db):
    db.expire_all()
    return db.scalars(select(Device)).all()


def expectCode(code, fn, *args, **kwargs):
    with pytest.raises(AuthError) as raised:
        fn(*args, **kwargs)
    assert raised.value.code == code, raised.value.code


# --- 1. Primera conexión: el operador registra un Arduino nuevo -----------------------------------------------------------------


def test_primer_operador_conecta_y_registra_un_arduino_nuevo(db, mails, team, bridge):
    connect(bridge)
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert (seen["nivel"], seen["situacion"], seen["codigo"]) == ("FISICA", "NO_REGISTRADO", ARDUINO)
    assert seen["puedeRegistrar"] and seen["dispositivo"] is None and seen["institucion"]["nombre"] == team.institution.nombre
    # Reconocerlo no lo registra: antes del alta el inventario sigue vacío.
    assert inventory(db) == []
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is False and ready["bloqueo"] == "REGISTRADO"

    result = register(db, team.operator, team)
    assert result["creado"] is True
    stored = devices.findByCode(db, ARDUINO)
    owner = relationOf(db, team, team.owner).idInstitucionUsuario
    assert (stored.nombre, stored.idInstitucionAsignada, stored.estado, stored.modeloSensor) == ("Arduino Consultorio 1", team.id, "OPERATIVO", "MAX30100")
    assert stored.idInstitucionUsuarioResponsable == owner, "queda a cargo del propietario, no del operador"
    assert stored.versionFirmware == "1.1.0" and stored.fechaAsignacionInstitucional is not None
    assert result["identificacion"]["situacion"] == "DE_LA_INSTITUCION" and result["identificacion"]["dispositivo"]["nombre"] == "Arduino Consultorio 1"

    # Quién lo registró y cuándo queda en la auditoría de la institución.
    [event] = [a for a in audits(db, "REGISTRAR_DISPOSITIVO")]
    assert event.idUsuario == team.operator.idUsuario and event.idInstitucion == team.id and event.fechaHora is not None
    assert '"CONEXION_OPERADOR"' in event.datosNuevos and '"BLUETOOTH"' in event.datosNuevos

    # Y puede continuar hacia la medición: sin elegir paciente ya está listo, y con uno inicia la sesión.
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is True and [s["estado"] for s in ready["pasos"]] == ["OK"] * len(ready["pasos"])
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    started = startFor(db, team.operator, patient.idPerfilMedicion, stored)
    assert started.estadoMedicion == "ADQUIRIENDO"


def test_el_registro_no_asocia_el_dispositivo_ni_a_un_operador_ni_a_un_paciente(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    stored = devices.findByCode(db, ARDUINO)
    assert stored.idInstitucionUsuarioResponsable != relationOf(db, team, team.operator).idInstitucionUsuario
    # Sin sesión de medición no hay nada asociado a ningún paciente.
    assert hub.session is None


# --- 2. Un segundo operador conecta el mismo Arduino ---------------------------------------------------------------------------


def test_segundo_operador_reconoce_el_mismo_dispositivo_sin_duplicar(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team, "Arduino Consultorio 1")
    second = addOperator(db, team)
    other = db.get(type(second), second.idInstitucionUsuario)
    secondUser = db.get(__import__("app.models.user", fromlist=["User"]).User, other.idUsuarioInvitado)

    seen = deviceConnection.identification(db, secondUser, team.id)
    assert seen["situacion"] == "DE_LA_INSTITUCION" and seen["dispositivo"]["nombre"] == "Arduino Consultorio 1" and not seen["puedeRegistrar"]
    again = register(db, secondUser, team, "Otro nombre")  # «Registrar» del segundo operador no crea otro: devuelve el existente
    assert again["creado"] is False and again["identificacion"]["dispositivo"]["nombre"] == "Arduino Consultorio 1"
    confirmed = deviceConnection.confirm(db, secondUser, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=seen["dispositivo"]["idDispositivo"]))
    assert confirmed["identificacion"]["usable"] is True
    assert len(inventory(db)) == 1 and len(audits(db, "REGISTRAR_DISPOSITIVO")) == 1

    patient = patients.createPatient(db, secondUser, team.id, patientData())
    assert startFor(db, secondUser, patient.idPerfilMedicion, devices.findByCode(db, ARDUINO)).estadoMedicion == "ADQUIRIENDO"


# --- 3. El mismo Arduino en otro puerto COM ------------------------------------------------------------------------------------


def test_cambiar_de_puerto_no_crea_otro_dispositivo_ni_asume_que_es_el_mismo(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    bridge.port, bridge.medium, bridge.baud = "COM7", "USB", 115200
    bridge.seconds(1)  # otra conexión y todavía sin ID: no se da por hecho que sea el mismo Arduino
    assert hub.identity()["nivel"] == "DECLARADA"
    unsure = deviceConnection.identification(db, team.operator, team.id)
    assert unsure["situacion"] == "IDENTIDAD_NO_CONFIRMADA" and unsure["dispositivo"] is None and unsure["requiereConfirmacion"]
    assert [d.codigoDispositivo for d in inventory(db)] == [ARDUINO]  # y no se inventó ningún dispositivo con el código del puente
    bridge.send([idLine()])  # el Arduino se identifica por la nueva conexión
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["situacion"] == "DE_LA_INSTITUCION" and seen["medio"] == "USB"
    assert register(db, team.operator, team)["creado"] is False
    assert len(inventory(db)) == 1


def test_otro_arduino_en_el_mismo_puerto_es_otro_dispositivo(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team, "Arduino A")
    other = "9b1c0a47-7a1e-4d52-9f0b-aaaaaaaaaaaa"
    bridge.send([idLine(other)])
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["codigo"] == other and seen["situacion"] == "NO_REGISTRADO"
    register(db, team.operator, team, "Arduino B")
    assert sorted(d.nombre for d in inventory(db)) == ["Arduino A", "Arduino B"]


# --- 4. Desconexión y reconexión ----------------------------------------------------------------------------------------------


def test_desconectar_no_elimina_el_registro_y_al_volver_se_reconoce(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    bridge.send([], state="DESCONECTADO")
    off = deviceConnection.identification(db, team.operator, team.id)
    assert off["situacion"] == "SIN_COMUNICACION" and off["nivel"] == "NINGUNA" and off["puedeRegistrar"] is False
    assert len(inventory(db)) == 1 and devices.findByCode(db, ARDUINO).estado == "OPERATIVO"
    connect(bridge)
    back = deviceConnection.identification(db, team.operator, team.id)
    assert back["situacion"] == "DE_LA_INSTITUCION" and back["dispositivo"]["nombre"] == "Arduino Consultorio 1"
    assert len(inventory(db)) == 1


# --- 5 y 6. El propietario lo consulta, lo edita y cambia su estado ---------------------------------------------------------------


def test_el_propietario_ve_el_dispositivo_con_quien_lo_registro_y_lo_administra(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    scope = devices.institutionScope(db, team.owner, team.id)
    page = devices.listDevices(db, scope, busqueda="consultorio")
    assert [d.nombre for d in page.items] == ["Arduino Consultorio 1"] and devices.summary(db, scope).total == 1
    detail = devices.getDevice(db, scope, page.items[0].idDispositivo)
    assert detail.registro.origen == "CONEXION_OPERADOR" and detail.registro.nombre == team.operator.nombre and detail.registro.fecha is not None
    assert detail.permisos.puedeEditar and detail.permisos.puedeCambiarEstado and detail.responsable is not None

    renamed = devices.editDevice(db, scope, detail.idDispositivo, DeviceEditRequest(nombre="Consultorio 1 (norte)"))
    assert renamed.nombre == "Consultorio 1 (norte)"
    # Cambia el estado administrativo: operativo ≠ conectado, y en mantenimiento no se puede medir aunque esté conectado.
    devices.changeState(db, scope, detail.idDispositivo, "EN_MANTENIMIENTO", "revisión")
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["nivel"] == "FISICA" and seen["dispositivo"]["estado"] == "EN_MANTENIMIENTO" and seen["usable"] is False
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is False and ready["bloqueo"] == "ASOCIADO"
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    expectCode("DISPOSITIVO_NO_DISPONIBLE", startFor, db, team.operator, patient.idPerfilMedicion, devices.findByCode(db, ARDUINO))
    devices.changeState(db, scope, detail.idDispositivo, "OPERATIVO", None)
    assert telemetryService.readiness(db, team.operator, None, team.id)["listo"] is True


def test_el_operador_no_cambia_titularidad_ni_estado_ni_edita_el_inventario(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    stored = devices.findByCode(db, ARDUINO)
    scope = devices.institutionScope(db, team.operator, team.id)
    for fn, args in ((devices.editDevice, (DeviceEditRequest(nombre="x"),)), (devices.changeState, ("FUERA_DE_SERVICIO", None)),
                     (devices.changeResponsible, (relationOf(db, team, team.operator).idInstitucionUsuario,)), (devices.unassign, ()),
                     (devices.decommission, ())):
        expectCode("PERMISO_INSUFICIENTE", fn, db, scope, stored.idDispositivo, *args)


# --- 7. Está en el inventario pero desconectado ---------------------------------------------------------------------------------


def test_un_dispositivo_registrado_y_desconectado_sigue_operativo_pero_no_esta_disponible(db, mails, team, bridge):
    makeDevice(db, institucion=team.id, codigo=ARDUINO)
    seen = deviceConnection.identification(db, team.operator, team.id)  # el puente ni siquiera está en ejecución
    assert seen["situacion"] == "SIN_COMUNICACION"
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is False and ready["bloqueo"] == "PUENTE"
    assert devices.findByCode(db, ARDUINO).estado == "OPERATIVO"
    bridge.send([], state="DESCONECTADO")
    assert telemetryService.readiness(db, team.operator, None, team.id)["listo"] is False


# --- 8. El puerto existe pero el Arduino no responde -------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["puerto abierto sin datos", "puerto con error"])
def test_sin_comunicacion_verificable_no_se_registra_nada(db, mails, team, bridge, state):
    if state == "puerto con error":
        bridge.send([], state="REINTENTANDO", attempt=2, error="El dispositivo no responde")
    else:
        bridge.send([])  # el puerto abre, pero no llegan lecturas ni ID
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["situacion"] == "SIN_COMUNICACION" and seen["puedeRegistrar"] is False
    expectCode("DISPOSITIVO_NO_CONECTADO", register, db, team.operator, team)
    assert inventory(db) == []


def test_el_id_que_informa_un_arduino_que_ya_no_responde_no_alcanza(db, mails, team, bridge, clock):
    connect(bridge)
    clock.advance(30)  # el Arduino dejó de enviar: la telemetría vence
    bridge.send([])
    assert deviceConnection.identification(db, team.operator, team.id)["situacion"] == "SIN_COMUNICACION"
    expectCode("DISPOSITIVO_NO_CONECTADO", register, db, team.operator, team)


# --- 9. Aislamiento entre instituciones ---------------------------------------------------------------------------------------


def test_un_dispositivo_de_otra_institucion_no_se_usa_ni_se_apropia(db, mails, team, bridge):
    other, _, _ = otherInstitution(db)
    foreign = makeDevice(db, institucion=other.idInstitucion, codigo=ARDUINO)
    connect(bridge)
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["situacion"] == "DE_OTRA_INSTITUCION" and seen["dispositivo"] is None and not seen["puedeRegistrar"] and not seen["usable"]
    assert "otra institución" in seen["motivoNoDisponible"] and "nombre" not in str(seen["dispositivo"])
    expectCode("DISPOSITIVO_NO_DISPONIBLE", register, db, team.operator, team)
    expectCode("DISPOSITIVO_NO_ENCONTRADO", deviceConnection.confirm, db, team.operator,
               DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=foreign.idDispositivo))
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    expectCode("DISPOSITIVO_NO_DISPONIBLE", startFor, db, team.operator, patient.idPerfilMedicion, foreign)
    stored = reload(db, Device, foreign.idDispositivo)
    assert stored.idInstitucionAsignada == other.idInstitucion and len(inventory(db)) == 1


def test_un_operador_no_registra_en_instituciones_ajenas_ni_otros_roles(db, mails, team, bridge):
    other, _, _ = otherInstitution(db)
    connect(bridge)
    expectCode("INSTITUCION_NO_ENCONTRADA", deviceConnection.register, db, team.operator, DeviceConnectRegister(idInstitucion=other.idInstitucion, nombre="x"))
    expectCode("INSTITUCION_NO_ENCONTRADA", deviceConnection.identification, db, team.operator, other.idInstitucion)
    for actor in (team.owner, team.moderator):  # administran el inventario por su pantalla; no conectan ni miden
        expectCode("PERMISO_INSUFICIENTE", deviceConnection.register, db, actor, DeviceConnectRegister(idInstitucion=team.id, nombre="x"))
    assert inventory(db) == []


def test_un_dispositivo_sin_institucion_no_se_adjudica_solo_ni_se_mide_con_pacientes_hasta_vincularlo(db, mails, team, bridge):
    shared = makeDevice(db, codigo=ARDUINO)  # p. ej. el que una cuenta individual ya verificó
    connect(bridge)
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["situacion"] == "SIN_INSTITUCION" and seen["puedeVincular"] and not seen["puedeRegistrar"]
    assert seen["usable"] is False and "vinculalo" in seen["motivoNoDisponible"]  # existe, pero no es del inventario de la institución
    expectCode("DISPOSITIVO_NO_DISPONIBLE", register, db, team.operator, team)  # registrar no lo duplica ni lo adjudica
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None and len(inventory(db)) == 1
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is False and ready["bloqueo"] == "REGISTRADO"
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    expectCode("DISPOSITIVO_NO_DISPONIBLE", startFor, db, team.operator, patient.idPerfilMedicion, shared)


# --- Vincular a la institución un dispositivo existente sin institución (confirmación explícita) ------------------------------


def link(db, actor, team_, idDispositivo, **extra):
    return deviceConnection.link(db, actor, DeviceConnectLink(idInstitucion=team_.id, idDispositivo=idDispositivo, **extra))


def test_vincular_exige_confirmacion_explicita_y_deja_el_dispositivo_en_el_inventario_del_propietario(db, mails, team, bridge):
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    expectCode("CONFIRMACION_REQUERIDA", link, db, team.operator, team, shared.idDispositivo)
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None
    result = link(db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True, nombre="Arduino Consultorio 1")
    assert result["vinculado"] is True and result["identificacion"]["situacion"] == "DE_LA_INSTITUCION" and result["identificacion"]["usable"]
    stored = reload(db, Device, shared.idDispositivo)
    owner = relationOf(db, team, team.owner).idInstitucionUsuario
    assert (stored.idInstitucionAsignada, stored.idInstitucionUsuarioResponsable, stored.nombre) == (team.id, owner, "Arduino Consultorio 1")
    assert stored.fechaAsignacionInstitucional is not None and len(inventory(db)) == 1  # el mismo registro: no se duplica
    [event] = audits(db, "VINCULAR_DISPOSITIVO_INSTITUCION")
    assert event.idUsuario == team.operator.idUsuario and event.idInstitucion == team.id
    assert '"idInstitucion": null' in event.datosPrevios and '"confirmacionExplicita": true' in event.datosNuevos
    # El propietario lo ve en su inventario, con quién lo vinculó.
    scope = devices.institutionScope(db, team.owner, team.id)
    detail = devices.getDevice(db, scope, shared.idDispositivo)
    assert detail.registro.origen == "VINCULACION_OPERADOR" and detail.registro.nombre == team.operator.nombre
    assert devices.summary(db, scope).total == 1
    # Ya puede medir a un paciente; y repetir la vinculación es idempotente.
    assert telemetryService.readiness(db, team.operator, None, team.id)["listo"] is True
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    assert startFor(db, team.operator, patient.idPerfilMedicion, stored).estadoMedicion == "ADQUIRIENDO"
    assert link(db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True)["vinculado"] is False
    assert len(audits(db, "VINCULAR_DISPOSITIVO_INSTITUCION")) == 1


def test_vincular_conserva_las_mediciones_anteriores_y_lo_quita_de_las_cuentas_individuales(db, mails, team, consumer, bridge, deviceMode):
    deviceMode(False)  # modo restringido: al vincularlo deja de estar disponible para las cuentas individuales (con TRUE lo siguen usando)
    user, profileId = consumer
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    startFor(db, user, profileId, shared)
    telemetryService.cancelSession(db, user)
    scope = devices.institutionScope(db, team.owner, team.id)
    link(db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True)
    assert devices.getDevice(db, scope, shared.idDispositivo).medicionesRegistradas == 1  # el historial no se pierde
    expectCode("DISPOSITIVO_NO_DISPONIBLE", startFor, db, user, profileId, shared)  # ya no es de las cuentas individuales
    assert '"medicionesPrevias": 1' in audits(db, "VINCULAR_DISPOSITIVO_INSTITUCION")[0].datosNuevos


def test_vincular_no_toca_dispositivos_de_otras_instituciones_ni_descomisionados(db, mails, team, bridge):
    other, _, _ = otherInstitution(db)
    foreign = makeDevice(db, institucion=other.idInstitucion, codigo=ARDUINO)
    connect(bridge)
    expectCode("DISPOSITIVO_NO_ENCONTRADO", link, db, team.operator, team, foreign.idDispositivo, confirmaVinculacion=True)
    assert reload(db, Device, foreign.idDispositivo).idInstitucionAsignada == other.idInstitucion
    retiredCode = "9b1c0a47-7a1e-4d52-9f0b-bbbbbbbbbbbb"
    retired = makeDevice(db, estado="BAJA", codigo=retiredCode)
    bridge.send([idLine(retiredCode)])
    expectCode("DISPOSITIVO_DESCOMISIONADO", link, db, team.operator, team, retired.idDispositivo, confirmaVinculacion=True)
    assert reload(db, Device, retired.idDispositivo).idInstitucionAsignada is None


def test_vincular_solo_el_dispositivo_conectado_y_con_comunicacion_verificada(db, mails, team, bridge):
    shared = makeDevice(db, codigo=ARDUINO)
    unrelated = makeDevice(db, codigo="GL-OTRO")
    expectCode("DISPOSITIVO_NO_CONECTADO", link, db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True)  # sin Arduino
    connect(bridge)
    expectCode("DISPOSITIVO_NO_COINCIDE", link, db, team.operator, team, unrelated.idDispositivo, confirmaVinculacion=True)
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None
    assert reload(db, Device, unrelated.idDispositivo).idInstitucionAsignada is None


def test_vincular_roles_e_instituciones_ajenas(db, mails, team, bridge):
    other, _, _ = otherInstitution(db)
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    for actor in (team.owner, team.moderator):
        expectCode("PERMISO_INSUFICIENTE", deviceConnection.link, db, actor, DeviceConnectLink(
            idInstitucion=team.id, idDispositivo=shared.idDispositivo, confirmaVinculacion=True))
    expectCode("INSTITUCION_NO_ENCONTRADA", deviceConnection.link, db, team.operator, DeviceConnectLink(
        idInstitucion=other.idInstitucion, idDispositivo=shared.idDispositivo, confirmaVinculacion=True))
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None


def test_dos_instituciones_vinculan_a_la_vez_solo_una_lo_obtiene(db, mails, team, bridge):
    from sqlalchemy import update

    other, _, _ = otherInstitution(db)
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    stale = devices.findByCode(db, ARDUINO)  # el segundo operador lo leyó cuando todavía no tenía institución
    assert stale.idInstitucionAsignada is None
    db.execute(update(Device).where(Device.idDispositivo == shared.idDispositivo).values(idInstitucionAsignada=other.idInstitucion)
               .execution_options(synchronize_session=False))  # …y la otra institución se lo adelantó
    expectCode("DISPOSITIVO_NO_DISPONIBLE", devices.linkToInstitution, db, team.operator, team.id, stale, nombre=None, medio="USB",
               identidad="FISICA")
    db.rollback()
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None  # la vinculación fallida no dejó nada a medias


def test_no_se_vincula_si_otra_cuenta_esta_midiendo_con_el_dispositivo(db, mails, team, consumer, bridge):
    user, profileId = consumer
    shared = makeDevice(db, codigo=ARDUINO)
    connect(bridge)
    startFor(db, user, profileId, shared)  # una cuenta individual está midiendo ahora
    expectCode("DISPOSITIVO_EN_USO", link, db, team.operator, team, shared.idDispositivo, confirmaVinculacion=True)
    assert reload(db, Device, shared.idDispositivo).idInstitucionAsignada is None


# --- Firmware anterior: nada se registra sin identidad verificable ni sin confirmación explícita --------------------------------


def test_un_arduino_que_no_responde_no_dispara_ningun_alta_automatica(db, mails, team, bridge, clock):
    bridge.send([])  # el puerto abre, pero el Arduino no envía nada
    for _ in range(40):
        clock.advance(1)
        bridge.send([])
    assert hub.registrationAllowed() is False and inventory(db) == []
    bridge.send([], state="REINTENTANDO", attempt=9, error="El dispositivo no responde")
    clock.advance(60)
    bridge.send([], state="REINTENTANDO", attempt=10, error="El dispositivo no responde")
    assert inventory(db) == []
    assert deviceConnection.identification(db, team.operator, team.id)["situacion"] == "SIN_COMUNICACION"


def test_el_alta_automatica_del_firmware_anterior_espera_y_nunca_es_institucional(db, mails, team, bridge, clock):
    bridge.seconds(1)
    assert inventory(db) == []  # dentro del margen todavía puede llegar un ID propio
    bridge.seconds(16)
    [auto] = inventory(db)
    assert auto.codigoDispositivo == CODE and auto.idInstitucionAsignada is None  # sin institución: el operador no lo hereda


def test_sin_id_propio_registrar_exige_confirmar_explicitamente_el_arduino(db, mails, team, bridge):
    bridge.seconds(1)  # firmware anterior, todavía dentro del margen: el código del puente no está en el inventario
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["situacion"] == "IDENTIDAD_NO_CONFIRMADA" and seen["puedeRegistrar"] and seen["requiereConfirmacion"] and not seen["confirmada"]
    expectCode("IDENTIDAD_NO_CONFIRMADA", register, db, team.operator, team)  # sin la confirmación no se registra nada
    assert inventory(db) == []
    result = deviceConnection.register(db, team.operator, DeviceConnectRegister(idInstitucion=team.id, nombre="Consultorio viejo",
                                                                                 confirmaIdentidad=True))
    assert result["creado"] and result["identificacion"]["confirmada"] and result["identificacion"]["usable"]
    [stored] = inventory(db)
    assert stored.codigoDispositivo == CODE and stored.idInstitucionAsignada == team.id
    assert '"DECLARADA"' in audits(db, "REGISTRAR_DISPOSITIVO")[0].datosNuevos
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    assert startFor(db, team.operator, patient.idPerfilMedicion, stored).estadoMedicion == "ADQUIRIENDO"


def test_sin_id_propio_vincular_un_dispositivo_existente_exige_confirmar_la_identidad(db, mails, team, bridge):
    bridge.seconds(17)  # el puente ya lo dio de alta solo, sin institución
    [auto] = inventory(db)
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["puedeVincular"] and seen["dispositivoDeclarado"]["codigoDispositivo"] == CODE and seen["requiereConfirmacion"]
    expectCode("IDENTIDAD_NO_CONFIRMADA", link, db, team.operator, team, auto.idDispositivo, confirmaVinculacion=True)
    assert reload(db, Device, auto.idDispositivo).idInstitucionAsignada is None
    assert link(db, team.operator, team, auto.idDispositivo, confirmaVinculacion=True, confirmaIdentidad=True)["vinculado"]
    assert reload(db, Device, auto.idDispositivo).idInstitucionAsignada == team.id and len(inventory(db)) == 1


# --- 10. Simultaneidad --------------------------------------------------------------------------------------------------------


def test_dos_altas_simultaneas_no_duplican(db, mails, team, bridge, monkeypatch):
    connect(bridge)
    register(db, team.operator, team)
    second = addOperator(db, team)
    secondUser = db.get(__import__("app.models.user", fromlist=["User"]).User, db.get(type(second), second.idInstitucionUsuario).idUsuarioInvitado)
    real = devices.findByCode
    calls = {"n": 0}

    def blind(db_, code):  # el segundo operador consultó ANTES de que el primero terminara el alta
        calls["n"] += 1
        return None if calls["n"] == 1 else real(db_, code)

    monkeypatch.setattr(devices, "findByCode", blind)
    result = register(db, secondUser, team)
    assert result["creado"] is False and len(inventory(db)) == 1 and len(audits(db, "REGISTRAR_DISPOSITIVO")) == 1


def test_dos_operadores_no_miden_a_la_vez_con_el_mismo_dispositivo(db, mails, team, bridge):
    connect(bridge)
    register(db, team.operator, team)
    second = addOperator(db, team)
    secondUser = db.get(__import__("app.models.user", fromlist=["User"]).User, db.get(type(second), second.idInstitucionUsuario).idUsuarioInvitado)
    stored = devices.findByCode(db, ARDUINO)
    first = patients.createPatient(db, team.operator, team.id, patientData())
    other = patients.createPatient(db, secondUser, team.id, patientData(dni="22333444", nombre="Luisa"))
    startFor(db, team.operator, first.idPerfilMedicion, stored)
    expectCode("DISPOSITIVO_EN_USO", startFor, db, secondUser, other.idPerfilMedicion, stored)
    assert deviceConnection.identification(db, secondUser, team.id)["situacion"] == "DE_LA_INSTITUCION"  # lo ve, pero está ocupado
    busy = {s["id"]: s for s in telemetryService.readiness(db, secondUser, None, team.id)["pasos"]}["DISPONIBLE"]
    assert busy["estado"] == "ERROR" and "Otra cuenta" in busy["detalle"]


# --- Identidad solo declarada (firmware anterior, sin ID propio) -----------------------------------------------------------------


def test_sin_id_propio_el_operador_elige_y_confirma_cual_dispositivo_es(db, mails, team, bridge):
    known = makeDevice(db, institucion=team.id, codigo="GL-CONSULTORIO-1")
    bridge.seconds(1)  # firmware anterior: solo lecturas
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert (seen["nivel"], seen["situacion"], seen["confirmada"]) == ("DECLARADA", "IDENTIDAD_NO_CONFIRMADA", False)
    assert [c["codigoDispositivo"] for c in seen["candidatos"]] == ["GL-CONSULTORIO-1"] and seen["dispositivo"] is None
    expectCode("IDENTIDAD_NO_CONFIRMADA", register, db, team.operator, team)
    ready = telemetryService.readiness(db, team.operator, None, team.id)
    assert ready["listo"] is False and ready["bloqueo"] == "IDENTIDAD"
    patient = patients.createPatient(db, team.operator, team.id, patientData())
    expectCode("IDENTIDAD_NO_CONFIRMADA", startFor, db, team.operator, patient.idPerfilMedicion, known)

    result = deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=known.idDispositivo))
    assert result["identificacion"]["confirmada"] and result["identificacion"]["dispositivo"]["codigoDispositivo"] == "GL-CONSULTORIO-1"
    assert len(audits(db, "CONFIRMAR_DISPOSITIVO_CONEXION")) == 1
    assert telemetryService.readiness(db, team.operator, None, team.id)["listo"] is True
    assert startFor(db, team.operator, patient.idPerfilMedicion, known).estadoMedicion == "ADQUIRIENDO"


def test_la_confirmacion_manual_se_pierde_si_cambia_la_conexion(db, mails, team, bridge):
    known = makeDevice(db, institucion=team.id, codigo="GL-CONSULTORIO-1")
    bridge.seconds(1)
    deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=known.idDispositivo))
    bridge.port = "COM9"  # otro puerto: nada garantiza que siga siendo el mismo Arduino
    bridge.seconds(1)
    assert deviceConnection.identification(db, team.operator, team.id)["confirmada"] is False


def test_con_id_propio_solo_se_confirma_el_dispositivo_que_el_arduino_informo(db, mails, team, bridge):
    wrong = makeDevice(db, institucion=team.id, codigo="GL-OTRO")
    connect(bridge)
    expectCode("DISPOSITIVO_NO_COINCIDE", deviceConnection.confirm, db, team.operator,
               DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=wrong.idDispositivo))


def test_las_cuentas_individuales_siguen_usando_el_codigo_configurado(db, mails, consumer, bridge):
    from tests.test_telemetry import measuring  # noqa: PLC0415

    user, profileId, dev, started = measuring(db, consumer, bridge)
    assert started.estadoMedicion == "ADQUIRIENDO" and dev.codigoDispositivo == CODE


def test_con_id_propio_una_cuenta_individual_verifica_y_se_da_de_alta_sin_institucion(db, mails, consumer, bridge):
    user, profileId = consumer
    connect(bridge)
    ready = telemetryService.readiness(db, user, profileId)
    assert ready["listo"] is True and ready["dispositivo"]["codigoDispositivo"] == ARDUINO
    assert devices.findByCode(db, ARDUINO).idInstitucionAsignada is None


# --- Compatibilidad con dispositivos registrados ANTES de este cambio ------------------------------------------------------------


def test_los_dispositivos_registrados_antes_siguen_funcionando_sin_migracion(db, mails, team, bridge):
    """Filas como las que dejaron el alta manual, el alta automática del puente y el script 026: sin nombre, sin firmware, sin responsable,
    con otra capitalización del código, descomisionadas con institución… Nada se reescribe ni se pierde, y el flujo nuevo las entiende."""
    other, _, _ = otherInstitution(db)
    owner = relationOf(db, team, team.owner).idInstitucionUsuario
    legacyAuto = Device(codigoDispositivo="GL-0001", nombre="Arduino GlucoLume (registro automático)", modelo="Arduino UNO + MAX30100",
                        modeloSensor="MAX30100", estado="OPERATIVO")  # alta del puente: sin institución ni firmware
    manualOld = Device(codigoDispositivo="Gl-0002", modeloSensor="MAX30102", estado="OPERATIVO", idInstitucionAsignada=team.id)  # sin nombre ni responsable
    retired = Device(codigoDispositivo="GL-0003", modeloSensor="MAX30102", estado="BAJA", idInstitucionAsignada=team.id,
                     idInstitucionUsuarioResponsable=owner)  # descomisionado: conserva su institución (script 026)
    foreign = Device(codigoDispositivo="GL-0004", modeloSensor="MAX30102", estado="OPERATIVO", idInstitucionAsignada=other.idInstitucion)
    db.add_all([legacyAuto, manualOld, retired, foreign])
    db.commit()

    scope = devices.institutionScope(db, team.owner, team.id)
    page = devices.listDevices(db, scope)
    assert sorted(d.codigoDispositivo for d in page.items) == ["GL-0003", "Gl-0002"]  # el propietario ve lo suyo, descomisionado incluido; nada ajeno
    assert devices.listDevices(db, scope, busqueda="gl-000").total == 2
    detail = devices.getDevice(db, scope, manualOld.idDispositivo)
    assert detail.registro is None and detail.nombre is None  # sin auditoría de alta no se inventa un origen
    assert devices.getDevice(db, scope, retired.idDispositivo).permisos.puedeEditar is False
    assert devices.editDevice(db, scope, manualOld.idDispositivo, DeviceEditRequest(nombre="Consultorio 2")).nombre == "Consultorio 2"

    # El código se reconoce sin importar mayúsculas: el mismo dispositivo, no uno nuevo.
    bridge.code = "GL-0002"
    bridge.seconds(1)
    seen = deviceConnection.identification(db, team.operator, team.id)
    assert seen["nivel"] == "DECLARADA" and seen["requiereConfirmacion"] and seen["puedeRegistrar"] is False
    assert [c["codigoDispositivo"] for c in seen["candidatos"]] == ["Gl-0002"] and seen["candidatos"][0]["sugerido"] is True
    confirmed = deviceConnection.confirm(db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=manualOld.idDispositivo))
    assert confirmed["identificacion"]["usable"] is True
    # El descomisionado no se ofrece, y el de otra institución responde como inexistente.
    expectCode("DISPOSITIVO_NO_DISPONIBLE", deviceConnection.confirm, db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=retired.idDispositivo))
    expectCode("DISPOSITIVO_NO_ENCONTRADO", deviceConnection.confirm, db, team.operator, DeviceConnectConfirm(idInstitucion=team.id, idDispositivo=foreign.idDispositivo))

    # El dado de alta por el puente (sin institución) se vincula conservando su registro, y el firmware que informe lo actualiza hacia adelante.
    bridge.code = "GL-0001"
    bridge.seconds(1)
    assert deviceConnection.identification(db, team.operator, team.id)["puedeVincular"] is True
    linked = link(db, team.operator, team, legacyAuto.idDispositivo, confirmaVinculacion=True, confirmaIdentidad=True)
    assert linked["vinculado"] and reload(db, Device, legacyAuto.idDispositivo).nombre == "Arduino GlucoLume (registro automático)"
    assert len(inventory(db)) == 4  # nada se duplicó ni se eliminó


# --- HTTP -----------------------------------------------------------------------------------------------------------------------


def test_http_registro_y_diagnostico_desde_la_conexion(db, mails, team, bridge, api):
    connect(bridge)
    base = "/api/v1/acquisition/telemetry"
    seen = api(team.operator).get(f"{base}/readiness?idInstitucion={team.id}")
    assert seen.status_code == 200 and seen.json()["identificacion"]["situacion"] == "NO_REGISTRADO"
    assert api(team.owner).post(f"{base}/device/register", json={"idInstitucion": str(team.id), "nombre": "x"}).status_code == 403
    assert api(team.operator).post(f"{base}/device/register", json={"idInstitucion": str(team.id), "nombre": "Arduino Consultorio 1",
                                                                      "codigoDispositivo": "forzado"}).status_code == 422  # el código no se elige
    created = api(team.operator).post(f"{base}/device/register", json={"idInstitucion": str(team.id), "nombre": "Arduino Consultorio 1"})
    assert created.status_code == 201 and created.json()["creado"] is True
    assert created.json()["identificacion"]["dispositivo"]["nombre"] == "Arduino Consultorio 1"
    again = api(team.operator).post(f"{base}/device/register", json={"idInstitucion": str(team.id), "nombre": "Arduino Consultorio 1"})
    assert again.json()["creado"] is False
    listed = api(team.owner).get(f"/api/v1/institutions/{team.id}/devices")
    assert listed.json()["total"] == 1
    assert api(team.operator).get(f"{base}/readiness?idInstitucion={uuid.uuid4()}").status_code == 404
