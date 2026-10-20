# NotificationConfig - ConfiguracionNotificacion

import uuid
from datetime import datetime, time

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, TIME, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class NotificationConfig(Base):
    __tablename__ = "ConfiguracionNotificacion"
    __table_args__ = (
        UniqueConstraint("idUsuario", name="UQ_ConfiguracionNotificacion_idUsuario"),
        CheckConstraint("[canal]=N'EMAIL' OR [canal]=N'WEB'", name="CK_ConfiguracionNotificacion_canal"),
        CheckConstraint("[intervaloMinutos]>(0)", name="CK_ConfiguracionNotificacion_intervalo"),
    )

    idConfiguracionNotificacion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Usuario.idUsuario", name="FK_ConfiguracionNotificacion_Usuario"),
    )
    habilitada: Mapped[bool] = mapped_column(BIT, server_default=text("1"))
    intervaloMinutos: Mapped[int] = mapped_column(Integer)
    horaInicio: Mapped[time | None] = mapped_column(TIME(precision=0))
    horaFin: Mapped[time | None] = mapped_column(TIME(precision=0))
    canal: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'WEB'"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )

    usuario: Mapped[User] = relationship()
