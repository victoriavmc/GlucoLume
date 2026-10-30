# UserNotification - NotificacionUsuario
#
# Avisos de una cuenta (la bandeja de «Notificaciones»). Solo guarda el texto del aviso, sin datos de salud: los valores de una
# medición nunca se escriben aquí.
#
# La fila es también el registro de entrega del evento: claveEvento identifica el hecho que la originó (quién, qué y de dónde viene) y
# el índice único impide que procesar dos veces el mismo hecho, aunque sea en paralelo, cree un segundo aviso o un segundo correo.
# Tres conceptos independientes (no se reutiliza uno como indicador de otro):
#   - fechaLectura: la persona ya lo leyó (sigue visible);
#   - fechaEliminacion: la persona lo quitó de SU bandeja (eliminación lógica: la fila queda, con su clave, para que el mismo hecho no vuelva a
#     crear el aviso; la depuración física la hace app/services/notificationRetention.py);
#   - visible: falso cuando la cuenta apagó el canal «en la página» (la fila queda solo como registro del correo).
# estadoCorreo sigue el envío: PENDIENTE -> ENVIADO | FALLIDO; una falla SMTP nunca quita el aviso de la página.

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.notificationEvents import eventCheck


class UserNotification(Base):
    __tablename__ = "NotificacionUsuario"
    __table_args__ = (
        CheckConstraint(eventCheck(), name="CK_NotificacionUsuario_evento"),
        CheckConstraint(
            "[estadoCorreo] IS NULL OR [estadoCorreo]=N'PENDIENTE' OR [estadoCorreo]=N'ENVIADO' OR [estadoCorreo]=N'FALLIDO'",
            name="CK_NotificacionUsuario_estadoCorreo",
        ),
        Index("IX_NotificacionUsuario_usuarioFecha", "idUsuario", "fechaCreacion"),
        Index("UX_NotificacionUsuario_clave", "idUsuario", "claveEvento", unique=True,
              mssql_where=text("[claveEvento] IS NOT NULL"), sqlite_where=text("claveEvento IS NOT NULL")),
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
    claveEvento: Mapped[str | None] = mapped_column(NVARCHAR(200), nullable=True)
    visible: Mapped[bool] = mapped_column(BIT, server_default=text("1"))
    fechaEliminacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3), nullable=True)
    estadoCorreo: Mapped[str | None] = mapped_column(NVARCHAR(12), nullable=True)
    intentosCorreo: Mapped[int] = mapped_column(Integer, server_default=text("0"))
