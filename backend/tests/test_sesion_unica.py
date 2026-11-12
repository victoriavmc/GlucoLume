# Pruebas de la sesión única por cuenta: si la cuenta ya tiene una sesión vigente, un inicio nuevo con credenciales correctas se rechaza,
# no se abre otra sesión y el titular recibe un aviso por correo y en la página (aunque tenga apagado ese canal).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_sesion_unica.py -v

import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.models.notificationPreference import NotificationPreference
from app.models.userNotification import UserNotification
from app.models.userSession import UserSession
from app.services import auth as authService
from app.services import userNotifications
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    EMAIL,
    PASSWORD,
    db,
    engine,
    mails,
    makeUser,
)

WRONG = "OtraClave#2026"
ASUNTO_BLOQUEO = "Bloqueamos"


def sesionesVigentes(db) -> int:
    db.expire_all()
    return len(db.scalars(select(UserSession).where(UserSession.fechaRevocacion.is_(None))).all())


def avisosDeBloqueo(mails) -> list:
    return [mail for mail in mails if ASUNTO_BLOQUEO in mail["subject"]]


def test_segundo_inicio_con_sesion_vigente_se_rechaza(db, mails):
    makeUser(db)
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"

    with pytest.raises(AuthError) as error:
        authService.loginLocal(db, EMAIL, PASSWORD)

    assert error.value.code == "SESION_ACTIVA"
    assert sesionesVigentes(db) == 1  # no se abrió una segunda sesión


def test_el_titular_recibe_correo_y_aviso_en_la_pagina(db, mails):
    user = makeUser(db)
    authService.loginLocal(db, EMAIL, PASSWORD)

    with pytest.raises(AuthError):
        authService.loginLocal(db, EMAIL, PASSWORD)

    bloqueos = avisosDeBloqueo(mails)
    assert len(bloqueos) == 1
    assert bloqueos[0]["to"] == EMAIL
    avisos = db.scalars(select(UserNotification).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.evento == userNotifications.ACTIVIDAD_SOSPECHOSA
    )).all()
    assert len(avisos) == 1
    assert avisos[0].visible


def test_el_aviso_en_la_pagina_llega_aunque_la_cuenta_lo_tenga_apagado(db, mails):
    user = makeUser(db)
    db.add(NotificationPreference(
        idUsuario=user.idUsuario, evento=userNotifications.ACTIVIDAD_SOSPECHOSA, enPagina=False, porCorreo=False,
        fechaActualizacion=nowForDb(),
    ))
    db.commit()
    authService.loginLocal(db, EMAIL, PASSWORD)

    with pytest.raises(AuthError):
        authService.loginLocal(db, EMAIL, PASSWORD)

    avisos = db.scalars(select(UserNotification).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.evento == userNotifications.ACTIVIDAD_SOSPECHOSA
    )).all()
    assert len(avisos) == 1
    assert avisos[0].visible


def test_contrasena_incorrecta_no_avisa_ni_bloquea_con_mensaje_de_sesion(db, mails):
    makeUser(db)
    authService.loginLocal(db, EMAIL, PASSWORD)

    with pytest.raises(AuthError) as error:
        authService.loginLocal(db, EMAIL, WRONG)

    assert error.value.code == "CREDENCIALES_INVALIDAS"
    assert avisosDeBloqueo(mails) == []


def test_tras_cerrar_la_sesion_el_otro_dispositivo_puede_entrar(db, mails):
    makeUser(db)
    authService.loginLocal(db, EMAIL, PASSWORD)
    authService.logout(db, db.scalar(select(UserSession)))

    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    assert sesionesVigentes(db) == 1


def test_sesion_vencida_no_bloquea(db, mails, monkeypatch):
    makeUser(db)
    authService.loginLocal(db, EMAIL, PASSWORD)
    despues = nowForDb() + timedelta(days=getSettings().REFRESH_TOKEN_EXPIRE_DAYS + 1)
    monkeypatch.setattr(authService, "nowForDb", lambda: despues)

    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    assert avisosDeBloqueo(mails) == []


def test_renovar_el_token_del_mismo_dispositivo_no_se_bloquea(db, mails):
    makeUser(db)
    primera = authService.loginLocal(db, EMAIL, PASSWORD)

    rotada = authService.refreshSession(db, primera.tokens.refreshToken)

    assert rotada.refreshToken != primera.tokens.refreshToken
    assert avisosDeBloqueo(mails) == []


# --- Enlace «fui yo» del aviso: el titular cierra la sesión que quedó abierta y puede ingresar -------------------------------------------


def _enlacesDeLiberacion(mails) -> list[str]:
    """Tokens de los enlaces «fui yo» de los avisos de bloqueo, en orden de envío."""
    return [re.search(r"liberar-sesion\?token=([A-Za-z0-9_-]+)", mail["html"]).group(1) for mail in avisosDeBloqueo(mails)]


def _bloquearInicio(db) -> None:
    authService.loginLocal(db, EMAIL, PASSWORD)
    with pytest.raises(AuthError):
        authService.loginLocal(db, EMAIL, PASSWORD)


def test_el_enlace_fui_yo_cierra_la_sesion_anterior_y_permite_ingresar(db, mails):
    makeUser(db)
    _bloquearInicio(db)
    [token] = _enlacesDeLiberacion(mails)

    authService.liberarSesionesActivas(db, token)

    assert sesionesVigentes(db) == 0
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"
    assert sesionesVigentes(db) == 1


def test_el_enlace_fui_yo_sirve_una_sola_vez(db, mails):
    makeUser(db)
    _bloquearInicio(db)
    [token] = _enlacesDeLiberacion(mails)
    authService.liberarSesionesActivas(db, token)
    authService.loginLocal(db, EMAIL, PASSWORD)  # el titular ingresa; esta sesión nueva no debe caer con el mismo enlace

    with pytest.raises(AuthError) as error:
        authService.liberarSesionesActivas(db, token)

    assert error.value.code == "TOKEN_INVALIDO"
    assert sesionesVigentes(db) == 1


def test_el_enlace_fui_yo_vence(db, mails, monkeypatch):
    makeUser(db)
    _bloquearInicio(db)
    [token] = _enlacesDeLiberacion(mails)
    despues = nowForDb() + timedelta(minutes=getSettings().SESION_LIBERACION_MINUTOS + 1)
    monkeypatch.setattr(authService, "nowForDb", lambda: despues)

    with pytest.raises(AuthError) as error:
        authService.liberarSesionesActivas(db, token)

    assert error.value.code == "TOKEN_VENCIDO"
    assert sesionesVigentes(db) == 1  # un enlace vencido no cierra nada


def test_un_token_inventado_no_cierra_ninguna_sesion(db, mails):
    makeUser(db)
    _bloquearInicio(db)

    with pytest.raises(AuthError) as error:
        authService.liberarSesionesActivas(db, "token-inventado")

    assert error.value.code == "TOKEN_INVALIDO"
    assert sesionesVigentes(db) == 1


def test_un_aviso_nuevo_reemplaza_al_enlace_anterior(db, mails):
    makeUser(db)
    _bloquearInicio(db)
    with pytest.raises(AuthError):
        authService.loginLocal(db, EMAIL, PASSWORD)  # segundo intento bloqueado: emite un enlace nuevo
    primero, segundo = _enlacesDeLiberacion(mails)

    with pytest.raises(AuthError) as error:
        authService.liberarSesionesActivas(db, primero)
    assert error.value.code == "TOKEN_INVALIDO"
    assert sesionesVigentes(db) == 1

    authService.liberarSesionesActivas(db, segundo)
    assert sesionesVigentes(db) == 0
