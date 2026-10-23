# Límites de solicitudes compartidos entre réplicas (H-06). Usa un redis-server REAL y descartable (127.0.0.1, puerto libre, sin persistencia,
# datos sintéticos) que la propia prueba levanta y baja; si el binario no está instalado, estas pruebas se omiten. Dos objetos RateLimiter con
# el mismo nombre simulan dos réplicas distintas (cada una con su memoria local).

import shutil
import socket
import subprocess
import time

import pytest
from pydantic import ValidationError

from app.api import rateLimit
from app.core.config import Settings, getSettings
from app.services import rateLimiter as rateLimiterModule
from app.services.rateLimiter import RateLimiter

pytestmark = pytest.mark.skipif(shutil.which("redis-server") is None, reason="redis-server no está instalado")

BASE = {"_env_file": None, "DB_HOST": "h", "DB_NAME": "n", "DB_USER": "u", "DB_PASSWORD": "p", "JWT_SECRET": "j" * 40}


def freePort() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RedisServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self.process = None

    @property
    def url(self) -> str:
        return f"redis://127.0.0.1:{self.port}/0"

    def start(self) -> None:
        self.process = subprocess.Popen(["redis-server", "--port", str(self.port), "--bind", "127.0.0.1", "--save", "", "--appendonly", "no",
                                         "--daemonize", "no", "--loglevel", "warning"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import redis

        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                redis.Redis.from_url(self.url).ping()
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        raise RuntimeError("redis-server no arrancó")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None

    def keys(self) -> list[bytes]:
        import redis

        return redis.Redis.from_url(self.url).keys("*")


@pytest.fixture
def server():
    redisServer = RedisServer(freePort())
    redisServer.start()
    yield redisServer
    redisServer.stop()


@pytest.fixture
def shared(server, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", server.url)
    monkeypatch.setenv("RATE_LIMIT_REDIS_RETRY_SECONDS", "0.5")
    getSettings.cache_clear()
    yield server
    getSettings.cache_clear()


def replica(name: str, limit: int = 3, window: float = 60) -> RateLimiter:
    """Una «réplica»: un objeto propio (memoria local propia) que cuenta en el mismo Redis bajo el mismo nombre."""
    limiter = RateLimiter(limit, window, name=name)
    limiter.clear()
    return limiter


def test_sin_redis_configurado_todo_sigue_en_memoria_y_no_se_usa_el_cliente(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    getSettings.cache_clear()
    limiter = RateLimiter(2, 60, name="prueba:local")
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]
    assert rateLimiterModule.sharedBackend()[0] is None


def test_dos_replicas_comparten_la_cuota_en_lugar_de_multiplicarla(shared):
    a, b = replica("prueba:cuota"), replica("prueba:cuota")
    results = [a.allow("203.0.113.9"), b.allow("203.0.113.9"), a.allow("203.0.113.9"), b.allow("203.0.113.9"), a.allow("203.0.113.9")]
    assert results == [True, True, True, False, False]  # 3 en total, no 3 por réplica
    assert b.exceeded("203.0.113.9") and a.exceeded("203.0.113.9")
    assert a.allow("198.51.100.1") and not b.exceeded("198.51.100.1")  # otra clave, otra cuota


def test_los_rechazos_no_alargan_el_bloqueo_y_la_ventana_se_desliza(shared):
    a, b = replica("prueba:ventana", limit=2, window=1), replica("prueba:ventana", limit=2, window=1)
    assert [a.allow("k"), b.allow("k"), a.allow("k"), b.allow("k")] == [True, True, False, False]
    import redis

    assert redis.Redis.from_url(shared.url).zcard(shared.keys()[0]) == 2  # los rechazados no quedaron registrados
    time.sleep(1.2)
    assert not a.exceeded("k") and b.allow("k")


def test_redis_no_guarda_direcciones_ni_correos_en_claro(shared):
    limiter = replica("prueba:privacidad")
    limiter.allow("203.0.113.77")
    limiter.allow("persona.privada@example.com")
    stored = b" ".join(shared.keys())
    assert b"203.0.113.77" not in stored and b"persona.privada" not in stored and b"example.com" not in stored
    assert all(key.startswith(b"glucolume:rl:prueba:privacidad:") for key in shared.keys())


def test_un_limitador_sin_nombre_nunca_es_compartido(shared):
    a, b = RateLimiter(1, 60), RateLimiter(1, 60)
    assert a.allow("k") and b.allow("k")  # cada uno cuenta en su memoria
    assert shared.keys() == []


def test_dos_limitadores_con_el_mismo_nombre_y_otros_parametros_son_un_error():
    RateLimiter(5, 60, name="prueba:duplicado")
    RateLimiter(5, 60, name="prueba:duplicado")  # mismo nombre y mismos parámetros: son la misma cuota
    with pytest.raises(ValueError, match="parámetros distintos"):
        RateLimiter(6, 60, name="prueba:duplicado")


def test_si_redis_cae_con_politica_local_se_sigue_contando_en_memoria_y_no_se_reintenta_en_cada_pedido(shared, monkeypatch):
    limiter = replica("prueba:caida", limit=2)
    assert limiter.allow("k")
    shared.stop()
    attempts = []
    backend = rateLimiterModule.sharedBackend()[0]
    original = backend._client.pipeline
    monkeypatch.setattr(backend._client, "pipeline", lambda *a, **k: attempts.append(1) or original(*a, **k))
    results = [limiter.allow("k") for _ in range(4)]
    assert results == [True, True, False, False]  # nunca más débil que sin Redis: el límite local rige
    assert len(attempts) == 1  # corte de circuito: una sola consulta fallida, no una por pedido
    shared.start()
    time.sleep(0.6)  # vence RATE_LIMIT_REDIS_RETRY_SECONDS: vuelve a usar Redis
    other = replica("prueba:caida", limit=2)
    assert other.allow("zzz") and attempts


def test_si_redis_cae_con_politica_deny_se_rechaza_y_al_volver_se_recupera(shared, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ON_FAILURE", "deny")
    getSettings.cache_clear()
    limiter = replica("prueba:deny")
    assert limiter.allow("k")
    shared.stop()
    assert limiter.allow("k") is False and limiter.exceeded("k") is True
    shared.start()
    time.sleep(0.6)
    assert limiter.allow("k-nueva") is True


def test_un_redis_inalcanzable_desde_el_arranque_aplica_la_politica_sin_romper_el_servicio(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", f"redis://127.0.0.1:{freePort()}/0")
    getSettings.cache_clear()
    limiter = replica("prueba:inalcanzable", limit=1)
    assert [limiter.allow("k"), limiter.allow("k")] == [True, False]
    getSettings.cache_clear()


def test_los_endpoints_publicos_comparten_el_limite_entre_replicas(shared, monkeypatch):
    # El mismo límite de login contado por «otra réplica»: aunque la memoria local esté vacía, Redis ya sabe cuántos pedidos hubo.
    limiter = rateLimit._limiters["resend"]
    maximum = rateLimit.LIMITS["resend"][0]
    ip = "203.0.113.50"
    assert all(limiter.allow(ip) for _ in range(maximum))
    limiter.clear()  # una réplica nueva arranca con la memoria vacía
    assert limiter.allow(ip) is False
    assert rateLimit.bridgeFailures.name == "puente:fallos" and limiter.name == "ip:resend"


def test_configuracion_de_redis_invalida_o_riesgosa():
    with pytest.raises(ValidationError, match="redis://"):
        Settings(**BASE, RATE_LIMIT_REDIS_URL="http://servidor:6379")
    with pytest.raises(ValidationError):
        Settings(**BASE, RATE_LIMIT_REDIS_TIMEOUT_SECONDS=0)
    with pytest.raises(ValidationError):
        Settings(**BASE, RATE_LIMIT_ON_FAILURE="ignorar")
    assert "sin cifrar" in " ".join(Settings(**BASE, API_ENV="production", RATE_LIMIT_REDIS_URL="redis://otra-maquina:6379/0").securityWarnings())
    assert "sin cifrar" not in " ".join(Settings(**BASE, API_ENV="production", RATE_LIMIT_REDIS_URL="rediss://otra-maquina:6379/0").securityWarnings())
    assert "rechazan todo" in " ".join(Settings(**BASE, RATE_LIMIT_ON_FAILURE="deny", RATE_LIMIT_REDIS_URL="redis://127.0.0.1:6379/0").securityWarnings())
    assert "rechazan todo" not in " ".join(Settings(**BASE, RATE_LIMIT_REDIS_URL="redis://127.0.0.1:6379/0").securityWarnings())
    secret = "redis://:clave-sintetica-123@127.0.0.1:6379/0"
    assert "clave-sintetica-123" not in repr(Settings(**BASE, RATE_LIMIT_REDIS_URL=secret)) and \
        "clave-sintetica-123" not in " ".join(Settings(**BASE, RATE_LIMIT_REDIS_URL=secret).securityWarnings())
