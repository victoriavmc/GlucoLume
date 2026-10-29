# Matrix - Matriz

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalizers import normalizeDate, normalizeSentence, normalizeStatus, normalizeUpper

AmbitoMatriz = Literal["GLOBAL", "INSTITUCION"]
EstadoMatriz = Literal["BORRADOR", "ACTIVA", "INACTIVA", "ARCHIVADA"]

_URL_REFERENCIA = re.compile(r"https?://\S+", re.IGNORECASE)


def normalizeReferenciaBase(value):
    """Nombre del lugar de donde se tomaron los criterios: se recorta y no puede quedar vacío (lo exige el alta)."""
    return value.strip() if isinstance(value, str) else value


def normalizeUrlReferencia(value):
    """Enlace opcional a la referencia: vacío = sin enlace; si se informa, tiene que ser http(s) y sin espacios."""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if value is not None and not (isinstance(value, str) and _URL_REFERENCIA.fullmatch(value)):
        raise ValueError("El enlace de referencia tiene que empezar con http:// o https:// y no llevar espacios.")
    return value


class MatrixBase(BaseModel):
    # Nombre de la matriz: no es nombre de persona, se conserva tal cual.
    nombre: Annotated[str, Field(max_length=100)]
    fechaVigenciaDesde: date
    fechaVigenciaHasta: date | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("fechaVigenciaDesde", "fechaVigenciaHasta", mode="before")
    @classmethod
    def normalizarVigencia(cls, value):
        return normalizeDate(value)

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)


class MatrixCreate(MatrixBase):
    model_config = ConfigDict(extra="forbid")

    # Versión: identificador de versión, se conserva tal cual.
    version: Annotated[str, Field(max_length=50)]
    ambito: AmbitoMatriz = "GLOBAL"
    idInstitucion: uuid.UUID | None = None

    @field_validator("ambito", mode="before")
    @classmethod
    def normalizarAmbito(cls, value):
        return normalizeUpper(value)


class MatrixUpdate(MatrixBase):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(max_length=100)] | None = None
    fechaVigenciaDesde: date | None = None
    estado: EstadoMatriz | None = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


class MatrixRead(MatrixBase):
    model_config = ConfigDict(from_attributes=True)

    idMatriz: uuid.UUID
    idInstitucion: uuid.UUID | None = None
    version: str
    ambito: AmbitoMatriz
    estado: EstadoMatriz
    fechaCreacion: datetime

    @field_validator("ambito", mode="before")
    @classmethod
    def normalizarAmbito(cls, value):
        return normalizeUpper(value)

    @field_validator("estado", mode="before")
    @classmethod
    def normalizarEstado(cls, value):
        return normalizeStatus(value)


# --- Contratos del módulo de matrices de estimación (/matrices e /institutions/{id}/matrices) -------------------
#
# Estados de la base (CK_Matriz_estado): BORRADOR, ACTIVA, INACTIVA, ARCHIVADA. Solo un BORRADOR se edita; al
# activarse se vuelve inmutable (las mediciones conservan la referencia a esa versión). La versión la asigna el
# servidor (1, 2, 3…) y el código de cada regla también: el cliente no inventa identificadores.

from datetime import date as _date  # noqa: E402
from decimal import Decimal  # noqa: E402

from pydantic import model_validator  # noqa: E402

from app.schemas.measurement import CondicionComida  # noqa: E402


# Una regla también puede ser para «sexo no informado» (la base lo admite, CK_ReglaMatriz_sexo); un perfil, en cambio, solo
# es femenino o masculino, por eso no se reutiliza SexoModelo.
SexoRegla = Literal["MASCULINO", "FEMENINO", "NO_INFORMADO"]

Edad = Annotated[int, Field(ge=0, le=130)]
Minutos = Annotated[int, Field(ge=0)]
Glucosa = Annotated[Decimal, Field(max_digits=8, decimal_places=2, ge=0)]


class MatrixRuleInput(BaseModel):
    """Regla de una matriz en BORRADOR (columnas de dbo.ReglaMatriz). El código lo asigna el servidor."""

    model_config = ConfigDict(extra="forbid")

    sexoModelo: SexoRegla
    # Ambas vacías = «edad no especificada» (así existen las reglas generales de la matriz global; la base lo admite,
    # CK_ReglaMatriz_edad). Informar una sola no tiene sentido: se rechaza.
    edadDesde: Edad | None = None
    edadHasta: Edad | None = None
    condicionComida: CondicionComida
    minutosComidaMin: Minutos | None = None
    minutosComidaMax: Minutos | None = None
    glucosaMinReferencia: Glucosa
    glucosaMaxReferencia: Glucosa

    @field_validator("sexoModelo", "condicionComida", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)

    @field_validator("edadDesde", "edadHasta", "minutosComidaMin", "minutosComidaMax", mode="before")
    @classmethod
    def vacioEsNulo(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validarRangos(self):
        if (self.edadDesde is None) != (self.edadHasta is None):
            raise ValueError("Informá la edad mínima y la máxima, o dejá ambas vacías (edad no especificada).")
        if self.edadDesde is not None and self.edadHasta < self.edadDesde:
            raise ValueError("La edad mínima no puede superar la máxima.")
        if (self.minutosComidaMin is not None and self.minutosComidaMax is not None
                and self.minutosComidaMax < self.minutosComidaMin):
            raise ValueError("El tiempo mínimo desde la última comida no puede superar el máximo.")
        if self.glucosaMaxReferencia < self.glucosaMinReferencia:
            raise ValueError("El límite mínimo de glucosa no puede superar el máximo.")
        return self


class MatrixRulesCheckRequest(BaseModel):
    """Reglas a revisar antes de guardar una matriz (no se guarda nada)."""

    model_config = ConfigDict(extra="forbid")

    reglas: Annotated[list[MatrixRuleInput], Field(max_length=300)]


class MatrixCreateRequest(BaseModel):
    """Crea una matriz nueva (versión 1 de ese nombre) en BORRADOR, opcionalmente con sus reglas (todo o nada: si una regla
    es inválida, duplicada o solapada no se crea nada). Una institución elige su propio idInstitucion solo si es
    propietario o moderador de ella: el backend lo verifica."""

    model_config = ConfigDict(extra="forbid")

    ambito: AmbitoMatriz
    idInstitucion: uuid.UUID | None = None
    nombre: Annotated[str, Field(min_length=2, max_length=100)]
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    # Obligatorio: de dónde se tomaron los criterios (p. ej., el nombre de la guía o del servicio). Opcional: el enlace.
    referenciaBase: Annotated[str, Field(min_length=2, max_length=200)]
    urlReferencia: Annotated[str, Field(max_length=500)] | None = None
    fechaVigenciaDesde: _date | None = None
    fechaVigenciaHasta: _date | None = None
    reglas: Annotated[list[MatrixRuleInput], Field(max_length=300)] = []

    @field_validator("ambito", mode="before")
    @classmethod
    def normalizarAmbito(cls, value):
        return normalizeUpper(value)

    @field_validator("nombre", mode="before")
    @classmethod
    def recortarNombre(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)

    @field_validator("referenciaBase", mode="before")
    @classmethod
    def normalizarReferenciaBase(cls, value):
        return normalizeReferenciaBase(value)

    @field_validator("urlReferencia", mode="before")
    @classmethod
    def normalizarUrlReferencia(cls, value):
        return normalizeUrlReferencia(value)

    @field_validator("fechaVigenciaDesde", "fechaVigenciaHasta", mode="before")
    @classmethod
    def normalizarVigencia(cls, value):
        return normalizeDate(value) if value not in ("", None) else None

    @model_validator(mode="after")
    def validar(self):
        if (self.ambito == "GLOBAL") != (self.idInstitucion is None):
            raise ValueError("Una matriz global no lleva institución y una institucional la requiere.")
        if self.fechaVigenciaDesde and self.fechaVigenciaHasta and self.fechaVigenciaHasta < self.fechaVigenciaDesde:
            raise ValueError("La vigencia no puede terminar antes de empezar.")
        return self


class MatrixDraftUpdateRequest(BaseModel):
    """Datos editables de un BORRADOR. Solo se modifican los campos enviados."""

    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    descripcion: Annotated[str, Field(max_length=500)] | None = None
    referenciaBase: Annotated[str, Field(min_length=2, max_length=200)] | None = None
    urlReferencia: Annotated[str, Field(max_length=500)] | None = None
    fechaVigenciaDesde: _date | None = None
    fechaVigenciaHasta: _date | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def recortarNombre(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("descripcion", mode="before")
    @classmethod
    def normalizarDescripcion(cls, value):
        return normalizeSentence(value)

    @field_validator("referenciaBase", mode="before")
    @classmethod
    def referenciaBaseObligatoria(cls, value):
        # Enviada explícitamente en null, quedaría sin valor: la base la exige (NOT NULL). Si no se envía, no se toca.
        if value is None:
            raise ValueError("Indicá de dónde se tomaron los criterios: es obligatorio.")
        return normalizeReferenciaBase(value)

    @field_validator("urlReferencia", mode="before")
    @classmethod
    def normalizarUrlReferencia(cls, value):
        return normalizeUrlReferencia(value)

    @field_validator("fechaVigenciaDesde", "fechaVigenciaHasta", mode="before")
    @classmethod
    def normalizarVigencia(cls, value):
        return normalizeDate(value) if value not in ("", None) else None


class MatrixRuleUpdateRequest(BaseModel):
    """Modificación parcial de una regla de un BORRADOR (se vuelve a validar la regla completa)."""

    model_config = ConfigDict(extra="forbid")

    sexoModelo: SexoRegla | None = None
    edadDesde: Edad | None = None
    edadHasta: Edad | None = None
    condicionComida: CondicionComida | None = None
    minutosComidaMin: Minutos | None = None
    minutosComidaMax: Minutos | None = None
    glucosaMinReferencia: Glucosa | None = None
    glucosaMaxReferencia: Glucosa | None = None

    @field_validator("sexoModelo", "condicionComida", mode="before")
    @classmethod
    def normalizarCodigo(cls, value):
        return normalizeUpper(value)


class MatrixRuleView(BaseModel):
    idReglaMatriz: uuid.UUID
    codigoRegla: str
    sexoModelo: str
    # NULL = «edad no especificada» (así existen las reglas generales de la matriz global): no es un rango.
    edadDesde: int | None
    edadHasta: int | None
    condicionComida: str
    minutosComidaMin: int | None
    minutosComidaMax: int | None
    glucosaMinReferencia: Decimal
    glucosaMaxReferencia: Decimal


class MatrixItem(BaseModel):
    """Resumen de una versión de matriz (listados e historial)."""

    idMatriz: uuid.UUID
    nombre: str
    version: str
    ambito: AmbitoMatriz
    estado: EstadoMatriz
    descripcion: str | None = None
    referenciaBase: str
    urlReferencia: str | None = None
    fechaVigenciaDesde: _date
    fechaVigenciaHasta: _date | None
    fechaCreacion: datetime
    cantidadReglas: int
    # Cantidad de mediciones registradas con esta versión: si es mayor que 0, es parte del historial y no cambia.
    medicionesRegistradas: int


class MatrixSummary(BaseModel):
    """Matriz que se aplica (o se aplicaría): sin reglas."""

    idMatriz: uuid.UUID
    nombre: str
    version: str
    ambito: AmbitoMatriz
    estado: EstadoMatriz
    referenciaBase: str
    urlReferencia: str | None = None


class MatrixIssue(BaseModel):
    codigo: str
    mensaje: str
    codigoRegla: str | None = None


class MatrixPermissions(BaseModel):
    puedeEditar: bool
    puedeActivar: bool
    puedeDesactivar: bool
    puedeArchivar: bool
    puedeCrearVersion: bool
    puedeVerAuditoria: bool


class MatrixModifier(BaseModel):
    fecha: datetime
    por: str | None


class MatrixDetail(MatrixItem):
    idInstitucion: uuid.UUID | None
    nombreInstitucion: str | None
    reglas: list[MatrixRuleView]
    permisos: MatrixPermissions
    # Solo para quien puede consultar la auditoría (moderación de plataforma / propietario de la institución).
    creadaPor: MatrixModifier | None = None
    ultimaModificacion: MatrixModifier | None = None


class MatrixValidation(BaseModel):
    valida: bool
    problemas: list[MatrixIssue]
    # Observaciones que no impiden guardar ni activar (p. ej. edades sin regla): se informan para que se revisen.
    advertencias: list[MatrixIssue] = []


class MatrixAuditEntry(BaseModel):
    fechaHora: datetime
    accion: str
    resultado: str
    usuario: str | None


class InstitutionMatrixOverview(BaseModel):
    """Panel de matrices de una institución (propietario y moderador)."""

    institucionActiva: MatrixSummary | None
    globalActiva: MatrixSummary | None
    efectiva: MatrixSummary | None
    versiones: list[MatrixItem]
