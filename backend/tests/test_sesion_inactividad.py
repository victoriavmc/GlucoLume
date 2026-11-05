# Pruebas del cierre de sesión por inactividad (SesionUsuario.ultimaActividad y SESION_INACTIVIDAD_MINUTOS).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_sesion_inactividad.py -v

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.exceptions import AuthError
from app.models.userSession import UserSession
from app.services import auth as authService
from app.services import schemaCompat
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeUser,
)


@pytest.fixture
def clock(monkeypatch):
    """Reloj controlable del servicio de autenticación."""

    class Clock:
        now = nowForDb()

        def advance(self, **delta):
            self.now += timedelta(**delta)

    current = Clock()
    monkeypatch.setattr(authService, "nowForDb", lambda: current.now)
    return current


def loginYSesion(db):
    user = makeUser(db)
    tokens = authService.loginLocal(db, EMAIL, PASSWORD).tokens
    session = db.scalar(select(UserSession))
    return user, tokens, session


def pedido(db, user, session):
    """Un pedido autenticado: el access token resuelve la sesión."""
    return authService.resolveAccessSession(db, {"sub": str(user.idUsuario), "sid": str(session.idSesion)})


def sesionRevocada(db, session) -> bool:
    db.expire_all()
    return db.get(UserSession, session.idSesion).fechaRevocacion is not None


def test_sesion_sin_actividad_mas_de_15_minutos_se_cierra(db, mails, clock):
    user, _, session = loginYSesion(db)

    clock.advance(minutes=16)

    with pytest.raises(AuthError) as error:
        pedido(db, user, session)
    assert error.value.motivo == "SESION_INACTIVA"
    assert sesionRevocada(db, session)


def test_cada_pedido_renueva_la_actividad(db, mails, clock):
    user, _, session = loginYSesion(db)

    for _ in range(4):  # 40 minutos en total, pero nunca más de 10 sin actividad
        clock.advance(minutes=10)
        pedido(db, user, session)

    assert not sesionRevocada(db, session)


def test_renovar_el_token_cuenta_como_actividad(db, mails, clock):
    _, tokens, _ = loginYSesion(db)

    clock.advance(minutes=10)
    authService.refreshSession(db, tokens.refreshToken)
    clock.advance(minutes=10)  # 20 minutos desde el login, pero solo 10 desde la renovación

    nueva = db.scalar(select(UserSession).where(UserSession.fechaRevocacion.is_(None)))
    user = nueva.usuario
    pedido(db, user, nueva)  # sigue viva


def test_renovar_una_sesion_inactiva_la_cierra(db, mails, clock):
    _, tokens, _ = loginYSesion(db)

    clock.advance(minutes=16)

    with pytest.raises(AuthError) as error:
        authService.refreshSession(db, tokens.refreshToken)
    assert error.value.motivo == "SESION_INACTIVA"
    assert db.scalar(select(UserSession).where(UserSession.fechaRevocacion.is_(None))) is None


def test_el_sondeo_de_fondo_no_renueva_la_sesion(db, mails, clock):
    user, _, session = loginYSesion(db)

    for _ in range(3):  # una pestaña abierta que consulta cada minuto, sin ninguna acción del usuario
        clock.advance(minutes=5)
        authService.resolveAccessSession(db, {"sub": str(user.idUsuario), "sid": str(session.idSesion)}, renovarActividad=False)

    clock.advance(minutes=1)  # 16 minutos desde la última acción real
    with pytest.raises(AuthError) as error:
        authService.resolveAccessSession(db, {"sub": str(user.idUsuario), "sid": str(session.idSesion)}, renovarActividad=False)
    assert error.value.motivo == "SESION_INACTIVA"


def test_sesion_anterior_a_la_migracion_no_se_cierra_de_golpe(db, mails, clock):
    user, _, session = loginYSesion(db)
    db.execute(update(UserSession).values(ultimaActividad=None))
    db.commit()

    clock.advance(minutes=60)  # sin valor previo: queda activa desde este pedido

    assert pedido(db, user, session)[0].idUsuario == user.idUsuario
    assert not sesionRevocada(db, session)
    db.expire_all()
    assert db.get(UserSession, session.idSesion).ultimaActividad is not None


def test_una_sesion_inactiva_mas_de_15_minutos_no_bloquea_otro_equipo(db, mails, clock):
    loginYSesion(db)  # la cuenta queda con una sesión abierta y sin uso

    clock.advance(minutes=16)

    # Ya no está en uso: el otro equipo puede entrar.
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"


def test_una_sesion_usada_hace_poco_sigue_bloqueando_otro_equipo(db, mails, clock):
    user, _, session = loginYSesion(db)

    clock.advance(minutes=10)
    pedido(db, user, session)  # actividad a los 10 minutos
    clock.advance(minutes=6)  # 16 desde el login, pero 6 desde la última actividad

    with pytest.raises(AuthError) as error:
        authService.loginLocal(db, EMAIL, PASSWORD)
    assert error.value.code == "SESION_ACTIVA"


def test_sin_la_columna_la_inactividad_no_se_controla(db, mails, clock, monkeypatch):
    monkeypatch.setattr(schemaCompat, "sessionActivityReady", lambda db: False)  # base sin migrar
    user, _, session = loginYSesion(db)

    clock.advance(minutes=60)

    assert pedido(db, user, session)[0].idUsuario == user.idUsuario
    assert not sesionRevocada(db, session)
