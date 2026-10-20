# ResultDelivery - EnvioResultado
#
# El estado del envío lo gestiona el servidor: sin Update.
# detalleError (detalle técnico del proveedor de correo) no se expone.
# correoDestino queda en NULL una vez enviado (CK_EnvioResultado_enviado).

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeEmail, normalizeStatus

EstadoEnvio = Literal["PENDIENTE", "ENVIADO", "FALLIDO"]


class ResultDeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idMedicion: uuid.UUID
    correoDestino: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoDestino", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


class ResultDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idEnvioResultado: uuid.UUID
    idMedicion: uuid.UUID
    correoDestino: Annotated[EmailStr, Field(max_length=254)] | None = None
    estadoEnvio: EstadoEnvio
    fechaSolicitud: datetime
    fechaEnvio: datetime | None = None

    @field_validator("correoDestino", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)

    @field_validator("estadoEnvio", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class ResultSendRequest(BaseModel):
    """Pedido de envío del resultado por correo. Cuenta individual: se envía a su propio correo (sin correoDestino).
    Paciente institucional: el operador indica el correo que el paciente le dio y confirma su autorización. El correo
    del paciente no se guarda: solo vive en el envío pendiente y se borra al terminar (CK_EnvioResultado_enviado)."""

    model_config = ConfigDict(extra="forbid")

    correoDestino: Annotated[EmailStr, Field(max_length=254)] | None = None
    pacienteAutoriza: bool = False

    @field_validator("correoDestino", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value) if value else None


class ResultSendRead(BaseModel):
    # CONFIRMACION_PENDIENTE: la dirección escrita no es la confirmada; el resultado sale cuando el paciente confirma desde su correo.
    estadoEnvio: Literal["PENDIENTE", "ENVIADO", "FALLIDO", "CONFIRMACION_PENDIENTE"]
    correoEnmascarado: str
    mensaje: str
