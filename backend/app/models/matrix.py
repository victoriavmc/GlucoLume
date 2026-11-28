# Matrix - Matriz

import uuid
from datetime import date, datetime

from sqlalchemy import NVARCHAR, CheckConstraint, Date, ForeignKey, Index, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institution import Institution


class Matrix(Base):
    __tablename__ = "Matriz"
    __table_args__ = (
        UniqueConstraint("idInstitucion", "nombre", "version", name="UQ_Matriz_version"),
        CheckConstraint(
            "[ambito]=N'GLOBAL' AND [idInstitucion] IS NULL OR [ambito]=N'INSTITUCION' AND [idInstitucion] IS NOT NULL",
            name="CK_Matriz_ambito",
        ),
        CheckConstraint(
            "[estado]=N'ARCHIVADA' OR [estado]=N'INACTIVA' OR [estado]=N'ACTIVA' OR [estado]=N'BORRADOR'",
            name="CK_Matriz_estado",
        ),
        CheckConstraint(
            "[fechaVigenciaHasta] IS NULL OR [fechaVigenciaHasta]>=[fechaVigenciaDesde]",
            name="CK_Matriz_vigencia",
        ),
        # De dónde se tomaron los criterios: obligatorio (el servicio ya lo recorta y exige al menos 2 caracteres).
        CheckConstraint("[referenciaBase]<>N''", name="CK_Matriz_referenciaBase"),
        # Una sola matriz ACTIVA por ámbito.
        Index(
            "UX_Matriz_globalActiva", "ambito", unique=True,
            mssql_where=text("[ambito]=N'GLOBAL' AND [estado]=N'ACTIVA'"),
            sqlite_where=text("ambito='GLOBAL' AND estado='ACTIVA'"),
        ),
        Index(
            "UX_Matriz_institucionActiva", "idInstitucion", unique=True,
            mssql_where=text("[ambito]=N'INSTITUCION' AND [estado]=N'ACTIVA'"),
            sqlite_where=text("ambito='INSTITUCION' AND estado='ACTIVA'"),
        ),
    )

    idMatriz: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idInstitucion: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_Matriz_Institucion")
    )
    nombre: Mapped[str] = mapped_column(NVARCHAR(100))
    version: Mapped[str] = mapped_column(NVARCHAR(50))
    ambito: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'GLOBAL'"))
    fechaVigenciaDesde: Mapped[date] = mapped_column(Date)
    fechaVigenciaHasta: Mapped[date | None] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(NVARCHAR(500))
    urlReferencia: Mapped[str | None] = mapped_column(NVARCHAR(500))
    referenciaBase: Mapped[str] = mapped_column(NVARCHAR(200))
    estado:Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'BORRADOR'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    # Estado de los avisos de vencimiento al administrador de la plataforma (services/matrixExpiryAlerts.py). No son datos de la matriz:
    # no cambian su contenido, así que una ACTIVA sigue siendo inmutable.
    #   avisoVencimientoNivel: último umbral avisado (10, 5, 3, 2 o 1 día antes); NULL = ninguno.
    #   avisoVencimientoUltimo: último aviso de «vencida» (se repite cada 24 h).
    #   avisoVencimientoSilenciado: el administrador eligió no recibir los avisos de esta matriz (puede cambiarlo en cualquier momento).
    avisoVencimientoNivel: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    avisoVencimientoUltimo: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3), nullable=True)
    avisoVencimientoSilenciado: Mapped[bool] = mapped_column(BIT, server_default=text("0"))

    institucion: Mapped[Institution | None] = relationship()
