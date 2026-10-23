"""H-06: DOS procesos reales de la API compartiendo un Redis real y descartable (Docker), con datos sintéticos.

Comprueba: (1) sin Redis cada instancia cuenta por su cuenta (el límite efectivo se duplica); (2) con Redis la cuota es una sola entre ambas;
(3) Redis no guarda IP ni identificadores; (4) caída de Redis con política `local` (la API sigue respondiendo y cuenta en memoria) y recuperación;
(5) caída con política `deny` (rechaza) y recuperación. Uso: python redis_multi_instancia.py   (necesita docker, la imagen redis:7-alpine y el
entorno virtual del backend). No toca ninguna base real: cada instancia usa un SQLite temporal.
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "servidor_sintetico.py")
RPW = "Redis" + os.urandom(6).hex()  # contraseña sintética de un Redis descartable
CONTAINER = "gl-redis-h06"
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("OK    " if ok else "FALLA ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def redis_up():
    sh("docker", "rm", "-f", CONTAINER)
    r = sh("docker", "run", "-d", "--name", CONTAINER, "-p", "127.0.0.1:16379:6379", "redis:7-alpine", "redis-server", "--requirepass", RPW, "--save", "", "--appendonly", "no")
    assert r.returncode == 0, r.stderr
    for _ in range(50):
        if "PONG" in sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "ping").stdout:
            return
        time.sleep(0.2)
    raise SystemExit("redis no arrancó")


def start_instance(port, env_extra):
    env = {**os.environ, "PORT": str(port), **env_extra}
    p = subprocess.Popen([sys.executable, SERVER], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return p
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    p.kill()
    raise SystemExit(f"la instancia {port} no arrancó")


def login_attempt(port):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/auth/login", method="POST",
                                 data=json.dumps({"identificador": "persona.inexistente", "password": "Clave#Falsa2026"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:  # noqa: BLE001
        return 0


def burst(ports, n):
    return [login_attempt(ports[i % len(ports)]) for i in range(n)]


def accepted(codes):  # no-429 = la API dejó pasar el intento (401 credenciales inválidas)
    return sum(1 for c in codes if c == 401)


def run(env_extra, ports=(18001, 18002)):
    return [start_instance(p, env_extra) for p in ports], list(ports)


def stop(procs):
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


LIMIT = 60  # app/api/rateLimit.py: login = 60 por 10 minutos y por IP

print("== 1. SIN Redis: dos instancias, cada una cuenta aparte")
procs, ports = run({})
codes = burst(ports, 2 * LIMIT + 10)
check("sin Redis el límite efectivo se multiplica por el número de réplicas", accepted(codes) == 2 * LIMIT, f"aceptados={accepted(codes)} de {len(codes)}, 429={codes.count(429)}")
stop(procs)

print("== 2. CON Redis compartido: una sola cuota entre las dos instancias")
redis_up()
base = {"RATE_LIMIT_REDIS_URL": f"redis://:{RPW}@127.0.0.1:16379/0", "RATE_LIMIT_REDIS_RETRY_SECONDS": "2", "RATE_LIMIT_REDIS_TIMEOUT_SECONDS": "0.5"}
procs, ports = run({**base, "RATE_LIMIT_ON_FAILURE": "local"})
codes = burst(ports, 2 * LIMIT + 10)
check("con Redis la cuota es compartida (no se duplica)", accepted(codes) == LIMIT, f"aceptados={accepted(codes)} de {len(codes)}, 429={codes.count(429)}")
a_first = [login_attempt(ports[0]) for _ in range(3)]
b_first = [login_attempt(ports[1]) for _ in range(3)]
check("una instancia ve el bloqueo causado por la otra", set(a_first + b_first) == {429}, str(a_first + b_first))
keys = sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "--scan").stdout.split()
check("Redis tiene claves del limitador", len(keys) > 0, f"{len(keys)} claves")
dump = " ".join(keys)
check("las claves no contienen IP ni identificadores en claro", "127.0.0.1" not in dump and "persona" not in dump and "inexistente" not in dump, keys[0] if keys else "")

print("== 3. Caída de Redis con política local: la API sigue respondiendo y cuenta en memoria")
stop(procs)
procs, ports = run({**base, "RATE_LIMIT_ON_FAILURE": "local"})
sh("docker", "stop", CONTAINER)
codes = burst(ports, 8)
check("Redis caído (local): ninguna respuesta 5xx ni conexión rota", all(c in (401, 429) for c in codes), str(sorted(set(codes))))
codes = burst(ports, 2 * LIMIT + 10)
check("Redis caído (local): sigue limitando en memoria (nunca más débil que sin Redis)", codes.count(429) > 0 and accepted(codes) <= 2 * LIMIT, f"429={codes.count(429)}")
sh("docker", "start", CONTAINER)
time.sleep(1)
redis_ready = False
for _ in range(50):
    if "PONG" in sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "ping").stdout:
        redis_ready = True
        break
    time.sleep(0.2)
check("Redis vuelve", redis_ready)
sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "flushall")
time.sleep(3)  # RATE_LIMIT_REDIS_RETRY_SECONDS=2: las instancias vuelven a intentar
codes = burst(ports, 2 * LIMIT + 10)
check("tras la recuperación vuelve la cuota compartida", accepted(codes) <= LIMIT + 2, f"aceptados={accepted(codes)}")
stop(procs)

print("== 4. Caída de Redis con política deny: rechaza mientras dure y se recupera")
sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "flushall")
procs, ports = run({**base, "RATE_LIMIT_ON_FAILURE": "deny"})
check("Redis sano (deny): se atiende normalmente", login_attempt(ports[0]) == 401)
sh("docker", "stop", CONTAINER)
codes = burst(ports, 6)
check("Redis caído (deny): se rechaza (429) en vez de dejar pasar sin límite", set(codes) == {429}, str(sorted(set(codes))))
sh("docker", "start", CONTAINER)
for _ in range(50):
    if "PONG" in sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "ping").stdout:
        break
    time.sleep(0.2)
sh("docker", "exec", CONTAINER, "redis-cli", "-a", RPW, "--no-auth-warning", "flushall")
time.sleep(3)
check("Redis vuelve (deny): se atiende de nuevo", login_attempt(ports[0]) == 401)
stop(procs)

sh("docker", "rm", "-f", CONTAINER)
print(f"\nRESUMEN: {sum(results)} correctas, {len(results) - sum(results)} con falla")
sys.exit(0 if all(results) else 1)
