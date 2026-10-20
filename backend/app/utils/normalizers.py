# Normalizers - Normalizadores comunes de datos de entrada
#
# Funciones puras y reutilizables desde cualquier schema (field_validator en modo "before").
# Sin acceso a base de datos, SQLAlchemy, FastAPI ni reglas de autorización.
#
# Reglas comunes:
# - None devuelve None (campos opcionales).
# - Un tipo incompatible lanza ValueError; nunca se convierte en silencio. Se usa ValueError
#   (y no TypeError) porque Pydantic solo lo transforma en error de validación (TRY004).
# - Se preservan acentos, ñ y demás caracteres Unicode.
# - Solo normalizan formato. La validación de valores permitidos (Literal/Enum, EmailStr,
#   longitudes) queda en el schema.
# - No usar sobre contraseñas, tokens, hashes, UUID ni identificadores técnicos.

import re
from datetime import date, datetime

# Formatos de referencia para representar valores.
DATE_FORMAT = "%Y-%m-%d"  # 2002-02-16
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # 2026-10-06 14:30:00

_HORIZONTAL_SPACES = re.compile(r"[^\S\n]+")
_ANY_SPACES = re.compile(r"\s+")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}.*")
# Separadores tras los cuales comienza una nueva palabra en un nombre propio.
_NAME_SEPARATORS = frozenset(" -'’")


def _requireText(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Se esperaba texto y se recibió {type(value).__name__}.")  # noqa: TRY004
    return value


def _collapseSpaces(text: str) -> str:
    """Quita espacios externos y reduce cualquier secuencia de espacios a uno solo."""
    return _ANY_SPACES.sub(" ", text).strip()


def _collapseSpacesKeepingLines(text: str) -> str:
    """Igual que _collapseSpaces pero conserva los saltos de línea del texto."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(_HORIZONTAL_SPACES.sub(" ", line).strip() for line in lines).strip()


def normalizeSentence(value: str | None) -> str | None:
    """Texto tipo oración: "hOLA. cOMO ESTAS." -> "Hola. Como estas."

    Pasa todo a minúscula y pone en mayúscula la primera letra del texto y la primera letra
    luego de un punto seguido de espacio. Preserva la puntuación y no agrega puntos.
    Un punto sin espacio posterior (decimales, abreviaturas, dominios) no inicia oración.
    """
    if value is None:
        return None
    text = _collapseSpacesKeepingLines(_requireText(value)).lower()
    result = []
    capitalizeNext = True
    afterPeriod = False
    for char in text:
        if afterPeriod:
            afterPeriod = False
            if char.isspace():
                capitalizeNext = True
        if capitalizeNext and char.isalpha():
            char = char.upper()
            capitalizeNext = False
        elif capitalizeNext and char.isdigit():
            capitalizeNext = False
        if char == ".":
            afterPeriod = True
        result.append(char)
    return "".join(result)


def normalizeProperName(value: str | None) -> str | None:
    """Nombre propio de persona: "vICTORIA valentina" -> "Victoria Valentina".

    Mayúscula inicial en cada palabra, incluidas las partes separadas por guion o apóstrofo:
    "maría-josé o'neill" -> "María-José O'Neill".
    """
    if value is None:
        return None
    text = _collapseSpaces(_requireText(value)).lower()
    result = []
    previous = " "
    for char in text:
        if previous in _NAME_SEPARATORS and char.isalpha():
            char = char.upper()
        result.append(char)
        previous = char
    return "".join(result)


def normalizeLower(value: str | None) -> str | None:
    """Todo en minúscula: "EJEMPLO   TEXTO" -> "ejemplo texto"."""
    if value is None:
        return None
    return _collapseSpaces(_requireText(value)).lower()


def normalizeUpper(value: str | None) -> str | None:
    """Todo en mayúscula: " habilitado " -> "HABILITADO"."""
    if value is None:
        return None
    return _requireText(value).strip().upper()


def normalizeStatus(value: str | None) -> str | None:
    """Estado en mayúsculas: " Activo " -> "ACTIVO".

    Solo normaliza el formato. El conjunto de estados válidos lo define el schema (Literal)
    a partir de las restricciones CHECK del SQL.
    """
    return normalizeUpper(value)


def normalizeEmail(value: str | None) -> str | None:
    """Correo electrónico: quita espacios externos y pasa el dominio a minúscula.

    No modifica la parte local (se conservan ".", "_", "-", "+" y mayúsculas).
    Rechaza espacios internos. La validación del formato corresponde a EmailStr.
    """
    if value is None:
        return None
    text = _requireText(value).strip()
    if any(char.isspace() for char in text):
        raise ValueError("El correo electrónico no puede contener espacios.")
    local, separator, domain = text.rpartition("@")
    if not separator:
        return text
    return f"{local}@{domain.lower()}"


def normalizeDateTime(value: datetime | str | None) -> datetime | None:
    """Fecha con hora como datetime.

    Acepta datetime o texto ISO 8601 con hora ("2026-10-06 14:30:00", "2026-10-06T14:30:00.123").
    Rechaza fechas sin hora para no inventar una hora. Conserva la zona horaria solo si el
    dato original la incluye; nunca la agrega.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not _ISO_DATETIME.fullmatch(text):
            raise ValueError("Formato de fecha y hora inválido; se esperaba YYYY-MM-DD HH:MM:SS.")
        try:
            return datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError("Fecha y hora inexistente o mal formada.") from error
    raise ValueError(f"Se esperaba fecha y hora y se recibió {type(value).__name__}.")


def normalizeDate(value: date | str | None) -> date | None:
    """Solo fecha como date: "2002-02-16" -> date(2002, 2, 16).

    Rechaza datetime para no descartar la hora en silencio.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError("Se esperaba una fecha sin hora.")  # noqa: TRY004
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not _ISO_DATE.fullmatch(text):
            raise ValueError("Formato de fecha inválido; se esperaba YYYY-MM-DD.")
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise ValueError("Fecha inexistente.") from error
    raise ValueError(f"Se esperaba una fecha y se recibió {type(value).__name__}.")
