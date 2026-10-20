# User - Usuario

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeDate, normalizeEmail, normalizeProperName, normalizeStatus, normalizeUpper
from app.utils.timeZone import nowArgentina

TipoCuenta = Literal["CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL", "ADMINISTRADOR_PLATAFORMA", "MODERADOR_PLATAFORMA"]
# Únicos tipos seleccionables en el registro público. Los tipos de plataforma
# (ADMINISTRADOR_PLATAFORMA, MODERADOR_PLATAFORMA) nunca se eligen desde el cliente.
TipoCuentaPublica = Literal["CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL"]
EstadoUsuario = Literal["PENDIENTE", "ACTIVO", "BLOQUEADO", "ELIMINADO"]
# Mismos valores que sexoModelo (CK_Usuario_sexo, 002_usuario_datos_personales.sql).
Sexo = Literal["MASCULINO", "FEMENINO"]
# Edad máxima admitida por las mediciones (CK_Medicion_edad).
EDAD_MAXIMA = 130


# Largo mínimo del username (medida de seguridad: evita identificadores triviales de adivinar).
USERNAME_MIN_LENGTH = 4


def validateUsername(value: str | None) -> str | None:
    """El "@" distingue correo de username al iniciar sesión; el username no puede quedar vacío.

    Se aplica al crear o elegir el username (registro local y perfil de una cuenta Google). Los espacios
    de los extremos no cuentan para el largo mínimo.
    """
    if value is None:
        return value
    if not value or "@" in value:
        raise ValueError("El nombre de usuario no puede estar vacío ni contener '@'.")
    if len(value.strip()) < USERNAME_MIN_LENGTH:
        raise ValueError(f"El nombre de usuario debe tener al menos {USERNAME_MIN_LENGTH} caracteres.")
    return value


class UserBase(BaseModel):
    nombre: Annotated[str, Field(max_length=100)] | None = None
    apellido: Annotated[str, Field(max_length=100)] | None = None
    # Username/login: se conserva tal cual (sin cambio de mayúsculas). Regla funcional pendiente.
    usuario: Annotated[str, Field(max_length=50)] | None = None

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)


class UserCreate(UserBase):
    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class UserUpdate(UserBase):
    model_config = ConfigDict(extra="forbid")


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    idUsuario: uuid.UUID
    correoElectronico: Annotated[EmailStr, Field(max_length=254)] | None = None
    tipoCuenta: TipoCuenta
    estado: EstadoUsuario
    fechaCreacion: datetime
    fechaActualizacion: datetime
    fechaEliminacion: datetime | None = None
    fechaNacimiento: date | None = None
    sexo: Sexo | None = None

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)

    @field_validator("tipoCuenta", mode="before")
    @classmethod
    def normalizarTipoCuenta(cls, value):
        return normalizeUpper(value)

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)

    @field_validator("sexo", mode="before")
    @classmethod
    def normalizarSexo(cls, value):
        return normalizeUpper(value)


class UserProfileUpdate(BaseModel):
    """Completar o actualizar los datos personales base del Usuario autenticado.

    Los campos omitidos no se modifican. Ninguno admite null: una vez completados no se borran.
    """

    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    apellido: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    # Username/login: se conserva tal cual (sin cambio de mayúsculas).
    usuario: Annotated[str, Field(max_length=50)] | None = None
    fechaNacimiento: date | None = None
    sexo: Sexo | None = None

    @field_validator("nombre", "apellido", "usuario", "fechaNacimiento", "sexo", mode="before")
    @classmethod
    def rechazarNulo(cls, value):
        if value is None:
            raise ValueError("No puede ser null; omitir el campo para no modificarlo.")
        return value

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)

    @field_validator("usuario")
    @classmethod
    def validarUsuario(cls, value: str | None) -> str | None:
        return validateUsername(value)

    @field_validator("fechaNacimiento", mode="before")
    @classmethod
    def normalizarFechaNacimiento(cls, value):
        return normalizeDate(value)

    @field_validator("fechaNacimiento")
    @classmethod
    def validarFechaNacimiento(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = nowArgentina().date()
        if value > today:
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age > EDAD_MAXIMA:
            raise ValueError(f"La edad no puede superar los {EDAD_MAXIMA} años.")
        return value

    @field_validator("sexo", mode="before")
    @classmethod
    def normalizarSexo(cls, value):
        return normalizeUpper(value)
