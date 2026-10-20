# SensorSample - MuestraSensor
#
# Muestras crudas del sensor: inmutables una vez registradas, sin Update.

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

ValorNoNegativo = Annotated[int, Field(ge=0)]


class SensorSampleBase(BaseModel):
    numeroMuestra: ValorNoNegativo
    tiempoRelativoMs: ValorNoNegativo | None = None
    valorRed: ValorNoNegativo
    valorIR: ValorNoNegativo


class SensorSampleCreate(SensorSampleBase):
    model_config = ConfigDict(extra="forbid")

    idMedicion: uuid.UUID


class SensorSampleRead(SensorSampleBase):
    model_config = ConfigDict(from_attributes=True)

    idMuestraSensor: uuid.UUID
    idMedicion: uuid.UUID
