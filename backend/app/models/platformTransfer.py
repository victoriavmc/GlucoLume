# PlatformTransfer - TransferenciaAdministracion
#
# Traspaso del control principal de GlucoLume (rol ADMINISTRADOR_PLATAFORMA) a un MODERADOR_PLATAFORMA activo. Es una
# solicitud con aceptación: no cambia ningún rol hasta que el destinatario acepta (services/platform.py). El índice
# único filtrado permite una sola solicitud PENDIENTE en toda la plataforma (sin transferencias concurrentes).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformTransfer(Base):
    __tablename__ = "TransferenciaAdministracion"
    __table_args__ = (
        CheckConstraint(
            "[estado]=N'PENDIENTE' OR [estado]=N'ACEPTADA' OR [estado]=N'RECHAZADA' OR [estado]=N'CANCELADA'",
            name="CK_TransferenciaAdministracion_estado",
        ),
        CheckConstraint("[idUsuarioOrigen]<>[idUsuarioDestino]", name="CK_TransferenciaAdministracion_distintos"),
        CheckConstraint(
            "([estado]=N'PENDIENTE' AND [fechaRespuesta] IS NULL) OR ([estado]<>N'PENDIENTE' AND [fechaRespuesta] IS NOT NULL)",
            name="CK_TransferenciaAdministracion_respuesta",
        ),
        Index(
            "UX_TransferenciaAdministracion_pendiente", "estado", unique=True,
            mssql_where=text("[estado]=N'PENDIENTE'"), sqlite_where=text("estado='PENDIENTE'"),
        ),
        Index("IX_TransferenciaAdministracion_destino", "idUsuarioDestino", "estado"),
    )

    idTransferenciaAdministracion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuarioOrigen: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_TransferenciaAdministracion_origen")
    )
    idUsuarioDestino: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_TransferenciaAdministracion_destino")
    )
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'PENDIENTE'"))
    fechaSolicitud: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaRespuesta: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
