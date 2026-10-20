# LocalCredential - CredencialLocal
#
# Entidad sensible. passwordHash, intentosFallidosConsecutivos, fechaUltimoIntentoFallido y
# bloqueadoHasta nunca se exponen ni los establece el cliente.
# La contraseña se recibe en texto plano solo para calcular passwordHash en el servidor:
# no se normaliza (sin strip ni cambios de mayúsculas), se maneja como SecretStr y debe cumplir
# la política de contraseñas (app/core/security.py).

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.auth import NewPassword


class LocalCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: NewPassword


class LocalCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: NewPassword


class LocalCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idUsuario: uuid.UUID
    requiereCambioPassword: bool
    fechaUltimoCambioPassword: datetime | None = None
    fechaCreacion: datetime
    fechaActualizacion: datetime
