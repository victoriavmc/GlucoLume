# MatrixRule - ReglaMatriz

import uuid
from decimal import Decimal

from sqlalchemy import DECIMAL, NVARCHAR, CheckConstraint, ForeignKey, Integer, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.matrix import Matrix


class MatrixRule(Base):
    __tablename__ = "ReglaMatriz"
    __table_args__ = (
        UniqueConstraint("idMatriz", "codigoRegla", name="UQ_ReglaMatriz_codigo"),
        CheckConstraint(
            "[condicionComida]=N'NO_INFORMADA' OR [condicionComida]=N'POSTPRANDIAL' OR [condicionComida]=N'AYUNO'",
            name="CK_ReglaMatriz_condicion",
        ),
        CheckConstraint(
            "[edadDesde]>=(0) AND [edadDesde]<=(130) AND ([edadHasta]>=(0) AND [edadHasta]<=(130))"
            " AND [edadHasta]>=[edadDesde]",
            name="CK_ReglaMatriz_edad",
        ),
        CheckConstraint(
            "[glucosaMinReferencia]>=(0) AND [glucosaMaxReferencia]>=[glucosaMinReferencia]",
            name="CK_ReglaMatriz_glucosaReferencia",
        ),
        CheckConstraint(
            "([minutosComidaMin] IS NULL OR [minutosComidaMin]>=(0))"
            " AND ([minutosComidaMax] IS NULL OR [minutosComidaMax]>=(0))"
            " AND ([minutosComidaMin] IS NULL OR [minutosComidaMax] IS NULL"
            " OR [minutosComidaMax]>=[minutosComidaMin])",
            name="CK_ReglaMatriz_minutos",
        ),
        # La base real también admite NO_INFORMADO (reglas previstas para cuando el sexo no se informó).
        CheckConstraint("[sexoModelo]=N'MASCULINO' OR [sexoModelo]=N'FEMENINO' OR [sexoModelo]=N'NO_INFORMADO'", name="CK_ReglaMatriz_sexo"),
    )

    idReglaMatriz: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idMatriz: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Matriz.idMatriz", name="FK_ReglaMatriz_Matriz")
    )
    codigoRegla: Mapped[str] = mapped_column(NVARCHAR(50))
    sexoModelo: Mapped[str] = mapped_column(NVARCHAR(30))
    # NULL = sin límite (así existen en la base real: reglas para «edad no especificada»).
    edadDesde: Mapped[int | None] = mapped_column(SmallInteger)
    edadHasta: Mapped[int | None] = mapped_column(SmallInteger)
    condicionComida: Mapped[str] = mapped_column(NVARCHAR(30))
    minutosComidaMin: Mapped[int | None] = mapped_column(Integer)
    minutosComidaMax: Mapped[int | None] = mapped_column(Integer)
    glucosaMinReferencia: Mapped[Decimal] = mapped_column(DECIMAL(8, 2))
    glucosaMaxReferencia: Mapped[Decimal] = mapped_column(DECIMAL(8, 2))

    matriz: Mapped[Matrix] = relationship()
