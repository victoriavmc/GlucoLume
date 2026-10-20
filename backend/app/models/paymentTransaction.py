# PaymentTransaction - TransaccionPago

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, DECIMAL, NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.paymentProvider import PaymentProvider
from app.models.subscription import Subscription


class PaymentTransaction(Base):
    __tablename__ = "TransaccionPago"
    __table_args__ = (
        UniqueConstraint("idOperacionProveedor", name="UQ_TransaccionPago_operacion"),
        CheckConstraint(
            "[detalleProveedor] IS NULL OR isjson([detalleProveedor])=(1)",
            name="CK_TransaccionPago_detalleJson",
        ),
        CheckConstraint(
            "[estado]=N'REEMBOLSADA' OR [estado]=N'ANULADA' OR [estado]=N'RECHAZADA' OR [estado]=N'APROBADA'"
            " OR [estado]=N'PENDIENTE'",
            name="CK_TransaccionPago_estado",
        ),
        CheckConstraint("[monto]>=(0)", name="CK_TransaccionPago_monto"),
    )

    idTransaccionPago: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idSuscripcion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Suscripcion.idSuscripcion", name="FK_TransaccionPago_Suscripcion"),
    )
    idProveedorPago: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("ProveedorPago.idProveedorPago", name="FK_TransaccionPago_Proveedor"),
    )
    idOperacionProveedor: Mapped[str] = mapped_column(NVARCHAR(150))
    monto: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    moneda: Mapped[str] = mapped_column(CHAR(3), server_default=text("'ARS'"))
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaConfirmacion: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    detalleProveedor: Mapped[str | None] = mapped_column(NVARCHAR(None))

    suscripcion: Mapped[Subscription] = relationship()
    proveedorPago: Mapped[PaymentProvider] = relationship()
