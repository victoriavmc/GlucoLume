# SubscriptionUser - SuscripcionUsuario
#
# Relación usuario-suscripción. Sin objetos anidados: solo identificadores.
# esTitular lo asigna el servidor; la baja es una operación de negocio (sin Update).

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeStatus

EstadoSuscripcionUsuario = Literal["ACTIVA", "BAJA"]


class SubscriptionUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idSuscripcion: uuid.UUID
    idUsuario: uuid.UUID


class SubscriptionUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idSuscripcionUsuario: uuid.UUID
    idSuscripcion: uuid.UUID
    idUsuario: uuid.UUID
    esTitular: bool
    estadoRelacion: EstadoSuscripcionUsuario
    fechaIncorporacion: datetime
    fechaBaja: datetime | None = None

    @field_validator("estadoRelacion", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
