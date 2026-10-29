# NotificationPreference - PreferenciaNotificacion
#
# Canales de cada aviso de la cuenta: en la página (NotificacionUsuario) y por correo. Sin fila rige el valor por omisión de
# services/userNotifications.py. El correo de inicio de sesión sigue en Usuario.notificarNuevoInicioSesion (no se duplica).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.notificationEvents import eventCheck


class NotificationPreference(Base):
    __tablename__ = "PreferenciaNotificacion"
    __table_args__ = (
        UniqueConstraint("idUsuario", "evento", name="UQ_PreferenciaNotificacion_usuarioEvento"),
        CheckConstraint(eventCheck(), name="CK_PreferenciaNotificacion_evento"),
    )

    idPreferenciaNotificacion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_PreferenciaNotificacion_Usuario")
    )
    evento: Mapped[str] = mapped_column(NVARCHAR(40))
    enPagina: Mapped[bool] = mapped_column(BIT, server_default=text("1"))
    porCorreo: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
