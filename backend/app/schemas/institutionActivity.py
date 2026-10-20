# InstitutionActivity - Contrato de la «Actividad reciente» de una institución (solo lectura)
#
# Resumen comprensible de lo que pasó en la institución: no es la auditoría (que conserva identificadores, valores anteriores y
# nuevos y trazabilidad técnica) sino una vista curada y filtrada por permisos de los mismos eventos. Nunca incluye datos
# personales de pacientes (solo su seudónimo), contraseñas ni secretos.

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.utils.timeZone import withArgentinaZone

Categoria = Literal["INSTITUCION", "MODERADORES", "OPERADORES", "PACIENTES", "MEDICIONES", "DISPOSITIVOS", "MATRICES", "SEGURIDAD"]


class ActivityItem(BaseModel):
    titulo: str  # nombre descriptivo de la operación («Moderador incorporado»)
    categoria: Categoria  # el cliente elige el ícono
    entidad: str | None  # sobre quién o qué se realizó («Victoria Valentina Collins», «Dispositivo GL-0001»)
    usuario: str | None  # quién la realizó
    fechaHora: datetime
    resultado: Literal["EXITO", "FALLO"]
    critica: bool = False
    rechazado: bool = False  # operación rechazada por falta de permiso o acceso (solo la ve quien puede consultar la auditoría)
    # Ruta relativa a la institución (p. ej. «personal/moderadores») solo si quien consulta puede abrir esa pantalla.
    ruta: str | None = None
    # Evento de auditoría que lo originó; se informa solo a quien puede consultar la auditoría (para abrir su detalle).
    idAuditoria: uuid.UUID | None = None

    @field_serializer("fechaHora")
    def _withZone(self, value: datetime) -> str:
        """El backend persiste hora de Argentina sin zona: se informa con su zona (UTC-03:00)."""
        return withArgentinaZone(value).isoformat()


class ActivityPage(BaseModel):
    items: list[ActivityItem]
