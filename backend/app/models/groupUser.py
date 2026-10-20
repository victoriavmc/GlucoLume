# GroupUser - GrupoUsuario

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.group import Group
from app.models.user import User


class GroupUser(Base):
    __tablename__ = "GrupoUsuario"
    __table_args__ = (
        CheckConstraint("[estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL", name="CK_GrupoUsuario_baja"),
        CheckConstraint(
            "[estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'SUSPENDIDO' OR [estadoRelacion]=N'ACTIVO'"
            " OR [estadoRelacion]=N'PENDIENTE'",
            name="CK_GrupoUsuario_estado",
        ),
        CheckConstraint(
            "[estadoRelacion]<>N'ACTIVO' OR [fechaIncorporacion] IS NOT NULL",
            name="CK_GrupoUsuario_incorporacion",
        ),
        CheckConstraint(
            "[nivelComparticion]=N'MEDICION_COMPLETA' OR [nivelComparticion]=N'SOLO_MOMENTO'"
            " OR [nivelComparticion]=N'NINGUNA'",
            name="CK_GrupoUsuario_nivel",
        ),
        CheckConstraint(
            "[rolGrupo]=N'MIEMBRO' OR [rolGrupo]=N'MODERADOR' OR [rolGrupo]=N'PROPIETARIO'",
            name="CK_GrupoUsuario_rol",
        ),
        Index("UX_GrupoUsuario_grupoActivo", "idUsuario", unique=True,
              mssql_where=text("[estadoRelacion]=N'ACTIVO'"), sqlite_where=text("estadoRelacion='ACTIVO'")),
        Index("UX_GrupoUsuario_vinculoVigente", "idGrupo", "idUsuario", unique=True,
              mssql_where=text("[estadoRelacion]<>N'BAJA'"), sqlite_where=text("estadoRelacion<>'BAJA'")),
        Index("UX_GrupoUsuario_administrador", "idGrupo", unique=True,
              mssql_where=text("[rolGrupo]=N'PROPIETARIO' AND [estadoRelacion]=N'ACTIVO'"),
              sqlite_where=text("rolGrupo='PROPIETARIO' AND estadoRelacion='ACTIVO'")),
    )

    idGrupoUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idGrupo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Grupo.idGrupo", name="FK_GrupoUsuario_Grupo")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_GrupoUsuario_Usuario")
    )
    rolGrupo: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'MIEMBRO'"))
    estadoRelacion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    nivelComparticion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'NINGUNA'"))
    fechaInvitacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    fechaIncorporacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaBaja: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    visualiza: Mapped[bool] = mapped_column(BIT, server_default=text("1"))
    # Agregadas por 010_grupo_familiar.sql: permisos personales de compartición, independientes y en 0 por defecto.
    # Solo los modifica la propia cuenta del vínculo (app/services/group.py).
    compartePerfil: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    comparteUltimaMedicion: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    # Autoriza también los gráficos y estadísticas derivados del historial (012 quitó el permiso separado).
    comparteHistorial: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    # Agregada por 020_aviso_medicion_grupo.sql: los demás integrantes reciben un aviso (quién y cuándo, nunca el valor).
    notificaMedicion: Mapped[bool] = mapped_column(BIT, server_default=text("0"))

    grupo: Mapped[Group] = relationship()
    usuario: Mapped[User] = relationship()
