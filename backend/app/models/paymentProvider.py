# PaymentProvider - ProveedorPago

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentProvider(Base):
    __tablename__ = "ProveedorPago"
    __table_args__ = (
        UniqueConstraint("codigo", name="UQ_ProveedorPago_codigo"),
        CheckConstraint("[entorno]=N'PRODUCCION' OR [entorno]=N'SANDBOX'", name="CK_ProveedorPago_entorno"),
        CheckConstraint("[estado]=N'INACTIVO' OR [estado]=N'ACTIVO'", name="CK_ProveedorPago_estado"),
    )

    idProveedorPago: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    codigo: Mapped[str] = mapped_column(NVARCHAR(40))
    nombre: Mapped[str] = mapped_column(NVARCHAR(100))
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'INACTIVO'"))
    entorno: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'SANDBOX'"))
    fechaAlta: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
