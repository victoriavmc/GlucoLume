# MatrixRule - ReglaMatriz

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.measurement import CondicionComida
from app.schemas.measurementProfile import SexoModelo
from app.utils.normalizers import normalizeUpper

Edad = Annotated[int, Field(ge=0, le=130)]
Minutos = Annotated[int, Field(ge=0)]
Glucosa = Annotated[Decimal, Field(max_digits=8, decimal_places=2, ge=0)]


class MatrixRuleBase(BaseModel):
    sexoModelo: SexoModelo
    edadDesde: Edad
    edadHasta: Edad
    condicionComida: CondicionComida
    minutosComidaMin: Minutos | None = None
    minutosComidaMax: Minutos | None = None
    glucosaMinReferencia: Glucosa
    glucosaMaxReferencia: Glucosa

    @field_validator("sexoModelo", "condicionComida", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)


class MatrixRuleCreate(MatrixRuleBase):
    model_config = ConfigDict(extra="forbid")

    idMatriz: uuid.UUID
    # Código de la regla: identificador técnico, se conserva tal cual.
    codigoRegla: Annotated[str, Field(max_length=50)]


class MatrixRuleUpdate(MatrixRuleBase):
    model_config = ConfigDict(extra="forbid")

    sexoModelo: SexoModelo | None = None
    edadDesde: Edad | None = None
    edadHasta: Edad | None = None
    condicionComida: CondicionComida | None = None
    glucosaMinReferencia: Glucosa | None = None
    glucosaMaxReferencia: Glucosa | None = None


class MatrixRuleRead(MatrixRuleBase):
    model_config = ConfigDict(from_attributes=True)

    idReglaMatriz: uuid.UUID
    idMatriz: uuid.UUID
    codigoRegla: str
