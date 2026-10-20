# AuditContext - AuditoriaContexto
#
# Datos de seguridad de un evento de auditoría, separados de `Auditoria` a propósito:
#   - son datos personales o técnicos de la solicitud (IP, cliente), con un plazo de conservación más corto que el del evento mismo: pasado el
#     plazo se anulan `ipOrigen` y `agenteUsuario` y el evento sigue (services/auditRetention.py);
#   - solo los lee la administración de la plataforma (la auditoría institucional nunca los devuelve);
#   - agregarlos no modifica la tabla que ya usan todos los módulos: si la base instalada todavía no tiene la tabla, el backend sigue auditando sin
#     ellos (schemaCompat.hasTable).
# Nunca se guardan contraseñas, tokens, cookies, códigos de autenticación ni cuerpos de solicitudes. `identificadorHash` es un HMAC con
# clave del servidor del identificador ingresado en un intento sobre una cuenta inexistente: permite ver repeticiones sin guardar lo que
# se escribió (a veces es una contraseña pegada en el campo equivocado).

import uuid

from sqlalchemy import NVARCHAR, ForeignKey, Index
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditContext(Base):
    __tablename__ = "AuditoriaContexto"
    __table_args__ = (
        Index("IX_AuditoriaContexto_correlacion", "idCorrelacion"),
        Index("IX_AuditoriaContexto_ip", "ipOrigen"),
        Index("IX_AuditoriaContexto_identificador", "identificadorHash"),
    )

    idAuditoria: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Auditoria.idAuditoria", ondelete="CASCADE", name="FK_AuditoriaContexto_Auditoria"),
        primary_key=True)
    idCorrelacion: Mapped[str | None] = mapped_column(NVARCHAR(64))
    ipOrigen: Mapped[str | None] = mapped_column(NVARCHAR(45))
    agenteUsuario: Mapped[str | None] = mapped_column(NVARCHAR(100))
    motivo: Mapped[str | None] = mapped_column(NVARCHAR(40))
    identificadorHash: Mapped[str | None] = mapped_column(NVARCHAR(32))
