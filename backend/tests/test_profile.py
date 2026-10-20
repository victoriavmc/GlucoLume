# Pruebas de perfil del usuario autenticado (PATCH /auth/me/profile, GET /auth/me).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_profile.py -v

import json
from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.user import User
from app.schemas.user import UserProfileUpdate
from app.services import auth as authService
from app.services import user as userService
from app.utils.timeZone import nowArgentina
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    db,
    engine,
    mails,
    makeUser,
    reload,
)


def test_actualizar_perfil_persiste_y_se_refleja_en_me(db, mails):
    user = makeUser(db)
    changed = userService.updateProfile(
        db, user, UserProfileUpdate(nombre="vicky", apellido="cortés lópez", usuario="vicky_2026",
                                    fechaNacimiento="1991-02-03", sexo="femenino"),
    )
    assert changed is True

    stored = reload(db, User, user.idUsuario)
    assert (stored.nombre, stored.apellido, stored.usuario, stored.fechaNacimiento, stored.sexo) == (
        "Vicky", "Cortés López", "vicky_2026", date(1991, 2, 3), "FEMENINO")
    summary = authService.accountSummary(db, stored)
    assert summary.usuario.usuario == "vicky_2026" and summary.usuario.nombre == "Vicky"

    audit = db.scalar(select(Audit).where(Audit.accion == "ACTUALIZAR_PERFIL"))
    assert "Vicky" not in (audit.datosNuevos or "") and json.loads(audit.datosNuevos)["nombre"] == {"estado": "ACTUALIZADO"}


def test_sin_cambios_reales_no_actualiza(db, mails):
    user = makeUser(db)
    assert userService.updateProfile(db, user, UserProfileUpdate(nombre="Victoria", usuario="victoria")) is False
    assert db.scalar(select(Audit).where(Audit.accion == "ACTUALIZAR_PERFIL")) is None


def test_username_duplicado(db, mails):
    makeUser(db, email="otra@example.com", usuario="ocupado")
    user = makeUser(db)
    with pytest.raises(AuthError) as error:
        userService.updateProfile(db, user, UserProfileUpdate(usuario="ocupado"))
    assert error.value.code == "USUARIO_NO_DISPONIBLE"
    assert reload(db, User, user.idUsuario).usuario == "victoria"


@pytest.mark.parametrize(
    "payload",
    [
        {"fechaNacimiento": (nowArgentina().date() + timedelta(days=1)).isoformat()},
        {"fechaNacimiento": "1880-01-01"},
        {"sexo": "OTRO"},
        {"usuario": "abc"},
        {"usuario": "con@arroba"},
        {"nombre": ""},
        {"nombre": None},
        {"correoElectronico": "nuevo@example.com"},
    ],
)
def test_validaciones_del_perfil(payload):
    with pytest.raises(ValidationError):
        UserProfileUpdate(**payload)


def test_fecha_de_nacimiento_de_hoy_es_valida():
    assert UserProfileUpdate(fechaNacimiento=nowArgentina().date().isoformat()).fechaNacimiento == nowArgentina().date()
