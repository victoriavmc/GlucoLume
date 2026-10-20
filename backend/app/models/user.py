# User - Usuario

import uuid
from datetime import date, datetime

from sqlalchemy import NVARCHAR, CheckConstraint, Date, Index, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "Usuario"
    __table_args__ = (
        CheckConstraint(
            "[estado]=N'ELIMINADO' OR [correoElectronico] IS NOT NULL",
            name="CK_Usuario_correo",
        ),
        CheckConstraint(
            "[estado]=N'ELIMINADO' AND [fechaEliminacion] IS NOT NULL"
            " OR [estado]<>N'ELIMINADO' AND [fechaEliminacion] IS NULL",
            name="CK_Usuario_eliminacion",
        ),
        CheckConstraint(
            "[estado]=N'ELIMINADO' OR [estado]=N'BLOQUEADO' OR [estado]=N'ACTIVO' OR [estado]=N'PENDIENTE'",
            name="CK_Usuario_estado",
        ),
        CheckConstraint(
            "[tipoCuenta]=N'MODERADOR_PLATAFORMA' OR [tipoCuenta]=N'ADMINISTRADOR_PLATAFORMA'"
            " OR [tipoCuenta]=N'USUARIO_INSTITUCIONAL' OR [tipoCuenta]=N'CONSUMIDOR_FINAL'",
            name="CK_Usuario_tipoCuenta",
        ),
        CheckConstraint(
            "[sexo] IS NULL OR ([sexo]=N'MASCULINO' OR [sexo]=N'FEMENINO')",
            name="CK_Usuario_sexo",
        ),
        CheckConstraint(
            "[fechaNacimiento] IS NULL OR [fechaNacimiento]<=CONVERT([date],sysutcdatetime())",
            name="CK_Usuario_fechaNacimiento",
        ),
        # Período de gracia de 30 días.
        CheckConstraint(
            "([fechaInicioGracia] IS NULL AND [fechaVencimientoGracia] IS NULL)"
            " OR ([fechaInicioGracia] IS NOT NULL AND [fechaVencimientoGracia] IS NOT NULL"
            " AND [fechaVencimientoGracia]>[fechaInicioGracia])",
            name="CK_Usuario_gracia",
        ),
        # Un único ADMINISTRADOR_PLATAFORMA vigente.
        Index(
            "UX_Usuario_administradorUnico", "tipoCuenta", unique=True,
            mssql_where=text("[tipoCuenta]=N'ADMINISTRADOR_PLATAFORMA' AND [estado]<>N'ELIMINADO'"),
            sqlite_where=text("tipoCuenta='ADMINISTRADOR_PLATAFORMA' AND estado<>'ELIMINADO'"),
        ),
        # Correo y usuario únicos entre las cuentas que los tienen (una cuenta ELIMINADO los deja en NULL). Los usan services/user.py e
        # institution.py para reconocer la violación. Existen en la base instalada (definición y filtro verificados en su catálogo el
        # 19/10/2026); faltaban en los modelos y en v5.
        Index("UX_Usuario_correoElectronico", "correoElectronico", unique=True,
              mssql_where=text("[correoElectronico] IS NOT NULL"), sqlite_where=text("correoElectronico IS NOT NULL")),
        Index("UX_Usuario_usuario", "usuario", unique=True, mssql_where=text("[usuario] IS NOT NULL"), sqlite_where=text("usuario IS NOT NULL")),
        Index("IX_Usuario_graciaVencimiento", "fechaVencimientoGracia", mssql_where=text("[fechaVencimientoGracia] IS NOT NULL"),
              sqlite_where=text("fechaVencimientoGracia IS NOT NULL")),
    )

    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    nombre: Mapped[str | None] = mapped_column(NVARCHAR(100))
    apellido: Mapped[str | None] = mapped_column(NVARCHAR(100))
    correoElectronico: Mapped[str | None] = mapped_column(NVARCHAR(254))
    usuario: Mapped[str | None] = mapped_column(NVARCHAR(50))
    tipoCuenta: Mapped[str] = mapped_column(NVARCHAR(40), server_default=text("N'CONSUMIDOR_FINAL'"))
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    fechaEliminacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaNacimiento: Mapped[date | None] = mapped_column(Date)
    sexo: Mapped[str | None] = mapped_column(NVARCHAR(30))
    notificarNuevoInicioSesion: Mapped[bool] = mapped_column(BIT, default=True, server_default=text("1"))
    # Período de gracia de una cuenta institucional que
    # perdió su última vinculación activa (30 días corridos). Ambas NULL = sin plazo en curso.
    fechaInicioGracia: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    fechaVencimientoGracia: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
