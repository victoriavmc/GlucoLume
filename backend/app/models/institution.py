# Institution - Institucion

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, Boolean, CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Institution(Base):
    __tablename__ = "Institucion"
    __table_args__ = (
        UniqueConstraint("identificadorLegal", name="UQ_Institucion_identificadorLegal"),
        CheckConstraint(
            "[estado]=N'CERRADA' OR [estado]=N'INACTIVA' OR [estado]=N'ACTIVA'",
            name="CK_Institucion_estado",
        ),
        CheckConstraint(
            "[tipoInstitucion]=N'OTRO' OR [tipoInstitucion]=N'LABORATORIO' OR [tipoInstitucion]=N'CONSULTORIO'"
            " OR [tipoInstitucion]=N'CLINICA' OR [tipoInstitucion]=N'HOSPITAL'",
            name="CK_Institucion_tipo",
        ),
        CheckConstraint(
            "[tipoIdentificadorLegal]=N'OTRO' OR [tipoIdentificadorLegal]=N'CUIT'",
            name="CK_Institucion_tipoIdentificador",
        ),
        CheckConstraint("[cantidadReaperturas]>=(0)", name="CK_Institucion_cantidadReaperturas"),
        # La capacidad es un entero positivo.
        CheckConstraint("[capacidadMaximaUsuarios]>(0)", name="CK_Institucion_capacidadMaximaUsuarios"),
        # La marca de cierre administrativo solo existe en una CERRADA y
        # exige actor, fecha y motivo; sin marca, ninguno de los tres.
        CheckConstraint(
            "([cierreAdministrativo]=(0) AND [fechaCierreAdministrativo] IS NULL AND [idUsuarioCierreAdministrativo] IS NULL AND [motivoCierreAdministrativo] IS NULL)"
            " OR ([cierreAdministrativo]=(1) AND [estado]=N'CERRADA' AND [fechaCierreAdministrativo] IS NOT NULL"
            " AND [idUsuarioCierreAdministrativo] IS NOT NULL AND [motivoCierreAdministrativo] IS NOT NULL)",
            name="CK_Institucion_cierreAdministrativo",
        ),
    )

    # capacidadMaximaUsuarios se agrega con la migración 028: no se mapea como atributo para que el backend siga funcionando si todavía no se
    # aplicó (el INSERT no la nombra: SQL Server aplica su valor predeterminado). Se lee con Core, solo si existe (services/quota.py).
    # Columnas de migraciones posteriores (028 y 033) que el ORM NO mapea: ni se piden en los SELECT, ni se nombran en el INSERT ni en su RETURNING, así el
    # backend funciona con la base sin migrar. Se leen y escriben con Institution.__table__.c, tras schemaCompat.hasColumn / administrativeClosureReady.
    __mapper_args__ = {"exclude_properties": ["capacidadMaximaUsuarios", "cierreAdministrativo", "fechaCierreAdministrativo", "idUsuarioCierreAdministrativo",
                                              "motivoCierreAdministrativo"]}

    idInstitucion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    tipoIdentificadorLegal: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'CUIT'"))
    identificadorLegal: Mapped[str] = mapped_column(NVARCHAR(50))
    nombre: Mapped[str] = mapped_column(NVARCHAR(150))
    tipoInstitucion: Mapped[str] = mapped_column(NVARCHAR(30))
    descripcion: Mapped[str | None] = mapped_column(NVARCHAR(500))
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'ACTIVA'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaActualizacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    # Reaperturas efectivas (no se reinicia al cerrar)
    # e inicio del período operativo vigente.
    cantidadReaperturas: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    fechaUltimaReapertura: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    # Capacidad máxima de cuentas institucionales ACTIVAS (cupos). Predeterminada 1000. Solo la administra el sistema.
    capacidadMaximaUsuarios: Mapped[int] = mapped_column(Integer, server_default=text("1000"))

    # Cierre ADMINISTRATIVO (eliminación por la plataforma). Es la única fuente de verdad para distinguirlo del cierre pedido por el
    # propietario: una institución con cierreAdministrativo = 1 no puede reabrirla su último propietario. SQL Server: cierreAdministrativo BIT NOT NULL
    # DEFAULT 0 y las otras tres anulables; sin mapear en el ORM (ver exclude_properties).
    cierreAdministrativo: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    fechaCierreAdministrativo: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    idUsuarioCierreAdministrativo: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_Institucion_cierreAdministrativo_Usuario"))
    motivoCierreAdministrativo: Mapped[str | None] = mapped_column(NVARCHAR(300))
