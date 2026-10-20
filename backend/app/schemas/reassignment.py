# Reassignment - Pacientes pendientes de reasignación (gestión por moderador o propietario)
#
# Solo identificación administrativa del paciente (seudónimo y nombre, como en el padrón): nunca documento, sexo, fecha de nacimiento
# ni mediciones. El nombre del operador anterior es el histórico registrado en su vínculo.

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeSentence

EstadoReasignacion = Literal["PENDIENTE", "COMPLETADA", "CANCELADA"]
ResultadoReasignacion = Literal["REASIGNADO", "PACIENTE_DADO_DE_BAJA", "INSTITUCION_CERRADA", "YA_RESUELTA", "NO_ENCONTRADA"]

MAX_BATCH = 200


class ReassignmentGroup(BaseModel):
    """Un operador desvinculado con sus pacientes: la fila del tablero «Pacientes pendientes de reasignación»."""

    idOperadorAnterior: uuid.UUID
    operadorAnterior: str | None = None
    fechaDesvinculacion: datetime | None = None
    pendientes: int
    completadas: int
    canceladas: int
    # PENDIENTE mientras queden pacientes por reasignar; RESUELTA cuando ya no queda ninguno.
    estado: Literal["PENDIENTE", "RESUELTA"]


class ReassignmentUnregistered(BaseModel):
    """Un operador ya desvinculado que sigue figurando como responsable de pacientes SIN tarea de reasignación (asignación inconsistente,
    p. ej. una baja anterior a este control). Se regulariza a pedido de quien gestiona: nada se reasigna solo."""

    idOperadorAnterior: uuid.UUID
    operadorAnterior: str | None = None
    fechaDesvinculacion: datetime | None = None
    pacientes: int


class ReassignmentOverview(BaseModel):
    pendientes: int
    operadoresDisponibles: int
    grupos: list[ReassignmentGroup]
    sinRegularizar: int = 0  # pacientes con responsable desvinculado y sin tarea de reasignación
    gruposSinRegularizar: list[ReassignmentUnregistered] = []


class ReassignmentRegularizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idOperadorAnterior: uuid.UUID


class ReassignmentRegularizeResult(BaseModel):
    pacientesPendientes: int


class ReassignmentItem(BaseModel):
    idReasignacionPaciente: uuid.UUID
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None = None
    nombre: str | None = None
    apellido: str | None = None
    idOperadorAnterior: uuid.UUID
    operadorAnterior: str | None = None
    estado: EstadoReasignacion
    resultado: str | None = None
    fechaCreacion: datetime
    fechaResolucion: datetime | None = None
    idOperadorNuevo: uuid.UUID | None = None
    operadorNuevo: str | None = None
    resueltoPor: str | None = None
    observacion: str | None = None


class ReassignmentPage(BaseModel):
    items: list[ReassignmentItem]
    total: int


class ReassignmentAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idsReasignacion: Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_BATCH)]
    idOperadorNuevo: uuid.UUID
    observacion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("observacion", mode="before")
    @classmethod
    def normalizarObservacion(cls, value):
        return normalizeSentence(value)


class ReassignmentOutcome(BaseModel):
    idReasignacionPaciente: uuid.UUID
    resultado: ResultadoReasignacion


class ReassignmentAssignResult(BaseModel):
    reasignados: int
    resultados: list[ReassignmentOutcome]
