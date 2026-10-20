# Un único Arduino físico compartido por todas las cuentas: una sola adquisición activa a la vez, mediciones independientes por perfil.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_shared_device.py -v

import threading
import uuid

import pytest
from sqlalchemy import select

from app.acquisition.telemetry import ABANDON_SECONDS, RESERVATION_SECONDS, hub
from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.measurement import Measurement
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import device, expectError  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, freshHub, startFor  # noqa: F401


@pytest.fixture
def two(db, mails):
    """Dos cuentas individuales distintas, cada una con su perfil, y el único Arduino registrado (sin asignar a nadie)."""
    a = makeUser(db, email="a@example.com", usuario="cuentaa")
    b = makeUser(db, email="b@example.com", usuario="cuentab")
    profileA = measurements.getOwnProfile(db, a).idPerfilMedicion
    profileB = measurements.getOwnProfile(db, b).idPerfilMedicion
    return (a, profileA), (b, profileB)


def stateOf(db, idMedicion):
    db.expire_all()
    return db.get(Measurement, idMedicion).estadoMedicion


def test_1_usuario_a_mide_y_guarda_y_el_equipo_queda_libre(db, two, bridge, clock):
    (a, profileA), _ = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    session = startFor(db, a, profileA, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, a)
    assert saved.estadoMedicion == "COMPLETADA" and hub.session is None and session.idMedicion == saved.idMedicion


def test_2_usuario_b_usa_el_mismo_arduino_inmediatamente_despues(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, a, profileA, dev)
    bridge.seconds(9)
    first = telemetryService.saveSession(db, a)
    started = startFor(db, b, profileB, dev)  # el mismo dispositivo, sin ninguna reasignación
    bridge.seconds(9)
    second = telemetryService.saveSession(db, b)
    assert first.idMedicion != second.idMedicion and started.idMedicion == second.idMedicion
    assert db.query(type(dev)).count() == 1  # un solo registro del Arduino


def test_3_usuario_a_cancela_y_usuario_b_puede_medir(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    started = startFor(db, a, profileA, dev)
    telemetryService.cancelSession(db, a)
    assert stateOf(db, started.idMedicion) == "CANCELADA" and hub.session is None
    assert startFor(db, b, profileB, dev).estadoMedicion == "ADQUIRIENDO"


def test_ocupado_solo_durante_una_adquisicion_activa_de_otra_cuenta(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, a, profileA, dev)
    busy = expectError("DISPOSITIVO_EN_USO", startFor, db, b, profileB, dev)
    assert "Dispositivo temporalmente ocupado" in busy.message
    snapshot = telemetryService.status(db, b)
    assert snapshot["ocupado"] is True and snapshot["lectura"] is None and snapshot["sesion"] is None  # no ve datos del otro
    assert telemetryService.status(db, a)["ocupado"] is False


def test_4_una_reserva_vencida_o_abandonada_no_bloquea_el_equipo(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    abandoned = startFor(db, a, profileA, dev)
    # A cerró la pestaña: nadie consulta el estado en nombre de A durante más de ABANDON_SECONDS.
    clock.advance(ABANDON_SECONDS + 5)
    bridge.seconds(1)
    started = startFor(db, b, profileB, dev)  # B puede medir sin esperar el tope de 30 minutos
    assert started.estadoMedicion == "ADQUIRIENDO"
    assert stateOf(db, abandoned.idMedicion) == "CANCELADA"  # coherencia: la medición huérfana se cerró
    actions = [row.accion for row in db.scalars(select(Audit))]
    assert "CANCELAR_SESION_ABANDONADA" in actions  # y quedó auditado


def test_una_sesion_cuyo_dueno_sigue_consultando_no_se_libera(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    mine = startFor(db, a, profileA, dev)
    for _ in range(5):  # A sigue con la pantalla abierta: su consulta periódica renueva la sesión
        clock.advance(ABANDON_SECONDS - 10)
        bridge.seconds(1)
        telemetryService.status(db, a)
    expectError("DISPOSITIVO_EN_USO", startFor, db, b, profileB, dev)
    assert stateOf(db, mine.idMedicion) == "ADQUIRIENDO"  # jamás se cancela una adquisición activa de otra cuenta


def test_una_reserva_sin_medicion_vence_rapido(db, two, bridge, clock):
    (a, _), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    hub.reserve(a.idUsuario)  # reserva que nunca llegó a crear la medición
    clock.advance(RESERVATION_SECONDS + 1)
    bridge.seconds(1)  # el puente sigue latiendo
    assert startFor(db, b, profileB, dev).estadoMedicion == "ADQUIRIENDO"


def test_5_dos_cuentas_a_la_vez_solo_una_obtiene_la_reserva():
    hub.reset()
    winners, losers = [], []
    barrier = threading.Barrier(8)

    def attempt(user):
        barrier.wait()
        try:
            hub.reserve(user)
            winners.append(user)
        except PermissionError:
            losers.append(user)

    users = [uuid.uuid4() for _ in range(8)]
    threads = [threading.Thread(target=attempt, args=(user,)) for user in users]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(winners) == 1 and len(losers) == 7
    hub.reset()


def test_6_cada_medicion_conserva_su_propietario_y_su_perfil(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, a, profileA, dev)
    bridge.seconds(9)
    first = telemetryService.saveSession(db, a)
    startFor(db, b, profileB, dev)
    bridge.seconds(9)
    second = telemetryService.saveSession(db, b)
    db.expire_all()
    rows = {m.idMedicion: m for m in db.scalars(select(Measurement))}
    assert rows[first.idMedicion].idPerfilMedicion == profileA and rows[second.idMedicion].idPerfilMedicion == profileB
    assert rows[first.idMedicion].idDispositivo == rows[second.idMedicion].idDispositivo == dev.idDispositivo  # mismo equipo, perfiles distintos
    started = {row.idRegistro: row.idUsuario for row in db.scalars(select(Audit).where(Audit.accion == "INICIAR_SESION_DISPOSITIVO"))}
    assert started[first.idMedicion] == a.idUsuario and started[second.idMedicion] == b.idUsuario  # quién inició cada adquisición


def test_7_nadie_accede_a_las_mediciones_privadas_de_otra_cuenta(api, db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, a, profileA, dev)
    bridge.seconds(9)
    mine = telemetryService.saveSession(db, a)
    other = api(b)
    assert other.get(f"/api/v1/measurements/{mine.idMedicion}").status_code in (403, 404)
    assert other.post(f"/api/v1/measurements/{mine.idMedicion}/cancel").status_code in (403, 404)
    assert other.get("/api/v1/measurements").json()["total"] == 0
    assert other.get(f"/api/v1/measurements/devices?idPerfilMedicion={profileA}").status_code in (403, 404)  # ni usar su perfil
    assert api(a).get(f"/api/v1/measurements/{mine.idMedicion}").status_code == 200


def test_cerrar_sesion_cancela_y_libera_la_adquisicion_pendiente_sin_tocar_lo_guardado(db, two, bridge, clock):
    (a, profileA), (b, profileB) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, a, profileA, dev)
    bridge.seconds(9)
    saved = telemetryService.saveSession(db, a)
    pending = startFor(db, a, profileA, dev)
    telemetryService.releaseOnLogout(db, a)
    assert hub.session is None and stateOf(db, pending.idMedicion) == "CANCELADA"
    assert stateOf(db, saved.idMedicion) == "COMPLETADA"  # lo ya guardado no se toca
    assert startFor(db, b, profileB, dev).estadoMedicion == "ADQUIRIENDO"


def test_cerrar_sesion_de_otra_cuenta_no_cancela_una_adquisicion_ajena(db, two, bridge, clock):
    (a, profileA), (b, _) = two
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    mine = startFor(db, a, profileA, dev)
    telemetryService.releaseOnLogout(db, b)
    assert hub.session is not None and stateOf(db, mine.idMedicion) == "ADQUIRIENDO"


def test_el_arduino_registrado_no_pertenece_a_ninguna_cuenta(db, two, bridge, clock):
    dev = device(db, codigo=CODE)
    assert dev.idInstitucionAsignada is None and dev.idInstitucionUsuarioResponsable is None
    (a, profileA), (b, profileB) = two
    assert [d.idDispositivo for d in measurements.listDevices(db, a, profileA)] == [dev.idDispositivo]
    assert [d.idDispositivo for d in measurements.listDevices(db, b, profileB)] == [dev.idDispositivo]
    with pytest.raises(AuthError):
        measurements.listDevices(db, b, profileA)  # compartir el equipo no es compartir el perfil
