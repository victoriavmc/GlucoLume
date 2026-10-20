# PaymentProvider - ProveedorPago
#
# Catálogo administrativo. El proveedor de pagos aún no está definido; la tabla no almacena
# credenciales ni claves.

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

EstadoProveedorPago = Literal["ACTIVO", "INACTIVO"]
EntornoProveedorPago = Literal["SANDBOX", "PRODUCCION"]


class PaymentProviderBase(BaseModel):
    # Nombre comercial del proveedor: se conserva tal cual.
    nombre: Annotated[str, Field(max_length=100)]
    entorno: EntornoProveedorPago = "SANDBOX"

    @field_validator("entorno", mode="before")
    @classmethod
    def normalizarEntorno(cls, value):
        return normalizeUpper(value)


class PaymentProviderCreate(PaymentProviderBase):
    model_config = ConfigDict(extra="forbid")

    # Código técnico único del proveedor: se conserva tal cual.
    codigo: Annotated[str, Field(max_length=40)]


class PaymentProviderUpdate(PaymentProviderBase):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=100)] | None = None
    entorno: EntornoProveedorPago | None = None
    estado: EstadoProveedorPago | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class PaymentProviderRead(PaymentProviderBase):
    model_config = ConfigDict(from_attributes=True)

    idProveedorPago: uuid.UUID
    codigo: str
    estado: EstadoProveedorPago
    fechaAlta: datetime

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
