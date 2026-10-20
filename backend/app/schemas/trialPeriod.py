# TrialPeriod - PeriodoPrueba
#
# Gestionado íntegramente por el servidor (alta, reactivación, vencimiento): solo lectura.

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

EstadoPeriodoPrueba = Literal["ACTIVO", "VENCIDO", "CANCELADO"]
OrigenPeriodoPrueba = Literal["PRIMER_ALTA", "REACTIVACION"]


class TrialPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idPeriodoPrueba: uuid.UUID
    idUsuario: uuid.UUID | None = None
    idInstitucion: uuid.UUID | None = None
    numeroPeriodo: int
    origen: OrigenPeriodoPrueba
    fechaInicio: datetime
    fechaFin: datetime
    estado: EstadoPeriodoPrueba

    @field_validator("origen", mode="before")
    @classmethod
    def normalizarOrigen(cls, value):
        return normalizeUpper(value)

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
