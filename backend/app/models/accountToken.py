# AccountToken - TokenCuenta

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class TipoTokenCuenta(StrEnum):
    """Única fuente de los valores de TokenCuenta.tipo en el backend.

    Debe coincidir con CK_TokenCuenta_tipo en SQL Server. Agregar un tipo exige actualizar el CHECK en
    database/reference/GlucoLume_DB_v5.sql (y, en una base instalada, recrearlo con la lista completa);
    tests/test_reference_schema.py verifica que el modelo y v5 admitan los mismos valores.
    """

    VERIFICACION_EMAIL = "VERIFICACION_EMAIL"
    RECUPERACION_PASSWORD = "RECUPERACION_PASSWORD"  # nosec B105 - tipo reservado; aún sin endpoint
    ELIMINAR_CUENTA = "ELIMINAR_CUENTA"  # 003_eliminacion_cuenta.sql
    INTERCAMBIO_GOOGLE = "INTERCAMBIO_GOOGLE"  # 006_intercambio_google.sql
    RECUPERACION_MFA = "RECUPERACION_MFA"  # 007_recuperacion_mfa.sql
    ACTIVACION_CUENTA = "ACTIVACION_CUENTA"  # 011_activacion_cuenta_invitada.sql


TOKEN_TYPE_CHECK_NAME = "CK_TokenCuenta_tipo"


class AccountToken(Base):
    __tablename__ = "TokenCuenta"
    __table_args__ = (
        UniqueConstraint("tokenHash", name="UQ_TokenCuenta_tokenHash"),
        CheckConstraint("[fechaExpiracion]>[fechaCreacion]", name="CK_TokenCuenta_expiracion"),
        CheckConstraint(
            " OR ".join(f"[tipo]=N'{tipo}'" for tipo in TipoTokenCuenta),
            name=TOKEN_TYPE_CHECK_NAME,
        ),
    )

    idTokenCuenta: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_TokenCuenta_Usuario")
    )
    tipo: Mapped[str] = mapped_column(NVARCHAR(40))
    tokenHash: Mapped[str] = mapped_column(NVARCHAR(255))
    fechaCreacion: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    fechaExpiracion: Mapped[datetime] = mapped_column(DATETIME2(precision=3))
    fechaUso: Mapped[datetime | None] = mapped_column(DATETIME2(precision=3))

    usuario: Mapped[User] = relationship()
