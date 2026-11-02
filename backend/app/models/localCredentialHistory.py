# LocalCredentialHistory - CredencialLocalHistorial

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocalCredentialHistory(Base):
    """Hashes de contraseñas anteriores de una CredencialLocal: no se pueden volver a usar al cambiarla.

    Se borra en cascada con su CredencialLocal (la eliminación o la baja de la cuenta no necesitan tocarla aparte).
    """

    __tablename__ = "CredencialLocalHistorial"
    __table_args__ = (
        Index("IX_CredencialLocalHistorial_idCredencialLocal_fechaCreacion", "idCredencialLocal", "fechaCreacion"),
    )

    idCredencialLocalHistorial: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idCredencialLocal: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("CredencialLocal.idCredencialLocal", name="FK_CredencialLocalHistorial_CredencialLocal", ondelete="CASCADE"),
    )
    passwordHash: Mapped[str] = mapped_column(NVARCHAR(255))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
