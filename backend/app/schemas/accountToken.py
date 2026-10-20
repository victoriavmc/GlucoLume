# AccountToken - TokenCuenta
#
# Tokens generados por el servidor (verificación de correo, eliminación de cuenta, intercambio de Google...).
# tokenHash nunca se expone; el cliente no crea ni modifica tokens.

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.accountToken import TipoTokenCuenta
from app.utils.normalizers import normalizeUpper


class AccountTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idTokenCuenta: uuid.UUID
    tipo: TipoTokenCuenta
    fechaCreacion: datetime
    fechaExpiracion: datetime
    fechaUso: datetime | None = None

    @field_validator("tipo", mode="before")
    @classmethod
    def normalizarTipo(cls, value):
        return normalizeUpper(value)
