# Group - Grupo

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Group(Base):
    __tablename__ = "Grupo"
    __table_args__ = (
        CheckConstraint(
            "[estado]=N'CERRADO' OR [estado]=N'INACTIVO' OR [estado]=N'ACTIVO'",
            name="CK_Grupo_estado",
        ),
    )

    idGrupo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    nombre: Mapped[str] = mapped_column(NVARCHAR(100))
    descripcion: Mapped[str | None] = mapped_column(NVARCHAR(500))
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'ACTIVO'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
