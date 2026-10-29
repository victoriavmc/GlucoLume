# MeasurementProfile - PerfilMedicion
#
# Contiene datos personales (nombre, apellido, dni, fechaNacimiento). Qué perfiles puede leer
# cada usuario lo decide la capa de servicios.
# idUsuario / idInstitucionUsuarioResponsable los asigna el servidor según quien crea el perfil
# (CK_PerfilMedicion_coherenciaTipo). Las fechas de expiración y depuración son del servidor.

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.normalizers import normalizeDate, normalizeEmail, normalizeProperName, normalizeUpper
from app.utils.timeZone import nowArgentina

TipoPerfil = Literal["CONSUMIDOR_FINAL", "INSTITUCIONAL"]
SexoModelo = Literal["MASCULINO", "FEMENINO"]


class MeasurementProfileBase(BaseModel):
    # Identificador pseudónimo institucional: no se normaliza.
    identificadorPseudonimo: Annotated[str, Field(max_length=100)] | None = None
    nombre: Annotated[str, Field(max_length=100)] | None = None
    apellido: Annotated[str, Field(max_length=100)] | None = None
    # DNI: formato no definido en el modelo, se conserva tal cual.
    dni: Annotated[str, Field(max_length=20)] | None = None
    fechaNacimiento: date | None = None
    edadDeclarada: Annotated[int, Field(ge=0, le=130)] | None = None
    sexoModelo: SexoModelo

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)

    @field_validator("fechaNacimiento", mode="before")
    @classmethod
    def normalizarFechaNacimiento(cls, value):
        return normalizeDate(value)

    @field_validator("sexoModelo", mode="before")
    @classmethod
    def normalizarSexo(cls, value):
        return normalizeUpper(value)


class MeasurementProfileCreate(MeasurementProfileBase):
    model_config = ConfigDict(extra="forbid")

    tipoPerfil: TipoPerfil

    @field_validator("tipoPerfil", mode="before")
    @classmethod
    def normalizarTipoPerfil(cls, value):
        return normalizeUpper(value)


class MeasurementProfileUpdate(MeasurementProfileBase):
    model_config = ConfigDict(extra="forbid")

    sexoModelo: SexoModelo | None = None


class MeasurementProfileRead(MeasurementProfileBase):
    model_config = ConfigDict(from_attributes=True)

    idPerfilMedicion: uuid.UUID
    tipoPerfil: TipoPerfil
    idUsuario: uuid.UUID | None = None
    idInstitucionUsuarioResponsable: uuid.UUID | None = None
    fechaCreacion: datetime
    fechaUltimaMedicion: datetime | None = None
    fechaExpiracionDatosPersonales: datetime | None = None
    fechaDepuracionDatosPersonales: datetime | None = None

    @field_validator("tipoPerfil", mode="before")
    @classmethod
    def normalizarTipoPerfil(cls, value):
        return normalizeUpper(value)


DOCUMENT_FORMAT = re.compile(r"[A-Z0-9]{6,12}")


def normalizeDocument(value):
    """DNI u otro documento: sin puntos, espacios ni guiones, en mayúsculas (30.111.222 -> 30111222)."""
    if not isinstance(value, str):
        return value
    return "".join(char for char in value if char not in " .-").upper()


def validateDocument(value):
    if value is not None and not DOCUMENT_FORMAT.fullmatch(value):
        raise ValueError("Ingresá un documento válido: entre 6 y 12 letras o números.")
    return value


class InstitutionalProfileCreate(BaseModel):
    """Datos de un paciente institucional (lo carga un operador). Preparado para el módulo Institución/Medición.

    El servidor asigna tipoPerfil, idInstitucionUsuarioResponsable, identificadorPseudonimo y fechaCreacion.
    No incluye contexto de la medición (comida, estado actual): eso pertenece a Medicion.
    """

    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=1, max_length=100)]
    apellido: Annotated[str, Field(min_length=1, max_length=100)]
    # Documento, fecha de nacimiento y sexo son opcionales: se pueden completar después. Para MEDIR hacen falta
    # la edad (fecha de nacimiento) y el sexo.
    dni: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    fechaNacimiento: date | None = None
    sexoModelo: SexoModelo | None = None

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)

    @field_validator("dni", mode="before")
    @classmethod
    def normalizarDni(cls, value):
        return normalizeDocument(value)

    @field_validator("dni")
    @classmethod
    def validarDni(cls, value):
        return validateDocument(value)

    @field_validator("fechaNacimiento", mode="before")
    @classmethod
    def normalizarFechaNacimiento(cls, value):
        return normalizeDate(value)

    @field_validator("fechaNacimiento")
    @classmethod
    def validarFechaNacimiento(cls, value: date | None) -> date | None:
        if value is not None and value > nowArgentina().date():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        return value

    @field_validator("sexoModelo", mode="before")
    @classmethod
    def normalizarSexo(cls, value):
        return normalizeUpper(value)

    # Definido al final: los validadores «before» se ejecutan en orden inverso, así un texto vacío llega a los
    # demás ya convertido en None.
    @field_validator("dni", "fechaNacimiento", "sexoModelo", mode="before")
    @classmethod
    def vacioEsNulo(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


# --- Pacientes institucionales (módulo Institución) ----------------------------------------
#
# Un paciente institucional es un PerfilMedicion INSTITUCIONAL administrado por una institución: no es una cuenta
# de GlucoLume ni puede iniciar sesión. Pertenece a la institución a través de su operador responsable
# (idInstitucionUsuarioResponsable -> InstitucionUsuario.idInstitucion); hay un único responsable por paciente.
# No se cargan datos de contacto ni información clínica: solo lo necesario para identificarlo y para el modelo.
#
# Baja administrativa sin columnas nuevas: un perfil institucional con fechaExpiracionDatosPersonales informada está
# dado de baja (en su período de conservación de 12 meses); con fechaDepuracionDatosPersonales ya fue desidentificado.
# `estado` se deriva de esas columnas existentes.

EstadoPaciente = Literal["ACTIVO", "BAJA"]


class PatientCreateRequest(InstitutionalProfileCreate):
    """Alta de paciente. Un OPERADOR no elige responsable: el paciente queda a su cargo (se resuelve en el servidor con su sesión y su
    vínculo activo) y, si envía el identificador de otro operador, se rechaza. Propietario y moderador sí designan al operador
    responsable entre los activos de la institución."""

    idInstitucionUsuarioResponsable: uuid.UUID | None = None


class PatientExportRequest(BaseModel):
    """`SELECCION`: los pacientes de `idsPerfilMedicion`. `TODOS`: los que coinciden con los filtros del listado (un operador, solo los suyos)."""

    alcance: Literal["SELECCION", "TODOS"]
    idsPerfilMedicion: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    busqueda: str | None = Field(default=None, max_length=100)
    idResponsable: uuid.UUID | None = None
    estado: Literal["ACTIVO", "BAJA"] = "ACTIVO"


class PatientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    apellido: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    dni: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    fechaNacimiento: date | None = None
    sexoModelo: SexoModelo | None = None

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value)

    @field_validator("dni", mode="before")
    @classmethod
    def normalizarDni(cls, value):
        return normalizeDocument(value)

    @field_validator("dni")
    @classmethod
    def validarDni(cls, value):
        return validateDocument(value)

    @field_validator("fechaNacimiento", mode="before")
    @classmethod
    def normalizarFechaNacimiento(cls, value):
        return normalizeDate(value)

    @field_validator("fechaNacimiento")
    @classmethod
    def validarFechaNacimiento(cls, value):
        if value is not None and value > nowArgentina().date():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        return value

    @field_validator("sexoModelo", mode="before")
    @classmethod
    def normalizarSexo(cls, value):
        return normalizeUpper(value)


class PatientAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idInstitucionUsuarioResponsable: uuid.UUID


class AssignableOperator(BaseModel):
    """Operador activo que puede quedar a cargo de un paciente: solo lo necesario para identificarlo."""

    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None


class PatientResponsible(AssignableOperator):
    activo: bool


class PatientRegistrant(BaseModel):
    """Quién realizó el alta administrativa del paciente (no es necesariamente su operador responsable)."""

    nombre: str | None
    apellido: str | None
    rolInstitucion: str | None = None


class PatientRead(BaseModel):
    idPerfilMedicion: uuid.UUID
    identificadorPseudonimo: str
    nombre: str | None
    apellido: str | None
    # Datos personales más allá de la identificación administrativa: no se informan a un operador que consulta un paciente ajeno.
    dni: str | None
    fechaNacimiento: date | None
    edad: int | None
    sexoModelo: SexoModelo | None
    estado: EstadoPaciente
    fechaCreacion: datetime
    # Información de salud (fecha de la última medición): solo para quien está autorizado a consultar sus mediciones.
    fechaUltimaMedicion: datetime | None
    # Fin del período de conservación de los datos personales (informada solo si el perfil está de baja).
    fechaExpiracionDatosPersonales: datetime | None
    responsable: PatientResponsible
    puedeModificar: bool
    # Paciente asignado al usuario autenticado («a mi cargo») frente a «registrado en la institución».
    esMio: bool = False
    # El usuario puede consultar y registrar las mediciones de este paciente (operador responsable vigente).
    medicionesAutorizadas: bool = False
    # Quién lo registró (Auditoria CREAR_PACIENTE): distinto de quien es responsable de sus mediciones. None en altas anteriores al registro.
    registradoPor: PatientRegistrant | None = None
    # Correo para recibir los resultados, ENMASCARADO y solo para el operador responsable; vence a los 12 meses de cargarlo o cambiarlo.
    correoResultados: str | None = None
    correoResultadosVence: datetime | None = None
    # Correo (enmascarado) al que se acaba de enviar el pedido de confirmación: se activa cuando el paciente lo confirma (GL-08).
    correoResultadosPendiente: str | None = None


class ResultEmailConfirmRequest(BaseModel):
    """Token del enlace que recibió el paciente para confirmar su correo (viaja en el fragmento de la URL, nunca en la consulta)."""

    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=20, max_length=4096)]


class ResultEmailConfirmRead(BaseModel):
    confirmado: bool
    correoEnmascarado: str
    correoGuardado: bool
    resultadoEnviado: bool


class PatientPage(BaseModel):
    items: list[PatientRead]
    total: int
    pagina: int
    tamanioPagina: int


class PatientResultEmailRequest(BaseModel):
    """Carga o cambio del correo del paciente para recibir sus resultados. El operador confirma que el paciente lo autorizó."""

    model_config = ConfigDict(extra="forbid")

    correo: Annotated[EmailStr, Field(max_length=254)]
    pacienteAutoriza: bool = False

    @field_validator("correo", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)
