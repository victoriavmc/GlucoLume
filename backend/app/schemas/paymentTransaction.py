# PaymentTransaction - TransaccionPago
#
# Entidad sensible. Las transacciones las registra el servidor a partir del proveedor de pagos:
# sin Create ni Update para el cliente.
# detalleProveedor (respuesta cruda del proveedor) e idOperacionProveedor (referencia técnica
# del proveedor) no se exponen.

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

EstadoTransaccionPago = Literal["PENDIENTE", "APROBADA", "RECHAZADA", "ANULADA", "REEMBOLSADA"]


class PaymentTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idTransaccionPago: uuid.UUID
    idSuscripcion: uuid.UUID
    idProveedorPago: uuid.UUID
    monto: Decimal
    moneda: str
    estado: EstadoTransaccionPago
    fechaCreacion: datetime
    fechaConfirmacion: datetime | None = None

    @field_validator("moneda", mode="before")
    @classmethod
    def normalizarMoneda(cls, value):
        return normalizeUpper(value)

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
