# CapillaryReferenceMeasurement - MedicionReferenciaCapilar

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeDateTime, normalizeSentence

Glucosa = Annotated[Decimal, Field(max_digits=8, decimal_places=2, ge=0)]


class CapillaryReferenceMeasurementBase(BaseModel):
    glucosaReferencia: Glucosa
    fechaHoraReferencia: datetime
    # Marca y modelo comerciales (p. ej. "OneTouch"): se conservan tal cual.
    marcaGlucometro: Annotated[str, Field(max_length=100)] | None = None
    modeloGlucometro: Annotated[str, Field(max_length=100)] | None = None
    observacion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("fechaHoraReferencia", mode="before")
    @classmethod
    def normalizarFechaHora(cls, value):
        return normalizeDateTime(value)

    @field_validator("observacion", mode="before")
    @classmethod
    def normalizarObservacion(cls, value):
        return normalizeSentence(value)


class CapillaryReferenceMeasurementCreate(CapillaryReferenceMeasurementBase):
    model_config = ConfigDict(extra="forbid")

    idMedicion: uuid.UUID


class CapillaryReferenceMeasurementUpdate(CapillaryReferenceMeasurementBase):
    model_config = ConfigDict(extra="forbid")

    glucosaReferencia: Glucosa | None = None
    fechaHoraReferencia: datetime | None = None


class CapillaryReferenceMeasurementRead(CapillaryReferenceMeasurementBase):
    model_config = ConfigDict(from_attributes=True)

    idMedicionReferencia: uuid.UUID
    idMedicion: uuid.UUID
