# Institution - Institucion

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator

from app.schemas.institutionUser import RolInstitucion
from app.utils.normalizers import normalizeEmail, normalizeProperName, normalizeSentence, normalizeStatus, normalizeUpper

TipoIdentificadorLegal = Literal["CUIT", "OTRO"]
TipoInstitucion = Literal["HOSPITAL", "CLINICA", "CONSULTORIO", "LABORATORIO", "OTRO"]
EstadoInstitucion = Literal["ACTIVA", "INACTIVA", "CERRADA"]


class InstitutionBase(BaseModel):
    # Nombre de institución: no es nombre de persona, se conserva tal cual.
    nombre: Annotated[str, Field(max_length=150)]
    tipoInstitucion: TipoInstitucion
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("tipoInstitucion", mode="before")
    @classmethod
    def normalizarTipoInstitucion(cls, value):
        return normalizeUpper(value)

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)


class InstitutionCreate(InstitutionBase):
    model_config = ConfigDict(extra="forbid")

    tipoIdentificadorLegal: TipoIdentificadorLegal = "CUIT"
    # Identificador legal (CUIT u otro): formato no definido, se conserva tal cual.
    identificadorLegal: Annotated[str, Field(max_length=50)]

    @field_validator("tipoIdentificadorLegal", mode="before")
    @classmethod
    def normalizarTipoIdentificador(cls, value):
        return normalizeUpper(value)


class InstitutionUpdate(InstitutionBase):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=150)] | None = None
    tipoInstitucion: TipoInstitucion | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None


class InstitutionRead(InstitutionBase):
    model_config = ConfigDict(from_attributes=True)

    idInstitucion: uuid.UUID
    tipoIdentificadorLegal: TipoIdentificadorLegal
    identificadorLegal: str
    estado: EstadoInstitucion
    fechaCreacion: datetime
    fechaActualizacion: datetime

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del módulo Institución -----------------------------------------------------
#
# Roles institucionales (por institución, en InstitucionUsuario) y permisos: ver
# backend/app/services/institution.py (ROLE_PERMISSIONS). El rol nunca lo decide el cliente.

CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
CUIT_FORMAT = re.compile(r"\d{2}-\d{8}-\d|\d{11}")

# Permisos que el backend informa por institución (criterio de presentación en React; la autorización
# real se valida en cada endpoint).
PermisoInstitucion = Literal[
    "CONSULTAR_INSTITUCION",
    "MODIFICAR_INSTITUCION",
    "GESTIONAR_MODERADORES",
    "INCORPORAR_OPERADORES",
    "ADMINISTRAR_OPERADORES",
    "CONSULTAR_EQUIPO",
    "ELIMINAR_INSTITUCION",
    "CONSULTAR_PACIENTES",
    "GESTIONAR_PACIENTES",
    "BAJA_PACIENTES",
    "GESTIONAR_MATRICES",
    "CONSULTAR_MATRIZ",
    "CONSULTAR_AUDITORIA",
    "CONSULTAR_DISPOSITIVOS",
    "GESTIONAR_DISPOSITIVOS",
    "RETIRAR_DISPOSITIVOS",
]


def isValidCuit(digits: str) -> bool:
    """CUIT/CUIL argentino: 11 dígitos con dígito verificador (módulo 11)."""
    if len(digits) != 11 or not digits.isdigit():
        return False
    remainder = 11 - sum(int(d) * w for d, w in zip(digits[:10], CUIT_WEIGHTS)) % 11
    expected = {11: 0, 10: 9}.get(remainder, remainder)
    return int(digits[10]) == expected


def normalizeLegalId(tipo: str, value: str) -> str:
    """Valida y normaliza el identificador legal. CUIT: formato argentino XX-XXXXXXXX-X u 11 dígitos, con dígito
    verificador; se guarda solo con dígitos para que la unicidad no dependa del formato."""
    value = value.strip()
    if tipo == "CUIT":
        if not CUIT_FORMAT.fullmatch(value):
            raise ValueError("El CUIT no es válido: usá el formato XX-XXXXXXXX-X o los 11 dígitos.")
        value = value.replace("-", "")
        if not isValidCuit(value):
            raise ValueError("El CUIT no es válido: deben ser 11 dígitos con su dígito verificador.")
    elif not value:
        raise ValueError("Ingresá el identificador legal de la institución.")
    return value


def _trimName(value):
    return value.strip() if isinstance(value, str) else value


class InstitutionCreateRequest(InstitutionCreate):
    """Institución que crea una cuenta USUARIO_INSTITUCIONAL ya existente (queda como PROPIETARIO).

    El nombre puede repetirse entre instituciones; el CUIT es único (UQ_Institucion_identificadorLegal).
    """

    nombre: Annotated[str, Field(min_length=2, max_length=150)]

    @field_validator("nombre", mode="before")
    @classmethod
    def recortarNombre(cls, value):
        return _trimName(value)

    @model_validator(mode="after")
    def validarIdentificador(self):
        self.identificadorLegal = normalizeLegalId(self.tipoIdentificadorLegal, self.identificadorLegal)
        return self


class InstitutionUpdateRequest(BaseModel):
    """Datos institucionales que puede modificar el PROPIETARIO. El CUIT no se modifica: identifica a la institución
    y cambiarlo permitiría apropiarse de otra identidad legal sin una verificación que GlucoLume no realiza."""

    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=150)] | None = None
    tipoInstitucion: TipoInstitucion | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def recortarNombre(cls, value):
        return _trimName(value)

    @field_validator("tipoInstitucion", mode="before")
    @classmethod
    def normalizarTipoInstitucion(cls, value):
        return normalizeUpper(value)

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)



class MyInstitutionRead(BaseModel):
    """Institución activa a la que pertenece la cuenta autenticada, con su rol en ella."""

    idInstitucion: uuid.UUID
    nombre: str
    tipoInstitucion: TipoInstitucion
    estado: EstadoInstitucion
    rolInstitucion: RolInstitucion
    estadoRelacion: str
    permisos: list[PermisoInstitucion]


class PersonSummary(BaseModel):
    """Identificación mínima de una persona del equipo (sin correo ni otros datos personales)."""

    nombre: str | None
    apellido: str | None


class InstitutionDetail(MyInstitutionRead):
    """Detalle completo con las columnas reales de Institucion (datos generales, identificación legal, estado y
    fechas) más datos derivados: propietario, rol y permisos de la cuenta, y composición del equipo y pacientes."""

    tipoIdentificadorLegal: TipoIdentificadorLegal
    identificadorLegal: str
    descripcion: str | None
    fechaCreacion: datetime
    fechaActualizacion: datetime
    propietario: PersonSummary | None
    cantidadModeradores: int
    cantidadOperadores: int
    cantidadPacientes: int
    # Cupos de cuentas institucionales (solo propietario y moderador; el operador no los recibe). Se calculan en el servidor.
    capacidadMaximaUsuarios: int | None = None
    usuariosActivos: int | None = None
    cuposDisponibles: int | None = None
    porcentajeUtilizacion: float | None = None
    cantidadReaperturas: int
    fechaUltimaReapertura: datetime | None


class InstitutionOperationResult(InstitutionDetail):
    """Respuesta de POST /institutions (CREADA) y POST /institutions/reopen (REABIERTA)."""

    operacion: Literal["CREADA", "REABIERTA"]


# --- Estado de un CUIT y reapertura de instituciones cerradas ------------------------------


class LegalIdCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipoIdentificadorLegal: TipoIdentificadorLegal = "CUIT"
    identificadorLegal: Annotated[str, Field(max_length=50)]

    @field_validator("tipoIdentificadorLegal", mode="before")
    @classmethod
    def normalizarTipoIdentificador(cls, value):
        return normalizeUpper(value)

    @model_validator(mode="after")
    def validarIdentificador(self):
        self.identificadorLegal = normalizeLegalId(self.tipoIdentificadorLegal, self.identificadorLegal)
        return self


class ReopenPreview(BaseModel):
    """Datos vigentes de la institución cerrada, solo para quien está autorizado a reabrirla."""

    nombre: str
    tipoInstitucion: TipoInstitucion
    descripcion: str | None
    cantidadReaperturas: int


class LegalIdStatus(BaseModel):
    """DISPONIBLE: se puede crear. ACTIVA: ya registrada. CERRADA: existe cerrada; `puedeReabrir` indica si la cuenta
    autenticada está autorizada a reabrirla (en ese caso se incluyen sus datos vigentes)."""

    estado: Literal["DISPONIBLE", "ACTIVA", "CERRADA"]
    puedeReabrir: bool = False
    mensaje: str | None = None
    institucion: ReopenPreview | None = None


class InstitutionReopenRequest(InstitutionCreateRequest):
    """Reapertura de una institución CERRADA por su último propietario: nuevos datos administrativos más la misma
    reautenticación que las operaciones sensibles (contraseña si tiene credencial local; MFA si lo tiene)."""

    password: Annotated[SecretStr, Field(min_length=1)] | None = None
    codigo: Annotated[str, Field(max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(max_length=32)] | None = None

    @model_validator(mode="after")
    def validarUnFactor(self):
        if self.codigo is not None and self.codigoRecuperacion is not None:
            raise ValueError("Indicar solo uno: codigo o codigoRecuperacion.")
        return self


class MemberEmailRequest(BaseModel):
    """Búsqueda o invitación por correo exacto de una cuenta institucional (nunca coincidencias parciales)."""

    model_config = ConfigDict(extra="forbid")

    correoElectronico: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("correoElectronico", mode="before")
    @classmethod
    def normalizarCorreo(cls, value):
        return normalizeEmail(value)


MEMBER_ADMIN_FIELDS = (
    "matriculaProfesional", "legajoInstitucional", "funcionProfesional", "nombreProfesionalHistorico",
    "apellidoProfesionalHistorico",
)
# Función profesional descriptiva del vínculo; NO es el rol institucional (que define los permisos).
FuncionProfesional = Literal["OPERADOR", "ENFERMERO", "MEDICO"]


class MemberAdminFields(BaseModel):
    """Datos administrativos del vínculo (InstitucionUsuario), iguales para moderadores y operadores. Todos son
    opcionales: matrícula y legajo no tienen formato obligatorio; un texto vacío se guarda como NULL. El nombre y
    apellido profesional histórico son los de la persona en esta institución (no modifican la cuenta Usuario)."""

    model_config = ConfigDict(extra="forbid")

    matriculaProfesional: Annotated[str, Field(max_length=100)] | None = None
    legajoInstitucional: Annotated[str, Field(max_length=100)] | None = None
    funcionProfesional: FuncionProfesional | None = None
    nombreProfesionalHistorico: Annotated[str, Field(max_length=100)] | None = None
    apellidoProfesionalHistorico: Annotated[str, Field(max_length=100)] | None = None

    @field_validator("funcionProfesional", mode="before")
    @classmethod
    def normalizarFuncion(cls, value):
        return normalizeUpper(value) if isinstance(value, str) and value.strip() else None

    @field_validator("matriculaProfesional", "legajoInstitucional", mode="before")
    @classmethod
    def recortarTexto(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("nombreProfesionalHistorico", "apellidoProfesionalHistorico", mode="before")
    @classmethod
    def normalizarNombreHistorico(cls, value):
        if isinstance(value, str):
            return normalizeProperName(value) if value.strip() else None
        return value


class MemberInviteRequest(MemberEmailRequest, MemberAdminFields):
    """Incorporar personal: correo y, si la persona todavía no tiene cuenta, nombre y apellido para crearla
    (USUARIO_INSTITUCIONAL pendiente de activación), más los datos administrativos del vínculo. Si el nombre o
    apellido histórico no se envían, se toman los de la persona. El rol lo fija el endpoint, nunca el cliente."""

    nombre: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    apellido: Annotated[str, Field(min_length=1, max_length=100)] | None = None

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def normalizarNombre(cls, value):
        return normalizeProperName(value) if isinstance(value, str) and value.strip() else None

    def adminFields(self) -> dict:
        return {field: getattr(self, field) for field in MEMBER_ADMIN_FIELDS}


# Mismo contrato para ambos roles (se conserva el nombre usado por el endpoint de operadores).
OperatorInviteRequest = MemberInviteRequest


class MemberAdminUpdateRequest(MemberAdminFields):
    """Edición de los datos administrativos de un vínculo. Solo se modifican los campos enviados; el rol no forma
    parte del contrato (un campo desconocido como `rolInstitucion` responde 422)."""


class MemberCandidate(BaseModel):
    """Datos mínimos para confirmar a quién se invita (sin DNI, fecha de nacimiento ni datos de salud).

    Solo se devuelve cuando la cuenta existe y puede invitarse; si no existe, la búsqueda responde 404 y el
    formulario pide nombre y apellido para crearla. `cuentaPendiente`: invitada antes y todavía sin activar.
    """

    nombre: str | None
    apellido: str | None
    rolPropuesto: Literal["MODERADOR", "OPERADOR"]
    cuentaPendiente: bool = False


class MemberRead(BaseModel):
    """Integrante del equipo (vínculo vigente o invitación pendiente). Sin correo ni datos personales extra."""

    idInstitucionUsuario: uuid.UUID
    nombre: str | None
    apellido: str | None
    usuario: str | None
    # Lo ve solo quien gestiona el equipo (PROPIETARIO o MODERADOR).
    correoElectronico: str | None = None
    rolInstitucion: RolInstitucion
    estadoRelacion: str
    # La cuenta todavía no se activó (creada por la invitación).
    cuentaPendiente: bool = False
    matriculaProfesional: str | None = None
    legajoInstitucional: str | None = None
    funcionProfesional: FuncionProfesional | None = None
    nombreProfesionalHistorico: str | None = None
    apellidoProfesionalHistorico: str | None = None
    fechaInvitacion: datetime | None = None
    fechaIncorporacion: datetime | None = None
    fechaBaja: datetime | None = None
    fechaVencimientoInvitacion: datetime | None = None
    invitacionVencida: bool = False


class InvitationRead(BaseModel):
    """Invitación recibida por la cuenta autenticada: PENDIENTE (se puede responder) o VENCIDA (solo informativa)."""

    idInstitucionUsuario: uuid.UUID
    idInstitucion: uuid.UUID
    nombreInstitucion: str
    tipoInstitucion: TipoInstitucion
    rolInstitucion: RolInstitucion
    nombreInvitante: str | None
    fechaInvitacion: datetime
    fechaVencimiento: datetime
    estado: Literal["PENDIENTE", "VENCIDA"] = "PENDIENTE"


class InstitutionDeletionRequest(BaseModel):
    """Eliminación lógica: confirmación explícita (nombre exacto) y la reautenticación que tenga la cuenta.

    password: obligatoria si la cuenta tiene contraseña local. codigo / codigoRecuperacion: uno de los dos si tiene
    MFA habilitado; nunca ambos.
    """

    model_config = ConfigDict(extra="forbid")

    confirmacionNombre: Annotated[str, Field(min_length=1, max_length=150)]
    password: Annotated[SecretStr, Field(min_length=1)] | None = None
    codigo: Annotated[str, Field(max_length=10)] | None = None
    codigoRecuperacion: Annotated[str, Field(max_length=32)] | None = None

    @model_validator(mode="after")
    def validarUnFactor(self):
        if self.codigo is not None and self.codigoRecuperacion is not None:
            raise ValueError("Indicar solo uno: codigo o codigoRecuperacion.")
        return self


class QuotaRead(BaseModel):
    """Cupos de cuentas institucionales de UNA institución. Capacidad máxima de cuentas activas, cuentas activas hoy (propietario,
    moderadores y operadores con relación ACTIVA; sin invitaciones pendientes ni bajas), disponibles y utilización."""

    capacidadMaximaUsuarios: int
    usuariosActivos: int
    cuposDisponibles: int
    porcentajeUtilizacion: float
    estado: Literal["DISPONIBLE", "PROXIMO_AL_LIMITE", "COMPLETA", "EXCEDIDA"]
    excedente: int = 0  # cuentas activas por encima del límite (la plataforma lo redujo): se conservan, pero no se admiten más


class SupportRequest(BaseModel):
    """Consulta del PROPIETARIO de una institución pausada al soporte de GlucoLume. Nombre y correo salen de la cuenta autenticada (no se piden):
    solo el asunto y el mensaje. El contexto de la institución lo agrega el servidor."""

    model_config = ConfigDict(extra="forbid")

    asunto: Annotated[str, Field(min_length=3, max_length=100)]
    mensaje: Annotated[str, Field(min_length=10, max_length=1500)]

    @field_validator("asunto", mode="before")
    @classmethod
    def unaLinea(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("mensaje", mode="before")
    @classmethod
    def recortar(cls, value):
        return value.strip() if isinstance(value, str) else value


class SupportRequestResult(BaseModel):
    mensaje: str
    confirmacionEnviada: bool
