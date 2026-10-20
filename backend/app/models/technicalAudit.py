# TechnicalAudit - AuditoriaTecnicaMedicion
#
# Proyección ANONIMIZADA de los intentos de medición que no terminaron bien (cancelados, inválidos, abandonados o vencidos), para analizar
# el funcionamiento y la estabilidad del prototipo. NO tiene ninguna clave foránea ni columna que identifique a la persona, al perfil o a la
# medición (ni idUsuario, ni idPerfilMedicion, ni idMedicion): `idEvento` es un identificador aleatorio sin relación con ellos y la hora se
# redondea a la hora en punto para que el evento no pueda cruzarse con la auditoría general por su instante exacto. Eso es lo que la
# distingue de `Auditoria` (seudonimizada: sigue ligada a un usuario). Se consulta solo con rol administrativo y se purga por antigüedad.
# Tabla AuditoriaTecnica (esquema v5).

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, Index, Integer
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TechnicalAudit(Base):
    __tablename__ = "AuditoriaTecnicaMedicion"
    __table_args__ = (
        CheckConstraint("[estadoFinal]=N'CANCELADA' OR [estadoFinal]=N'INVALIDA'", name="CK_AuditoriaTecnica_estado"),
        CheckConstraint("[duracionSegundos] IS NULL OR [duracionSegundos]>=(0)", name="CK_AuditoriaTecnica_duracion"),
        Index("IX_AuditoriaTecnica_fecha", "fechaHora"),
    )

    idEvento: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER(as_uuid=True), primary_key=True)
    fechaHora: Mapped[datetime] = mapped_column(DATETIME2(precision=0))  # truncada a la hora
    tipoOperacion: Mapped[str] = mapped_column(NVARCHAR(30))  # MEDICION | SESION_DISPOSITIVO | MANTENIMIENTO
    estadoFinal: Mapped[str] = mapped_column(NVARCHAR(12))
    motivo: Mapped[str] = mapped_column(NVARCHAR(40))
    modeloSensor: Mapped[str | None] = mapped_column(NVARCHAR(20))
    duracionSegundos: Mapped[int | None] = mapped_column(Integer)
    codigoError: Mapped[str | None] = mapped_column(NVARCHAR(40))
