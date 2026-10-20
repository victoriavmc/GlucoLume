# InstitutionUser - InstitucionUsuario

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institution import Institution
from app.models.user import User


class InstitutionUser(Base):
    __tablename__ = "InstitucionUsuario"
    __table_args__ = (
        CheckConstraint(
            "[idUsuarioInvitador] IS NULL OR [idUsuarioInvitador]<>[idUsuarioInvitado]",
            name="CK_InstitucionUsuario_autoInvitacion",
        ),
        CheckConstraint(
            "[estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL",
            name="CK_InstitucionUsuario_baja",
        ),
        CheckConstraint(
            "[estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'SUSPENDIDO' OR [estadoRelacion]=N'ACTIVO'"
            " OR [estadoRelacion]=N'PENDIENTE'",
            name="CK_InstitucionUsuario_estado",
        ),
        CheckConstraint(
            "[estadoRelacion]<>N'ACTIVO' OR [fechaIncorporacion] IS NOT NULL",
            name="CK_InstitucionUsuario_incorporacion",
        ),
        CheckConstraint(
            "[origenVinculo]=N'CREACION_INSTITUCION' OR [idUsuarioInvitador] IS NOT NULL",
            name="CK_InstitucionUsuario_invitador",
        ),
        CheckConstraint(
            "[origenVinculo]=N'CREACION_CUENTA' OR [origenVinculo]=N'INVITACION'"
            " OR [origenVinculo]=N'CREACION_INSTITUCION'",
            name="CK_InstitucionUsuario_origen",
        ),
        CheckConstraint(
            "[rolInstitucion]=N'OPERADOR' OR [rolInstitucion]=N'MODERADOR' OR [rolInstitucion]=N'PROPIETARIO'",
            name="CK_InstitucionUsuario_rol",
        ),
        # Descriptivo, no define permisos.
        CheckConstraint(
            "[funcionProfesional] IS NULL OR [funcionProfesional]=N'OPERADOR' OR [funcionProfesional]=N'ENFERMERO'"
            " OR [funcionProfesional]=N'MEDICO'",
            name="CK_InstitucionUsuario_funcionProfesional",
        ),
        # Un vínculo vigente por cuenta e institución.
        Index(
            "UX_InstitucionUsuario_vinculoVigente", "idInstitucion", "idUsuarioInvitado", unique=True,
            mssql_where=text("[estadoRelacion]<>N'BAJA'"), sqlite_where=text("estadoRelacion<>'BAJA'"),
        ),
    )

    idInstitucionUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idInstitucion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Institucion.idInstitucion", name="FK_InstitucionUsuario_Institucion"),
    )
    idUsuarioInvitado: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_InstitucionUsuario_Invitado")
    )
    rolInstitucion: Mapped[str] = mapped_column(NVARCHAR(30))
    matriculaProfesional: Mapped[str | None] = mapped_column(NVARCHAR(100))
    legajoInstitucional: Mapped[str | None] = mapped_column(NVARCHAR(100))
    # Función profesional opcional: OPERADOR | ENFERMERO | MEDICO. No es rolInstitucion ni da permisos.
    funcionProfesional: Mapped[str | None] = mapped_column(NVARCHAR(30))
    # Identidad profesional histórica,
    # conservada aunque el Usuario se elimine y anonimice.
    nombreProfesionalHistorico: Mapped[str | None] = mapped_column(NVARCHAR(100))
    apellidoProfesionalHistorico: Mapped[str | None] = mapped_column(NVARCHAR(100))
    estadoRelacion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    origenVinculo: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'INVITACION'"))
    idUsuarioInvitador: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_InstitucionUsuario_Invitador")
    )
    fechaInvitacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    fechaIncorporacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaBaja: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    # Cuándo se suprimieron los datos personales históricos
    # (nombre, apellido, legajo y matrícula) por vencer el plazo de conservación. Las fechas, el rol y la función se conservan.
    fechaMinimizacionDatos: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    institucion: Mapped[Institution] = relationship()
    usuarioInvitado: Mapped[User] = relationship(foreign_keys=[idUsuarioInvitado])
    usuarioInvitador: Mapped[User | None] = relationship(foreign_keys=[idUsuarioInvitador])
