# ProfileTransfer - TransferenciaPerfil

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile


class ProfileTransfer(Base):
    __tablename__ = "TransferenciaPerfil"
    __table_args__ = (
        CheckConstraint(
            "[estado]=N'CANCELADA' OR [estado]=N'RECHAZADA' OR [estado]=N'ACEPTADA' OR [estado]=N'PENDIENTE'",
            name="CK_TransferenciaPerfil_estado",
        ),
        CheckConstraint(
            "[estado]=N'ACEPTADA' AND [fechaTransferencia] IS NOT NULL AND [fechaTransferencia]>=[fechaPeticion]"
            " OR [estado]<>N'ACEPTADA' AND [fechaTransferencia] IS NULL",
            name="CK_TransferenciaPerfil_fechaTransferencia",
        ),
        Index(
            "UX_TransferenciaPerfil_pendiente", "idPerfilMedicion", unique=True,
            mssql_where=text("[estado]=N'PENDIENTE'"), sqlite_where=text("estado='PENDIENTE'"),
        ),
        Index("IX_TransferenciaPerfil_destino", "idOperadorDestino", "estado"),
    )

    idTransferenciaPerfil: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idPerfilMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("PerfilMedicion.idPerfilMedicion", name="FK_TransferenciaPerfil_Perfil"),
    )
    idOperadorDestino: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("InstitucionUsuario.idInstitucionUsuario", name="FK_TransferenciaPerfil_Destino"),
    )
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'PENDIENTE'"))
    fechaPeticion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaTransferencia: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    observacion: Mapped[str | None] = mapped_column(NVARCHAR(500))

    perfilMedicion: Mapped[MeasurementProfile] = relationship()
    operadorDestino: Mapped[InstitutionUser] = relationship()
