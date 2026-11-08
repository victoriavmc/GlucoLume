# Reglas de M-2 aprobadas (auditoría 07/11/2026). Cubren lo que el usuario exigió después de la primera implementación:
#  - el límite del login es por (cuenta, origen): 5 fallos en 15 min y 15 en 1 h;
#  - los intentos bloqueados quedan trazados en INTENTO_INGRESO, distinguidos de las contraseñas incorrectas, y acotados (una traza por
#    cuenta, origen y ventana), sin guardar la IP en claro;
#  - la respuesta y el trabajo de la solicitud no dependen de que la cuenta exista (protección contra enumeración, también por tiempo);
#  - la reconfirmación de la contraseña dentro de una sesión bloquea SOLO su operación y su usuario, sin afectar al login;
#  - el origen lo fija el socket (no una cabecera del cliente) y el límite no se multiplica por procesos.

import re
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from app.db.session import getDb
from app.main import app
from app.models.localCredential import LocalCredential
from app.services import auth as authService
from app.services import email as emailService
from app.services import userNotifications as service
from app.utils.userAgent import ClientInfo
from tests.test_account_deletion import EMAIL, PASSWORD, audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_login_lockout import FakeMonotonic, clock, steps  # noqa: F401 - fixtures de reloj

WRONG = "OtraClave#2026"
ORIGEN_A = "198.51.100.10"
ORIGEN_B = "198.51.100.20"
REPO = Path(__file__).resolve().parents[2]
TITULO_CONTRASENA = "Intento de ingreso rechazado"
TITULO_LIMITE = "Intento de ingreso bloqueado por seguridad"


def attempt(db, password=WRONG, ip=ORIGEN_A, identificador=EMAIL):
    try:
        return authService.loginLocal(db, identificador, password, ClientInfo(ip=ip))
    except AuthError as error:
        return error


def credential(db) -> LocalCredential:
    db.expire_all()
    return db.scalar(select(LocalCredential))


def intentos(db, user):
    return [n for n in service.inbox(db, user).notificaciones if n.evento == "INTENTO_INGRESO"]


# --- Trazabilidad de INTENTO_INGRESO --------------------------------------------------------------------------------------------------------


def test_los_intentos_bloqueados_quedan_trazados_una_vez_por_ventana_y_con_titulo_propio(db, mails, steps):
    user = makeUser(db)
    for _ in range(5):
        assert attempt(db).code == "CREDENCIALES_INVALIDAS"
    for _ in range(10):  # diez intentos ya bloqueados en la misma ventana
        assert attempt(db).code == "CUENTA_BLOQUEADA"

    titulos = Counter(n.titulo for n in intentos(db, user))
    assert titulos[TITULO_CONTRASENA] == 5  # una traza por contraseña incorrecta, como antes
    assert titulos[TITULO_LIMITE] == 1  # los bloqueados: una sola traza para toda la ventana (sin registros sin fin)
    assert len(mails) == 1  # el correo de actividad sospechosa sale una vez, al activarse el límite

    # La traza no guarda la dirección de origen en ningún campo visible ni en la clave de deduplicación.
    for n in service.inbox(db, user).notificaciones:
        for valor in (n.titulo, n.mensaje, n.url or "", getattr(n, "claveEvento", "") or ""):
            assert ORIGEN_A not in valor


def test_una_ventana_nueva_genera_una_nueva_traza(db, mails, steps, clock):
    user = makeUser(db)
    for _ in range(5):
        attempt(db)
    attempt(db)  # primera traza de la ventana
    clock.advance(minutes=16)  # la ventana del reloj de la aplicación avanza y el límite de 15 min se libera
    steps.advance(16 * 60)
    for _ in range(5):
        attempt(db)
    attempt(db)  # segunda traza, en la nueva ventana
    assert Counter(n.titulo for n in intentos(db, user))[TITULO_LIMITE] == 2


# --- Enumeración: respuesta y trabajo iguales para cuentas existentes e inexistentes --------------------------------------------------


def test_respuesta_y_trabajo_de_la_solicitud_no_revelan_si_la_cuenta_existe(db, mails, steps, monkeypatch):
    makeUser(db)
    llamadas = []
    original = emailService.runInBackground

    def contando(tarea, *args):
        llamadas.append(tarea.__name__)
        return original(tarea, *args)

    monkeypatch.setattr(emailService, "runInBackground", contando)

    def secuencia(identificador, ip):
        resultados = []
        for _ in range(7):
            antes = len(llamadas)
            r = attempt(db, identificador=identificador, ip=ip)
            resultados.append((r.code, r.message, r.retryAfterSeconds is not None, len(llamadas) - antes))
        return resultados

    existente = secuencia(EMAIL, ORIGEN_A)
    inexistente = secuencia("nadie.inexistente@example.com", ORIGEN_B)
    # Mismo código, mismo mensaje, mismo tipo de Retry-After y mismo número de tareas programadas en cada solicitud.
    assert existente == inexistente
    assert existente[0][0] == "CREDENCIALES_INVALIDAS" and existente[6][0] == "CUENTA_BLOQUEADA"


# --- Reconfirmación de la contraseña dentro de una sesión ----------------------------------------------------------------------------------


def test_la_reconfirmacion_bloquea_solo_su_operacion_y_no_el_login(db, mails, steps):
    makeUser(db)
    row = credential(db)
    for _ in range(3):
        assert authService.verifyCurrentPassword(db, row, WRONG, "cambio_contrasena") is False
        db.commit()
    with pytest.raises(AuthError) as bloqueada:
        authService.verifyCurrentPassword(db, row, PASSWORD, "cambio_contrasena")
    assert bloqueada.value.code == "CUENTA_BLOQUEADA" and bloqueada.value.retryAfterSeconds >= 1

    # Otra operación del mismo usuario sigue disponible, y el login con la contraseña correcta también.
    assert authService.verifyCurrentPassword(db, row, PASSWORD, "eliminacion_cuenta") is True
    db.commit()
    assert attempt(db, PASSWORD).estado == "AUTENTICADO"


def test_la_reconfirmacion_es_por_usuario(db, mails, steps):
    victima = makeUser(db)
    makeUser(db, email="otra.persona@example.com", usuario="otra")
    row_victima = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario == victima.idUsuario))
    otra = db.scalar(select(LocalCredential).where(LocalCredential.idUsuario != victima.idUsuario))
    for _ in range(3):
        authService.verifyCurrentPassword(db, row_victima, WRONG, "cambio_contrasena")
        db.commit()
    with pytest.raises(AuthError):
        authService.verifyCurrentPassword(db, row_victima, PASSWORD, "cambio_contrasena")
    # El otro usuario, con la misma operación, no se ve afectado.
    assert authService.verifyCurrentPassword(db, otra, PASSWORD, "cambio_contrasena") is True


def test_la_reconfirmacion_se_libera_cuando_vence_la_ventana(db, mails, steps):
    makeUser(db)
    row = credential(db)
    for _ in range(3):
        authService.verifyCurrentPassword(db, row, WRONG, "cambio_contrasena")
        db.commit()
    with pytest.raises(AuthError):
        authService.verifyCurrentPassword(db, row, PASSWORD, "cambio_contrasena")
    steps.advance(15 * 60 + 1)
    assert authService.verifyCurrentPassword(db, row, PASSWORD, "cambio_contrasena") is True


# --- Un tercero no bloquea a la víctima --------------------------------------------------------------------------------------------------


def test_un_tercero_desde_otro_origen_no_bloquea_el_login_de_la_victima(db, mails, steps):
    makeUser(db)
    for _ in range(6):
        attempt(db, ip=ORIGEN_B)
    assert attempt(db, PASSWORD, ip=ORIGEN_A).estado == "AUTENTICADO"


# --- Origen: lo fija el socket, no una cabecera del cliente --------------------------------------------------------------------------------


@pytest.fixture
def http(engine):  # noqa: F811 - SQLite de prueba, como en las demás pruebas HTTP
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def getTestDb():
        session = makeSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[getDb] = getTestDb
    yield TestClient(app, raise_server_exceptions=False, client=("203.0.113.50", 50000))
    app.dependency_overrides.clear()


def test_las_cabeceras_de_origen_del_cliente_no_cambian_el_limite(db, mails, steps, http):
    makeUser(db)
    codigos = []
    for i in range(7):
        r = http.post("/api/v1/auth/login", json={"identificador": EMAIL, "password": WRONG},
                      headers={"X-Forwarded-For": f"198.51.100.{100 + i}", "X-Real-IP": f"192.0.2.{i}"})
        codigos.append(r.json().get("codigo"))
    # Cada intento llega con otra cabecera de origen: el límite sigue contando un único origen, el del socket.
    assert codigos[:5] == ["CREDENCIALES_INVALIDAS"] * 5 and codigos[5:] == ["CUENTA_BLOQUEADA"] * 2


# --- Un solo proceso: el contador en memoria no se multiplica --------------------------------------------------------------------------


def test_el_backend_corre_con_un_solo_proceso_y_el_limite_es_exacto():
    dockerfile = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    cmd = re.search(r"^CMD \[(.*)\]\s*$", dockerfile, re.M).group(1)
    assert "--workers" not in cmd, "con varios workers cada proceso cuenta por separado (sin RATE_LIMIT_REDIS_URL)"
    archivos = [REPO / "compose.yaml", REPO / "compose.prod.yaml", REPO / ".env.example", REPO / "backend" / "Dockerfile"]
    for archivo in archivos:
        assert "WEB_CONCURRENCY" not in archivo.read_text(encoding="utf-8"), archivo.name


# --- Auditoría de los intentos rechazados por el límite (conservada, una fila por intento) ----------------------------------------------

def _filas(db, accion, motivo):
    from app.models.audit import Audit
    from app.models.auditContext import AuditContext

    db.expire_all()
    rows = db.execute(
        select(Audit, AuditContext).join(AuditContext, AuditContext.idAuditoria == Audit.idAuditoria)
        .where(Audit.accion == accion, AuditContext.motivo == motivo).order_by(Audit.fechaHora, Audit.idAuditoria)
    ).all()
    return rows


def test_cada_intento_limitado_queda_auditado_una_vez_y_sin_IP_en_claro(db, mails, steps):
    from app.models.audit import Audit

    user = makeUser(db)
    for _ in range(5):
        attempt(db)
    for _ in range(10):
        assert attempt(db).code == "CUENTA_BLOQUEADA"
    filas = _filas(db, "LOGIN_LOCAL", "CUENTA_BLOQUEADA")
    assert len(filas) == 10  # una fila por intento rechazado: no se descarta por no validar la contraseña, y no se duplica
    assert all(a.idUsuario == user.idUsuario for a, _ in filas)
    assert all(ORIGEN_A not in (a.observacion or "") for a, _ in filas)
    # La activación del límite sigue siendo un único evento propio.
    db.expire_all()
    assert len(db.scalars(select(Audit).where(Audit.accion == "BLOQUEO_TEMPORAL_CUENTA")).all()) == 1


def test_intento_limitado_de_cuenta_inexistente_se_audita_solo_con_hmac(db, mails, steps):
    makeUser(db)
    for _ in range(5):
        attempt(db, identificador="nadie.inexistente@example.com")
    for _ in range(3):
        attempt(db, identificador="nadie.inexistente@example.com")
    filas = [(a, c) for a, c in _filas(db, "LOGIN_LOCAL", "CUENTA_BLOQUEADA") if a.idUsuario is None]
    assert len(filas) == 3
    assert all(c.identificadorHash for _, c in filas)
    assert all("nadie.inexistente" not in (a.observacion or "") for a, _ in filas)
