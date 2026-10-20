# MfaFactor - FactorMfa
#
# Factor TOTP de una cuenta (esquema v5).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, BigInteger, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, TINYINT, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class MfaFactor(Base):
    __tablename__ = "FactorMfa"
    __table_args__ = (
        UniqueConstraint("idUsuario", name="UQ_FactorMfa_idUsuario"),
        CheckConstraint("[tipo]=N'TOTP'", name="CK_FactorMfa_tipo"),
        CheckConstraint(
            "[intentosFallidosConsecutivos]>=(0) AND [intentosFallidosConsecutivos]<=(5)",
            name="CK_FactorMfa_intentos",
        ),
        CheckConstraint("[habilitado]=(0) OR [fechaConfirmacion] IS NOT NULL", name="CK_FactorMfa_confirmacion"),
    )

    idFactorMfa: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_FactorMfa_Usuario")
    )
    tipo: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'TOTP'"))
    secretoCifrado: Mapped[str] = mapped_column(NVARCHAR(500))
    habilitado: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    ultimoPasoUsado: Mapped[int | None] = mapped_column(BigInteger)
    intentosFallidosConsecutivos: Mapped[int] = mapped_column(TINYINT, server_default=text("0"))
    bloqueadoHasta: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaConfirmacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    usuario: Mapped[User] = relationship()
