# Consent - ConsentimientoUsuario
#
# Historial de solo-agregado: cada aceptación o revocación es una fila
# nueva. El estado vigente de una persona para un tipo es la fila más reciente.

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import NVARCHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TipoConsentimiento(StrEnum):
    POLITICA_PRIVACIDAD = "POLITICA_PRIVACIDAD"
    DATOS_EXPERIMENTALES = "DATOS_EXPERIMENTALES"


class EstadoConsentimiento(StrEnum):
    ACEPTADO = "ACEPTADO"
    REVOCADO = "REVOCADO"


class Consent(Base):
    __tablename__ = "ConsentimientoUsuario"
    __table_args__ = (
        CheckConstraint(" OR ".join(f"[tipo]=N'{tipo}'" for tipo in TipoConsentimiento),
                        name="CK_ConsentimientoUsuario_tipo"),
        CheckConstraint(" OR ".join(f"[estado]=N'{estado}'" for estado in EstadoConsentimiento),
                        name="CK_ConsentimientoUsuario_estado"),
        Index("IX_ConsentimientoUsuario_usuario_tipo_fecha", "idUsuario", "tipo", "fechaHora"),
    )

    idConsentimiento: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), primary_key=True, server_default=text("newid()"), default=uuid.uuid4
    )
    idUsuario: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER(as_uuid=True), ForeignKey("Usuario.idUsuario", name="FK_ConsentimientoUsuario_Usuario")
    )
    tipo: Mapped[str] = mapped_column(NVARCHAR(30))
    version: Mapped[str] = mapped_column(NVARCHAR(20))
    estado: Mapped[str] = mapped_column(NVARCHAR(20))
    fechaHora: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=text("sysutcdatetime()"))
