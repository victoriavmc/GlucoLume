# TrialPeriod - PeriodoPrueba

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.mssql import DATETIME2, TINYINT, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institution import Institution
from app.models.user import User


class TrialPeriod(Base):
    __tablename__ = "PeriodoPrueba"
    __table_args__ = (
        CheckConstraint(
            "[idUsuario] IS NOT NULL AND [idInstitucion] IS NULL OR [idUsuario] IS NULL AND [idInstitucion] IS NOT NULL",
            name="CK_PeriodoPrueba_duenio",
        ),
        CheckConstraint("[fechaFin]=dateadd(day,(7),[fechaInicio])", name="CK_PeriodoPrueba_duracion"),
        CheckConstraint(
            "[estado]=N'CANCELADO' OR [estado]=N'VENCIDO' OR [estado]=N'ACTIVO'",
            name="CK_PeriodoPrueba_estado",
        ),
        CheckConstraint(
            "[idUsuario] IS NOT NULL AND [numeroPeriodo]=(1)"
            " OR [idInstitucion] IS NOT NULL AND ([numeroPeriodo]>=(1) AND [numeroPeriodo]<=(3))",
            name="CK_PeriodoPrueba_numero",
        ),
        CheckConstraint(
            "[numeroPeriodo]=(1) AND [origen]=N'PRIMER_ALTA' OR [numeroPeriodo]>(1) AND [origen]=N'REACTIVACION'",
            name="CK_PeriodoPrueba_origen",
        ),
    )

    idPeriodoPrueba: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_PeriodoPrueba_Usuario")
    )
    idInstitucion: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_PeriodoPrueba_Institucion")
    )
    numeroPeriodo: Mapped[int] = mapped_column(TINYINT, server_default=text("1"))
    origen: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PRIMER_ALTA'"))
    fechaInicio: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaFin: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'ACTIVO'"))

    usuario: Mapped[User | None] = relationship()
    institucion: Mapped[Institution | None] = relationship()
