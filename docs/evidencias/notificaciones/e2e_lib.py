"""Cliente HTTP mínimo para las pruebas de extremo a extremo (backend real en Docker + SQL Server descartable)."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18000/api/v1"
PW = "Glucolume#Prueba2026"
SMTP_FILE = None


def call(method, path, token=None, body=None, ua=None, expect=None):
    headers = {"Accept": "application/json", "User-Agent": ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    payload = json.loads(raw) if raw else None
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} -> {status} (esperaba {expect}): {payload}")
    return status, payload


def login(usuario, ua=None, password=None):
    status, payload = call("POST", "/auth/login", body={"identificador": usuario, "password": password or PW}, ua=ua, expect=200)
    assert payload["estado"] == "AUTENTICADO", payload
    return payload["tokens"]["accessToken"]


def mails(path):
    try:
        return [json.loads(line) for line in open(path, encoding="utf-8")]
    except FileNotFoundError:
        return []


CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

RESULTS = []


def check(name, condition, evidence=""):
    RESULTS.append((name, bool(condition), evidence))
    print(("PASA   " if condition else "FALLA  ") + name + (f"  [{evidence}]" if evidence else ""), flush=True)
