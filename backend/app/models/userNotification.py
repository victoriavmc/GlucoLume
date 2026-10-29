# UserNotification - NotificacionUsuario
#
# Avisos de la página para una cuenta (la campana de «Notificaciones»). Solo guarda el texto del aviso, sin datos de salud:
# los valores de una medición nunca se escriben aquí.

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserNotification(Base):
    __tablename__ = "NotificacionUsuario"
    __table_args__ = (
        CheckConstraint(
            "[evento]=N'INICIO_SESION' OR [evento]=N'AGREGADO_GRUPO' OR [evento]=N'RECORDATORIO_MEDICION'"
            " OR [evento]=N'NUEVA_ACCION_GRUPO'",
            name="CK_NotificacionUsuario_evento",
        ),
        Index("IX_NotificacionUsuario_usuarioFecha", "idUsuario", "fechaCreacion"),
    )

    idNotificacion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_NotificacionUsuario_Usuario")
    )
    evento: Mapped[str] = mapped_column(NVARCHAR(40))
    titulo: Mapped[str] = mapped_column(NVARCHAR(120))
    mensaje: Mapped[str] = mapped_column(NVARCHAR(400))
    url: Mapped[str | None] = mapped_column(NVARCHAR(300), nullable=True)
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaLectura: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3), nullable=True)
