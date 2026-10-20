# NotificationConfig - ConfiguracionNotificacion
#
# idUsuario lo asigna el servidor (configuración del usuario autenticado).

import uuid
from datetime import datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeUpper

CanalNotificacion = Literal["WEB", "EMAIL"]


class NotificationConfigBase(BaseModel):
    habilitada: bool = True
    intervaloMinutos: Annotated[int, Field(gt=0)]
    horaInicio: time | None = None
    horaFin: time | None = None
    canal: CanalNotificacion = "WEB"

    @field_validator("canal", mode="before")
    @classmethod
    def normalizarCanal(cls, value):
        return normalizeUpper(value)


class NotificationConfigCreate(NotificationConfigBase):
    model_config = ConfigDict(extra="forbid")


class NotificationConfigUpdate(NotificationConfigBase):
    model_config = ConfigDict(extra="forbid")

    habilitada: bool | None = None
    intervaloMinutos: Annotated[int, Field(gt=0)] | None = None
    canal: CanalNotificacion | None = None


class NotificationConfigRead(NotificationConfigBase):
    model_config = ConfigDict(from_attributes=True)

    idConfiguracionNotificacion: uuid.UUID
    idUsuario: uuid.UUID
    habilitada: bool
    canal: CanalNotificacion
    fechaActualizacion: datetime
