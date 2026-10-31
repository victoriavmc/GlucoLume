# AuditReview - AuditoriaRevision
#
# Marca «analizado» de un evento de auditoría, puesta por la administración de la plataforma al revisarlo. Va en su propia tabla y no
# modifica la fila de Auditoria: los registros originales no cambian. Existe a lo sumo una marca por evento (la clave es el evento);
# desmarcarlo borra la fila. Solo la administración la lee y la cambia; la auditoría institucional nunca la devuelve. Si la base instalada
# todavía no tiene la tabla, la auditoría sigue igual, sin marca (schemaCompat.auditReviewReady).

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditReview(Base):
    __tablename__ = "AuditoriaRevision"

    idAuditoria: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True),
        ForeignKey("Auditoria.idAuditoria", ondelete="CASCADE", name="FK_AuditoriaRevision_Auditoria"),
        primary_key=True,
    )
    idUsuarioRevisor: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_AuditoriaRevision_Usuario"), nullable=False
    )
    fechaRevision: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
