# KnownAccess - AccesoConocido
#
# Combinaciones de navegador, sistema y tipo de equipo desde las que una cuenta ya inició sesión. Es lo que permite decidir, con un
# criterio verificable, cuándo un inicio de sesión merece un aviso visible: solo el que llega desde una combinación que la cuenta
# nunca había usado. No guarda IP ni el agente de usuario completo (la auditoría de autenticación conserva ese detalle por su cuenta);
# `huella` es un SHA-256 de los tres rótulos, único por cuenta.

import uuid
from datetime import datetime

from sqlalchemy import NVARCHAR, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnownAccess(Base):
    __tablename__ = "AccesoConocido"
    __table_args__ = (UniqueConstraint("idUsuario", "huella", name="UQ_AccesoConocido_usuarioHuella"),)

    idAccesoConocido: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()")
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_AccesoConocido_Usuario")
    )
    huella: Mapped[str] = mapped_column(NVARCHAR(64))
    navegador: Mapped[str | None] = mapped_column(NVARCHAR(60), nullable=True)
    sistemaOperativo: Mapped[str | None] = mapped_column(NVARCHAR(60), nullable=True)
    dispositivo: Mapped[str | None] = mapped_column(NVARCHAR(40), nullable=True)
    primerAcceso: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
    ultimoAcceso: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
