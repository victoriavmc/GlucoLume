# SubscriptionPlan - PlanSuscripcion

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, DECIMAL, NVARCHAR, CheckConstraint, Date, Integer, UniqueConstraint, text
from sqlalchemy.dialects.mssql import BIT, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionPlan(Base):
    __tablename__ = "PlanSuscripcion"
    __table_args__ = (
        UniqueConstraint("nombre", name="UQ_PlanSuscripcion_nombre"),
        CheckConstraint(
            "[tipoCliente]=N'CONSUMIDOR' AND ([tipoPlan]=N'MULTIUSUARIO' OR [tipoPlan]=N'INDIVIDUAL')"
            " OR [tipoCliente]=N'INSTITUCION' AND [tipoPlan]=N'INSTITUCIONAL'",
            name="CK_PlanSuscripcion_coherencia",
        ),
        CheckConstraint(
            "([cupoUsuarios] IS NULL OR [cupoUsuarios]>(0)) AND ([tipoPlan]<>N'INDIVIDUAL' OR [cupoUsuarios]=(1))",
            name="CK_PlanSuscripcion_cupo",
        ),
        CheckConstraint("[estado]=N'INACTIVO' OR [estado]=N'ACTIVO'", name="CK_PlanSuscripcion_estado"),
        CheckConstraint("[precioBase] IS NULL OR [precioBase]>=(0)", name="CK_PlanSuscripcion_precio"),
        CheckConstraint(
            "[tipoCliente]=N'INSTITUCION' OR [tipoCliente]=N'CONSUMIDOR'",
            name="CK_PlanSuscripcion_tipoCliente",
        ),
        CheckConstraint(
            "[tipoPlan]=N'INSTITUCIONAL' OR [tipoPlan]=N'MULTIUSUARIO' OR [tipoPlan]=N'INDIVIDUAL'",
            name="CK_PlanSuscripcion_tipoPlan",
        ),
        CheckConstraint(
            "[fechaVigenciaHasta] IS NULL OR [fechaVigenciaHasta]>=[fechaVigenciaDesde]",
            name="CK_PlanSuscripcion_vigencia",
        ),
    )

    idPlan: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    nombre: Mapped[str] = mapped_column(NVARCHAR(100))
    tipoCliente: Mapped[str] = mapped_column(NVARCHAR(30))
    tipoPlan: Mapped[str] = mapped_column(NVARCHAR(30))
    cupoUsuarios: Mapped[int | None] = mapped_column(Integer)
    precioBase: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2))
    moneda: Mapped[str | None] = mapped_column(CHAR(3), server_default=text("'ARS'"))
    requiereCanalVentas: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    estado: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'ACTIVO'"))
    fechaVigenciaDesde: Mapped[date] = mapped_column(Date)
    fechaVigenciaHasta: Mapped[date | None] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(NVARCHAR(500))
