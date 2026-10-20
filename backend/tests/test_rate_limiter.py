# RateLimiter en memoria: purga amortizada, tope de claves y agrupación de IPv6 por /64.
#
#     python -m pytest tests/test_rate_limiter.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): con más de 5000 claves vigentes cada pedido recorría todas bajo el candado (≈22 ms con 100 000
# claves) y rotar la dirección IPv6 en cada pedido daba una clave nueva por pedido: el costo crecía sin tope y el límite se esquivaba.

from app.api.rateLimit import normalizeIp
from app.services.contact import RateLimiter


def test_la_purga_no_se_ejecuta_en_cada_pedido():
    limiter = RateLimiter(5, 3600)
    calls = []
    original = limiter._purge

    def counting(now):
        calls.append(now)
        original(now)

    limiter._purge = counting
    for i in range(RateLimiter.PURGE_THRESHOLD + 2000):  # todas las claves siguen vigentes: la purga no libera nada
        limiter.allow(f"ip-{i}", now=float(i) / 1000)  # unos 7 segundos de tráfico
    assert len(calls) <= 1, f"purga por pedido: {len(calls)} llamadas"


def test_el_numero_de_claves_tiene_tope_y_las_nuevas_comparten_un_cubo():
    limiter = RateLimiter(2, 3600)
    limiter.MAX_KEYS = 100
    for i in range(300):
        limiter.allow(f"ip-{i}", now=1.0)
    assert len(limiter._events) <= 101  # 100 claves + el cubo de desborde
    assert limiter.allow("otra-nueva", now=1.0) is False, "el cubo de desborde ya agotó su presupuesto conjunto"
    assert limiter.allow("ip-0", now=1.0) is True, "una clave ya conocida conserva su propio presupuesto"


def test_las_claves_vencidas_se_descartan_pasado_el_intervalo():
    limiter = RateLimiter(1, 10)
    for i in range(RateLimiter.PURGE_THRESHOLD + 10):
        limiter.allow(f"ip-{i}", now=0.0)
    limiter.allow("nueva", now=100.0)
    assert len(limiter._events) < 10


def test_ipv6_se_agrupa_por_prefijo_64_e_ipv4_queda_exacta():
    assert normalizeIp("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == normalizeIp("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert normalizeIp("2001:db8:1:3::1") != normalizeIp("2001:db8:1:2::1")
    assert normalizeIp("203.0.113.7") == "203.0.113.7"
    assert normalizeIp("::ffff:203.0.113.7") == "203.0.113.7"  # IPv4 mapeada: es el mismo cliente
    assert normalizeIp("testclient") == "testclient" and normalizeIp(None) == "desconocido"


def test_rotar_la_direccion_ipv6_dentro_del_64_no_evita_el_limite():
    limiter = RateLimiter(3, 3600)
    results = [limiter.allow(normalizeIp(f"2001:db8:9:9::{i:x}"), now=1.0) for i in range(1, 8)]
    assert results == [True, True, True, False, False, False, False]
