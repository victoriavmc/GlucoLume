# CapillaryReferenceMeasurement - MedicionReferenciaCapilar

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.measurement import Measurement


class CapillaryReferenceMeasurement(Base):
    __tablename__ = "MedicionReferenciaCapilar"
    __table_args__ = (
        UniqueConstraint("idMedicion", name="UQ_MedicionReferenciaCapilar_medicion"),
        CheckConstraint("[glucosaReferencia]>=(0)", name="CK_MedicionReferenciaCapilar_valor"),
    )

    idMedicionReferencia: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Medicion.idMedicion", name="FK_MedicionReferenciaCapilar_Medicion"),
    )
    glucosaReferencia: Mapped[Decimal] = mapped_column(DECIMAL(8, 2))
    fechaHoraReferencia: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    marcaGlucometro: Mapped[str | None] = mapped_column(NVARCHAR(100))
    modeloGlucometro: Mapped[str | None] = mapped_column(NVARCHAR(100))
    observacion: Mapped[str | None] = mapped_column(NVARCHAR(500))

    medicion: Mapped[Measurement] = relationship()
