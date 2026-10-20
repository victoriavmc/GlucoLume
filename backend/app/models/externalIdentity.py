# ExternalIdentity - IdentidadExterna

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class ExternalIdentity(Base):
    __tablename__ = "IdentidadExterna"
    __table_args__ = (
        UniqueConstraint("proveedor", "subjectProveedor", name="UQ_IdentidadExterna_proveedor_subject"),
        CheckConstraint("[proveedor]=N'GOOGLE'", name="CK_IdentidadExterna_proveedor"),
    )

    idIdentidadExterna: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_IdentidadExterna_Usuario")
    )
    proveedor: Mapped[str] = mapped_column(NVARCHAR(30))
    subjectProveedor: Mapped[str] = mapped_column(NVARCHAR(255))
    emailProveedor: Mapped[str | None] = mapped_column(NVARCHAR(254))
    emailVerificado: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    fechaVinculacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    ultimoAcceso: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    usuario: Mapped[User] = relationship()
