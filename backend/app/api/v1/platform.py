# Platform - Rutas de la administración de la plataforma (/api/v1/platform)
#
# Solo traduce HTTP <-> servicios. La autorización NO es visual: cada ruta valida en SQL Server el rol global vigente
# (Usuario.tipoCuenta) y, salvo /me y la configuración de MFA, exige MFA habilitado. Un usuario normal recibe 403.
# La autenticación es la existente: /auth/login, /auth/google/*, /auth/mfa/*, /auth/refresh. Aquí solo hay lo propio de la
# administración: perfil/permisos, dashboard, moderadores, seguridad de cuentas y transferencia del control.

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api import sessionCookie
from app.api.deps import AuthContext, CurrentAuth, DbSession
from app.api.rateLimit import rateLimit
from app.schemas.auth import (
    LoginResponse,
    MessageResponse,
)
from app.schemas.platform import (
    CodeActivation,
    CapacityChange,
    InstitutionAction,
    InstitutionAuditPage,
    InstitutionDeletion,
    InstitutionDetail,
    InstitutionPage,
    ForgotPassword,
    ModeratorActionResult,
    ModeratorInvite,
    ModeratorRead,
    PasswordChange,
    PlatformDashboard,
    PlatformMe,
    ReauthenticatedAction,
    ResetPassword,
    SystemStatus,
    TransferOverview,
    TransferRead,
    TransferStart,
)
from app.services import platform as platformService
from app.services import platformDashboard, platformInstitutions
from app.utils.userAgent import ClientInfo, describeClient

router = APIRouter(prefix="/platform", tags=["platform"])


def _clientInfo(request: Request) -> ClientInfo:
    return describeClient(request.headers.get("user-agent"), request.client.host if request.client else None)


def platformAccess(auth: CurrentAuth, db: DbSession) -> AuthContext:
    """Cuenta con rol global vigente (403 para cualquier otra, que además queda registrado)."""
    platformService.requirePlatformAccount(db, auth.user)
    return auth


PlatformAccess = Annotated[AuthContext, Depends(platformAccess)]


def platformSecure(auth: PlatformAccess, db: DbSession) -> AuthContext:
    """Además exige MFA habilitado: sin él solo se puede configurar la seguridad de la cuenta."""
    platformService.requireMfaEnabled(db, auth.user)
    return auth


PlatformSecure = Annotated[AuthContext, Depends(platformSecure)]


# --- Perfil y panel ----------------------------------------------------------------------------------------------


@router.get("/me", response_model=PlatformMe, summary="Rol, permisos y estado de seguridad de la cuenta administrativa",
            description="403 `ACCESO_PLATAFORMA_DENEGADO` para cualquier cuenta que no sea administrador o moderador del sistema.")
def platformMe(auth: PlatformAccess, db: DbSession):
    return platformService.me(db, auth.user)


@router.get("/dashboard", response_model=PlatformDashboard, summary="Dashboard global",
            description="Administrador: indicadores de todo GlucoLume y actividad. Moderador: parte técnica. Solo agregados.")
def dashboard(auth: PlatformSecure, db: DbSession, dias: int = 30, desde: date | None = None, hasta: date | None = None):
    return platformDashboard.dashboard(db, auth.user, dias, desde, hasta)


@router.get("/institutions", response_model=InstitutionPage, summary="Instituciones (solo el administrador)",
            description="Una fila por institución con estado, fechas, personal y cuentas internas; filtros por nombre y estado. Solo conteos: "
            "nunca pacientes ni valores clínicos.")
def institutionList(auth: PlatformSecure, db: DbSession, busqueda: str | None = None, estado: str | None = None, pagina: int = 1, tamanio: int = 15):
    return platformDashboard.listInstitutions(db, auth.user, busqueda, estado, pagina, tamanio)


@router.get("/institutions/{idInstitucion}", response_model=InstitutionDetail, summary="Detalle administrativo de una institución",
            description="Estado, cupo, personal, dispositivos asignados con su estado técnico y volumen de mediciones; sin pacientes ni valores clínicos.")
def institutionDetail(idInstitucion: uuid.UUID, auth: PlatformSecure, db: DbSession, dias: int = 30):
    return platformDashboard.institutionDetail(db, auth.user, idInstitucion, dias)


@router.get("/institutions/{idInstitucion}/audit", response_model=InstitutionAuditPage, summary="Auditoría administrativa y de seguridad de una institución",
            description="Administrador y moderador del sistema (`AUDITAR_INSTITUCIONES`). Registro, pausa, reactivación, cierre, cupos, altas y bajas de cuentas, "
            "exportaciones, intentos de autenticación fallidos y eventos de seguridad; disponible aunque la institución esté pausada o cerrada. "
            "Sin datos clínicos, contraseñas, tokens ni códigos.")
def institutionAudit(idInstitucion: uuid.UUID, auth: PlatformSecure, db: DbSession, categoria: str | None = None, resultado: str | None = None,
                     desde: datetime | None = None, hasta: datetime | None = None, pagina: int = 1, tamanio: int = 20):
    return platformInstitutions.auditPage(db, auth.user, idInstitucion, categoria=categoria, resultado=resultado, desde=desde, hasta=hasta,
                                          pagina=pagina, tamanio=tamanio)


@router.post("/institutions/{idInstitucion}/pause", response_model=InstitutionDetail, summary="Pausar una institución",
             description="`GESTIONAR_ESTADO_INSTITUCIONES` (administrador y moderador del sistema). ACTIVA → INACTIVA con motivo obligatorio. Bloquea de inmediato, "
             "desde el backend, todo contexto institucional (también con sesiones y tokens ya emitidos). No elimina datos. Notifica a los propietarios.")
def pauseInstitution(idInstitucion: uuid.UUID, data: InstitutionAction, auth: PlatformSecure, db: DbSession):
    platformInstitutions.pause(db, auth.user, idInstitucion, data)
    return platformDashboard.institutionDetail(db, auth.user, idInstitucion)


@router.post("/institutions/{idInstitucion}/reactivate", response_model=InstitutionDetail, summary="Reactivar una institución pausada",
             description="`GESTIONAR_ESTADO_INSTITUCIONES`. INACTIVA → ACTIVA con motivo obligatorio. No levanta bloqueos individuales ni restablece sesiones.")
def reactivateInstitution(idInstitucion: uuid.UUID, data: InstitutionAction, auth: PlatformSecure, db: DbSession):
    platformInstitutions.reactivate(db, auth.user, idInstitucion, data)
    return platformDashboard.institutionDetail(db, auth.user, idInstitucion)


@router.post("/institutions/{idInstitucion}/delete", response_model=InstitutionDetail, summary="Eliminar una institución (cierre administrativo)",
             description="`ELIMINAR_INSTITUCIONES` (solo el administrador del sistema; MFA obligatoria y reautenticación con contraseña y código). Cierre LÓGICO de la "
             "institución (activa o pausada) con la marca de cierre administrativo: su último propietario no puede reabrirla desde la cuenta. Conserva los datos "
             "clínicos con su plazo de retención. Motivo y confirmación del nombre obligatorios. Requiere que la base instalada tenga las columnas de cierre administrativo del esquema v5; sin ellas responde 409.")
def deleteInstitution(idInstitucion: uuid.UUID, data: InstitutionDeletion, auth: PlatformSecure, db: DbSession):
    platformInstitutions.deleteInstitution(db, auth.user, idInstitucion, data)
    return platformDashboard.institutionDetail(db, auth.user, idInstitucion)


@router.put("/institutions/{idInstitucion}/capacity", response_model=InstitutionDetail, summary="Modificar el límite de cuentas internas",
            description="`GESTIONAR_CUPOS_INSTITUCIONES`. Máximo de cuentas internas (no pacientes ni grupos). Puede ser menor que las cuentas activas: se conservan "
            "y la institución queda excedida, sin admitir cuentas nuevas hasta regularizarse. Audita el límite anterior y el nuevo.")
def changeInstitutionCapacity(idInstitucion: uuid.UUID, data: CapacityChange, auth: PlatformSecure, db: DbSession):
    platformInstitutions.changeCapacity(db, auth.user, idInstitucion, data)
    return platformDashboard.institutionDetail(db, auth.user, idInstitucion)


@router.get("/system", response_model=SystemStatus, summary="Estado de los componentes de la plataforma")
def systemStatus(auth: PlatformSecure, db: DbSession):
    return platformDashboard.systemStatus(db, auth.user)


# --- Moderadores del sistema (solo administrador) ----------------------------------------------------------------


@router.get("/moderators", response_model=list[ModeratorRead], summary="Moderadores del sistema")
def listModerators(auth: PlatformSecure, db: DbSession):
    return platformService.listModerators(db, auth.user)


@router.post("/moderators", response_model=ModeratorActionResult, status_code=status.HTTP_201_CREATED,
             summary="Invitar a un moderador del sistema",
             description="Alta controlada: cuenta pendiente + enlace de activación de un solo uso. Exige reautenticación. "
             "Una cuenta individual o institucional existente no se convierte (409 `CUENTA_NO_CONVERTIBLE`).")
def inviteModerator(data: ModeratorInvite, auth: PlatformSecure, db: DbSession):
    moderator, sent, message = platformService.inviteModerator(db, auth.user, data)
    return ModeratorActionResult(moderador=moderator, correoEnviado=sent, mensaje=message)


@router.get("/moderators/{idUsuario}", response_model=ModeratorRead, summary="Datos administrativos de un moderador")
def getModerator(idUsuario: uuid.UUID, auth: PlatformSecure, db: DbSession):
    return platformService.getModerator(db, auth.user, idUsuario)


@router.post("/moderators/{idUsuario}/resend-invitation", response_model=ModeratorActionResult,
             summary="Reenviar la invitación (invalida el enlace anterior)")
def resendInvitation(idUsuario: uuid.UUID, data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    moderator, sent, message = platformService.resendInvitation(db, auth.user, idUsuario, data.reautenticacion)
    return ModeratorActionResult(moderador=moderator, correoEnviado=sent, mensaje=message)


@router.post("/moderators/{idUsuario}/revoke", response_model=ModeratorRead, summary="Revocar el acceso de un moderador",
             description="Bloquea la cuenta, cierra sus sesiones y cancela cualquier transferencia pendiente hacia esa persona.")
def revokeModerator(idUsuario: uuid.UUID, data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    return platformService.revokeModerator(db, auth.user, idUsuario, data.reautenticacion)


@router.post("/moderators/{idUsuario}/password-reset", response_model=ModeratorActionResult,
             summary="Iniciar el restablecimiento de contraseña de un moderador",
             description="Envía al correo del moderador un enlace de un solo uso con vencimiento. Nadie ve ni define la contraseña.")
def moderatorPasswordReset(idUsuario: uuid.UUID, data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    moderator, sent, message = platformService.startModeratorPasswordReset(db, auth.user, idUsuario, data.reautenticacion)
    return ModeratorActionResult(moderador=moderator, correoEnviado=sent, mensaje=message)


# --- Transferencia del control principal ------------------------------------------------------------------------


@router.get("/transfer", response_model=TransferOverview, summary="Transferencia de administración: estado y moderadores elegibles")
def transferOverview(auth: PlatformSecure, db: DbSession):
    return platformService.transferOverview(db, auth.user)


@router.post("/transfer", response_model=TransferRead, status_code=status.HTTP_201_CREATED,
             summary="Solicitar la transferencia del control (administrador)",
             description="Exige reautenticación reforzada. No cambia ningún rol hasta que el destinatario acepta.")
def startTransfer(data: TransferStart, auth: PlatformSecure, db: DbSession):
    return platformService.startTransfer(db, auth.user, data.idUsuarioDestino, data.reautenticacion)


@router.post("/transfer/cancel", response_model=TransferRead, summary="Cancelar la transferencia pendiente (administrador)")
def cancelTransfer(data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    return platformService.cancelTransfer(db, auth.user, data.reautenticacion)


@router.post("/transfer/accept", response_model=TransferRead, summary="Aceptar la administración (destinatario)",
             description="Cambia ambos roles en una sola transacción: el destinatario pasa a administrador del sistema y quien "
             "la ofreció a moderador.")
def acceptTransfer(data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    return platformService.respondTransfer(db, auth.user, True, data.reautenticacion)


@router.post("/transfer/reject", response_model=TransferRead, summary="Rechazar la administración (destinatario)")
def rejectTransfer(data: ReauthenticatedAction, auth: PlatformSecure, db: DbSession):
    return platformService.respondTransfer(db, auth.user, False, data.reautenticacion)


# --- Contraseña propia ----------------------------------------------------------------------------------------------


@router.post("/password/change", response_model=MessageResponse, summary="Cambiar la propia contraseña",
             description="Contraseña actual (si hay credencial local), nueva con confirmación y código MFA. Cierra las demás sesiones.")
def changePassword(data: PasswordChange, auth: PlatformAccess, db: DbSession):
    platformService.changeOwnPassword(
        db, auth.user, auth.session, data.passwordActual.get_secret_value() if data.passwordActual else None,
        data.passwordNueva.get_secret_value(), data.confirmacion.get_secret_value(), data.codigo, data.codigoRecuperacion)
    return MessageResponse(mensaje="Cambiaste tu contraseña. Cerramos tus otras sesiones.")


# --- Sin sesión: activación de la invitación y recuperación de contraseña -----------------------------------------


@router.post("/activation/with-code", dependencies=[rateLimit("activationCode"), Depends(sessionCookie.requireDeliveryMode)], response_model=LoginResponse,
             summary="Activar una cuenta administrativa con el código de un solo uso",
             description="Sin sesión. Exige el código de un solo uso que generó el servidor (primer administrador) o la invitación de un moderador; "
             "esa invitación ya identifica a la persona. El rol lo fija la invitación, nunca el cuerpo. Cualquier fallo responde lo mismo "
             "(`CODIGO_ACTIVACION_INVALIDO`). La sesión que se abre solo puede configurar MFA.")
def activateWithCode(data: CodeActivation, request: Request, response: Response, db: DbSession):
    return sessionCookie.deliver(request, response, platformService.activateWithCode(db, data, _clientInfo(request)))


@router.post("/password/forgot", dependencies=[rateLimit("passwordForgot")], status_code=status.HTTP_204_NO_CONTENT, summary="Recuperar la contraseña (acceso administrativo)",
             description="Sin sesión. Responde siempre igual: si la cuenta administrativa existe, recibe un enlace de un solo uso.")
def forgotPassword(data: ForgotPassword, db: DbSession):
    platformService.requestPasswordReset(db, data.correoElectronico)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/reset", dependencies=[rateLimit("passwordReset")], response_model=MessageResponse, summary="Establecer la nueva contraseña con el enlace recibido")
def resetPassword(data: ResetPassword, db: DbSession):
    platformService.resetPassword(db, data.token, data.password.get_secret_value())
    return MessageResponse(mensaje="Contraseña actualizada. Iniciá sesión con la nueva.")
