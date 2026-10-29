# ReminderSchedule - RecordatorioMedicion
#
# Horario en el que se recuerda medirse a una cuenta individual: cada N horas o en horas fijas. Un solo horario por usuario;
# modo NINGUNO lo apaga (sin DELETE: la API solo tiene permisos de lectura, inserción y actualización). Los canales (página y
# correo) se eligen en PreferenciaNotificacion. ultimoAviso marca el último recordatorio para no repetirlo.

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Integer, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReminderSchedule(Base):
    __tablename__ = "RecordatorioMedicion"
    __table_args__ = (
        CheckConstraint(
            "[modo]=N'NINGUNO' OR [modo]=N'INTERVALO' OR [modo]=N'HORARIOS'", name="CK_RecordatorioMedicion_modo"
        ),
        CheckConstraint(
            "[intervaloHoras] IS NULL OR ([intervaloHoras]>(0) AND [intervaloHoras]<=(24))",
            name="CK_RecordatorioMedicion_intervalo",
        ),
        CheckConstraint(
            "[modo]<>N'INTERVALO' OR [intervaloHoras] IS NOT NULL", name="CK_RecordatorioMedicion_intervaloRequerido"
        ),
        CheckConstraint(
            "[modo]<>N'HORARIOS' OR [horarios] IS NOT NULL", name="CK_RecordatorioMedicion_horariosRequeridos"
        ),
    )

    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_RecordatorioMedicion_Usuario"),
        primary_key=True,
    )
    modo: Mapped[str] = mapped_column(NVARCHAR(12), server_default=text("N'NINGUNO'"))
    intervaloHoras: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horarios: Mapped[str | None] = mapped_column(NVARCHAR(200), nullable=True)
    ultimoAviso: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3), nullable=True)
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
