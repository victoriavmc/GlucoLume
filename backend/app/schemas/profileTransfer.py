# ProfileTransfer - TransferenciaPerfil
#
# Aceptar, rechazar o cancelar una transferencia son operaciones de negocio que cambian
# estado y fechaTransferencia: no hay Update genérico.

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeSentence, normalizeStatus

EstadoTransferencia = Literal["PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA"]


class ProfileTransferBase(BaseModel):
    observacion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("observacion", mode="before")
    @classmethod
    def normalizarObservacion(cls, value):
        return normalizeSentence(value)


class ProfileTransferCreate(ProfileTransferBase):
    model_config = ConfigDict(extra="forbid")

    idPerfilMedicion: uuid.UUID
    idOperadorDestino: uuid.UUID


class ProfileTransferRead(ProfileTransferBase):
    model_config = ConfigDict(from_attributes=True)

    idTransferenciaPerfil: uuid.UUID
    idPerfilMedicion: uuid.UUID
    idOperadorDestino: uuid.UUID
    estado: EstadoTransferencia
    fechaPeticion: datetime
    fechaTransferencia: datetime | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del módulo de transferencias institucionales (/institutions/{id}/transfers) -----------------------


class TransferRequest(ProfileTransferBase):
    """Solicitud de transferencia: el perfil va en la ruta y el solicitante sale de la sesión (nunca del cliente)."""

    model_config = ConfigDict(extra="forbid")

    idOperadorDestino: uuid.UUID


class TransferParty(BaseModel):
    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    activo: bool
    # Vínculo institucional (histórico: sigue informando el rol aunque la persona ya no esté vinculada).
    rolInstitucion: str | None = None
    estadoRelacion: str | None = None


class TransferPatient(BaseModel):
    """Paciente de la transferencia. Siempre el identificador seudónimo, la edad y el sexo; nombre y apellido solo si
    quien consulta está autorizado a ver los datos identificativos (nunca documento ni fecha de nacimiento)."""

    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str | None
    edad: int | None
    sexoModelo: str | None
    nombre: str | None = None
    apellido: str | None = None
    puedeVerPerfil: bool = False
    # None: sin autorización para ver datos identificativos. False: autorizado, pero depurados o no registrados.
    datosIdentificativos: bool | None = None


TipoTransferencia = Literal["TRANSFERENCIA", "REASIGNACION"]


class TransferItem(BaseModel):
    idTransferenciaPerfil: uuid.UUID
    estado: EstadoTransferencia
    fechaPeticion: datetime
    fechaTransferencia: datetime | None
    observacion: str | None
    paciente: TransferPatient
    origen: TransferParty | None
    destino: TransferParty
    # Relación de quien consulta con la transferencia y las acciones que le corresponden.
    esRecibida: bool
    esEnviada: bool
    puedeAceptar: bool
    puedeRechazar: bool
    puedeCancelar: bool
    # TRANSFERENCIA: solicitud entre operadores. REASIGNACION: cambio directo hecho por propietario o moderador.
    tipo: TipoTransferencia = "TRANSFERENCIA"


class TransferActor(BaseModel):
    nombre: str | None
    apellido: str | None
    rolInstitucion: str | None


class TransferInstitution(BaseModel):
    idInstitucion: uuid.UUID
    nombre: str


class TransferStep(BaseModel):
    clave: str
    etiqueta: str
    fechaHora: datetime
    usuario: str | None = None


class TransferTechnical(BaseModel):
    idTransferenciaPerfil: uuid.UUID
    idPerfilMedicion: uuid.UUID
    idOperadorOrigen: uuid.UUID | None
    idOperadorDestino: uuid.UUID
    idInstitucion: uuid.UUID
    eventos: list[dict]


class TransferDetail(TransferItem):
    """Detalle de una transferencia. Las fechas llevan su zona (hora de Argentina, UTC-03:00)."""

    paciente: TransferPatient
    institucion: TransferInstitution
    solicitante: TransferActor | None
    fechaRespuesta: datetime | None
    descripcion: str
    historial: list[TransferStep]
    # Identificadores y eventos originales: solo para quien supervisa (propietario y moderador). El operador no los recibe.
    tecnico: TransferTechnical | None = None


class TransferPage(BaseModel):
    items: list[TransferItem]
    total: int
    pagina: int
    tamanioPagina: int
