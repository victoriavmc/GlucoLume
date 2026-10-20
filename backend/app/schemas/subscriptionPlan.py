# SubscriptionPlan - PlanSuscripcion

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeDate, normalizeSentence, normalizeStatus, normalizeUpper

TipoCliente = Literal["CONSUMIDOR", "INSTITUCION"]
TipoPlan = Literal["INDIVIDUAL", "MULTIUSUARIO", "INSTITUCIONAL"]
EstadoPlan = Literal["ACTIVO", "INACTIVO"]

Precio = Annotated[Decimal, Field(max_digits=12, decimal_places=2, ge=0)]
Moneda = Annotated[str, Field(min_length=3, max_length=3)]


class SubscriptionPlanBase(BaseModel):
    # Nombre comercial del plan: se conserva tal cual.
    nombre: Annotated[str, Field(max_length=100)]
    tipoCliente: TipoCliente
    tipoPlan: TipoPlan
    cupoUsuarios: Annotated[int, Field(gt=0)] | None = None
    precioBase: Precio | None = None
    moneda: Moneda | None = "ARS"
    requiereCanalVentas: bool = False
    fechaVigenciaDesde: date
    fechaVigenciaHasta: date | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("tipoCliente", "tipoPlan", "moneda", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)

    @field_validator("fechaVigenciaDesde", "fechaVigenciaHasta", mode="before")
    @classmethod
    def normalizarVigencia(cls, value):
        return normalizeDate(value)

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)


class SubscriptionPlanCreate(SubscriptionPlanBase):
    model_config = ConfigDict(extra="forbid")


class SubscriptionPlanUpdate(SubscriptionPlanBase):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=100)] | None = None
    tipoCliente: TipoCliente | None = None
    tipoPlan: TipoPlan | None = None
    moneda: Moneda | None = None
    requiereCanalVentas: bool | None = None
    fechaVigenciaDesde: date | None = None
    estado: EstadoPlan | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class SubscriptionPlanRead(SubscriptionPlanBase):
    model_config = ConfigDict(from_attributes=True)

    idPlan: uuid.UUID
    requiereCanalVentas: bool
    estado: EstadoPlan

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
