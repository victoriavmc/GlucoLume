# Streams SSE: no retienen conexiones del pool de base, tienen tope por cuenta y terminan al revocarse la sesión.
#
#     python -m pytest tests/test_stream_limits.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): cada stream retenía una conexión de base durante toda su vida; ~15 streams de UNA cuenta
# agotaban el pool y el resto de la API respondía 500. Usa la app real (rutas, getDb y getAuthContext reales) con un motor SQLite
# temporal de pool pequeño (3 conexiones, sin desborde) para observar la retención. Datos sintéticos.

import asyncio

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import sessionmaker

from app.api import streams
from app.models.userSession import UserSession
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, makeSession, makeUser  # noqa: F401 - fixtures


async def call(app, path, token, hold=False, timeout=8.0):
    """Invoca la app por ASGI. hold=True devuelve (tarea, estado, desconectar) tras el primer cuerpo, sin esperar el fin del stream."""
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": "GET", "path": path,
             "raw_path": path.encode(), "query_string": b"", "scheme": "http", "server": ("testserver", 80), "client": ("203.0.113.5", 1234),
             "headers": [(b"host", b"testserver"), (b"authorization", f"Bearer {token}".encode())]}
    disconnect, firstBody = asyncio.Event(), asyncio.Event()
    state = {"status": None, "body": b"", "error": None}
    requested = {"done": False}

    async def receive():
        if not requested["done"]:
            requested["done"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body" and message.get("body"):
            state["body"] += message["body"]
            firstBody.set()

    async def runner():
        try:
            await app(scope, receive, send)
        except BaseException as error:  # noqa: BLE001
            state["error"] = f"{type(error).__name__}: {str(error)[:100]}"
        finally:
            firstBody.set()

    task = asyncio.create_task(runner())
    if hold:
        await asyncio.wait_for(firstBody.wait(), timeout)
        return task, state, disconnect
    await asyncio.wait_for(task, timeout)
    return state


@pytest.fixture
def world(engine, db, monkeypatch):  # noqa: F811
    """App real + motor de pool pequeño + dos cuentas (atacante y otra persona) con sesión."""
    import app.db.session as sessionModule
    from app.core.security import createAccessToken
    from app.main import app

    small = create_engine(engine.url, pool_size=3, max_overflow=0, pool_timeout=1)
    for listener in list(engine.pool.dispatch.connect):
        event.listen(small, "connect", listener)
    factory = sessionmaker(bind=small, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(sessionModule, "getSessionFactory", lambda: factory)
    monkeypatch.setattr(streams, "registry", streams.StreamRegistry(perUser=3, total=50))
    attacker, other = makeUser(db, email="a@example.com", usuario="atacante"), makeUser(db, email="b@example.com", usuario="otrapersona")
    sessions = {"attacker": makeSession(db, attacker), "other": makeSession(db, other)}
    tokens = {"attacker": createAccessToken(attacker.idUsuario, sessions["attacker"].idSesion),
              "other": createAccessToken(other.idUsuario, sessions["other"].idSesion)}
    return app, small, tokens, sessions


@pytest.mark.parametrize("path", ["/api/v1/acquisition/stream", "/api/v1/acquisition/telemetry/stream"])
def test_los_streams_no_retienen_conexiones_del_pool(world, path):
    app, pool, tokens, _ = world

    async def scenario():
        held = [await call(app, path, tokens["attacker"], hold=True) for _ in range(3)]  # == tamaño del pool
        assert all(state["status"] == 200 for _, state, _ in held)
        assert pool.pool.checkedout() == 0, "ningún stream debe retener una conexión de base"
        during = await call(app, "/api/v1/auth/me", tokens["other"], timeout=15)  # otra cuenta sigue siendo atendida
        for task, _, disconnect in held:
            disconnect.set()
        await asyncio.gather(*(task for task, _, _ in held))
        return during

    during = asyncio.run(scenario())
    assert during["status"] == 200 and during["error"] is None


def test_una_cuenta_no_supera_su_tope_de_streams_y_el_cupo_se_libera(world):
    app, _, tokens, _ = world
    path = "/api/v1/acquisition/stream"

    async def scenario():
        held = [await call(app, path, tokens["attacker"], hold=True) for _ in range(3)]
        fourth = await call(app, path, tokens["attacker"])  # el cuarto se rechaza
        otherAccount = await call(app, path, tokens["other"], hold=True)  # otra cuenta no se ve afectada
        for task, _, disconnect in [*held, otherAccount]:
            disconnect.set()
        await asyncio.gather(*(task for task, _, _ in [*held, otherAccount]))
        return fourth, otherAccount[1]["status"], await call(app, path, tokens["attacker"], hold=True)

    fourth, otherStatus, again = asyncio.run(scenario())
    assert fourth["status"] == 429 and b"DEMASIADAS_SOLICITUDES" in fourth["body"]
    assert otherStatus == 200
    assert again[1]["status"] == 200, "al cerrarse los streams el cupo vuelve a estar disponible"


def test_un_stream_termina_cuando_la_sesion_se_revoca(world, db, monkeypatch):
    app, _, tokens, sessions = world
    monkeypatch.setattr(streams, "STREAM_REVALIDATE_SECONDS", 0)
    path = "/api/v1/acquisition/stream"

    async def scenario():
        task, state, disconnect = await call(app, path, tokens["attacker"], hold=True)
        assert not task.done()
        db.execute(update(UserSession).where(UserSession.idSesion == sessions["attacker"].idSesion).values(fechaRevocacion=nowForDb()))
        db.commit()
        await asyncio.wait_for(task, 10)  # el servidor cierra el stream sin que el cliente se desconecte
        assert not disconnect.is_set() and state["error"] is None, state
        assert state["status"] == 200  # terminó de forma ordenada, no por un error

    asyncio.run(scenario())
    assert streams.registry.active() == 0


def test_el_registro_de_cupos_respeta_los_topes_y_release_es_idempotente():
    import uuid

    from app.core.exceptions import AuthError

    registry = streams.StreamRegistry(perUser=2, total=3)
    a, b = uuid.uuid4(), uuid.uuid4()
    slotA1, slotA2 = registry.acquire(a), registry.acquire(a)
    with pytest.raises(AuthError) as perUser:
        registry.acquire(a)
    slotB = registry.acquire(b)
    with pytest.raises(AuthError) as total:
        registry.acquire(b)
    assert perUser.value.code == total.value.code == "DEMASIADAS_SOLICITUDES"
    slotA1.release()
    slotA1.release()  # idempotente: no libera un cupo ajeno
    assert registry.active() == 2
    slotA2.release()
    slotB.release()
    assert registry.active() == 0
