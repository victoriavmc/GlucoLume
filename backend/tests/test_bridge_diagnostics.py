# Diagnóstico de «Conectar dispositivo» y órdenes acotadas al puente: ¿qué falta para poder medir?
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_bridge_diagnostics.py -v
#
# Sin Arduino ni puerto COM: `ping` hace lo que el puente real (latido hacia ingest()). Es un mecanismo de prueba;
# el servidor no tiene ningún modo simulado. Las pruebas con hardware real se describen aparte (docs/PUENTE.md).

import uuid

import pytest
from pydantic import ValidationError

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.schemas.acquisition import BridgeCheckRequest, BridgeCommandRequest, BridgeIngest, BridgeLine, BridgePort
from app.services import telemetry as telemetryService
from sqlalchemy import select
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institutions import team  # noqa: F401 - fixture
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, TOKEN, FakeBridge, bridge, clock, freshHub, line, payload, startFor  # noqa: F401

PORTS = [
    BridgePort(puerto="COM3", descripcion="USB-SERIAL CH340 (COM3)", esArduino=True, estadoWindows="OK"),
    BridgePort(puerto="COM4", descripcion="Serie estándar sobre el vínculo Bluetooth (COM4)", esBluetooth=True, estadoWindows="OK"),
]


def ping(db, bridgeId, *, state="CONECTADO", code=None, ports=PORTS, lines=(), seq=0, port="COM4", medium="BLUETOOTH",
         baud=9600, command=None, error=None, stopped=False):
    entries = [BridgeLine(seq=seq + i, edadMs=0, texto=text) for i, text in enumerate(lines)]
    return telemetryService.ingest(db, BridgeIngest(
        idPuente=bridgeId, codigoDispositivo=CODE, puerto=port, medio=medium, baudios=baud, estadoEnlace=state,
        error=error, codigoError=code, puertos=ports, versionPuente="1.2.0", comando=command, lineas=entries,
        detenido=stopped))


def steps(result):
    return {step["id"]: step for step in result["pasos"]}


# --- ¿Qué falta para poder medir? --------------------------------------------------------------------------------------------


def test_sin_puente_explica_como_iniciarlo_y_no_dice_listo(db, mails, consumer):
    user, profileId = consumer
    result = telemetryService.readiness(db, user, profileId)
    assert result["listo"] is False and result["bloqueo"] == "PUENTE"
    assert "no está ejecutándose" in steps(result)["PUENTE"]["detalle"]
    assert steps(result)["DISPONIBLE"]["estado"] == "PENDIENTE"


@pytest.mark.parametrize("code,expected", [
    ("PUERTO_OCUPADO", "COM4 ocupado por otra aplicación"),
    ("PUERTO_INEXISTENTE", "El puerto COM4 no existe"),
    ("DISPOSITIVO_SIN_RESPUESTA", "el dispositivo no responde"),
])
def test_cada_falla_del_puerto_se_explica_con_su_solucion(db, mails, consumer, clock, code, expected):
    user, profileId = consumer
    ping(db, uuid.uuid4(), state="REINTENTANDO", code=code, error="x")
    port = steps(telemetryService.readiness(db, user, profileId))["PUERTO"]
    assert port["estado"] == "ERROR" and expected in port["detalle"] and port["solucion"]


def test_puerto_abierto_sin_telemetria_no_es_dispositivo_listo(db, mails, consumer, clock):
    user, profileId = consumer
    device(db, codigo=CODE)
    ping(db, uuid.uuid4())  # el puerto abrió, pero no llegó ninguna lectura
    result = telemetryService.readiness(db, user, profileId)
    assert steps(result)["PUERTO"]["estado"] == "OK" and steps(result)["TELEMETRIA"]["estado"] == "PENDIENTE"
    assert result["listo"] is False and result["bloqueo"] == "TELEMETRIA"


def deviceByCode(db, code):
    from sqlalchemy import func

    from app.models.device import Device

    db.expire_all()
    return db.scalars(select(Device).where(func.lower(Device.codigoDispositivo) == code.lower())).all()


def settle(db, bridgeId, clock, seq=1):
    """Firmware sin ID propio: el alta automática del código configurado espera LEGACY_REGISTRATION_GRACE_SECONDS (por si el Arduino todavía no
    repitió su ID) y se hace en el siguiente latido."""
    clock.advance(16)
    ping(db, bridgeId, lines=[line()], seq=seq)


def test_el_dispositivo_se_da_de_alta_solo_cuando_el_puente_lo_informa(db, mails, consumer, clock):
    user, profileId = consumer
    assert deviceByCode(db, CODE) == []
    bridgeId = uuid.uuid4()
    ping(db, bridgeId, lines=[line()])
    assert deviceByCode(db, CODE) == []  # todavía puede llegar el ID propio del Arduino: no se inventa un dispositivo
    settle(db, bridgeId, clock)
    [registered] = deviceByCode(db, CODE)
    assert (registered.estado, registered.modeloSensor, registered.idInstitucionAsignada) == ("OPERATIVO", "MAX30100", None)
    assert "registro automático" in registered.nombre
    audit = db.scalar(select(Audit).where(Audit.accion == "REGISTRAR_DISPOSITIVO"))
    assert audit.idUsuario is None and '"registroAutomatico": true' in audit.datosNuevos and "PUENTE_SERIE" in audit.datosNuevos
    # Sin ninguna intervención de la administración: queda asociado al perfil y listo para medir.
    result = telemetryService.readiness(db, user, profileId)
    assert steps(result)["REGISTRADO"]["estado"] == "OK" and steps(result)["ASOCIADO"]["estado"] == "OK"
    assert result["listo"] is True


def test_el_alta_automatica_es_idempotente_y_no_reactiva_ni_modifica_un_dispositivo_existente(db, mails, consumer, clock):
    bridgeId = uuid.uuid4()
    ping(db, bridgeId, lines=[line()])
    settle(db, bridgeId, clock)
    ping(db, bridgeId, lines=[line()], seq=2)
    assert len(deviceByCode(db, CODE)) == 1
    # Un dispositivo que la administración dejó en mantenimiento o dio de baja NO se vuelve operativo por conectarse.
    [existing] = deviceByCode(db, CODE)
    for state in ("EN_MANTENIMIENTO", "BAJA"):
        existing.estado = state
        db.commit()
        hub.registeredCodes.clear()
        ping(db, bridgeId, lines=[line()], seq=3)
        assert [d.estado for d in deviceByCode(db, CODE)] == [state]


def test_si_el_dispositivo_desaparece_de_la_base_se_vuelve_a_registrar_solo(db, mails, consumer, clock):
    """La base se pudo recrear o el dispositivo borrarse mientras el backend seguía en marcha: no queda 'recordado' para siempre."""
    from sqlalchemy import delete

    from app.models.device import Device

    bridgeId = uuid.uuid4()
    ping(db, bridgeId, lines=[line()])
    settle(db, bridgeId, clock)
    assert len(deviceByCode(db, CODE)) == 1
    db.execute(delete(Device))
    db.commit()
    ping(db, bridgeId, lines=[line()], seq=2)  # dentro de la ventana de revalidación todavía no se consulta
    clock.advance(31)
    ping(db, bridgeId, lines=[line()], seq=3)
    assert len(deviceByCode(db, CODE)) == 1


def test_el_diagnostico_repara_un_alta_faltante_antes_de_dar_error(db, mails, consumer, clock):
    from sqlalchemy import delete

    from app.models.device import Device

    user, profileId = consumer
    bridgeId = uuid.uuid4()
    ping(db, bridgeId, lines=[line()])
    settle(db, bridgeId, clock)
    db.execute(delete(Device))
    db.commit()
    assert steps(telemetryService.readiness(db, user, profileId))["REGISTRADO"]["estado"] == "OK"
    assert len(deviceByCode(db, CODE)) == 1


def test_un_codigo_invalido_no_se_registra_y_se_explica(db, mails, consumer, clock):
    user, profileId = consumer
    bridgeId = uuid.uuid4()

    def send(seq):
        return telemetryService.ingest(db, BridgeIngest(idPuente=bridgeId, codigoDispositivo="a b", puerto="COM4", medio="BLUETOOTH",
                                                        baudios=9600, estadoEnlace="CONECTADO", lineas=[BridgeLine(seq=seq, edadMs=0, texto=line())]))

    bad = send(0)
    assert bad.aceptadas == 1  # la telemetría se recibe igual
    pending = steps(telemetryService.readiness(db, user, profileId))["REGISTRADO"]
    assert pending["estado"] == "PENDIENTE"  # dentro del margen todavía puede llegar un ID propio: no se declara error ni se registra nada
    clock.advance(16)
    send(1)
    assert deviceByCode(db, "a b") == []
    register = steps(telemetryService.readiness(db, user, profileId))["REGISTRADO"]
    assert register["estado"] == "ERROR" and "no se pudo registrar automáticamente" in register["detalle"] and "BRIDGE_DEVICE_CODE" in register["solucion"]


def test_una_cuenta_individual_puede_medir_con_el_dispositivo_registrado_solo(db, mails, consumer, bridge, clock):
    from app.models.device import Device
    from tests.test_telemetry import startFor

    user, profileId = consumer
    bridge.seconds(17)  # firmware sin ID propio: el alta automática espera unos segundos por si todavía llega el ID
    [registered] = deviceByCode(db, CODE)
    started = startFor(db, user, profileId, registered)
    assert started.estadoMedicion == "ADQUIRIENDO" and started.dispositivo.codigoDispositivo == CODE


def test_dispositivo_registrado_pero_no_asociado_al_perfil(db, mails, consumer, clock):
    user, profileId = consumer
    registered = device(db, codigo=CODE, estado="EN_MANTENIMIENTO")
    ping(db, uuid.uuid4(), lines=[line()])
    result = telemetryService.readiness(db, user, profileId)
    assert steps(result)["REGISTRADO"]["estado"] == "OK"
    assert steps(result)["ASOCIADO"]["estado"] == "ERROR"
    assert "todavía no está asociado a este perfil" in steps(result)["ASOCIADO"]["detalle"]
    assert result["listo"] is False and result["dispositivo"]["codigoDispositivo"] == registered.codigoDispositivo


def test_dispositivo_autorizado_con_telemetria_esta_listo(db, mails, consumer, clock):
    user, profileId = consumer
    registered = device(db, codigo=CODE)
    ping(db, uuid.uuid4(), lines=[line()])
    result = telemetryService.readiness(db, user, profileId)
    assert result["listo"] is True and result["bloqueo"] is None
    assert [s["estado"] for s in result["pasos"]] == ["OK"] * len(result["pasos"])
    assert result["dispositivo"]["idDispositivo"] == str(registered.idDispositivo)
    # Sin elegir un perfil no se puede afirmar que esté asociado: nunca «listo».
    assert telemetryService.readiness(db, user, None)["listo"] is False


def test_operador_sin_perfil_queda_listo_si_su_institucion_puede_usar_el_dispositivo(db, mails, team, clock):
    # El operador no tiene perfil propio: el paciente se elige al medir, así que no puede quedar «pendiente» para siempre.
    operator = team.operator
    registered = device(db, codigo=CODE)
    ping(db, uuid.uuid4(), lines=[line()])
    result = telemetryService.readiness(db, operator, None)
    assert steps(result)["ASOCIADO"]["estado"] == "OK" and result["listo"] is True and result["bloqueo"] is None
    registered.estado = "EN_MANTENIMIENTO"
    db.commit()
    result = telemetryService.readiness(db, operator, None)
    assert steps(result)["ASOCIADO"]["estado"] == "ERROR" and result["listo"] is False


def test_el_sensor_con_error_se_informa(db, mails, consumer, clock):
    user, profileId = consumer
    device(db, codigo=CODE)
    ping(db, uuid.uuid4(), lines=["ERROR: MAX30100 no detectado por I2C (0x57). Revisar cableado/alimentacion.", line()])
    sensor = steps(telemetryService.readiness(db, user, profileId))["SENSOR"]
    assert sensor["estado"] == "ERROR" and "MAX30100 no detectado" in sensor["detalle"] and sensor["solucion"]
    assert hub.snapshot(user.idUsuario)["avisoDispositivo"]["error"] is True


def test_otra_cuenta_midiendo_ocupa_el_dispositivo(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    registered = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, user, profileId, registered)
    other = makeUser(db, email="otra@example.com", usuario="otra")
    from app.services import measurement as measurements

    otherProfile = measurements.getOwnProfile(db, other).idPerfilMedicion
    result = telemetryService.readiness(db, other, otherProfile)
    assert result["listo"] is False and steps(result)["DISPONIBLE"]["estado"] == "ERROR"


# --- Órdenes acotadas al puente ----------------------------------------------------------------------------------------------


def test_orden_configurar_solo_con_un_puerto_que_el_puente_informo(db, mails, consumer, clock):
    user, _ = consumer
    ping(db, uuid.uuid4())
    telemetryService.takeControl(db, user)  # solo da órdenes quien controla el dispositivo
    with pytest.raises(AuthError) as unknown:
        telemetryService.command(db, user, BridgeCommandRequest(accion="CONFIGURAR", puerto="COM99", medio="USB"))
    assert unknown.value.code == "PUERTO_NO_DISPONIBLE"
    state = telemetryService.command(db, user, BridgeCommandRequest(accion="CONFIGURAR", puerto="com3", medio="usb"))
    assert state["puente"]["comandoPendiente"] == "CONFIGURAR"


def test_el_puente_recibe_la_orden_en_su_proximo_latido_y_la_confirma(db, mails, consumer, clock):
    user, _ = consumer
    bridgeId = uuid.uuid4()
    ping(db, bridgeId)
    telemetryService.takeControl(db, user)
    telemetryService.command(db, user, BridgeCommandRequest(accion="CONFIGURAR", puerto="COM3", medio="USB"))
    delivered = ping(db, bridgeId)
    assert delivered.comando.accion == "CONFIGURAR" and (delivered.comando.puerto, delivered.comando.medio) == ("COM3", "USB")
    # Mientras no confirme, sigue pendiente (por si el latido se perdió) y no se acepta otra orden.
    assert ping(db, bridgeId).comando is not None
    with pytest.raises(AuthError) as busy:
        telemetryService.command(db, user, BridgeCommandRequest(accion="PAUSAR"))
    assert busy.value.code == "COMANDO_PENDIENTE"
    from app.schemas.acquisition import BridgeCommandResult

    done = ping(db, bridgeId, command=BridgeCommandResult(id=delivered.comando.id, ok=True, mensaje="Ahora lee COM3."),
                port="COM3", medium="USB", baud=115200)
    assert done.comando is None
    snapshot = hub.snapshot(user.idUsuario)["puente"]
    assert snapshot["comandoPendiente"] is None and snapshot["ultimoComando"]["ok"] is True


def test_sin_puente_activo_no_hay_a_quien_darle_ordenes(db, mails, consumer):
    user, _ = consumer
    with pytest.raises(AuthError) as error:
        telemetryService.command(db, user, BridgeCommandRequest(accion="DETENER"))
    assert error.value.code == "PUENTE_NO_ACTIVO"


def test_no_se_interrumpe_una_sesion_de_medicion(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    device_ = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, user, profileId, device_)
    for action in ("PAUSAR", "DETENER", "REINICIAR"):
        with pytest.raises(AuthError) as error:
            telemetryService.command(db, user, BridgeCommandRequest(accion=action))
        assert error.value.code == "SESION_EN_CURSO"


def test_las_ordenes_son_una_lista_cerrada_y_solo_para_quienes_miden(db, mails, consumer, clock):
    for bad in ({"accion": "EJECUTAR"}, {"accion": "ESCRIBIR"}, {"accion": "DETENER", "extra": "x"}):
        with pytest.raises(ValidationError):
            BridgeCommandRequest(**bad)
    user, _ = consumer
    ping(db, uuid.uuid4())
    telemetryService.takeControl(db, user)
    with pytest.raises(AuthError) as invalid:
        telemetryService.command(db, user, BridgeCommandRequest(accion="PAUSAR", puerto="COM4"))
    assert invalid.value.code == "COMANDO_INVALIDO"
    institutional = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL", email="inst@example.com", usuario="inst")
    with pytest.raises(AuthError) as denied:
        telemetryService.command(db, institutional, BridgeCommandRequest(accion="DETENER"))
    assert denied.value.code == "PERMISO_INSUFICIENTE"


def test_cada_orden_queda_auditada(db, mails, consumer, clock):
    user, _ = consumer
    ping(db, uuid.uuid4())
    telemetryService.takeControl(db, user)
    telemetryService.command(db, user, BridgeCommandRequest(accion="PAUSAR"))
    rows = db.scalars(select(Audit).where(Audit.accion == "ORDEN_PUENTE_SERIE")).all()
    assert len(rows) == 1 and rows[0].idUsuario == user.idUsuario and "PAUSAR" in rows[0].datosNuevos


def test_reiniciar_y_detener_se_reflejan_en_el_resultado(db, mails, consumer, clock):
    user, _ = consumer
    first = uuid.uuid4()
    ping(db, first)
    telemetryService.takeControl(db, user)
    telemetryService.command(db, user, BridgeCommandRequest(accion="REINICIAR"))
    ping(db, first, stopped=True)  # el puente cierra y vuelve a abrir con otro identificador
    clock.advance(1)
    ping(db, uuid.uuid4())
    assert hub.snapshot(user.idUsuario)["puente"]["ultimoComando"]["mensaje"] == "El puente se reinició."


# --- HTTP ----------------------------------------------------------------------------------------------------------------------


def test_comprobar_el_codigo_requiere_el_token_y_no_filtra_datos(api, db, mails, consumer):
    user, _ = consumer
    device(db, codigo=CODE)
    client = api(user)
    assert client.post("/api/v1/acquisition/bridge/check", json={"codigoDispositivo": CODE}).status_code == 403
    ok = client.post("/api/v1/acquisition/bridge/check", json={"codigoDispositivo": CODE.lower()}, headers={"X-Bridge-Token": TOKEN})
    assert ok.status_code == 200 and ok.json()["registrado"] is True and ok.json()["operativo"] is True
    assert set(ok.json()) == {"registrado", "operativo", "sensor", "nombre", "asignadoAInstitucion"}
    missing = client.post("/api/v1/acquisition/bridge/check", json={"codigoDispositivo": "NADA"}, headers={"X-Bridge-Token": TOKEN})
    assert missing.json() == {"registrado": False, "operativo": False, "sensor": None, "nombre": None, "asignadoAInstitucion": False}


def test_orden_y_diagnostico_por_http_exigen_sesion_y_nunca_devuelven_el_token(api, db, mails, consumer, bridge):
    user, profileId = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    client = api(user)
    readiness = client.get(f"/api/v1/acquisition/telemetry/readiness?idPerfilMedicion={profileId}")
    assert readiness.status_code == 200 and readiness.json()["listo"] is True
    assert client.post("/api/v1/acquisition/telemetry/control").status_code == 200
    status = client.post("/api/v1/acquisition/bridge/command", json={"accion": "PAUSAR"})
    assert status.status_code == 200 and status.json()["puente"]["comandoPendiente"] == "PAUSAR"
    assert client.post("/api/v1/acquisition/bridge/command", json={"accion": "FORMATEAR"}).status_code == 422
    assert TOKEN not in readiness.text + status.text
