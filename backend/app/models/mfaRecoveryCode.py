# MfaRecoveryCode - CodigoRecuperacionMfa
#
# Códigos de recuperación de un factor MFA (esquema v5).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mfaFactor import MfaFactor


class MfaRecoveryCode(Base):
    __tablename__ = "CodigoRecuperacionMfa"
    __table_args__ = (UniqueConstraint("codigoHash", name="UQ_CodigoRecuperacionMfa_codigoHash"),)

    idCodigoRecuperacionMfa: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idFactorMfa: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("FactorMfa.idFactorMfa", name="FK_CodigoRecuperacionMfa_FactorMfa"),
    )
    codigoHash: Mapped[str] = mapped_column(NVARCHAR(255))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaUso: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    factorMfa: Mapped[MfaFactor] = relationship()
