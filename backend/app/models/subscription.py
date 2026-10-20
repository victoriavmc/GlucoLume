# Subscription - Suscripcion

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.institution import Institution
from app.models.subscriptionPlan import SubscriptionPlan
from app.models.user import User


class Subscription(Base):
    __tablename__ = "Suscripcion"
    __table_args__ = (
        CheckConstraint(
            "[estado]=N'CANCELADA' OR [estado]=N'SUSPENDIDA' OR [estado]=N'VENCIDA' OR [estado]=N'ACTIVA'"
            " OR [estado]=N'PENDIENTE'",
            name="CK_Suscripcion_estado",
        ),
        CheckConstraint("[fechaFin] IS NULL OR [fechaFin]>=[fechaInicio]", name="CK_Suscripcion_fechas"),
        CheckConstraint(
            "[origenContratacion]=N'CANAL_VENTAS' OR [origenContratacion]=N'ONLINE'",
            name="CK_Suscripcion_origen",
        ),
        CheckConstraint(
            "[idUsuarioTitular] IS NOT NULL AND [idInstitucion] IS NULL"
            " OR [idUsuarioTitular] IS NULL AND [idInstitucion] IS NOT NULL",
            name="CK_Suscripcion_titular",
        ),
    )

    idSuscripcion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idPlan: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("PlanSuscripcion.idPlan", name="FK_Suscripcion_Plan")
    )
    idUsuarioTitular: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_Suscripcion_Titular")
    )
    idInstitucion: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Institucion.idInstitucion", name="FK_Suscripcion_Institucion")
    )
    estado: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'PENDIENTE'"))
    fechaInicio: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    fechaFin: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))
    renovacionAutomatica: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    origenContratacion: Mapped[str] = mapped_column(NVARCHAR(30), server_default=text("N'ONLINE'"))
    referenciaContrato: Mapped[str | None] = mapped_column(NVARCHAR(100))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))

    plan: Mapped[SubscriptionPlan] = relationship()
    usuarioTitular: Mapped[User | None] = relationship()
    institucion: Mapped[Institution | None] = relationship()
