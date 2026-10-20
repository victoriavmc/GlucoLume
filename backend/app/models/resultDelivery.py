# ResultDelivery - EnvioResultado

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.measurement import Measurement


class ResultDelivery(Base):
    __tablename__ = "EnvioResultado"
    __table_args__ = (
        CheckConstraint(
            "[estadoEnvio]<>N'ENVIADO' OR [fechaEnvio] IS NOT NULL AND [correoDestino] IS NULL",
            name="CK_EnvioResultado_enviado",
        ),
        CheckConstraint(
            "[estadoEnvio]=N'FALLIDO' OR [estadoEnvio]=N'ENVIADO' OR [estadoEnvio]=N'PENDIENTE'",
            name="CK_EnvioResultado_estado",
        ),
        CheckConstraint(
            "[estadoEnvio]<>N'PENDIENTE' OR [correoDestino] IS NOT NULL",
            name="CK_EnvioResultado_pendiente",
        ),
    )

    idEnvioResultado: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Medicion.idMedicion", name="FK_EnvioResultado_Medicion")
    )
    correoDestino: Mapped[str | None] = mapped_column(NVARCHAR(254))
    estadoEnvio: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'PENDIENTE'"))
    fechaSolicitud: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaEnvio: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    detalleError: Mapped[str | None] = mapped_column(NVARCHAR(500))

    medicion: Mapped[Measurement] = relationship()
