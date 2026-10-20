# Audit - Auditoria
#
# Registro de solo escritura por el servidor: el cliente nunca crea ni modifica auditoría.
# datosPrevios, datosNuevos y detalle (instantáneas JSON que pueden contener datos sensibles)
# no se exponen en la lectura general.

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeUpper

TipoEventoAuditoria = Literal["LOGIN", "CRUD", "PERMISO", "ACCESO"]
ResultadoAuditoria = Literal["EXITO", "FALLO"]


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idAuditoria: uuid.UUID
    idUsuario: uuid.UUID | None = None
    tipoEvento: TipoEventoAuditoria
    accion: str
    tablaAfectada: str | None = None
    idRegistro: uuid.UUID | None = None
    tablaRelacionada: str | None = None
    idRelacionado: uuid.UUID | None = None
    resultado: ResultadoAuditoria
    fechaHora: datetime
    observacion: str | None = None

    @field_validator("tipoEvento", "resultado", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)
