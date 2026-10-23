# Config - Configuración de la aplicación leída desde variables de entorno / .env

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
# Archivo de configuración: el .env de la raíz. GLUCOLUME_ENV_FILE lo reemplaza (las pruebas usan backend/tests/test.env, GL-12).
ENV_FILE = Path(os.environ.get("GLUCOLUME_ENV_FILE") or ROOT_DIR / ".env")

# Algoritmos HMAC permitidos. No se mezclan con algoritmos asimétricos.
JWT_ALLOWED_ALGORITHMS = ("HS256", "HS384", "HS512")

# SESSION_SECRET firma la cookie que guarda state/nonce/PKCE durante el flujo OAuth.
GOOGLE_REQUIRED_VARIABLES = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI", "SESSION_SECRET")


class Settings(BaseSettings):
    # Variables vacías (p. ej. "DB_TRUST_SERVER_CERTIFICATE=") usan el valor por defecto.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True,
        # Un error de validación nunca incluye el valor recibido: muchos campos son secretos (GL-06/GL-20).
        hide_input_in_errors=True,
    )

    API_ENV: Literal["development", "test", "production"] = "development"
    API_BASE_URL: str = "http://localhost:8000"

    # Base de datos (SQL Server vía ODBC)
    DB_HOST: str
    DB_PORT: int = 1433
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    # Sin valor explícito: solo se confía en el certificado del servidor en development.
    DB_TRUST_SERVER_CERTIFICATE: bool | None = None
    # Validación del certificado de SQL Server sin confiar a ciegas (GL-07). DB_SERVER_CERTIFICATE: ruta (dentro del contenedor) del
    # certificado público del servidor, para fijarlo (ODBC 18.1+ «ServerCertificate»: sirve también con un certificado autofirmado propio).
    # DB_CERTIFICATE_HOSTNAME: nombre que figura en el certificado cuando DB_HOST es una IP (ODBC «HostNameInCertificate»).
    DB_SERVER_CERTIFICATE: str | None = None
    DB_CERTIFICATE_HOSTNAME: str | None = None
    # Cuenta de base propia de los procesos de conservación (servicio «lifecycle» y app/jobs), GL-03: es la única que puede borrar eventos
    # vencidos de Auditoria y anular IP/navegador de AuditoriaContexto; la de la API (DB_USER) queda con DENY UPDATE, DELETE sobre ambas
    # (database/reference/GlucoLume_permisos.sql). Las dos o ninguna; sin ellas, los jobs usan DB_USER como antes. El contenedor de la API
    # no las recibe (compose.yaml las vacía).
    DB_JOBS_USER: str | None = None
    DB_JOBS_PASSWORD: SecretStr | None = None

    # JWT de acceso
    JWT_SECRET: SecretStr
    # Secreto anterior durante una rotación (H-08): firma solo JWT_SECRET; los tokens firmados con el anterior se siguen aceptando hasta que
    # vencen. Quitarlo pasada la vigencia del token más largo (docs/SEGURIDAD.md, «Rotación de secretos»).
    JWT_PREVIOUS_SECRET: SecretStr | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Sesiones y autenticación
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_LOCKOUT_MINUTES: int = 15
    # Plazo para verificar una cuenta local desde Usuario.fechaCreacion (los reenvíos no lo extienden).
    # Vencido, la cuenta pendiente se elimina (app/services/unverifiedAccounts.py).
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24

    # MFA (TOTP). Clave Fernet para cifrar los secretos TOTP; sin ella MFA queda deshabilitado.
    MFA_ENCRYPTION_KEY: SecretStr | None = None
    # Claves Fernet ANTERIORES, separadas por coma, usadas solo para DESCIFRAR secretos guardados con ellas (cifrar usa siempre
    # MFA_ENCRYPTION_KEY). Permiten corregir una clave duplicada o rotarla sin dejar sin MFA a nadie (diagnóstico: python -m app.cli.mfaKeys).
    MFA_PREVIOUS_ENCRYPTION_KEYS: SecretStr | None = None
    MFA_CHALLENGE_EXPIRE_MINUTES: int = 5
    MFA_ISSUER: str = "GlucoLume"

    # Administración de la plataforma. Las cuentas administrativas exigen MFA habilitado para operar.
    PLATFORM_MFA_REQUIRED: bool = True
    PLATFORM_INVITATION_EXPIRE_HOURS: int = 72
    PLATFORM_RESET_EXPIRE_MINUTES: int = 30
    # Vigencia del enlace «Olvidé mi contraseña» de las cuentas comunes.
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # Google OAuth 2.0 / OpenID Connect. Sin estos valores el acceso con Google queda deshabilitado.
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    # Firma la cookie de sesión que guarda state/nonce/PKCE durante el flujo OAuth.
    SESSION_SECRET: SecretStr | None = None

    # Correo (SMTP con STARTTLS)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    # Remitente visible. Sin SMTP_FROM se usa SMTP_USERNAME.
    SMTP_FROM: str | None = None
    SMTP_FROM_NAME: str = "GlucoLume"

    # Casilla que recibe las consultas del formulario de contacto de la landing (POST /api/v1/contact).
    # Sin valor, el formulario responde que el contacto no está disponible.
    CONTACT_EMAIL: str | None = None

    # Puente serie (acquisition/bridge): token compartido con el servicio que lee el Arduino en el equipo anfitrión
    # (Windows) y envía las lecturas por POST /acquisition/bridge/ingest. Sin valor, la recepción queda deshabilitada.
    BRIDGE_TOKEN: SecretStr | None = None
    # Rotación sin corte (GL-11): el token anterior se sigue aceptando mientras se actualiza el puente; quitarlo apenas el puente use el nuevo.
    BRIDGE_PREVIOUS_TOKEN: SecretStr | None = None
    # Plazo máximo explícito de ese token anterior (H-16), p. ej. 2026-11-03T18:00 (hora de Argentina si no lleva zona): vencido, se ignora.
    # Sin plazo sigue valiendo hasta que se lo quite (se advierte al arrancar).
    BRIDGE_PREVIOUS_TOKEN_UNTIL: datetime | None = None
    # Transitorio (equipo único compartido): permite que las cuentas individuales midan y den órdenes al puente con un dispositivo asignado a
    # una institución. NO cambia su propiedad ni los permisos de los operadores. Por defecto apagado; quitarlo cuando cada contexto tenga su equipo.
    ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE: bool = False
    # Mantenimiento periódico de mediciones (vencimientos y liberación de sesiones abandonadas). 0 lo desactiva.
    MAINTENANCE_INTERVAL_SECONDS: int = 60
    # Ciclo de vida de las cuentas institucionales (servicio «lifecycle»; app/jobs/accountLifecycle.py): cada cuánto revisa los períodos
    # de gracia vencidos. 0 lo desactiva. PERSONNEL_RETENTION_MONTHS: meses desde la baja de una relación institucional tras los cuales se
    # suprimen sus datos personales históricos (nombre, legajo, matrícula). 0 (por defecto) lo desactiva: el plazo todavía no fue aprobado.
    ACCOUNT_LIFECYCLE_INTERVAL_SECONDS: int = 3600
    PERSONNEL_RETENTION_MONTHS: int = 0

    # Auditoría y detección de actividad sospechosa (docs/AUDITORIA_ADMINISTRATIVA.md). Los umbrales NO bloquean a nadie: solo deciden qué
    # patrones se señalan en la consola de la administración (services/securityDetection.py, services/securityMonitor.py).
    #   AUDIT_ALERT_WINDOW_MINUTES: ventana en la que se cuentan los hechos de un mismo patrón.
    #   AUDIT_ALERT_FAILURES_PER_ACCOUNT: fallos de acceso contra una misma cuenta (o un mismo identificador inexistente) dentro de la ventana.
    #   AUDIT_ALERT_ACCOUNTS_PER_ORIGIN: cuentas o identificadores distintos probados desde un mismo origen dentro de la ventana.
    #   AUDIT_ALERT_AUTH_REJECTIONS / AUDIT_ALERT_VALIDATION_REJECTIONS: respuestas 401/403 o 400/422 de un mismo origen dentro de la ventana.
    #   AUDIT_UNUSUAL_ORIGIN_MIN_HISTORY: inicios de sesión exitosos con IP registrada que debe tener una cuenta para poder decir que un origen es
    #   inusual para ella (con menos historia no se afirma nada).
    AUDIT_ALERT_WINDOW_MINUTES: int = 15
    AUDIT_ALERT_FAILURES_PER_ACCOUNT: int = 5
    AUDIT_ALERT_ACCOUNTS_PER_ORIGIN: int = 5
    AUDIT_ALERT_AUTH_REJECTIONS: int = 20
    AUDIT_ALERT_VALIDATION_REJECTIONS: int = 30
    # Alerta activa (GL-15): una ráfaga detectada también se avisa por correo al administrador de la plataforma, como máximo una vez por
    # patrón cada SECURITY_ALERT_EMAIL_MINUTES. 0 lo desactiva (la señal sigue en la consola).
    SECURITY_ALERT_EMAIL_MINUTES: int = 60
    AUDIT_UNUSUAL_ORIGIN_MIN_HISTORY: int = 5
    # Conservación de la auditoría (services/auditRetention.py, la corre el servicio «lifecycle»):
    #   AUDIT_CONTEXT_RETENTION_DAYS: días que se conservan la IP y el cliente de un evento; pasado el plazo se anulan (el evento sigue). 0 lo desactiva.
    #   AUDIT_ANONYMOUS_RETENTION_MONTHS: meses que se conservan los intentos de acceso sin cuenta identificable (cuenta inexistente, límites por origen). 0 lo desactiva.
    #   AUDIT_RETENTION_MONTHS: meses tras los cuales se eliminan TODOS los eventos. 0 (por defecto) los conserva sin límite: el plazo todavía no fue aprobado.
    AUDIT_CONTEXT_RETENTION_DAYS: int = 90
    AUDIT_ANONYMOUS_RETENTION_MONTHS: int = 12
    AUDIT_RETENTION_MONTHS: int = 0

    # URL pública del frontend: destino de los botones de los correos (ingresar, revisar seguridad...).
    FRONTEND_URL: str = "http://localhost:5173"

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validarAlgoritmo(cls, value: str) -> str:
        if value not in JWT_ALLOWED_ALGORITHMS:
            raise ValueError(f"JWT_ALGORITHM debe ser uno de {JWT_ALLOWED_ALGORITHMS}.")
        return value

    @field_validator("BRIDGE_TOKEN", "BRIDGE_PREVIOUS_TOKEN")
    @classmethod
    def validarTokenPuente(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("El token del puente debe tener al menos 32 caracteres.")
        return value

    @field_validator("JWT_SECRET", "JWT_PREVIOUS_SECRET")
    @classmethod
    def validarSecreto(cls, value: SecretStr | None, info) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError(f"{info.field_name} debe tener al menos 32 caracteres.")
        return value

    @property
    def trustServerCertificate(self) -> bool:
        if self.DB_TRUST_SERVER_CERTIFICATE is None:
            return self.API_ENV == "development"
        return self.DB_TRUST_SERVER_CERTIFICATE

    @property
    def googleMissingVariables(self) -> list[str]:
        """Nombres (nunca valores) de las variables requeridas para Google que faltan o están vacías."""
        return [name for name in GOOGLE_REQUIRED_VARIABLES if not getattr(self, name)]

    @property
    def googleEnabled(self) -> bool:
        return not self.googleMissingVariables

    @property
    def frontendOrigin(self) -> str:
        """Origen (esquema://host:puerto) del frontend: el único admitido por CORS."""
        url = urlsplit(self.FRONTEND_URL)
        return f"{url.scheme}://{url.netloc}"

    @property
    def googleOrigin(self) -> str | None:
        """Origen (esquema://host:puerto) del callback de Google: el único válido para la cookie de state."""
        if not self.GOOGLE_REDIRECT_URI:
            return None
        url = urlsplit(self.GOOGLE_REDIRECT_URI)
        return f"{url.scheme}://{url.netloc}"

    def originWarnings(self) -> list[str]:
        """Inconsistencias de origen que rompen la cookie de state de OAuth (localhost vs 127.0.0.1)."""
        warnings = []
        # API_BASE_URL y GOOGLE_REDIRECT_URI pueden tener orígenes distintos a propósito (p. ej. la web en
        # glucolume.local y el callback en localhost, porque Google rechaza .local): /google/login redirige al origen
        # del callback antes de crear la cookie de state, así que no es una inconsistencia.
        for name, value in (("API_BASE_URL", self.API_BASE_URL), ("GOOGLE_REDIRECT_URI", self.GOOGLE_REDIRECT_URI)):
            if value and urlsplit(value).hostname == "127.0.0.1":
                warnings.append(f"{name} usa 127.0.0.1; en desarrollo usar localhost de forma consistente.")
        return warnings

    def mfaKeys(self) -> list[str]:
        """Clave vigente primero y después las anteriores (sin repetir). Nunca se registran en logs."""
        keys = [self.MFA_ENCRYPTION_KEY.get_secret_value()] if self.MFA_ENCRYPTION_KEY else []
        if self.MFA_PREVIOUS_ENCRYPTION_KEYS:
            keys += [k.strip() for k in self.MFA_PREVIOUS_ENCRYPTION_KEYS.get_secret_value().split(",") if k.strip()]
        return list(dict.fromkeys(keys))

    def securityWarnings(self, envPath: Path | None = None) -> list[str]:
        """Problemas de configuración que no impiden arrancar fuera de producción. Solo nombres de variables, nunca valores."""
        envPath = envPath or ENV_FILE
        warnings = []
        duplicated = duplicatedEnvKeys(envPath)
        if duplicated:
            warnings.append(f"Variables definidas más de una vez en .env (vale la última): {', '.join(duplicated)}.")
        if "MFA_ENCRYPTION_KEY" in duplicated:
            warnings.append("MFA_ENCRYPTION_KEY está repetida: comprobá cuál descifra los factores existentes con «python -m app.cli.mfaKeys» "
                            "antes de quitar una (la otra puede pasar a MFA_PREVIOUS_ENCRYPTION_KEYS).")
        warnings += [f"{name}: clave Fernet inválida." for name, ok in _fernetChecks(self) if not ok]
        if "DATABASE_URL" in envFileKeys(envPath) or os.environ.get("DATABASE_URL"):
            warnings.append("DATABASE_URL está definida pero ninguna parte de GlucoLume la usa: duplica la contraseña de la base; quitala.")
        if self.BRIDGE_PREVIOUS_TOKEN is not None:
            warnings.append("BRIDGE_PREVIOUS_TOKEN está definido: el puente acepta dos tokens. Quitalo cuando el puente use BRIDGE_TOKEN.")
            if self.BRIDGE_PREVIOUS_TOKEN_UNTIL is None:
                warnings.append("BRIDGE_PREVIOUS_TOKEN sin BRIDGE_PREVIOUS_TOKEN_UNTIL: fijá un plazo máximo para la ventana de rotación (H-16).")
        if self.JWT_PREVIOUS_SECRET is not None:
            warnings.append("JWT_PREVIOUS_SECRET está definido: la API acepta tokens firmados con dos secretos. Quitalo cuando venzan los "
                            "tokens firmados con el anterior (docs/SEGURIDAD.md, «Rotación de secretos»).")
        if self.API_ENV == "production" and self.DB_JOBS_USER is None:
            warnings.append("Sin DB_JOBS_USER: la API y la conservación de la auditoría comparten cuenta de base, así que no se le puede negar "
                            "UPDATE/DELETE sobre Auditoria a la API (GL-03).")
        if self.API_ENV == "production":
            pending = [name for name in ("AUDIT_RETENTION_MONTHS", "PERSONNEL_RETENTION_MONTHS") if getattr(self, name) == 0]
            if pending:
                warnings.append(f"{', '.join(pending)} en 0: esos datos se conservan sin límite porque el plazo legal todavía no fue aprobado "
                                "(Ley 25.326; H-04). Fijar los plazos aprobados antes de operar con datos reales (docs/PRIVACIDAD_Y_RETENCION.md).")
        if self.trustServerCertificate:
            warnings.append("La conexión a SQL Server no verifica el certificado del servidor (TrustServerCertificate): solo para desarrollo.")
        if self.reusedSecrets():
            warnings.append(f"Secretos repetidos entre variables (en producción impide arrancar): {', '.join(self.reusedSecrets())}.")
        return warnings

    @model_validator(mode="after")
    def validarCuentaDeJobs(self) -> "Settings":
        if (self.DB_JOBS_USER is None) != (self.DB_JOBS_PASSWORD is None):
            raise ValueError("DB_JOBS_USER y DB_JOBS_PASSWORD se definen juntas (o ninguna).")
        if self.DB_JOBS_USER is not None and self.DB_JOBS_USER == self.DB_USER:
            raise ValueError("DB_JOBS_USER debe ser una cuenta distinta de DB_USER.")
        return self

    def reusedSecrets(self) -> list[str]:
        """Pares de variables que comparten el mismo secreto (solo nombres). Cada secreto protege una cosa distinta: si uno se filtra o se
        rota, no debe arrastrar a los demás (GL-20)."""
        names = ("JWT_SECRET", "JWT_PREVIOUS_SECRET", "SESSION_SECRET", "BRIDGE_TOKEN", "BRIDGE_PREVIOUS_TOKEN", "MFA_ENCRYPTION_KEY", "DB_PASSWORD",
                 "DB_JOBS_PASSWORD", "SMTP_PASSWORD", "GOOGLE_CLIENT_SECRET")
        values = {name: getattr(self, name).get_secret_value() for name in names if getattr(self, name) is not None}
        seen: dict[str, str] = {}
        pairs = []
        for name, value in values.items():
            if value in seen:
                pairs.append(f"{seen[value]}={name}")
            else:
                seen[value] = name
        return pairs

    @model_validator(mode="after")
    def exigirEntornoExplicito(self) -> "Settings":
        """En la imagen Docker (GLUCOLUME_RUNTIME=container) API_ENV debe definirse: sin él caería en «development» y un despliegue que
        olvide fijarlo abriría /docs y confiaría en el certificado de SQL Server sin verificarlo (H-07). Fuera de la imagen sigue
        valiendo el valor por defecto."""
        if os.environ.get("GLUCOLUME_RUNTIME") == "container" and "API_ENV" not in self.model_fields_set:
            raise ValueError("API_ENV debe definirse explícitamente (development|test|production): en producción lo fija "
                             "compose.prod.yaml; en desarrollo, API_ENV=development en el .env.")
        return self

    @model_validator(mode="after")
    def validarCertificadoEnProduccion(self) -> "Settings":
        """En producción la conexión a SQL Server verifica el certificado: TrustServerCertificate=true impide arrancar (GL-07)."""
        if self.API_ENV == "production" and self.DB_TRUST_SERVER_CERTIFICATE:
            raise ValueError("DB_TRUST_SERVER_CERTIFICATE=true no se admite en producción: configurar un certificado confiable o "
                             "fijarlo con DB_SERVER_CERTIFICATE.")
        return self

    @model_validator(mode="after")
    def validarSecretosRepetidos(self) -> "Settings":
        if self.API_ENV == "production" and self.reusedSecrets():
            raise ValueError(f"Secretos repetidos entre variables: {', '.join(self.reusedSecrets())}.")
        if self.API_ENV == "production" and self.SESSION_SECRET is not None and len(self.SESSION_SECRET.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET debe tener al menos 32 caracteres en producción.")
        return self

    @model_validator(mode="after")
    def validarClavesEnProduccion(self) -> "Settings":
        """En producción una clave MFA inválida impide arrancar (fuera de producción se informa como advertencia)."""
        if self.API_ENV == "production":
            invalid = [name for name, ok in _fernetChecks(self) if not ok]
            if invalid:
                raise ValueError(f"Clave Fernet inválida en {', '.join(invalid)}.")
        return self

    @property
    def bridgeTokens(self) -> list[SecretStr]:
        """Tokens del puente que se aceptan ahora: el vigente y, mientras no venza su plazo (H-16), el anterior."""
        tokens = [token for token in (self.BRIDGE_TOKEN,) if token is not None]
        if self.BRIDGE_PREVIOUS_TOKEN is not None:
            from app.utils.timeZone import nowArgentina, withArgentinaZone

            until = self.BRIDGE_PREVIOUS_TOKEN_UNTIL
            if until is None or nowArgentina() < withArgentinaZone(until):
                tokens.append(self.BRIDGE_PREVIOUS_TOKEN)
        return tokens

    @property
    def mfaEnabled(self) -> bool:
        return self.MFA_ENCRYPTION_KEY is not None

    @property
    def smtpEnabled(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USERNAME and self.SMTP_PASSWORD)


def _fernetChecks(settings: "Settings") -> list[tuple[str, bool]]:
    from cryptography.fernet import Fernet

    def valid(key: str) -> bool:
        try:
            Fernet(key.encode("ascii"))
            return True
        except (ValueError, UnicodeEncodeError):
            return False

    checks = []
    if settings.MFA_ENCRYPTION_KEY:
        checks.append(("MFA_ENCRYPTION_KEY", valid(settings.MFA_ENCRYPTION_KEY.get_secret_value())))
    if settings.MFA_PREVIOUS_ENCRYPTION_KEYS:
        previous = [k.strip() for k in settings.MFA_PREVIOUS_ENCRYPTION_KEYS.get_secret_value().split(",") if k.strip()]
        checks.append(("MFA_PREVIOUS_ENCRYPTION_KEYS", all(valid(k) for k in previous)))
    return checks


def envFileEntries(path: Path) -> list[tuple[int, str, str]]:
    """(línea, nombre, valor) de cada asignación de un archivo .env, en orden y con repeticiones. Admite `export`, espacios y comillas.
    Uso interno: quien llama nunca muestra el valor."""
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), start=1):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            entries.append((number, name.removeprefix("export ").strip(), value))
    return entries


def envFileKeys(path: Path) -> list[str]:
    """Nombres de las variables de un archivo .env, en orden y con repeticiones (nunca los valores)."""
    return [name for _, name, _ in envFileEntries(path)]


def duplicatedEnvKeys(path: Path) -> list[str]:
    seen, repeated = set(), []
    for name in envFileKeys(path):
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return repeated


@lru_cache
def getSettings() -> Settings:
    return Settings()
