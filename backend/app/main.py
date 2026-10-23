# Main - Aplicación FastAPI de GlucoLume
#
# Ejecutar desde backend/:
#   uvicorn app.main:app --reload --host localhost --port 8000
#
# Usar siempre el mismo host que GOOGLE_REDIRECT_URI (también para /docs): http://localhost:8000 sin Docker,
# http://glucolume.local con Docker. La cookie que guarda el state de OAuth es por host.

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.errors import authErrorHandler, validationErrorHandler
from app.api.requestContext import RequestContextMiddleware
from app.api.securityHeaders import SecurityHeadersMiddleware
from app.api.unhandledErrors import UnhandledErrorMiddleware
from app.api.v1.acquisition import router as acquisitionRouter
from app.api.v1.auth import router as authRouter
from app.api.v1.telemetry import router as telemetryRouter
from app.api.v1.contact import router as contactRouter
from app.api.v1.groups import router as groupsRouter
from app.api.v1.audit import institutionRouter as institutionAuditRouter
from app.api.v1.devices import institutionRouter as institutionDevicesRouter
from app.api.v1.devices import router as devicesRouter
from app.api.v1.audit import router as auditRouter
from app.api.v1.matrices import router as matricesRouter
from app.api.v1.platform import router as platformRouter
from app.api.v1.measurements import router as measurementsRouter
from app.api.v1.institutions import router as institutionsRouter
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.services import maintenance

# Vida máxima de la cookie que guarda state/nonce/PKCE del flujo OAuth.
OAUTH_STATE_MAX_AGE_SECONDS = 600

logger = logging.getLogger("glucolume")

# Sin configuración previa (p. ej. uvicorn sin --log-config), los logs de la aplicación (envíos de correo,
# fallos SMTP con su causa, errores de base) se muestran en la consola del backend.
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = getSettings()

# Swagger UI, ReDoc y el esquema OpenAPI describen toda la API (incluidas las rutas administrativas): solo se publican fuera de
# producción. El control de salud de los contenedores usa /healthz.
isProduction = settings.API_ENV == "production"
app = FastAPI(
    title="GlucoLume API",
    lifespan=maintenance.lifespan,
    docs_url=None if isProduction else "/docs",
    redoc_url=None if isProduction else "/redoc",
    openapi_url=None if isProduction else "/openapi.json",
)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Liveness: la API responde. No consulta la base, para que una caída de SQL Server no reinicie en bucle el contenedor."""
    return {"estado": "ok"}


if not settings.googleEnabled:
    logger.warning(
        "Acceso con Google deshabilitado. Variables faltantes: %s", ", ".join(settings.googleMissingVariables)
    )
else:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET.get_secret_value(),
        session_cookie="glucolume_oauth",
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=settings.API_ENV == "production",
    )

# La más interna (se agrega primero): atrapa los errores que ninguna ruta resolvió y responde un 500 genérico que todavía pasa por CORS y por
# las cabeceras de seguridad, dejando un evento en la auditoría (H-15).
app.add_middleware(UnhandledErrorMiddleware)

# El frontend (FRONTEND_URL) llama a la API desde otro origen. Solo se permite ese origen; la autenticación
# viaja en el encabezado Authorization (sin cookies), por eso allow_credentials queda en False.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontendOrigin],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # El frontend lee Retry-After para informar cuándo termina un bloqueo temporal.
    expose_headers=["Retry-After", "X-Request-ID"],
    allow_credentials=False,
    max_age=600,
)

# Última en agregarse = más externa: las cabeceras alcanzan también a las respuestas de error y de CORS.
app.add_middleware(SecurityHeadersMiddleware, hsts=isProduction)
# La más externa de todas: el contexto (correlación, IP, cliente) está disponible en cualquier capa y el identificador sale en toda respuesta.
app.add_middleware(RequestContextMiddleware)

for warning in settings.originWarnings():
    logger.warning("Configuración de origen inconsistente: %s", warning)

for warning in settings.securityWarnings():
    logger.warning("Configuración de seguridad: %s", warning)

app.add_exception_handler(AuthError, authErrorHandler)
app.add_exception_handler(RequestValidationError, validationErrorHandler)
app.include_router(authRouter, prefix="/api/v1")
app.include_router(contactRouter, prefix="/api/v1")
app.include_router(institutionsRouter, prefix="/api/v1")
app.include_router(groupsRouter, prefix="/api/v1")
app.include_router(measurementsRouter, prefix="/api/v1")
app.include_router(acquisitionRouter, prefix="/api/v1")
app.include_router(telemetryRouter, prefix="/api/v1")
app.include_router(platformRouter, prefix="/api/v1")
app.include_router(matricesRouter, prefix="/api/v1")
app.include_router(auditRouter, prefix="/api/v1")
app.include_router(devicesRouter, prefix="/api/v1")
app.include_router(institutionDevicesRouter, prefix="/api/v1")
app.include_router(institutionAuditRouter, prefix="/api/v1")
