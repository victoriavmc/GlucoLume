# UserSession - SesionUsuario
#
# Sesiones creadas y revocadas por el servidor. refreshTokenHash nunca se expone.

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idSesion: uuid.UUID
    fechaCreacion: datetime
    fechaExpiracion: datetime
    fechaRevocacion: datetime | None = None
