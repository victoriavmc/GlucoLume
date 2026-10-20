# Contact - Formulario de contacto público de la landing (no corresponde a una tabla)
#
# Mismos nombres de campo en frontend y backend: nombre, email, tipoConsulta, asunto, mensaje.

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeEmail, normalizeProperName

TipoConsulta = Literal["INFORMACION_GENERAL", "SUSCRIPCIONES", "SOPORTE", "INSTITUCIONES", "PRIVACIDAD", "OTRO"]

TIPO_CONSULTA_LABELS = {
    "INFORMACION_GENERAL": "Información general",
    "SUSCRIPCIONES": "Suscripciones",
    "SOPORTE": "Ayuda / Soporte",
    "INSTITUCIONES": "Instituciones",
    "PRIVACIDAD": "Privacidad y datos",
    "OTRO": "Otro",
}

NOMBRE_MAX = 100
ASUNTO_MAX = 150
MENSAJE_MIN = 10
MENSAJE_MAX = 2000


def _strip(value):
    return value.strip() if isinstance(value, str) else value


class ContactResponse(BaseModel):
    mensaje: str
    # True si además se envió la confirmación automática al correo de la persona.
    confirmacionEnviada: bool


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=NOMBRE_MAX)]
    email: Annotated[EmailStr, Field(max_length=254)]
    tipoConsulta: TipoConsulta = "INFORMACION_GENERAL"
    asunto: Annotated[str, Field(min_length=3, max_length=ASUNTO_MAX)]
    mensaje: Annotated[str, Field(min_length=MENSAJE_MIN, max_length=MENSAJE_MAX)]
    # Campo trampa (honeypot): oculto para las personas; si llega con contenido, es un envío automatizado.
    sitioWeb: Annotated[str, Field(max_length=200)] = ""

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)

    @field_validator("asunto", mode="before")
    @classmethod
    def normalizarAsunto(cls, value):
        # Una sola línea: el asunto se muestra en el cuerpo del correo y no admite saltos.
        value = _strip(value)
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("mensaje", mode="before")
    @classmethod
    def recortarMensaje(cls, value):
        return _strip(value)
