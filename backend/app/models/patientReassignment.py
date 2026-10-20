# PatientReassignment - ReasignacionPaciente
#
# Tarea administrativa «paciente pendiente de reasignación»: nace cuando se desvincula a un operador con pacientes activos a su cargo
# y queda como historial al resolverse. Las relaciones (InstitucionUsuario) son las históricas: no se eliminan al anonimizar la cuenta.

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatientReassignment(Base):
    __tablename__ = "ReasignacionPaciente"
    __table_args__ = (
        CheckConstraint("[estado] IN (N'PENDIENTE', N'COMPLETADA', N'CANCELADA')", name="CK_ReasignacionPaciente_estado"),
        CheckConstraint("[motivo] IN (N'BAJA_OPERADOR')", name="CK_ReasignacionPaciente_motivo"),
        CheckConstraint(
            "[resultado] IS NULL OR [resultado] IN (N'REASIGNADO', N'PACIENTE_DADO_DE_BAJA', N'INSTITUCION_CERRADA')",
            name="CK_ReasignacionPaciente_resultado",
        ),
        CheckConstraint(
            "([estado]=N'PENDIENTE' AND [fechaResolucion] IS NULL AND [idOperadorNuevo] IS NULL AND [resultado] IS NULL)"
            " OR ([estado]=N'COMPLETADA' AND [fechaResolucion] IS NOT NULL AND [idOperadorNuevo] IS NOT NULL AND [resultado]=N'REASIGNADO')"
            " OR ([estado]=N'CANCELADA' AND [fechaResolucion] IS NOT NULL AND [idOperadorNuevo] IS NULL"
            " AND [resultado] IS NOT NULL AND [resultado]<>N'REASIGNADO')",
            name="CK_ReasignacionPaciente_coherencia",
        ),
        # A lo sumo una tarea pendiente por paciente.
        Index(
            "UX_ReasignacionPaciente_pendiente", "idPerfilMedicion", unique=True,
            mssql_where=text("[estado]=N'PENDIENTE'"), sqlite_where=text("estado='PENDIENTE'"),
        ),
        Index("IX_ReasignacionPaciente_institucion", "idInstitucion", "estado", "fechaCreacion"),
    )

    idReasignacionPaciente: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idInstitucion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_ReasignacionPaciente_Institucion")
    )
    idPerfilMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("PerfilMedicion.idPerfilMedicion", name="FK_ReasignacionPaciente_Perfil")
    )
    idOperadorAnterior: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("InstitucionUsuario.idInstitucionUsuario", name="FK_ReasignacionPaciente_Anterior"),
    )
    idOperadorNuevo: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("InstitucionUsuario.idInstitucionUsuario", name="FK_ReasignacionPaciente_Nuevo"),
    )
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'PENDIENTE'"))
    motivo: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'BAJA_OPERADOR'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaResolucion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    idUsuarioResolutor: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_ReasignacionPaciente_Resolutor")
    )
    resultado: Mapped[str | None] = mapped_column(NVARCHAR(30))
    observacion: Mapped[str | None] = mapped_column(NVARCHAR(500))
