# InstitutionUser - InstitucionUsuario
#
# Relación usuario-institución. Sin objetos anidados: solo identificadores.
# idUsuarioInvitador y origenVinculo los asigna el servidor; estadoRelacion cambia por
# operaciones de negocio (aceptar invitación, baja).

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

RolInstitucion = Literal["PROPIETARIO", "MODERADOR", "OPERADOR"]
EstadoRelacionInstitucion = Literal["PENDIENTE", "ACTIVO", "SUSPENDIDO", "BAJA"]
OrigenVinculo = Literal["CREACION_INSTITUCION", "INVITACION", "CREACION_CUENTA"]


class InstitutionUserBase(BaseModel):
    rolInstitucion: RolInstitucion
    # Matrícula y legajo: identificadores administrativos, se conservan tal cual.
    matriculaProfesional: Annotated[str, Field(max_length=100)] | None = None
    legajoInstitucional: Annotated[str, Field(max_length=100)] | None = None

    @field_validator("rolInstitucion", mode="before")
    @classmethod
    def normalizarRol(cls, value):
        return normalizeUpper(value)


class InstitutionUserCreate(InstitutionUserBase):
    model_config = ConfigDict(extra="forbid")

    idInstitucion: uuid.UUID
    idUsuarioInvitado: uuid.UUID


class InstitutionUserUpdate(InstitutionUserBase):
    model_config = ConfigDict(extra="forbid")

    rolInstitucion: RolInstitucion | None = None


class InstitutionUserRead(InstitutionUserBase):
    model_config = ConfigDict(from_attributes=True)

    idInstitucionUsuario: uuid.UUID
    idInstitucion: uuid.UUID
    idUsuarioInvitado: uuid.UUID
    estadoRelacion: EstadoRelacionInstitucion
    origenVinculo: OrigenVinculo
    idUsuarioInvitador: uuid.UUID | None = None
    fechaInvitacion: datetime
    fechaIncorporacion: datetime | None = None
    fechaBaja: datetime | None = None

    @field_validator("estadoRelacion", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)

    @field_validator("origenVinculo", mode="before")
    @classmethod
    def normalizarOrigen(cls, value):
        return normalizeUpper(value)
