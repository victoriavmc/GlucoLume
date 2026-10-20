# Offboarding - Desvinculación de un operador con reasignación obligatoria de sus pacientes
#
# Identificación administrativa del paciente (seudónimo y nombre, como en el padrón y en las reasignaciones): nunca documento, sexo, fecha de
# nacimiento ni mediciones. Los destinos son operadores activos de la misma institución (solo nombre y cantidad de pacientes a cargo).

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeSentence

MAX_PATIENTS = 2000

Bloqueo = Literal["SIN_OPERADOR_DISPONIBLE", "TRANSFERENCIAS_PENDIENTES"]


class OffboardPatient(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None = None
    nombre: str | None = None
    apellido: str | None = None
    # Hay una solicitud de transferencia pendiente de aceptación: hasta que se resuelva, el paciente sigue a cargo de este operador.
    transferenciaPendiente: bool = False


class OffboardTarget(BaseModel):
    idInstitucionUsuario: uuid.UUID
    operador: str | None = None
    pacientesActuales: int


class OffboardPlan(BaseModel):
    idInstitucionUsuario: uuid.UUID
    operador: str | None = None
    cantidadPacientes: int
    transferenciasPendientes: int
    pacientes: list[OffboardPatient]
    destinos: list[OffboardTarget]
    # None = se puede desvincular (sin pacientes) o reasignar y desvincular; si no, el motivo que lo impide.
    bloqueo: Bloqueo | None = None


class OffboardAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idPerfilMedicion: uuid.UUID
    idOperadorNuevo: uuid.UUID


class OffboardRequest(BaseModel):
    """Reasignación completa: UNA entrada por cada paciente que el operador tiene hoy a su cargo."""

    model_config = ConfigDict(extra="forbid")

    asignaciones: Annotated[list[OffboardAssignment], Field(max_length=MAX_PATIENTS)] = []
    observacion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("observacion", mode="before")
    @classmethod
    def normalizarObservacion(cls, value):
        return normalizeSentence(value)


class OffboardDestination(BaseModel):
    idOperadorNuevo: uuid.UUID
    operador: str | None = None
    cantidad: int


class OffboardResult(BaseModel):
    reasignados: int
    destinos: list[OffboardDestination]
