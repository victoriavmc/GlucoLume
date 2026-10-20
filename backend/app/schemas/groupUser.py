# GroupUser - GrupoUsuario
#
# Relación usuario-grupo. Sin objetos anidados: solo identificadores.
# estadoRelacion y sus fechas cambian por operaciones de negocio (aceptar invitación, baja).

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.normalizers import normalizeStatus, normalizeUpper

RolGrupo = Literal["PROPIETARIO", "MODERADOR", "MIEMBRO"]
EstadoRelacionGrupo = Literal["PENDIENTE", "ACTIVO", "SUSPENDIDO", "BAJA"]
NivelComparticion = Literal["NINGUNA", "SOLO_MOMENTO", "MEDICION_COMPLETA"]


class GroupUserBase(BaseModel):
    @field_validator("rolGrupo", "nivelComparticion", mode="before", check_fields=False)
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)


class GroupUserCreate(GroupUserBase):
    model_config = ConfigDict(extra="forbid")

    idGrupo: uuid.UUID
    idUsuario: uuid.UUID
    rolGrupo: RolGrupo = "MIEMBRO"


class GroupUserUpdate(GroupUserBase):
    model_config = ConfigDict(extra="forbid")

    rolGrupo: RolGrupo | None = None
    nivelComparticion: NivelComparticion | None = None
    visualiza: bool | None = None


class GroupUserRead(GroupUserBase):
    model_config = ConfigDict(from_attributes=True)

    idGrupoUsuario: uuid.UUID
    idGrupo: uuid.UUID
    idUsuario: uuid.UUID
    rolGrupo: RolGrupo
    estadoRelacion: EstadoRelacionGrupo
    nivelComparticion: NivelComparticion
    fechaInvitacion: datetime
    fechaIncorporacion: datetime | None = None
    fechaBaja: datetime | None = None
    visualiza: bool

    @field_validator("estadoRelacion", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)
