# UserSession - SesionUsuario

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class UserSession(Base):
    __tablename__ = "SesionUsuario"
    __table_args__ = (
        UniqueConstraint("refreshTokenHash", name="UQ_SesionUsuario_refreshTokenHash"),
        CheckConstraint("[fechaExpiracion]>[fechaCreacion]", name="CK_SesionUsuario_expiracion"),
    )

    idSesion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_SesionUsuario_Usuario")
    )
    refreshTokenHash: Mapped[str] = mapped_column(NVARCHAR(255))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaExpiracion: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    fechaRevocacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    usuario: Mapped[User] = relationship()
