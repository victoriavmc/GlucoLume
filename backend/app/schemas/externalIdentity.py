# ExternalIdentity - IdentidadExterna
#
# Se crea en el servidor a partir del token OIDC verificado del proveedor; el cliente no
# envía estos datos, por eso no hay Create ni Update.
# subjectProveedor (identificador técnico de la cuenta externa) no se expone.

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeEmail, normalizeUpper

ProveedorIdentidad = Literal["GOOGLE"]


class ExternalIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idIdentidadExterna: uuid.UUID
    proveedor: ProveedorIdentidad
    emailProveedor: Annotated[EmailStr, Field(max_length=254)] | None = None
    emailVerificado: bool
    fechaVinculacion: datetime
    ultimoAcceso: datetime | None = None

    @field_validator("proveedor", mode="before")
    @classmethod
    def normalizarProveedor(cls, value):
        return normalizeUpper(value)

    @field_validator("emailProveedor", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)
