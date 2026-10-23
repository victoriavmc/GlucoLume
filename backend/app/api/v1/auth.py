# Auth - Rutas HTTP de autenticación (/api/v1/auth)
#
# Solo traduce HTTP <-> servicios; las reglas viven en backend/app/services/auth.py y mfa.py.

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentAuth, DbSession
from app.api import sessionCookie
from app.api.rateLimit import rateLimit
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.integrations.google import oauth as googleOAuth
from app.services import email as emailService
from app.schemas.auth import (
    AccountDeletionPreview,
    AccountActivationCompleteRequest,
    ConsentsResponse,
    ExperimentalConsentRequest,
    AccountActivationTokenRequest,
    ActivationInfo,
    AccountMfaRecoveryStartRequest,
    AccountMfaRecoveryStartResponse,
    AccountMfaRecoveryVerifyRequest,
    AccountDeletionConfirmRequest,
    AccountDeletionRequestResponse,
    AccountResponse,
    GoogleAuthorizationUrlResponse,
    GoogleExchangeRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MfaCodeRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaRecoveryStartRequest,
    MfaRecoveryStartResponse,
    MfaRecoveryVerifyRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    NewLoginNotificationUpdate,
    NewLoginUnsubscribeRequest,
    ProfileUpdateResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ChangePasswordRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    SetPasswordRequest,
    TokenPair,
)
from app.schemas.user import UserProfileUpdate, UserRead
from app.services import accountActivation as accountActivationService
from app.services import accountDeletion as accountDeletionService
from app.services import auth as authService
from app.services import consent as consentService
from app.services import mfa as mfaService
from app.services import mfaRecovery as mfaRecoveryService
from app.services import user as userService
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo, describeClient

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Tipo de registro elegido antes de ir a Google. Viaja en la cookie de sesión OAuth firmada (la misma que
# guarda state/nonce/PKCE) y solo decide el tipo de una cuenta NUEVA; una cuenta existente no cambia.
GOOGLE_REGISTRATION_KEY = "glucolume_registro"
GOOGLE_REGISTRATION_TYPES = {"usuario": "CONSUMIDOR_FINAL", "institucion": "USUARIO_INSTITUCIONAL"}
# «Recordarme» elegido en el login. Se guarda en la misma cookie y se devuelve en el fragmento del callback: el
# login puede iniciarse en otro origen (localhost) que la aplicación (glucolume.local), que no comparte almacenamiento.
GOOGLE_REMEMBER_KEY = "glucolume_recordar"
# Confirmación de lectura de la Política de Privacidad hecha antes de ir a Google (registro o activación de cuenta).
GOOGLE_POLICY_KEY = "glucolume_politica"


def _clientInfo(request: Request) -> ClientInfo:
    """Datos del cliente para el aviso de nuevo inicio de sesión (solo informativos)."""
    return describeClient(request.headers.get("user-agent"), request.client.host if request.client else None)


# --- Cuenta local ------------------------------------------------------------------------


@router.post("/register", dependencies=[rateLimit("register")], response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession):
    return authService.registerLocal(db, data)


@router.get("/verify-email", dependencies=[rateLimit("verification")], response_model=MessageResponse)
def verifyEmail(token: str, db: DbSession):
    authService.verifyEmail(db, token)
    return MessageResponse(mensaje="Correo verificado. Ya podés iniciar sesión.")


@router.post("/verify-email/resend", dependencies=[rateLimit("resend")], response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def resendVerification(data: ResendVerificationRequest, db: DbSession):
    authService.resendVerification(db, data.correoElectronico)
    return MessageResponse(mensaje="Si el correo corresponde a una cuenta pendiente de verificación, te enviamos un nuevo correo electrónico.")


@router.post(
    "/login", dependencies=[rateLimit("login"), Depends(sessionCookie.requireDeliveryMode)],
    response_model=LoginResponse,
    summary="Iniciar sesión con correo electrónico o nombre de usuario",
    description=(
        "`identificador` acepta el **correo electrónico** o el **nombre de usuario** de la cuenta, junto con "
        "la contraseña local. Si contiene `@` se busca por correo; si no, por nombre de usuario. "
        "Las cuentas creadas solo con Google no tienen contraseña local: ingresan con `/google/login`."
    ),
)
def login(data: LoginRequest, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, authService.loginLocal(
        db, data.identificador, data.password.get_secret_value(), _clientInfo(request)
    ))


# --- Google ------------------------------------------------------------------------------


def _requireGoogle() -> None:
    settings = getSettings()
    missing = settings.googleMissingVariables
    if missing:
        # Fuera de producción se indican las variables faltantes (solo nombres, nunca valores).
        detail = "El acceso con Google no está configurado."
        if settings.API_ENV != "production":
            detail += f" Variables faltantes: {', '.join(missing)}."
        raise AuthError("GOOGLE_NO_DISPONIBLE", detail)


def _requestOrigin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


_GOOGLE_ERROR_RESPONSES = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Google no configurado (en desarrollo indica las variables faltantes)."}
}


@router.get(
    "/google/login",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Iniciar sesión con Google (navegación del navegador)",
    description=(
        "Inicia el flujo OAuth 2.0 / OpenID Connect con Google y **redirige** al navegador a la pantalla "
        "de consentimiento de Google. No devuelve JSON.\n\n"
        "**Abrir con navegación del navegador** (enlace, `window.location` o la barra de direcciones), "
        "por ejemplo `http://glucolume.local/api/v1/auth/google/login`. **No usar `Execute` de Swagger**: "
        "Swagger lo invoca con `fetch()` y el navegador bloquea por CORS la redirección hacia "
        "`accounts.google.com`, mostrando `Failed to fetch` aunque el endpoint funcione.\n\n"
        "Guarda `state`, `nonce` y el verificador PKCE en una cookie de sesión temporal firmada, válida "
        "solo para el origen del callback. Si se abre desde otro origen (por ejemplo `127.0.0.1` en lugar "
        "de `glucolume.local`), primero redirige (307) al origen del callback para que la cookie sea válida.\n\n"
        "Para probar desde Swagger en desarrollo, usar `GET /api/v1/auth/google/authorization-url`."
    ),
    responses={
        status.HTTP_302_FOUND: {
            "description": "Redirección a la pantalla de consentimiento de Google.",
            "headers": {"Location": {"description": "URL de autorización de Google.", "schema": {"type": "string"}}},
        },
        status.HTTP_307_TEMPORARY_REDIRECT: {
            "description": "Redirección al origen del callback (p. ej. de 127.0.0.1 a localhost).",
            "headers": {"Location": {"description": "Mismo endpoint en el origen correcto.", "schema": {"type": "string"}}},
        },
        **_GOOGLE_ERROR_RESPONSES,
    },
)
async def googleLogin(
    request: Request,
    registro: Annotated[
        Literal["usuario", "institucion"] | None,
        Query(description="Tipo de cuenta si Google crea una cuenta nueva (registro). Omitir para iniciar sesión."),
    ] = None,
    recordar: Annotated[bool, Query(description="«Recordarme»: el frontend lo recibe de vuelta en el callback.")] = False,
    acepta: Annotated[bool, Query(description=(
        "El usuario confirmó haber leído la Política de Privacidad. Obligatorio para registrarse (`registro`) o activar "
        "una cuenta invitada; el backend lo registra al crear o activar la cuenta."))] = False,
):
    _requireGoogle()
    canonicalOrigin = getSettings().googleOrigin
    if _requestOrigin(request) != canonicalOrigin:
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(
            f"{canonicalOrigin}{request.url.path}{query}", status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    if registro is not None and not acepta:
        # Registro sin confirmar la política: ni siquiera se inicia OAuth (la validación no depende del frontend).
        return _frontendGoogleRedirect("error=POLITICA_NO_ACEPTADA")
    request.session.pop(GOOGLE_REGISTRATION_KEY, None)
    request.session.pop(GOOGLE_REMEMBER_KEY, None)
    request.session.pop(GOOGLE_POLICY_KEY, None)
    if registro is not None:
        request.session[GOOGLE_REGISTRATION_KEY] = registro
    if recordar:
        request.session[GOOGLE_REMEMBER_KEY] = True
    if acepta:
        request.session[GOOGLE_POLICY_KEY] = True
    return await googleOAuth.authorizeRedirect(request)


@router.get(
    "/google/authorization-url",
    response_model=GoogleAuthorizationUrlResponse,
    summary="[Desarrollo] Preparar el flujo Google y devolver la URL de autorización",
    description=(
        "Solo disponible con `API_ENV=development`. Prepara el mismo flujo que `/google/login` "
        "(state, nonce y PKCE en la cookie de sesión temporal) y devuelve la URL de Google en JSON, "
        "para poder ejecutarlo desde Swagger. Luego abrir `authorizationUrl` en **el mismo navegador**; "
        "Google volverá a `/api/v1/auth/google/callback`.\n\n"
        "Swagger debe estar abierto en el mismo origen que el callback (`http://glucolume.local/docs`)."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Fuera de desarrollo."},
        status.HTTP_400_BAD_REQUEST: {"description": "Swagger abierto desde un origen distinto al del callback."},
        **_GOOGLE_ERROR_RESPONSES,
    },
    include_in_schema=getSettings().API_ENV == "development",
)
async def googleAuthorizationUrl(request: Request):
    settings = getSettings()
    if settings.API_ENV != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    _requireGoogle()
    if _requestOrigin(request) != settings.googleOrigin:
        raise AuthError(
            "ORIGEN_INCONSISTENTE",
            f"Abrí Swagger desde {settings.googleOrigin}/docs: la cookie de state solo es válida en ese origen.",
        )
    return GoogleAuthorizationUrlResponse(authorizationUrl=await googleOAuth.prepareAuthorization(request))


def _frontendGoogleRedirect(fragment: str) -> RedirectResponse:
    # Fragmento (#): no se envía a ningún servidor ni queda en logs de acceso.
    return RedirectResponse(
        f"{emailService.frontendUrl('googleCallback')}#{fragment}", status_code=status.HTTP_302_FOUND
    )


@router.get(
    "/google/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="Callback de Google (lo invoca Google, no el cliente)",
    description=(
        "Destino de la redirección de Google tras el consentimiento. Valida `state`, intercambia el código, "
        "valida el `id_token` y aplica la identificación, vinculación o creación de la cuenta. Requiere la "
        "cookie de sesión temporal creada por `/google/login`; no ejecutar manualmente desde Swagger.\n\n"
        "No devuelve tokens: **redirige al frontend** (`FRONTEND_URL/auth/google/callback`) con "
        "`#code=<código de un solo uso>` (vence en 2 minutos) o `#error=<CODIGO>`. El frontend canjea el "
        "código con `POST /google/exchange`, que aplica MFA si está habilitado."
    ),
    responses={
        status.HTTP_302_FOUND: {
            "description": "Redirección al frontend con `#code=…` o `#error=…`.",
            "headers": {"Location": {"description": "URL del frontend.", "schema": {"type": "string"}}},
        },
        **_GOOGLE_ERROR_RESPONSES,
    },
)
async def googleCallback(request: Request, db: DbSession):
    _requireGoogle()
    tipoCuentaNueva = GOOGLE_REGISTRATION_TYPES.get(request.session.pop(GOOGLE_REGISTRATION_KEY, None))
    remember = bool(request.session.pop(GOOGLE_REMEMBER_KEY, False))
    aceptaPolitica = bool(request.session.pop(GOOGLE_POLICY_KEY, False))
    try:
        identity = await googleOAuth.fetchIdentity(request)
    except Exception as error:  # noqa: BLE001 - state inválido, código vencido o error de Google
        logger.warning("Callback de Google rechazado (%s).", type(error).__name__)
        return _frontendGoogleRedirect("error=TOKEN_INVALIDO")
    try:
        user = await run_in_threadpool(authService.identifyGoogleUser, db, identity, tipoCuentaNueva, aceptaPolitica)
        code = await run_in_threadpool(authService.createGoogleExchangeCode, db, user)
    except AuthError as error:
        # Los códigos de error son estables y no contienen datos personales.
        return _frontendGoogleRedirect(f"error={error.code}")
    except SQLAlchemyError:
        # La causa ya quedó en el log (commitAccountToken). La sesión se revierte antes de devolverla.
        db.rollback()
        logger.exception("Error de base de datos en el callback de Google.")
        return _frontendGoogleRedirect("error=ERROR_SERVIDOR")
    return _frontendGoogleRedirect(f"code={code}" + ("&recordar=1" if remember else ""))


@router.post(
    "/google/exchange", dependencies=[rateLimit("googleExchange"), Depends(sessionCookie.requireDeliveryMode)],
    response_model=LoginResponse,
    summary="Canjear el código del callback de Google por la sesión",
    description=(
        "Lo invoca el frontend con el `code` recibido en `/auth/google/callback#code=…`. Un solo uso; vence a "
        "los 2 minutos. Devuelve lo mismo que `/login`: la sesión (`AUTENTICADO`) o un desafío "
        "(`MFA_REQUERIDO`) a completar con `/mfa/verify`."
    ),
)
def googleExchange(data: GoogleExchangeRequest, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, authService.exchangeGoogleCode(db, data.code, _clientInfo(request)))


@router.post(
    "/session-transfer",
    response_model=GoogleExchangeRequest,
    summary="Continuar la sesión actual en otro origen (código de un solo uso)",
    description=(
        "Para el login hecho en `localhost` (único origen que Google admite) cuando la aplicación vive en otro host: "
        "con la sesión ya autenticada (MFA incluido) devuelve un `code` de un solo uso que vence en 2 minutos. El "
        "otro origen lo canjea en `POST /google/exchange`, que abre una sesión nueva sin repetir MFA."
    ),
)
def sessionTransfer(auth: CurrentAuth, db: DbSession):
    return GoogleExchangeRequest(code=authService.createSessionTransferCode(db, auth.user))


# --- MFA ---------------------------------------------------------------------------------


@router.post("/mfa/verify", dependencies=[rateLimit("mfa"), Depends(sessionCookie.requireDeliveryMode)], response_model=LoginResponse)
def mfaVerify(data: MfaVerifyRequest, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, authService.verifyMfaChallenge(
        db, data.challengeToken, data.codigo, data.codigoRecuperacion, _clientInfo(request)
    ))


@router.post(
    "/mfa/recovery/start", dependencies=[rateLimit("mfaRecovery")],
    response_model=MfaRecoveryStartResponse,
    summary="Perdí acceso a mi aplicación autenticadora (paso 1)",
    description=(
        "Desde el paso MFA del login, con el `challengeToken`. Si la cuenta tiene contraseña local exige "
        "`password` (la actual; mismo bloqueo que el login). Si la cuenta es solo Google, el desafío debe venir de "
        "un ingreso con Google. Envía un código de 6 dígitos al **correo registrado** (10 minutos, un solo uso) y "
        "devuelve el correo enmascarado y un `recoveryToken` para el paso 2. Máximo 1 código por minuto y 3 por hora. "
        "No desactiva nada todavía."
    ),
)
def mfaRecoveryStart(data: MfaRecoveryStartRequest, db: DbSession):
    result = mfaRecoveryService.startRecovery(
        db, data.challengeToken, data.password.get_secret_value() if data.password else None
    )
    return MfaRecoveryStartResponse(
        recoveryToken=result.recoveryToken,
        correoEnmascarado=result.correoEnmascarado,
        vigenciaMinutos=result.vigenciaMinutos,
    )


@router.post(
    "/mfa/recovery/verify", dependencies=[rateLimit("mfaRecovery"), Depends(sessionCookie.requireDeliveryMode)],
    response_model=LoginResponse,
    summary="Perdí acceso a mi aplicación autenticadora (paso 2)",
    description=(
        "Valida el código del correo (5 intentos, después bloqueo temporal). Si es correcto, en una sola "
        "transacción desactiva el MFA perdido (borra el secreto TOTP y los códigos de recuperación), consume el "
        "código y revoca todas las sesiones anteriores; después abre una sesión nueva (`AUTENTICADO`) y avisa por "
        "correo. Para volver a usar MFA hay que configurarlo de nuevo desde Seguridad."
    ),
)
def mfaRecoveryVerify(data: MfaRecoveryVerifyRequest, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, mfaRecoveryService.verifyRecovery(db, data.recoveryToken, data.codigo, _clientInfo(request)))


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfaSetup(auth: CurrentAuth, db: DbSession):
    secreto, otpauthUri = mfaService.startSetup(db, auth.user)
    return MfaSetupResponse(secreto=secreto, otpauthUri=otpauthUri)


@router.post("/mfa/enable", response_model=MfaEnableResponse)
def mfaEnable(data: MfaEnableRequest, auth: CurrentAuth, db: DbSession):
    return MfaEnableResponse(codigosRecuperacion=mfaService.enable(db, auth.user, data.codigo))


@router.post(
    "/me/mfa/recovery/start",
    response_model=AccountMfaRecoveryStartResponse,
    summary="Perdí la aplicación y los códigos de recuperación (Seguridad, paso 1)",
    description=(
        "Con sesión. Alternativa a `/mfa/disable` cuando no hay código TOTP ni código de recuperación. Exige la "
        "contraseña actual (mismo bloqueo que el login) y envía un código de 6 dígitos al **correo registrado** "
        "(10 minutos, un solo uso; máximo 1 por minuto y 3 por hora). Una cuenta solo Google recibe "
        "`REAUTENTICACION_REQUERIDA`: debe volver a ingresar con Google y recuperar desde el paso MFA del login."
    ),
)
def accountMfaRecoveryStart(data: AccountMfaRecoveryStartRequest, auth: CurrentAuth, db: DbSession):
    masked, minutes = mfaRecoveryService.startAccountRecovery(db, auth.user, data.password.get_secret_value())
    return AccountMfaRecoveryStartResponse(correoEnmascarado=masked, vigenciaMinutos=minutes)


@router.post(
    "/me/mfa/recovery/verify",
    response_model=AccountResponse,
    summary="Perdí la aplicación y los códigos de recuperación (Seguridad, paso 2)",
    description=(
        "Con sesión. Valida el código del correo (5 intentos, después bloqueo temporal) y, en una sola transacción, "
        "desvincula el MFA (borra el secreto TOTP y los códigos de recuperación), consume el código y revoca las "
        "demás sesiones (la actual se conserva). Envía un aviso de seguridad por correo."
    ),
)
def accountMfaRecoveryVerify(data: AccountMfaRecoveryVerifyRequest, auth: CurrentAuth, db: DbSession):
    mfaRecoveryService.completeAccountRecovery(db, auth.user, auth.session.idSesion, data.codigo)
    return authService.accountSummary(db, auth.user)


@router.post("/mfa/disable", response_model=MessageResponse)
def mfaDisable(data: MfaCodeRequest, auth: CurrentAuth, db: DbSession):
    mfaService.disable(db, auth.user, data.codigo, data.codigoRecuperacion)
    return MessageResponse(mensaje="MFA deshabilitado.")


# --- Sesión ------------------------------------------------------------------------------


@router.post(
    "/refresh", dependencies=[rateLimit("refresh")], response_model=TokenPair,
    summary="Renovar la sesión (rota el refresh token)",
    description=(
        "En el navegador el refresh token viaja en la cookie HttpOnly `glucolume_refresh` (solo con la cabecera `X-GlucoLume-CSRF: 1` y un "
        "`Origin` permitido); la respuesta no lo incluye en el cuerpo y reemplaza la cookie. Los clientes sin esa cabecera lo mandan en el "
        "cuerpo (`REFRESH_TOKEN_IN_BODY`). Reutilizar un token ya rotado revoca todas las sesiones de la cuenta."
    ),
)
def refresh(request: Request, response: Response, db: DbSession, data: RefreshRequest | None = None):
    cookieToken = sessionCookie.readRefreshToken(request)
    if cookieToken is not None:
        return sessionCookie.deliver(request, response, _TokenHolder(authService.refreshSession(db, cookieToken)), rotate=True).tokens
    if sessionCookie.cookieModeRequested(request) or data is None or not getSettings().REFRESH_TOKEN_IN_BODY:
        raise AuthError("TOKEN_INVALIDO", "Sesión inválida.", motivo="SESION_INVALIDA")
    return authService.refreshSession(db, data.refreshToken)


class _TokenHolder:
    """Adapta un TokenPair al formato que espera sessionCookie.deliver (algo con .tokens)."""

    def __init__(self, tokens: TokenPair):
        self.tokens = tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(auth: CurrentAuth, response: Response, db: DbSession):
    sessionCookie.clear(response)
    authService.logout(db, auth.session)
    try:  # la adquisición pendiente de esta cuenta se cancela y el dispositivo compartido queda libre
        from app.services import telemetry as telemetryService

        telemetryService.releaseOnLogout(db, auth.user)
    except Exception:  # noqa: BLE001 - cerrar sesión nunca debe fallar por el dispositivo
        db.rollback()


@router.get("/me", response_model=AccountResponse)
def me(auth: CurrentAuth, db: DbSession):
    return authService.accountSummary(db, auth.user)


@router.patch(
    "/me/profile",
    response_model=ProfileUpdateResponse,
    summary="Completar o actualizar los datos personales de la cuenta actual",
    description=(
        "Modifica únicamente al Usuario autenticado (nombre, apellido, usuario, fechaNacimiento, sexo). "
        "Una cuenta creada con Google debe indicar `usuario` la primera vez. Los campos omitidos no cambian, "
        "y un campo enviado con el mismo valor que ya tiene no cuenta como cambio. "
        "`actualizado` indica si hubo al menos un cambio real; si no lo hubo, no se modifica ni se audita nada. "
        "Incluye el mismo resumen que `GET /auth/me`, con `requiereCompletarPerfil` y `camposFaltantes`."
    ),
)
def updateMyProfile(data: UserProfileUpdate, auth: CurrentAuth, db: DbSession):
    changed = userService.updateProfile(db, auth.user, data)
    summary = authService.accountSummary(db, auth.user)
    return ProfileUpdateResponse(
        **summary.model_dump(),
        actualizado=changed,
        detail="Se registraron los cambios." if changed else "No se registraron cambios.",
    )


@router.post("/password", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def setPassword(data: SetPasswordRequest, auth: CurrentAuth, db: DbSession):
    authService.setLocalPassword(db, auth.user, data.password.get_secret_value())
    return MessageResponse(mensaje="Contraseña local agregada.")


@router.post(
    "/password/forgot", dependencies=[rateLimit("passwordForgot")],
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Olvidé mi contraseña (paso 1)",
    description=(
        "Sin sesión. Si el correo pertenece a una cuenta activa con contraseña local, envía un enlace de un solo uso "
        "(30 minutos). La respuesta es **siempre la misma**, exista o no la cuenta: no revela qué correos están "
        "registrados. Una cuenta solo Google ingresa con Google. Máximo 1 enlace por minuto por cuenta."
    ),
)
def forgotPassword(data: PasswordForgotRequest, db: DbSession):
    authService.requestPasswordReset(db, data.correoElectronico)
    return MessageResponse(mensaje="Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la contraseña.")


@router.post(
    "/password/reset", dependencies=[rateLimit("passwordReset")],
    response_model=MessageResponse,
    summary="Olvidé mi contraseña (paso 2)",
    description=(
        "Con el `token` del enlace recibido por correo y la contraseña nueva (misma política que el registro). Un solo "
        "uso; cierra **todas** las sesiones de la cuenta, reinicia el bloqueo por intentos fallidos y avisa por correo. "
        "El MFA, si está activo, se sigue exigiendo al iniciar sesión."
    ),
)
def resetPassword(data: PasswordResetRequest, db: DbSession):
    authService.resetPassword(db, data.token, data.password.get_secret_value())
    return MessageResponse(mensaje="Contraseña actualizada. Iniciá sesión con la nueva.")


@router.post(
    "/password/change",
    response_model=MessageResponse,
    summary="Cambiar mi contraseña",
    description=(
        "Con sesión. Exige la contraseña actual (mismo bloqueo que el login) y, si la cuenta tiene MFA, `codigo` o "
        "`codigoRecuperacion`. Cierra las demás sesiones y conserva la actual; envía un aviso por correo. Una cuenta "
        "solo Google debe crear primero su contraseña con `POST /auth/password`."
    ),
)
def changePassword(data: ChangePasswordRequest, auth: CurrentAuth, db: DbSession):
    authService.changeLocalPassword(
        db, auth.user, auth.session, data.passwordActual.get_secret_value(), data.passwordNueva.get_secret_value(),
        data.codigo, data.codigoRecuperacion,
    )
    return MessageResponse(mensaje="Cambiaste tu contraseña. Cerramos tus otras sesiones.")


# --- Aviso de nuevo inicio de sesión ------------------------------------------------------


@router.put(
    "/me/notifications/new-login",
    response_model=AccountResponse,
    summary="Activar o desactivar el aviso por correo de nuevo inicio de sesión",
    description=(
        "Preferencia del Usuario autenticado. Solo afecta al correo que se envía en cada inicio de sesión; "
        "las alertas de actividad sospechosa y de cambios de seguridad se envían siempre."
    ),
)
def updateNewLoginNotification(data: NewLoginNotificationUpdate, auth: CurrentAuth, db: DbSession):
    authService.setNewLoginNotification(db, auth.user, data.habilitada)
    return authService.accountSummary(db, auth.user)


@router.post(
    "/notifications/new-login/unsubscribe", dependencies=[rateLimit("unsubscribe")],
    response_model=MessageResponse,
    summary="Dejar de recibir el aviso de nuevo inicio de sesión (enlace del correo)",
    description=(
        "Lo invoca la pantalla del frontend a la que lleva el enlace del correo, con su `token` firmado "
        "(vigencia 30 días). No requiere sesión y solo desactiva ese aviso. Es POST para que abrir o "
        "previsualizar el correo no cambie la preferencia."
    ),
)
def unsubscribeNewLogin(data: NewLoginUnsubscribeRequest, db: DbSession):
    authService.unsubscribeNewLogin(db, data.token)
    return MessageResponse(mensaje="Ya no vas a recibir avisos por correo de cada inicio de sesión.")


# --- Eliminación de cuenta ----------------------------------------------------------------

_EXAMPLE_TOKEN = "token-del-enlace-recibido-por-correo"  # nosec B105 - ejemplo de documentación
_CONFIRM_EXAMPLES = {
    "sinMfa": {
        "summary": "Cuenta con contraseña, sin MFA",
        "value": {"token": _EXAMPLE_TOKEN, "password": "TuContraseñaActual"},
    },
    "conTotp": {
        "summary": "Cuenta con contraseña y MFA (código de la app)",
        "value": {"token": _EXAMPLE_TOKEN, "password": "TuContraseñaActual", "codigo": "123456"},
    },
    "conRecuperacion": {
        "summary": "Cuenta con contraseña y MFA (código de recuperación)",
        "value": {"token": _EXAMPLE_TOKEN, "password": "TuContraseñaActual", "codigoRecuperacion": "ABCD-EFGH"},
    },
    "soloGoogle": {
        "summary": "Cuenta solo Google, sin MFA (sin contraseña local)",
        "value": {"token": _EXAMPLE_TOKEN},
    },
    "soloGoogleConMfa": {
        "summary": "Cuenta solo Google con MFA",
        "value": {"token": _EXAMPLE_TOKEN, "codigo": "123456"},
    },
}


@router.get(
    "/account-deletion/preview",
    response_model=AccountDeletionPreview,
    summary="Consultar las consecuencias de eliminar la cuenta",
    description=(
        "Requiere sesión (Bearer). Solo consulta: informa si la cuenta puede eliminarse (una cuenta institucional con una o más "
        "instituciones activas no puede), qué datos se eliminan, qué se conserva y, si la cuenta está en período de gracia, cuándo vence."
    ),
)
def previewAccountDeletion(auth: CurrentAuth, db: DbSession):
    return accountDeletionService.describeDeletion(db, auth.user, nowForDb())


@router.post(
    "/account-deletion/request",
    response_model=AccountDeletionRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicitar la eliminación de la cuenta propia (paso 1)",
    description=(
        "Requiere sesión (Bearer). **Sin body**: no pide contraseña ni MFA, que se solicitan al confirmar.\n\n"
        "Verifica primero que ningún vínculo de Grupo o Institución bloquee la baja. Si puede continuar, genera "
        "un enlace de confirmación de un solo uso que vence a los 30 minutos y lo envía al correo de la cuenta; "
        "una nueva solicitud invalida el enlace anterior. **Todavía no elimina nada.**"
    ),
)
def requestAccountDeletion(auth: CurrentAuth, db: DbSession):
    result = accountDeletionService.requestDeletion(db, auth.user)
    return AccountDeletionRequestResponse(
        mensaje="Se envió un enlace de confirmación al correo electrónico.",
        fechaExpiracion=result.fechaExpiracion,
        vigenciaMinutos=result.vigenciaMinutos,
    )


@router.post(
    "/account-deletion/confirm", dependencies=[rateLimit("accountDeletion")],
    response_model=MessageResponse,
    summary="Confirmar la eliminación de la cuenta con el token del correo (paso 2)",
    description=(
        "Lo invoca la pantalla de confirmación del frontend (enlace del correo) con el `token` recibido. "
        "No requiere sesión: el token identifica la cuenta. Es POST para que abrir o previsualizar el correo "
        "nunca elimine la cuenta.\n\n"
        "Reautenticación en este paso:\n"
        "- `password`: obligatoria solo si la cuenta tiene contraseña local (no en una cuenta solo Google).\n"
        "- `codigo` **o** `codigoRecuperacion`: obligatorio solo si la cuenta tiene MFA habilitado; nunca ambos.\n\n"
        "Valida que el token exista, no esté vencido, no se haya usado ni haya sido reemplazado por una "
        "solicitud posterior, y vuelve a comprobar los vínculos de Grupo/Institución. Si todo es correcto "
        "consume el token, anonimiza los datos personales, revoca sesiones y credenciales y deja la cuenta en "
        "estado ELIMINADO. Irreversible. Un error de contraseña, código o bloqueo no consume el token."
    ),
)
def confirmAccountDeletion(
    data: Annotated[AccountDeletionConfirmRequest, Body(openapi_examples=_CONFIRM_EXAMPLES)], db: DbSession
):
    accountDeletionService.confirmDeletion(
        db,
        data.token,
        data.password.get_secret_value() if data.password else None,
        data.codigo,
        data.codigoRecuperacion,
    )
    return MessageResponse(mensaje="La cuenta fue eliminada.")


# --- Activación de cuentas creadas por una invitación institucional --------------------------


@router.post(
    "/account-activation/check", dependencies=[rateLimit("activation")],
    response_model=ActivationInfo,
    summary="Validar un enlace de activación",
    description="Sin sesión. Devuelve el nombre, el correo enmascarado y las invitaciones pendientes de la cuenta. "
    "401 `TOKEN_INVALIDO` si el enlace es inválido o ya se usó; 410 `TOKEN_VENCIDO` si venció.",
)
def checkAccountActivation(data: AccountActivationTokenRequest, db: DbSession):
    return accountActivationService.checkActivation(db, data.token)


@router.post(
    "/account-activation/complete", dependencies=[rateLimit("activation"), Depends(sessionCookie.requireDeliveryMode)],
    response_model=LoginResponse,
    summary="Activar la cuenta con usuario y contraseña propios",
    description="Sin sesión. Crea la credencial local con la política de contraseñas del registro, activa la "
    "cuenta, consume el enlace y abre la sesión. Las invitaciones institucionales siguen pendientes de aceptación.",
)
def completeAccountActivation(data: AccountActivationCompleteRequest, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, accountActivationService.completeActivation(
        db, data.token, data.usuario, data.password.get_secret_value(), _clientInfo(request),
        aceptaPolitica=data.aceptaPoliticaPrivacidad,
    ))


# --- Consentimientos ----------------------------------------------------------------------


@router.get(
    "/consents",
    response_model=ConsentsResponse,
    summary="Estado de mis consentimientos",
    description="Con sesión. Estado vigente de la confirmación de la Política de Privacidad y de la autorización para "
    "almacenar mediciones experimentales (finalidad académica; no es historia clínica).",
)
def getConsents(auth: CurrentAuth, db: DbSession):
    return consentService.status(db, auth.user)


@router.put(
    "/consents/datos-experimentales",
    response_model=ConsentsResponse,
    summary="Autorizar o revocar el almacenamiento de mis mediciones experimentales",
    description="Con sesión. `acepta: true` registra la autorización expresa (usuario, fecha y versión); `false` la "
    "revoca: desde ese momento no se inician ni reciben nuevas mediciones. No borra lo ya medido (para eso está la "
    "eliminación de la cuenta).",
)
def setExperimentalConsent(data: ExperimentalConsentRequest, auth: CurrentAuth, db: DbSession):
    return consentService.setExperimentalConsent(db, auth.user, data.acepta)
