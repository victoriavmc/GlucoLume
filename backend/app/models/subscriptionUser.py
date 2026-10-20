# SubscriptionUser - SuscripcionUsuario

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.subscription import Subscription
from app.models.user import User


class SubscriptionUser(Base):
    __tablename__ = "SuscripcionUsuario"
    __table_args__ = (
        CheckConstraint("[estadoRelacion]<>N'BAJA' OR [fechaBaja] IS NOT NULL", name="CK_SuscripcionUsuario_baja"),
        CheckConstraint(
            "[estadoRelacion]=N'BAJA' OR [estadoRelacion]=N'ACTIVA'",
            name="CK_SuscripcionUsuario_estado",
        ),
    )

    idSuscripcionUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idSuscripcion: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Suscripcion.idSuscripcion", name="FK_SuscripcionUsuario_Suscripcion"),
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_SuscripcionUsuario_Usuario")
    )
    esTitular: Mapped[bool] = mapped_column(BIT, server_default=text("0"))
    estadoRelacion: Mapped[str] = mapped_column(NVARCHAR(20), server_default=text("N'ACTIVA'"))
    fechaIncorporacion: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=text("sysutcdatetime()")
    )
    fechaBaja: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    suscripcion: Mapped[Subscription] = relationship()
    usuario: Mapped[User] = relationship()
