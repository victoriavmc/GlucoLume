# Pruebas de los avisos de la administración de la plataforma en la bandeja de «Notificaciones»: quién los recibe, qué texto
# muestran y que no se repiten. Los correos de estos hechos ya los prueba test_platform.py; aquí solo se comprueba la bandeja.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_platform_notifications.py -v

import uuid

import pytest

from app.core.exceptions import AuthError
from app.models import notificationEvents as avisos
from app.services import platform
from app.services import userNotifications as service
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser  # noqa: F401 - fixtures

ADMIN = "ADMINISTRADOR_PLATAFORMA"
MOD = "MODERADOR_PLATAFORMA"


def expectError(code, fn, *args, **kwargs) -> AuthError:
    with pytest.raises(AuthError) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.message
    return error.value


def bandeja(db, user):
    return service.inbox(db, user).notificaciones


def test_la_respuesta_a_una_transferencia_llega_a_la_bandeja_del_administrador(db, mails):
    admin = makeUser(db, tipoCuenta=ADMIN, email="admin@example.com", usuario="admin")
    moderador = makeUser(db, tipoCuenta=MOD, email="mod@example.com", usuario="mod")
    idTransferencia = uuid.uuid4()

    platform._notifyResponse(db, admin, moderador, True, nowForDb(), idTransferencia)

    rows = bandeja(db, admin)
    assert [r.evento for r in rows] == [avisos.PLATAFORMA_TRANSFERENCIA_RESPONDIDA]
    assert rows[0].titulo == "Transferencia aceptada"
    assert rows[0].categoria == "PLATAFORMA"
    assert rows[0].url == "/plataforma/transferencia"
    assert "aceptó" in rows[0].mensaje
    # Repetir la misma respuesta no crea otro aviso: el hecho es la transferencia.
    platform._notifyResponse(db, admin, moderador, True, nowForDb(), idTransferencia)
    assert len(bandeja(db, admin)) == 1


def test_un_rechazo_se_avisa_con_su_propio_texto(db, mails):
    admin = makeUser(db, tipoCuenta=ADMIN, email="admin@example.com", usuario="admin")
    moderador = makeUser(db, tipoCuenta=MOD, email="mod@example.com", usuario="mod")

    platform._notifyResponse(db, admin, moderador, False, nowForDb(), uuid.uuid4())

    [aviso] = bandeja(db, admin)
    assert aviso.titulo == "Transferencia rechazada"
    assert "rechazó" in aviso.mensaje


def test_un_moderador_que_activa_su_cuenta_avisa_al_administrador_una_vez_por_invitacion(db, mails):
    admin = makeUser(db, tipoCuenta=ADMIN, email="admin@example.com", usuario="admin")
    moderador = makeUser(db, tipoCuenta=MOD, email="mod@example.com", usuario="mod")
    invitacion = uuid.uuid4()

    platform._notifyModeratorActivated(db, moderador, invitacion)
    platform._notifyModeratorActivated(db, moderador, invitacion)  # el mismo enlace, dos veces: un solo aviso
    assert [r.evento for r in bandeja(db, admin)] == [avisos.PLATAFORMA_MODERADOR_ACTIVO]

    platform._notifyModeratorActivated(db, moderador, uuid.uuid4())  # una re-invitación posterior es otro hecho
    assert len(bandeja(db, admin)) == 2
    assert bandeja(db, moderador) == []  # el moderador no recibe su propio aviso


def test_la_activacion_del_administrador_no_avisa_a_nadie(db, mails):
    admin = makeUser(db, tipoCuenta=ADMIN, email="admin@example.com", usuario="admin")

    platform._notifyModeratorActivated(db, admin, uuid.uuid4())

    assert bandeja(db, admin) == []


def test_los_avisos_de_la_plataforma_son_solo_para_cuentas_de_administracion(db, mails):
    individual = makeUser(db, email="persona@example.com", usuario="persona")
    admin = makeUser(db, tipoCuenta=ADMIN, email="admin@example.com", usuario="admin")

    expectError("EVENTO_NO_VALIDO", service.assertEditable, individual, avisos.PLATAFORMA_MODERADOR_ACTIVO)
    service.assertEditable(admin, avisos.PLATAFORMA_MODERADOR_ACTIVO)  # no lanza: la administración puede elegir sus canales

    soloPlataforma = {e for e, spec in avisos.CATALOGO.items() if spec.plataforma}
    individuales = {p.evento for p in service.settings(db, individual).preferencias}
    administrativas = {p.evento for p in service.settings(db, admin).preferencias}
    assert soloPlataforma and not individuales & soloPlataforma
    assert soloPlataforma <= administrativas
