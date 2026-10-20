# Control temporal del dispositivo compartido (DEC-01): una sola cuenta lo controla a la vez, con una acción explícita («Usar dispositivo» o
# «Iniciar medición»). Solo quien controla ve las señales en vivo y da órdenes al puente; una orden nunca toma el control; el control sin
# medición vence a los 5 min (o a los 30 s si su dueño deja de consultar) y una medición activa no vence por eso.
#
#     python -m pytest tests/test_device_control.py -v
#
# Datos sintéticos, SQLite temporal, puente simulado.

import threading

import pytest
from sqlalchemy import select, update

from app.acquisition.telemetry import PREVIEW_MAX_SECONDS, RESERVATION_SECONDS, hub
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institution import Institution
from app.schemas.acquisition import BridgeCommandRequest
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_institutions import team  # noqa: F401 - fixture
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, bridge, clock, freshHub, line, startFor  # noqa: F401 - fixtures

CONTROL = "/api/v1/acquisition/telemetry/control"


def code(fn, *args):
    try:
        fn(*args)
    except AuthError as error:
        return error.code
    return "OK"


def order(db, actor, accion="PAUSAR"):
    return telemetryService.command(db, actor, BridgeCommandRequest(accion=accion))


def wait(db, bridge, clock, seconds, *, polling=None, step=10):
    """Pasa el tiempo con el puente vivo; `polling` sigue consultando el estado (como la pantalla abierta)."""
    for _ in range(seconds // step):
        clock.advance(step)
        bridge.send([line()])
        if polling is not None:
            telemetryService.status(db, polling)


@pytest.fixture
def other(db, mails):
    return makeUser(db, email="otra@example.com", usuario="otra")


def test_una_orden_no_toma_el_control_de_un_dispositivo_libre(db, mails, consumer, bridge):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    assert code(order, db, user) == "CONTROL_REQUERIDO"
    assert hub.session is None and hub.bridge.pending is None  # ni control ni orden pendiente


def test_solo_quien_controla_ve_las_lecturas_y_da_ordenes(db, mails, consumer, other, bridge):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    free = telemetryService.status(db, user)
    assert free["lectura"] is None and free["edadUltimaLectura"] is not None  # libre: nadie ve valores, todos ven que hay telemetría
    mine = telemetryService.takeControl(db, user)
    assert mine["controlPropio"] is True and mine["lectura"]["bpm"] == 72.0
    seen = telemetryService.status(db, other)
    assert seen["ocupado"] is True and seen["controlPropio"] is False and seen["lectura"] is None
    assert code(telemetryService.takeControl, db, other) == "DISPOSITIVO_EN_USO"
    assert code(order, db, other) == "DISPOSITIVO_EN_USO"
    assert order(db, user)["puente"]["comandoPendiente"] == "PAUSAR"
    assert [a.idUsuario for a in audits(db, "TOMAR_CONTROL_DISPOSITIVO")] == [user.idUsuario]


def test_las_senales_por_stream_solo_le_llegan_a_quien_controla(db, mails, consumer, other, bridge):
    user, _ = consumer
    device(db, codigo=CODE)
    mineChannel, otherChannel = hub.subscribe(user.idUsuario), hub.subscribe(other.idUsuario)
    try:
        bridge.seconds(2)  # libre: las lecturas no le llegan a nadie
        telemetryService.takeControl(db, user)
        bridge.seconds(2)
        mine = [mineChannel.get_nowait()["tipo"] for _ in range(mineChannel.qsize())]
        others = [otherChannel.get_nowait()["tipo"] for _ in range(otherChannel.qsize())]
    finally:
        hub.unsubscribe(mineChannel)
        hub.unsubscribe(otherChannel)
    assert mine.count("lectura") == 2 and "lectura" not in others


def test_sin_medicion_el_control_vence_a_los_5_minutos_aunque_la_pantalla_siga_abierta(db, mails, consumer, other, bridge, clock):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    telemetryService.takeControl(db, user)
    wait(db, bridge, clock, PREVIEW_MAX_SECONDS - 60, polling=user)
    assert code(telemetryService.takeControl, db, other) == "DISPOSITIVO_EN_USO"
    wait(db, bridge, clock, 120, polling=user)
    assert telemetryService.takeControl(db, other)["controlPropio"] is True  # venció: otra cuenta lo toma
    assert code(order, db, user) == "DISPOSITIVO_EN_USO"


def test_volver_a_usar_el_dispositivo_renueva_el_plazo(db, mails, consumer, other, bridge, clock):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    telemetryService.takeControl(db, user)
    wait(db, bridge, clock, 240, polling=user)
    telemetryService.takeControl(db, user)  # acción explícita: renueva
    wait(db, bridge, clock, 180, polling=user)
    assert code(telemetryService.takeControl, db, other) == "DISPOSITIVO_EN_USO"


def test_si_su_duenia_deja_de_consultar_el_control_se_libera_a_los_30_segundos(db, mails, consumer, other, bridge, clock):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    telemetryService.takeControl(db, user)
    wait(db, bridge, clock, int(RESERVATION_SECONDS) + 10, step=5)  # cerró la pantalla o perdió la conexión
    assert telemetryService.takeControl(db, other)["controlPropio"] is True


def test_una_medicion_activa_no_vence_a_los_5_minutos(db, mails, consumer, other, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    telemetryService.takeControl(db, user)
    session = startFor(db, user, profileId, dev)  # «Iniciar medición» reutiliza su control
    wait(db, bridge, clock, PREVIEW_MAX_SECONDS + 60, polling=user)
    assert code(telemetryService.takeControl, db, other) == "DISPOSITIVO_EN_USO"
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, user)
    assert saved.idMedicion == session.idMedicion and saved.estadoMedicion == "COMPLETADA"
    assert hub.session is None  # al guardar se libera el equipo
    assert telemetryService.takeControl(db, other)["controlPropio"] is True


def test_soltar_el_control_lo_deja_libre_y_no_corta_una_medicion(db, mails, consumer, other, bridge):
    user, _ = consumer
    otherProfile = measurements.getOwnProfile(db, other).idPerfilMedicion
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    telemetryService.takeControl(db, user)
    assert telemetryService.releaseControl(db, user)["controlPropio"] is False and hub.session is None
    startFor(db, other, otherProfile, dev)
    assert code(telemetryService.releaseControl, db, other) == "SESION_EN_CURSO"
    assert code(telemetryService.releaseControl, db, user) == "OK" and hub.session.userId == other.idUsuario  # soltar lo ajeno no hace nada
    telemetryService.cancelSession(db, other)  # cancelar libera el equipo
    assert telemetryService.takeControl(db, user)["controlPropio"] is True


def test_dos_cuentas_que_lo_piden_a_la_vez_obtienen_una_sola_el_control(db, mails, consumer, other, bridge):
    user, _ = consumer
    device(db, codigo=CODE)
    bridge.seconds(1)
    for _ in range(25):
        hub.session = None
        barrier, results = threading.Barrier(2), []

        def take(userId):
            barrier.wait()
            try:
                hub.reserve(userId)
                results.append("OK")
            except PermissionError:
                results.append("EN_USO")

        threads = [threading.Thread(target=take, args=(who.idUsuario,)) for who in (user, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(results) == ["EN_USO", "OK"]


def test_modo_restringido_respeta_la_asignacion_al_tomar_el_control(db, mails, consumer, team, bridge, api, deviceMode):
    deviceMode(False)
    user, _ = consumer
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(1)
    response = api(user).post(CONTROL)
    assert response.status_code == 403 and response.json()["codigo"] == "PERMISO_INSUFICIENTE"
    assert hub.session is None
    assert api(team.operator).post(CONTROL).json()["controlPropio"] is True  # la operadora de la institución titular sí


def test_compartido_la_pausa_de_la_institucion_titular_no_impide_usar_el_equipo_a_otras_cuentas(db, mails, consumer, team, bridge, deviceMode):
    user, profileId = consumer
    dev = device(db, institucion=team.id, codigo=CODE)
    db.execute(update(Institution).where(Institution.idInstitucion == team.id).values(estado="INACTIVA"))
    db.commit()
    bridge.seconds(1)
    deviceMode(False)
    assert code(telemetryService.takeControl, db, user) == "PERMISO_INSUFICIENTE" and hub.session is None  # restringido: la pausa rige
    deviceMode(True)
    assert telemetryService.takeControl(db, user)["controlPropio"] is True
    assert startFor(db, user, profileId, dev).idPerfilMedicion == profileId
    assert code(telemetryService.takeControl, db, team.operator) == "PERMISO_INSUFICIENTE"  # su propio personal no opera mientras está pausada
    assert db.scalar(select(Audit).where(Audit.accion == "TOMAR_CONTROL_DISPOSITIVO")) is not None
