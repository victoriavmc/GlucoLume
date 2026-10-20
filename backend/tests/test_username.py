# Pruebas de la validación del nombre de usuario (app/schemas/user.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_username.py -v
#
# No requieren base de datos ni envían correos.

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.user import USERNAME_MIN_LENGTH, UserProfileUpdate

PASSWORD = "Glucolume#Prueba2026"  # nosec B105 - contraseña de prueba


def register(usuario):
    return RegisterRequest(aceptaPoliticaPrivacidad=True, 
        nombre="Victoria", apellido="Cortés", correoElectronico="persona@example.com",
        usuario=usuario, password=PASSWORD,
    )


def test_minimo_es_cuatro():
    assert USERNAME_MIN_LENGTH == 4


@pytest.mark.parametrize("usuario", ["a", "ab", "abc", "   ab   ", "  abc"])
def test_registro_rechaza_username_corto(usuario):
    with pytest.raises(ValidationError) as error:
        register(usuario)
    assert "al menos 4 caracteres" in str(error.value)


@pytest.mark.parametrize("usuario", ["abcd", "vmc_2026", "x" * 50])
def test_registro_acepta_username_valido(usuario):
    assert register(usuario).usuario == usuario


def test_registro_sin_username_sigue_permitido():
    assert register(None).usuario is None


@pytest.mark.parametrize("usuario", ["", "ab@c", "abcd@example.com"])
def test_sigue_rechazando_vacio_y_arroba(usuario):
    with pytest.raises(ValidationError):
        register(usuario)


def test_perfil_rechaza_username_corto():
    # Una cuenta Google elige su username desde el perfil: misma regla.
    with pytest.raises(ValidationError) as error:
        UserProfileUpdate(usuario="abc")
    assert "al menos 4 caracteres" in str(error.value)
    assert UserProfileUpdate(usuario="abcd").usuario == "abcd"
