# BridgeCredential - PuenteCredencial
#
# Credencial INDIVIDUAL de un puente serie (H-16), en lugar del BRIDGE_TOKEN compartido por todos:
#   - se guarda solo el SHA-256 del token (aleatorio, 48 bytes): quien lea la base no puede presentarse como el puente;
#   - atada a UN código de dispositivo (alcance): con ella el puente no puede informar ni consultar otro dispositivo;
#   - vence (`fechaExpiracion` obligatoria) y se revoca por separado (`fechaRevocacion`) sin afectar a los demás puentes;
#   - `fechaUltimoUso` permite detectar credenciales olvidadas. Nunca se guarda el token ni se escribe en registros.
# La administración es por línea de comandos (app/cli/bridgeTokens.py): la API no crea ni revoca credenciales.
# Si la base instalada todavía no tiene la tabla, el puente sigue funcionando con BRIDGE_TOKEN (schemaCompat.hasTable).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BridgeCredential(Base):
    __tablename__ = "PuenteCredencial"
    __table_args__ = (
        UniqueConstraint("tokenHash", name="UQ_PuenteCredencial_tokenHash"),
        CheckConstraint("[fechaExpiracion]>[fechaCreacion]", name="CK_PuenteCredencial_expiracion"),
        CheckConstraint("[codigoDispositivo]<>N'' AND [nombre]<>N''", name="CK_PuenteCredencial_textos"),
    )

    idPuenteCredencial: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()"))
    nombre: Mapped[str] = mapped_column(NVARCHAR(100))
    tokenHash: Mapped[str] = mapped_column(NVARCHAR(64))
    codigoDispositivo: Mapped[str] = mapped_column(NVARCHAR(100))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaExpiracion: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    fechaRevocacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaUltimoUso: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
