# Device - Dispositivo

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser


class Device(Base):
    __tablename__ = "Dispositivo"
    __table_args__ = (
        UniqueConstraint("codigoDispositivo", name="UQ_Dispositivo_codigo"),
        # CK_Dispositivo_bajaSinAsignacion (BAJA exigía no tener institución) se eliminó en
        # Un dispositivo descomisionado conserva la
        # institución de origen y la referencia histórica de su responsable.
        CheckConstraint(
            "[estado]=N'BAJA' OR [estado]=N'FUERA_DE_SERVICIO' OR [estado]=N'EN_MANTENIMIENTO'"
            " OR [estado]=N'OPERATIVO'",
            name="CK_Dispositivo_estado",
        ),
        CheckConstraint(
            "[modeloSensor]=N'MAX30102' OR [modeloSensor]=N'MAX30100'",
            name="CK_Dispositivo_modeloSensor",
        ),
        CheckConstraint(
            "[idInstitucionUsuarioResponsable] IS NULL OR [idInstitucionAsignada] IS NOT NULL",
            name="CK_Dispositivo_responsableRequiereInstitucion",
        ),
    )

    idDispositivo: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    codigoDispositivo: Mapped[str] = mapped_column(NVARCHAR(100))
    nombre: Mapped[str | None] = mapped_column(NVARCHAR(100))
    modelo: Mapped[str | None] = mapped_column(NVARCHAR(100))
    modeloSensor: Mapped[str] = mapped_column(NVARCHAR(20))
    versionFirmware: Mapped[str | None] = mapped_column(NVARCHAR(50))
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'OPERATIVO'"))
    idInstitucionAsignada: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_Dispositivo_Institucion")
    )
    idInstitucionUsuarioResponsable: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("InstitucionUsuario.idInstitucionUsuario", name="FK_Dispositivo_Responsable"),
    )
    fechaRegistro: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaAsignacionInstitucional: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    institucionAsignada: Mapped[Institution | None] = relationship()
    institucionUsuarioResponsable: Mapped[InstitutionUser | None] = relationship()
