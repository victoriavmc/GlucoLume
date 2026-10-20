# LocalCredential - CredencialLocal

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, TINYINT, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class LocalCredential(Base):
    __tablename__ = "CredencialLocal"
    __table_args__ = (
        UniqueConstraint("idUsuario", name="UQ_CredencialLocal_idUsuario"),
        CheckConstraint(
            "[intentosFallidosConsecutivos]>=(0) AND [intentosFallidosConsecutivos]<=(3)",
            name="CK_CredencialLocal_intentos",
        ),
    )

    idCredencialLocal: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_CredencialLocal_Usuario")
    )
    passwordHash: Mapped[str] = mapped_column(NVARCHAR(255))
    requiereCambioPassword: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    intentosFallidosConsecutivos: Mapped[int] = mapped_column(TINYINT, server_default=text("0"))
    fechaUltimoIntentoFallido: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    bloqueadoHasta: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaUltimoCambioPassword: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )

    usuario: Mapped[User] = relationship()
