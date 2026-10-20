# Subscription - Suscripcion
#
# El titular es el usuario autenticado o la institución indicada (CK_Suscripcion_titular);
# idUsuarioTitular lo asigna el servidor. estado, fechas, origenContratacion y
# referenciaContrato los gestiona el servidor o el canal de ventas.

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

EstadoSuscripcion = Literal["PENDIENTE", "ACTIVA", "VENCIDA", "SUSPENDIDA", "CANCELADA"]
OrigenContratacion = Literal["ONLINE", "CANAL_VENTAS"]


class SubscriptionBase(BaseModel):
    renovacionAutomatica: bool = False


class SubscriptionCreate(SubscriptionBase):
    model_config = ConfigDict(extra="forbid")

    idPlan: uuid.UUID
    idInstitucion: uuid.UUID | None = None


class SubscriptionUpdate(SubscriptionBase):
    model_config = ConfigDict(extra="forbid")

    renovacionAutomatica: bool | None = None


class SubscriptionRead(SubscriptionBase):
    model_config = ConfigDict(from_attributes=True)

    idSuscripcion: uuid.UUID
    idPlan: uuid.UUID
    idUsuarioTitular: uuid.UUID | None = None
    idInstitucion: uuid.UUID | None = None
    estado: EstadoSuscripcion
    fechaInicio: datetime
    fechaFin: datetime | None = None
    renovacionAutomatica: bool
    origenContratacion: OrigenContratacion
    referenciaContrato: str | None = None
    fechaCreacion: datetime

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)

    @field_validator("origenContratacion", mode="before")
    @classmethod
    def normalizarOrigen(cls, value):
        return normalizeUpper(value)
