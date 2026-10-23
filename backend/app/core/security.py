# Security - Primitivas criptográficas de autenticación
#
# Hash de contraseñas (Argon2id), JWT de acceso y de desafío MFA, tokens opacos
# (refresh, verificación de correo, códigos de recuperación) y TOTP.
# Sin acceso a base de datos.

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import getSettings
from app.utils.timeZone import nowArgentina

JWT_ISSUER = "glucolume"
JWT_AUDIENCE = "glucolume-api"
# Tipos de token (no son secretos; falsos positivos de bandit B105).
TOKEN_TYPE_ACCESS = "access"  # nosec B105
TOKEN_TYPE_MFA_CHALLENGE = "mfa_challenge"  # nosec B105
TOKEN_TYPE_MFA_RECOVERY = "mfa_recovery"  # nosec B105
# Vida del token que encadena los pasos de "perdí mi autenticador" (cubre el vencimiento del código).
MFA_RECOVERY_FLOW_MINUTES = 15
TOKEN_TYPE_UNSUBSCRIBE = "unsubscribe"  # nosec B105
# Vigencia del enlace "dejar de recibir este aviso" de un correo.
UNSUBSCRIBE_TOKEN_EXPIRE_DAYS = 30

TOTP_DIGITS = 6
TOTP_INTERVAL_SECONDS = 30
# Tolerancia de desfase de reloj: un intervalo antes y uno después.
TOTP_VALID_WINDOW = 1

# Parámetros de Argon2id fijados a propósito (H-12; OWASP Password Storage: m ≥ 64 MiB, t = 3, p = 4), no los de la librería: una actualización
# de pwdlib no debilita el hashing en silencio. Subirlos es seguro: verify_and_update rehace en el próximo acceso los hashes con parámetros menores.
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KIB = 64 * 1024
ARGON2_PARALLELISM = 4
_passwordHash = PasswordHash((Argon2Hasher(time_cost=ARGON2_TIME_COST, memory_cost=ARGON2_MEMORY_COST_KIB, parallelism=ARGON2_PARALLELISM),))
# Hash de referencia para igualar el tiempo de respuesta cuando el usuario no existe.
_DUMMY_PASSWORD_HASH = _passwordHash.hash(secrets.token_urlsafe(16))




# --- Contraseñas -------------------------------------------------------------------------


# Política para contraseñas nuevas (registro, alta o cambio). El login no la aplica para no bloquear
# cuentas con contraseñas anteriores a la política.
PASSWORD_MIN_LENGTH = 8
# Límite superior para evitar abusos del hash Argon2 con entradas enormes.
PASSWORD_MAX_LENGTH = 128


def passwordPolicyErrors(password: str) -> list[str]:
    """Requisitos que la contraseña no cumple (lista vacía si es válida). Nunca modifica la contraseña."""
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"al menos {PASSWORD_MIN_LENGTH} caracteres")
    if len(password) > PASSWORD_MAX_LENGTH:
        errors.append(f"como máximo {PASSWORD_MAX_LENGTH} caracteres")
    if not any(char.isupper() for char in password):
        errors.append("una letra mayúscula")
    if not any(char.islower() for char in password):
        errors.append("una letra minúscula")
    if not any(char.isdigit() for char in password):
        errors.append("un número")
    # Símbolo especial: cualquier carácter que no sea letra, número ni espacio (!@#$%&*._-...).
    if not any(not char.isalnum() and not char.isspace() for char in password):
        errors.append("un símbolo especial (por ejemplo ! @ # $ % & * . _ -)")
    return errors


# Mensaje de error, no una contraseña (falso positivo de bandit B105).
COMMON_PASSWORD_ERROR = (  # nosec B105
    "La contraseña es demasiado común o fácil de adivinar. Evitá palabras conocidas, secuencias de teclado "
    "y caracteres repetidos."
)
_COMMON_PASSWORDS_FILE = Path(__file__).with_name("commonPasswords.txt")
# Sustituciones típicas de letras por números o símbolos ("P@ssw0rd" -> "password").
_LEET = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s", "5": "s",
                       "7": "t", "+": "t", "8": "b", "9": "g", "|": "l"})
_SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm", "01234567890")
# Números, símbolos y espacios al principio o al final ("!!Password2026" -> "password").
_EDGE_FILLER = re.compile(r"^[\W\d_]+|[\W\d_]+$")


@lru_cache
def _commonPasswordWords() -> frozenset[str]:
    lines = _COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().casefold() for line in lines if line.strip() and not line.startswith("#"))


def isCommonPassword(password: str) -> bool:
    """True si la contraseña se reduce a una palabra común, una secuencia o una repetición."""
    lowered = password.casefold()
    core = _EDGE_FILLER.sub("", lowered)
    deleeted = core.translate(_LEET)
    if core in _commonPasswordWords() or deleeted in _commonPasswordWords():
        return True
    # Sin una parte "real" de al menos 3 letras (p. ej. "12345678Aa!").
    if len(core) < 3:
        return True
    # Palabra común con 2 letras extra como mucho: "Messi#2026x", "Admin1!ab".
    tokens = re.findall(r"[^\W\d_]+", core)
    letters = "".join(tokens)
    if any(token in _commonPasswordWords() and len(letters) - len(token) <= 2 for token in tokens):
        return True
    # Repeticiones: "Aaaaaaa1!", "Abababab1!", "Abcabcabc1!", o muy pocos caracteres distintos.
    if re.fullmatch(r"(.{1,3})\1+", letters) or len(set(re.sub(r"[\W_]+", "", lowered.translate(_LEET)))) <= 2:
        return True
    # Secuencias de abecedario o teclado, en cualquier sentido: "Abcd1234!", "Asdfgh#2026".
    return len(deleeted) >= 4 and any(deleeted in seq or deleeted in seq[::-1] for seq in _SEQUENCES)


def passwordContainsPersonalData(password: str, *identifiers: str | None) -> bool:
    """True si la contraseña contiene el nombre de usuario o la parte local del correo (3+ caracteres)."""
    lowered = password.casefold()
    for identifier in identifiers:
        if not identifier:
            continue
        value = identifier.split("@")[0].casefold()
        if len(value) >= 3 and value in lowered:
            return True
    return False


def hashPassword(password: str) -> str:
    return _passwordHash.hash(password)


def verifyPassword(password: str, passwordHash: str) -> tuple[bool, str | None]:
    """Devuelve (válida, nuevoHash). nuevoHash no es None si conviene rehashear."""
    return _passwordHash.verify_and_update(password, passwordHash)


def verifyDummyPassword(password: str) -> None:
    """Consume el mismo tiempo que una verificación real para no revelar si la cuenta existe."""
    _passwordHash.verify(password, _DUMMY_PASSWORD_HASH)


# --- Tokens opacos -----------------------------------------------------------------------


def generateOpaqueToken() -> str:
    return secrets.token_urlsafe(48)


def hashOpaqueToken(token: str) -> str:
    """SHA-256 de un token aleatorio de alta entropía (no apto para contraseñas)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- JWT ---------------------------------------------------------------------------------


def _encodeJwt(claims: dict, expiresIn: timedelta) -> str:
    settings = getSettings()
    # Instante con zona: PyJWT lo convierte a NumericDate (segundos epoch), independiente de la zona.
    now = nowArgentina()
    payload = {**claims, "iss": JWT_ISSUER, "aud": JWT_AUDIENCE, "iat": now, "exp": now + expiresIn}
    return jwt.encode(payload, settings.JWT_SECRET.get_secret_value(), algorithm=settings.JWT_ALGORITHM)


def _decodeJwt(token: str, expectedType: str) -> dict:
    """Decodifica con el algoritmo configurado (nunca el que declara el token). Lanza jwt.InvalidTokenError."""
    settings = getSettings()
    claims = jwt.decode(
        token,
        settings.JWT_SECRET.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "typ"]},
    )
    if claims["typ"] != expectedType:
        raise jwt.InvalidTokenError("Tipo de token inesperado.")
    return claims


def createAccessToken(idUsuario: uuid.UUID, idSesion: uuid.UUID) -> str:
    minutes = getSettings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    claims = {"sub": str(idUsuario), "sid": str(idSesion), "typ": TOKEN_TYPE_ACCESS}
    return _encodeJwt(claims, timedelta(minutes=minutes))


def decodeAccessToken(token: str) -> dict:
    claims = _decodeJwt(token, TOKEN_TYPE_ACCESS)
    if "sid" not in claims:
        raise jwt.InvalidTokenError("Token sin sesión.")
    return claims


def createMfaChallengeToken(idUsuario: uuid.UUID, primaryMethod: str) -> str:
    """Token de corta duración que solo habilita el paso de verificación MFA (no da acceso a la API)."""
    minutes = getSettings().MFA_CHALLENGE_EXPIRE_MINUTES
    claims = {"sub": str(idUsuario), "typ": TOKEN_TYPE_MFA_CHALLENGE, "amr": [primaryMethod]}
    return _encodeJwt(claims, timedelta(minutes=minutes))


def decodeMfaChallengeToken(token: str) -> dict:
    return _decodeJwt(token, TOKEN_TYPE_MFA_CHALLENGE)


def createMfaRecoveryToken(idUsuario: uuid.UUID, primaryMethod: str) -> str:
    """Encadena la recuperación de MFA: se emite tras validar la identidad y solo sirve para verificar el
    código enviado por correo. No da acceso a la API."""
    claims = {"sub": str(idUsuario), "typ": TOKEN_TYPE_MFA_RECOVERY, "amr": [primaryMethod]}
    return _encodeJwt(claims, timedelta(minutes=MFA_RECOVERY_FLOW_MINUTES))


def decodeMfaRecoveryToken(token: str) -> dict:
    return _decodeJwt(token, TOKEN_TYPE_MFA_RECOVERY)


# --- Códigos numéricos enviados por correo --------------------------------------------------


def generateNumericCode(digits: int = 6) -> str:
    """Código numérico aleatorio (CSPRNG) para enviar por correo."""
    return f"{secrets.randbelow(10**digits):0{digits}d}"


def derivedKey(purpose: str) -> bytes:
    """Clave de 32 bytes propia de `purpose`, derivada de JWT_SECRET con HKDF-SHA256 (GL-17): firmar JWT y calcular un HMAC no usan
    la misma clave, y conocer una clave derivada no da la de firma ni las de otros propósitos."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    secret = getSettings().JWT_SECRET.get_secret_value().encode("utf-8")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"glucolume:{purpose}".encode("utf-8")).derive(secret)


def hashShortCode(purpose: str, idUsuario: uuid.UUID, idToken: uuid.UUID, code: str, *, legacy: bool = False) -> str:
    """HMAC-SHA256 de un código corto, con una clave derivada del servidor y ligado al usuario y al token.

    Un código de 6 dígitos tiene poca entropía: un SHA-256 simple sería reversible probando el millón de
    combinaciones si se filtrara la base. Con la clave del servidor no lo es, y el idToken hace único el hash
    (UQ_TokenCuenta_tokenHash) aunque dos usuarios reciban el mismo código. `legacy`: el cálculo anterior (JWT_SECRET directo), solo
    para verificar códigos emitidos antes del cambio; vencen en minutos, así que se puede quitar en la próxima versión.
    """
    key = getSettings().JWT_SECRET.get_secret_value().encode("utf-8") if legacy else derivedKey("codigo-corto")
    message = f"{purpose}:{idUsuario}:{idToken}:{code}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def encodeScopedToken(claims: dict, expiresIn: timedelta) -> str:
    """Token firmado de propósito único (`typ` obligatorio en `claims`) para enlaces de correo que no dan acceso a la API."""
    if not claims.get("typ") or not claims.get("sub"):
        raise ValueError("Un token de propósito único necesita typ y sub.")
    return _encodeJwt(claims, expiresIn)


def decodeScopedToken(token: str, expectedType: str) -> dict:
    return _decodeJwt(token, expectedType)


def createUnsubscribeToken(idUsuario: uuid.UUID, evento: str) -> str:
    """Enlace para desactivar un aviso desde el correo. Solo permite apagar ese aviso, nunca acceder a la API."""
    claims = {"sub": str(idUsuario), "typ": TOKEN_TYPE_UNSUBSCRIBE, "evt": evento}
    return _encodeJwt(claims, timedelta(days=UNSUBSCRIBE_TOKEN_EXPIRE_DAYS))


def decodeUnsubscribeToken(token: str, evento: str) -> dict:
    claims = _decodeJwt(token, TOKEN_TYPE_UNSUBSCRIBE)
    if claims.get("evt") != evento:
        raise jwt.InvalidTokenError("Aviso inesperado.")
    return claims


# --- TOTP --------------------------------------------------------------------------------


def _fernet() -> MultiFernet:
    """Cifra con MFA_ENCRYPTION_KEY y descifra con ella o con las anteriores (MFA_PREVIOUS_ENCRYPTION_KEYS): una clave repetida o
    rotada no deja sin MFA a quien ya lo tenía (GL-06)."""
    keys = getSettings().mfaKeys()
    if not keys:
        raise RuntimeError("MFA_ENCRYPTION_KEY no está configurada.")
    return MultiFernet([Fernet(key.encode("ascii")) for key in keys])


def reencryptTotpSecret(encrypted: str) -> str:
    """Vuelve a cifrar con la clave vigente un secreto guardado con una anterior (MultiFernet.rotate)."""
    try:
        return _fernet().rotate(encrypted.encode("ascii")).decode("ascii")
    except InvalidToken as error:
        raise RuntimeError("No se pudo descifrar el secreto TOTP.") from error


def generateTotpSecret() -> str:
    return pyotp.random_base32()


def encryptTotpSecret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decryptTotpSecret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode("ascii")).decode("ascii")
    except InvalidToken as error:
        raise RuntimeError("No se pudo descifrar el secreto TOTP.") from error


def totpProvisioningUri(secret: str, accountName: str) -> str:
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL_SECONDS)
    return totp.provisioning_uri(name=accountName, issuer_name=getSettings().MFA_ISSUER)


def matchTotpStep(secret: str, code: str, at: datetime | None = None) -> int | None:
    """Devuelve el intervalo (time step) en el que el código es válido, o None.

    El intervalo permite rechazar la reutilización de un código ya aceptado.
    """
    code = code.strip()
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL_SECONDS)
    # Instante con zona: pyotp calcula el intervalo sobre epoch, independiente de la zona.
    moment = at or nowArgentina()
    currentStep = totp.timecode(moment)
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        step = currentStep + offset
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


# --- Códigos de recuperación MFA --------------------------------------------------------

RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generateRecoveryCode() -> str:
    """Código de 16 caracteres (~80 bits) en formato XXXX-XXXX-XXXX-XXXX."""
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def hashRecoveryCode(code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").upper()
    return hashOpaqueToken(normalized)
