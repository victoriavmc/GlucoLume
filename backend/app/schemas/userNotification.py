# UserNotification - contratos de la sección «Notificaciones» (preferencias por canal, horario de medición y avisos de la página).
#
# El horario lo validan aquí (formato HH:MM, intervalos fijos) y el servicio lo guarda. La identidad sale siempre de la sesión.

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EventoAviso = Literal["INICIO_SESION", "AGREGADO_GRUPO", "RECORDATORIO_MEDICION", "NUEVA_ACCION_GRUPO"]
ModoRecordatorio = Literal["NINGUNO", "INTERVALO", "HORARIOS"]

INTERVALOS_HORAS = (1, 2, 3, 4, 6, 8, 12, 24)
MAX_HORARIOS = 6
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotificationPreferenceRead(BaseModel):
    evento: EventoAviso
    enPagina: bool
    porCorreo: bool


class ReminderScheduleRead(BaseModel):
    modo: ModoRecordatorio
    intervaloHoras: int | None = None
    horarios: list[str] = Field(default_factory=list)


class NotificationSettingsRead(BaseModel):
    preferencias: list[NotificationPreferenceRead]
    recordatorio: ReminderScheduleRead


class NotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enPagina: bool | None = None
    porCorreo: bool | None = None


class ReminderScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modo: ModoRecordatorio
    intervaloHoras: int | None = None
    horarios: list[str] = Field(default_factory=list, max_length=MAX_HORARIOS)

    @field_validator("horarios")
    @classmethod
    def horariosValidos(cls, value: list[str]) -> list[str]:
        if any(not _HORA.match(hora) for hora in value):
            raise ValueError("Cada horario debe tener el formato HH:MM.")
        return sorted(set(value))

    @model_validator(mode="after")
    def coherente(self):
        if self.modo == "INTERVALO" and self.intervaloHoras not in INTERVALOS_HORAS:
            raise ValueError("Elegí cada cuántas horas recordar medirte.")
        if self.modo == "HORARIOS" and not self.horarios:
            raise ValueError("Elegí al menos un horario.")
        return self


class UserNotificationRead(BaseModel):
    idNotificacion: uuid.UUID
    evento: EventoAviso
    titulo: str
    mensaje: str
    url: str | None
    fechaCreacion: datetime
    leida: bool


class UserNotificationInbox(BaseModel):
    noLeidas: int
    notificaciones: list[UserNotificationRead]
