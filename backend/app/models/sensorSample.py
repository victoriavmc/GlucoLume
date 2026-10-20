# SensorSample - MuestraSensor

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.measurement import Measurement


class SensorSample(Base):
    __tablename__ = "MuestraSensor"
    __table_args__ = (
        UniqueConstraint("idMedicion", "numeroMuestra", name="UQ_MuestraSensor_orden"),
        CheckConstraint(
            "[numeroMuestra]>=(0) AND [valorRed]>=(0) AND [valorIR]>=(0)"
            " AND ([tiempoRelativoMs] IS NULL OR [tiempoRelativoMs]>=(0))",
            name="CK_MuestraSensor_valores",
        ),
    )

    idMuestraSensor: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newsequentialid()")
    )
    idMedicion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Medicion.idMedicion", name="FK_MuestraSensor_Medicion")
    )
    numeroMuestra: Mapped[int] = mapped_column(Integer)
    tiempoRelativoMs: Mapped[int | None] = mapped_column(Integer)
    valorRed: Mapped[int] = mapped_column(Integer)
    valorIR: Mapped[int] = mapped_column(Integer)

    medicion: Mapped[Measurement] = relationship()
