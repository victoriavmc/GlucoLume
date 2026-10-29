# Institutions - Rutas del módulo Institución (/api/v1/institutions)
#
# Solo traduce HTTP <-> servicios; las reglas y la autorización por rol viven en
# backend/app/services/institution.py. La identidad sale siempre de la sesión autenticada.

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import CurrentAuth, DbSession
from app.api.rateLimit import normalizeIp, rateLimit
from app.schemas.institutionActivity import ActivityPage
from app.schemas.personnel import PersonnelExportRequest, PersonnelPage, PersonnelProfile, SentInvitationsPage
from app.schemas.institution import (
    InstitutionCreateRequest,
    InstitutionDeletionRequest,
    InstitutionDetail,
    InstitutionOperationResult,
    InstitutionReopenRequest,
    InstitutionUpdateRequest,
    InvitationRead,
    QuotaRead,
    LegalIdCheckRequest,
    LegalIdStatus,
    MemberCandidate,
    MemberEmailRequest,
    MemberAdminUpdateRequest,
    MemberInviteRequest,
    MemberRead,
    MyInstitutionRead,
    OperatorInviteRequest,
    SupportRequest,
    SupportRequestResult,
)
from app.schemas.measurementProfile import (
    ResultEmailConfirmRead,
    ResultEmailConfirmRequest,
    AssignableOperator,
    PatientAssignRequest,
    PatientCreateRequest,
    PatientExportRequest,
    PatientPage,
    PatientRead,
    PatientResultEmailRequest,
    PatientUpdateRequest,
)
from app.schemas.dashboard import InstitutionDashboard, OperatorDashboard, PatientDashboard
from app.schemas.measurement import EvolutionRead
from app.schemas.patientAnalytics import PatientAnalytics
from app.schemas.measurement import InstitutionIndicators, MeasurementPage
from app.schemas.group import SharedStatisticsRead
from app.schemas.offboarding import OffboardPlan, OffboardRequest, OffboardResult
from app.schemas.reassignment import (
    ReassignmentAssignRequest,
    ReassignmentAssignResult,
    ReassignmentOverview,
    ReassignmentPage,
    ReassignmentRegularizeRequest,
    ReassignmentRegularizeResult,
)
from app.schemas.profileTransfer import TransferDetail, TransferItem, TransferPage, TransferRequest
from app.schemas.matrix import InstitutionMatrixOverview, MatrixSummary
from app.services import institution as institutionService
from app.services import institutionSupport
from app.services import resultEmailConfirmation
from app.services import institutionActivity as activityService
from app.services import operatorOffboarding as offboardingService
from app.services import personnel as personnelService
from app.services import matrix as matrixService
from app.services import profileTransfers as transferService
from app.services import institutionPatients as patientService
from app.services import patientAnalytics as analyticsService
from app.services import patientResultEmail as resultEmailService
from app.services import institutionReassignments as reassignmentService
from app.services import dashboard as dashboardService
from app.services import measurement as measurementService

router = APIRouter(prefix="/institutions", tags=["institutions"])

MODERADOR = institutionService.ROL_MODERADOR
OPERADOR = institutionService.ROL_OPERADOR


# --- Instituciones de la cuenta e invitaciones recibidas -----------------------------------


@router.post(
    "/{idInstitucion}/support-request",
    response_model=SupportRequestResult,
    summary="Escribir al soporte de GlucoLume desde una institución pausada",
    description="Solo el PROPIETARIO y solo mientras la institución está pausada (`INACTIVA`): es lo único que sigue abierto durante la pausa. Envía la consulta por "
    "el servicio de contacto (nombre y correo salen de la cuenta; Reply-To el correo del propietario) con los datos de la institución, y confirma al propietario. "
    "409 `INSTITUCION_NO_PAUSADA` si no está pausada; 404 si no es su propietario; 429 tras 3 consultas por hora; 503 si el correo no pudo enviarse.",
)
def requestSupport(idInstitucion: uuid.UUID, data: SupportRequest, auth: CurrentAuth, db: DbSession, request: Request):
    clientIp = normalizeIp(request.client.host if request.client else None)
    confirmed = institutionSupport.requestSupport(db, auth.user, idInstitucion, data, clientIp)
    return SupportRequestResult(mensaje="Enviamos tu consulta al soporte de GlucoLume.", confirmacionEnviada=confirmed)


@router.get(
    "/mine",
    response_model=list[MyInstitutionRead],
    summary="Instituciones de la cuenta autenticada",
    description="Instituciones activas con vínculo activo, con el rol y los permisos de la cuenta en cada una. "
    "Una cuenta institucional puede no tener ninguna.",
)
def myInstitutions(auth: CurrentAuth, db: DbSession, incluirPausadas: bool = False):
    return institutionService.listMine(db, auth.user, incluirPausadas)


@router.get(
    "/invitations",
    response_model=list[InvitationRead],
    summary="Invitaciones institucionales pendientes recibidas",
)
def myInvitations(auth: CurrentAuth, db: DbSession):
    return institutionService.listInvitations(db, auth.user)


@router.post(
    "/invitations/{idInstitucionUsuario}/accept",
    response_model=MyInstitutionRead,
    summary="Aceptar una invitación",
    description="Solo la cuenta invitada. 404 si no existe o ya fue respondida; 410 si venció, la institución se "
    "eliminó o quien invitó ya no tiene ese permiso.",
)
def acceptInvitation(idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.respondInvitation(db, auth.user, idInstitucionUsuario, accept=True)


@router.post(
    "/invitations/{idInstitucionUsuario}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rechazar una invitación",
)
def rejectInvitation(idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    institutionService.respondInvitation(db, auth.user, idInstitucionUsuario, accept=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Institución ----------------------------------------------------------------------------


def _result(db, user, idInstitucion, operacion: str) -> InstitutionOperationResult:
    return InstitutionOperationResult(
        **institutionService.getDetail(db, user, idInstitucion).model_dump(), operacion=operacion
    )


@router.post(
    "/legal-id/status",
    response_model=LegalIdStatus,
    summary="Estado de un CUIT antes de crear",
    description="Cuenta `USUARIO_INSTITUCIONAL`. DISPONIBLE (se puede crear), ACTIVA (ya registrada) o CERRADA, con "
    "`puedeReabrir` si la cuenta es el último propietario (solo entonces devuelve sus datos vigentes). Limitado por "
    "cuenta (429).",
)
def legalIdStatus(data: LegalIdCheckRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.checkLegalId(db, auth.user, data.tipoIdentificadorLegal, data.identificadorLegal)


@router.post(
    "",
    response_model=InstitutionOperationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una institución",
    description=(
        "Solo una cuenta `USUARIO_INSTITUCIONAL` (403 si no). Crea la institución (ACTIVA, `cantidadReaperturas` 0) y "
        "el vínculo PROPIETARIO en una transacción; `operacion` = CREADA. El nombre puede repetirse; el CUIT (11 "
        "dígitos con dígito verificador, normalizado) es único: 409 `INSTITUCION_REGISTRADA` si está activa, 409 "
        "`INSTITUCION_CERRADA` si existe cerrada (corresponde reabrirla con POST /institutions/reopen)."
    ),
)
def createInstitution(data: InstitutionCreateRequest, auth: CurrentAuth, db: DbSession):
    created = institutionService.createInstitution(db, auth.user, data)
    return _result(db, auth.user, created.idInstitucion, "CREADA")


@router.post(
    "/reopen",
    response_model=InstitutionOperationResult,
    summary="Reabrir una institución cerrada",
    description=(
        "Solo el último propietario de la institución CERRADA del CUIT (403 `REPRESENTACION_NO_VERIFICADA` si no), "
        "con la reautenticación de la cuenta (contraseña y/o MFA). Conserva el registro (mismo idInstitucion), "
        "actualiza los datos, pasa a ACTIVA, incrementa `cantidadReaperturas` y crea su vínculo PROPIETARIO; "
        "`operacion` = REABIERTA. No restaura integrantes, invitaciones ni acceso a pacientes anteriores."
    ),
)
def reopenInstitution(data: InstitutionReopenRequest, auth: CurrentAuth, db: DbSession):
    reopened = institutionService.reopenInstitution(db, auth.user, data)
    return _result(db, auth.user, reopened.idInstitucion, "REABIERTA")


@router.post(
    "/{idInstitucion}/creation-notice",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reenviar la confirmación de registro",
    description="Solo PROPIETARIO. Solo si el correo de confirmación no se pudo enviar (409 "
    "`NOTIFICACION_YA_ENVIADA` si ya se envió; 503 `NOTIFICACION_NO_ENVIADA` si vuelve a fallar).",
)
def resendCreationNotice(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    institutionService.resendCreationNotice(db, auth.user, idInstitucion)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{idInstitucion}",
    response_model=InstitutionDetail,
    summary="Panel de una institución propia",
    description="Cualquier integrante activo. Incluye el rol y los permisos de la cuenta y la cantidad de "
    "moderadores y operadores. 404 si la cuenta no pertenece o la institución fue eliminada.",
)
def getInstitution(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.getDetail(db, auth.user, idInstitucion)


@router.patch(
    "/{idInstitucion}",
    response_model=InstitutionDetail,
    summary="Modificar los datos de la institución",
    description="Solo PROPIETARIO (403). Nombre, tipo y descripción; el CUIT no se modifica.",
)
def updateInstitution(idInstitucion: uuid.UUID, data: InstitutionUpdateRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.updateInstitution(db, auth.user, idInstitucion, data)


@router.post(
    "/{idInstitucion}/deletion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar lógicamente la institución",
    description=(
        "Solo PROPIETARIO (403). Requiere el nombre exacto de la institución, la contraseña si la cuenta tiene "
        "credencial local y el código MFA si lo tiene habilitado. La institución pasa a CERRADA (el CUIT queda "
        "reservado), todos los vínculos e invitaciones a BAJA y los perfiles de pacientes se desidentifican. "
        "No elimina cuentas ni hace DELETE físico."
    ),
)
def deleteInstitution(idInstitucion: uuid.UUID, data: InstitutionDeletionRequest, auth: CurrentAuth, db: DbSession):
    institutionService.deleteInstitution(db, auth.user, idInstitucion, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Equipo ---------------------------------------------------------------------------------


@router.get(
    "/{idInstitucion}/activity",
    response_model=ActivityPage,
    summary="Actividad reciente de la institución",
    description="Cualquier integrante activo. Resumen de las últimas actividades administrativas y operativas, de la más reciente a la "
    "más antigua, filtrado por lo que el rol puede consultar (el operador ve solo lo que hizo). Sale de la auditoría, sin duplicados, "
    "y no incluye datos personales de pacientes. El detalle técnico sigue en la auditoría (solo propietario).",
)
def recentActivity(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, limite: Annotated[int, Query(ge=1, le=20)] = 5):
    return activityService.listActivity(db, auth.user, idInstitucion, limite)


@router.get(
    "/{idInstitucion}/quota",
    response_model=QuotaRead,
    summary="Cupos de cuentas institucionales",
    description="PROPIETARIO o MODERADOR. Capacidad máxima de cuentas activas de ESTA institución, cuentas activas (propietario, moderadores y "
    "operadores con relación ACTIVA; sin invitaciones pendientes ni bajas), cupos disponibles y porcentaje de utilización, calculados en el "
    "servidor. El operador no los consulta (403).",
)
def institutionQuota(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.getQuota(db, auth.user, idInstitucion)


@router.get(
    "/{idInstitucion}/personnel",
    response_model=PersonnelPage,
    summary="Personal de la institución",
    description="PROPIETARIO o MODERADOR. Todo el personal (propietario, moderadores y operadores, también los dados de baja), una "
    "vez por persona, con su rol y estado actuales. Filtros combinables: `rol` (también considera los roles que tuvo), `estado`, "
    "`busqueda` (nombre, apellido, correo, legajo o matrícula). El `resumen` cuenta a todo el personal, sin depender de los filtros.",
)
def listPersonnel(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    rol: Literal["PROPIETARIO", "MODERADOR", "OPERADOR"] | None = None,
    estado: Literal["ACTIVO", "PENDIENTE", "SUSPENDIDO", "BAJA"] | None = None,
    busqueda: Annotated[str | None, Query(max_length=100)] = None,
    pagina: Annotated[int, Query(ge=1)] = 1, tamanioPagina: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return personnelService.listPersonnel(db, auth.user, idInstitucion, rol=rol, estado=estado, busqueda=busqueda, pagina=pagina,
                                          tamanioPagina=tamanioPagina)


@router.post(
    "/{idInstitucion}/personnel/export",
    response_class=Response,
    summary="Exportar el personal (CSV)",
    description="PROPIETARIO o MODERADOR (CONSULTAR_EQUIPO), validado en el servidor. `alcance` = SELECCION (las personas de "
    "`idsInstitucionUsuario`) o TODOS (todas las que coinciden con los filtros `rol`, `estado` y `busqueda`, como el listado). "
    "Devuelve un CSV separado por punto y coma, en UTF-8. 403 si no tiene el permiso. Cada intento queda en la auditoría: "
    "EXPORTACION_SOLICITADA, y después EXPORTACION_COMPLETADA o EXPORTACION_FALLIDA.",
)
def exportPersonnel(idInstitucion: uuid.UUID, body: PersonnelExportRequest, auth: CurrentAuth, db: DbSession):
    content, filename = personnelService.exportPersonnel(
        db, auth.user, idInstitucion, alcance=body.alcance, idsInstitucionUsuario=body.idsInstitucionUsuario,
        rol=body.rol, estado=body.estado, busqueda=body.busqueda,
    )
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get(
    "/{idInstitucion}/invitations",
    response_model=SentInvitationsPage,
    summary="Invitaciones enviadas por la institución",
    description="PROPIETARIO o MODERADOR. Invitaciones pendientes, aceptadas, rechazadas, canceladas y vencidas. Solo las aceptadas "
    "son personal: las demás nunca se incorporaron y no figuran en `/personnel`. Filtro opcional `estado`.",
)
def listSentInvitations(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    estado: Literal["PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA", "VENCIDA"] | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1, tamanioPagina: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return personnelService.listSentInvitations(db, auth.user, idInstitucion, estado=estado, pagina=pagina, tamanioPagina=tamanioPagina)


@router.get(
    "/{idInstitucion}/personnel/{idInstitucionUsuario}",
    response_model=PersonnelProfile,
    summary="Perfil institucional de una persona",
    description="PROPIETARIO o MODERADOR. Datos personales e institucionales, información profesional, fechas diferenciadas "
    "(invitación, cuenta, incorporación, última modificación y baja), períodos anteriores e historial administrativo reconstruido "
    "de la auditoría y de las fechas del vínculo. 404 si el vínculo no pertenece a esta institución.",
)
def personnelProfile(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return personnelService.getProfile(db, auth.user, idInstitucion, idInstitucionUsuario)


@router.delete(
    "/{idInstitucion}/personnel/{idInstitucionUsuario}/personal-data",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar los datos históricos de una persona del personal",
    description="Con el permiso para desvincular a ese rol: PROPIETARIO (moderadores y operadores) o MODERADOR (operadores). Suprime "
    "nombre y apellido profesionales, legajo y matrícula de todos los períodos de la persona en ESTA institución; el vínculo (rol, "
    "fechas, autoría de mediciones y auditoría) se conserva sin identificarla. Solo si ya está desvinculada (409 `PERSONA_VIGENTE`); "
    "409 `DATOS_YA_ELIMINADOS` si no queda nada por eliminar. No se puede deshacer.",
)
def erasePersonnelData(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    personnelService.erasePersonalData(db, auth.user, idInstitucion, idInstitucionUsuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{idInstitucion}/members",
    response_model=list[MemberRead],
    summary="Equipo de la institución",
    description="PROPIETARIO o MODERADOR. Integrantes activos e invitaciones pendientes (sin correos).",
)
def listMembers(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.listMembers(db, auth.user, idInstitucion)


def _lookupDescription(who: str, role: str) -> str:
    return (
        f"{who}. Busca por correo exacto una cuenta `USUARIO_INSTITUCIONAL` activa y devuelve solo nombre y apellido "
        f"para confirmar la invitación como {role}. 404 si no existe una cuenta institucional con ese correo; 409 si "
        "es una cuenta de uso personal (su tipo no cambia), si ya pertenece o si tiene una invitación pendiente. "
        "Limitado por cuenta (429)."
    )


# Moderadores: los designa y revoca solo el PROPIETARIO.


@router.get("/{idInstitucion}/moderators", response_model=list[MemberRead], summary="Moderadores",
            description="PROPIETARIO o MODERADOR. Activos e invitaciones pendientes; `incluirBajas` agrega el historial.")
def listModerators(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, incluirBajas: bool = False):
    return institutionService.listMembers(db, auth.user, idInstitucion, MODERADOR, incluirBajas)


@router.post("/{idInstitucion}/moderators/lookup", response_model=MemberCandidate,
             summary="Buscar una cuenta para designarla moderador",
             description=_lookupDescription("Solo PROPIETARIO", "moderador"))
def lookupModerator(idInstitucion: uuid.UUID, data: MemberEmailRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.lookupCandidate(db, auth.user, idInstitucion, MODERADOR, data.correoElectronico)


@router.post("/{idInstitucion}/moderators", response_model=MemberRead, status_code=status.HTTP_201_CREATED,
             summary="Agregar un moderador",
             description=(
                 "Solo PROPIETARIO (403). Rol MODERADOR fijado por el backend. Si el correo no tiene cuenta, crea un "
                 "Usuario USUARIO_INSTITUCIONAL PENDIENTE (requiere `nombre` y `apellido`) y envía el enlace de "
                 "activación; si existe una cuenta institucional, la reutiliza. El vínculo queda PENDIENTE hasta que "
                 "la persona acepte. 409 si es una cuenta individual o ya está vinculada. No crea PerfilMedicion."
             ))
def inviteModerator(idInstitucion: uuid.UUID, data: MemberInviteRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.invite(db, auth.user, idInstitucion, MODERADOR, data.correoElectronico,
                                     nombre=data.nombre, apellido=data.apellido, datos=data.adminFields())


@router.patch("/{idInstitucion}/moderators/{idInstitucionUsuario}", response_model=MemberRead,
              summary="Modificar los datos administrativos de un moderador",
              description="Solo PROPIETARIO (403). Matrícula, legajo y nombre/apellido profesional histórico del "
              "vínculo; solo los campos enviados. No cambia el rol ni la cuenta Usuario. Auditado.")
def updateModerator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, data: MemberAdminUpdateRequest,
                    auth: CurrentAuth, db: DbSession):
    return institutionService.updateMemberAdmin(db, auth.user, idInstitucion, MODERADOR, idInstitucionUsuario,
                                                data.model_dump(exclude_unset=True))


@router.post("/{idInstitucion}/moderators/{idInstitucionUsuario}/resend", response_model=MemberRead,
             summary="Reenviar la invitación de un moderador",
             description="Solo PROPIETARIO. Renueva el vencimiento y, si la cuenta no se activó, el enlace de activación.")
def resendModerator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.resendInvitation(db, auth.user, idInstitucion, MODERADOR, idInstitucionUsuario)


@router.delete("/{idInstitucion}/moderators/{idInstitucionUsuario}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Revocar un moderador o cancelar su invitación",
               description="Solo PROPIETARIO. También cancela las invitaciones pendientes que ese moderador emitió.")
def revokeModerator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    institutionService.revokeMember(db, auth.user, idInstitucion, MODERADOR, idInstitucionUsuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Operadores: los incorpora un MODERADOR; los administra (baja) el PROPIETARIO o un MODERADOR.


@router.get("/{idInstitucion}/operators", response_model=list[MemberRead], summary="Operadores",
            description="PROPIETARIO o MODERADOR. Activos e invitaciones pendientes; `incluirBajas` agrega el historial.")
def listOperators(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, incluirBajas: bool = False):
    return institutionService.listMembers(db, auth.user, idInstitucion, OPERADOR, incluirBajas)


@router.post("/{idInstitucion}/operators/lookup", response_model=MemberCandidate,
             summary="Buscar una cuenta para incorporarla como operador",
             description=_lookupDescription("Solo MODERADOR", "operador"))
def lookupOperator(idInstitucion: uuid.UUID, data: MemberEmailRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.lookupCandidate(db, auth.user, idInstitucion, OPERADOR, data.correoElectronico)


@router.post("/{idInstitucion}/operators", response_model=MemberRead, status_code=status.HTTP_201_CREATED,
             summary="Agregar un operador",
             description="Solo MODERADOR (403). Mismo flujo que los moderadores: crea la cuenta institucional pendiente "
             "si no existe o reutiliza la existente; el vínculo queda PENDIENTE hasta la aceptación.")
def inviteOperator(idInstitucion: uuid.UUID, data: OperatorInviteRequest, auth: CurrentAuth, db: DbSession):
    return institutionService.invite(
        db, auth.user, idInstitucion, OPERADOR, data.correoElectronico,
        nombre=data.nombre, apellido=data.apellido, datos=data.adminFields(),
    )


@router.patch("/{idInstitucion}/operators/{idInstitucionUsuario}", response_model=MemberRead,
              summary="Modificar los datos administrativos de un operador",
              description="PROPIETARIO o MODERADOR (403). Matrícula, legajo y nombre/apellido profesional histórico "
              "del vínculo; solo los campos enviados. No cambia el rol ni la cuenta Usuario. Auditado.")
def updateOperator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, data: MemberAdminUpdateRequest,
                   auth: CurrentAuth, db: DbSession):
    return institutionService.updateMemberAdmin(db, auth.user, idInstitucion, OPERADOR, idInstitucionUsuario,
                                                data.model_dump(exclude_unset=True))


@router.post("/{idInstitucion}/operators/{idInstitucionUsuario}/resend", response_model=MemberRead,
             summary="Reenviar la invitación de un operador", description="Solo MODERADOR.")
def resendOperator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return institutionService.resendInvitation(db, auth.user, idInstitucion, OPERADOR, idInstitucionUsuario)


@router.get("/{idInstitucion}/operators/{idInstitucionUsuario}/offboarding", response_model=OffboardPlan,
            summary="Qué falta resolver para desvincular a un operador",
            description="PROPIETARIO o MODERADOR. Pacientes que el operador tiene a cargo, operadores activos que pueden recibirlos y, si "
            "corresponde, el motivo que impide desvincularlo (sin otro operador habilitado o con transferencias pendientes de aceptación).")
def operatorOffboardingPlan(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return offboardingService.plan(db, auth.user, idInstitucion, idInstitucionUsuario)


@router.post("/{idInstitucion}/operators/{idInstitucionUsuario}/offboard", response_model=OffboardResult,
             summary="Reasignar los pacientes de un operador y desvincularlo",
             description="PROPIETARIO o MODERADOR. Una sola transacción: reasigna a TODOS los pacientes del operador a operadores activos de "
             "la institución elegidos por quien gestiona y lo desvincula. Si falta alguno, hay transferencias pendientes o algo falla, no cambia "
             "nada y el operador sigue vinculado. Las mediciones anteriores conservan su autoría.")
def offboardOperator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, data: OffboardRequest, auth: CurrentAuth, db: DbSession):
    return offboardingService.offboard(db, auth.user, idInstitucion, idInstitucionUsuario, data)


@router.delete("/{idInstitucion}/operators/{idInstitucionUsuario}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Desvincular un operador o cancelar su invitación",
               description="PROPIETARIO o MODERADOR. Un operador con pacientes a su cargo no se desvincula por acá (409 PACIENTES_ASIGNADOS): "
               "hay que reasignarlos antes con `/offboard`.")
def revokeOperator(idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    institutionService.revokeMember(db, auth.user, idInstitucion, OPERADOR, idInstitucionUsuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Pacientes ------------------------------------------------------------------------------
# Pacientes institucionales (PerfilMedicion INSTITUCIONAL): no son cuentas de GlucoLume. Reglas en
# backend/app/services/institutionPatients.py; cada consulta filtra por institución en el backend.


@router.get(
    "/{idInstitucion}/patients",
    response_model=PatientPage,
    summary="Pacientes de la institución",
    description="Cualquier integrante activo. `busqueda` por nombre, apellido, documento o seudónimo; filtros por "
    "responsable, estado (ACTIVO | BAJA) o `soloMios`. Paginado (máximo 50 por página).",
)
def listPatients(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    busqueda: Annotated[str | None, Query(max_length=100)] = None,
    idResponsable: uuid.UUID | None = None,
    estado: Literal["ACTIVO", "BAJA"] = "ACTIVO",
    soloMios: bool = False,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanioPagina: Annotated[int, Query(ge=1, le=patientService.MAX_PAGE_SIZE)] = 20,
):
    return patientService.listPatients(
        db, auth.user, idInstitucion, busqueda=busqueda, idResponsable=idResponsable, estado=estado,
        soloMios=soloMios, pagina=pagina, tamanioPagina=tamanioPagina,
    )


@router.get(
    "/{idInstitucion}/patients/assignable-operators",
    response_model=list[AssignableOperator],
    summary="Operadores disponibles para asignar pacientes",
    description="Operadores activos de la institución (solo nombre y apellido), para elegir el responsable de un "
    "paciente. Lo consultan propietario, moderador y operador; no habilita a administrar operadores.",
)
def assignableOperators(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return patientService.assignableOperators(db, auth.user, idInstitucion)


@router.get(
    "/{idInstitucion}/reassignments",
    response_model=ReassignmentOverview,
    summary="Pacientes pendientes de reasignación",
    description="Propietario y moderador. Operadores desvinculados con pacientes a su cargo: cantidad, fecha de desvinculación y estado. "
    "El operador no tiene acceso (403).",
)
def reassignmentsOverview(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return reassignmentService.overview(db, auth.user, idInstitucion)


@router.get(
    "/{idInstitucion}/reassignments/items",
    response_model=ReassignmentPage,
    summary="Detalle de las reasignaciones",
    description="Propietario y moderador. Una fila por paciente (seudónimo y nombre; sin documento ni mediciones). Filtra por `estado` "
    "(PENDIENTE por omisión; vacío = todas) y por operador anterior.",
)
def reassignmentItems(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    estado: Literal["PENDIENTE", "COMPLETADA", "CANCELADA", "TODAS"] = "PENDIENTE",
    idOperadorAnterior: uuid.UUID | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanioPagina: Annotated[int, Query(ge=1, le=reassignmentService.MAX_PAGE_SIZE)] = 50,
):
    return reassignmentService.listItems(db, auth.user, idInstitucion, None if estado == "TODAS" else estado,
                                         idOperadorAnterior, pagina, tamanioPagina)


@router.post(
    "/{idInstitucion}/reassignments/assign",
    response_model=ReassignmentAssignResult,
    summary="Reasignar pacientes pendientes",
    description="Propietario y moderador. Asigna uno o varios pacientes pendientes a UN operador activo de la misma institución elegido "
    "por quien reasigna (nunca automático). Cambia solo el responsable vigente: las mediciones anteriores conservan su autoría. "
    "Una tarea que otra persona ya resolvió se informa como YA_RESUELTA.",
)
def assignReassignments(idInstitucion: uuid.UUID, data: ReassignmentAssignRequest, auth: CurrentAuth, db: DbSession):
    return reassignmentService.assign(db, auth.user, idInstitucion, data)


@router.post(
    "/{idInstitucion}/reassignments/regularize",
    response_model=ReassignmentRegularizeResult,
    summary="Regularizar un operador desvinculado con pacientes sin responsable",
    description="Propietario y moderador. Para un operador ya desvinculado que figura como responsable de pacientes sin tarea de reasignación, "
    "crea las tareas pendientes (una por paciente) para resolverlas con el flujo habitual. No reasigna nada ni elige destinatarios.",
)
def regularizeReassignments(idInstitucion: uuid.UUID, data: ReassignmentRegularizeRequest, auth: CurrentAuth, db: DbSession):
    return reassignmentService.regularize(db, auth.user, idInstitucion, data)


@router.post(
    "/{idInstitucion}/patients",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un paciente",
    description="Si lo crea un operador sin indicar responsable, queda a su cargo. El responsable debe ser un "
    "operador activo de la misma institución. 409 si ya hay un paciente activo con ese documento.",
)
def createPatient(idInstitucion: uuid.UUID, data: PatientCreateRequest, auth: CurrentAuth, db: DbSession):
    return patientService.createPatient(db, auth.user, idInstitucion, data)


@router.post(
    "/{idInstitucion}/patients/export",
    response_class=Response,
    summary="Exportar pacientes (CSV)",
    description="Propietario, moderador u operador (CONSULTAR_PACIENTES), validado en el servidor. `alcance` = SELECCION (los pacientes de "
    "`idsPerfilMedicion`) o TODOS (los que coinciden con `busqueda`, `idResponsable` y `estado`). El operador exporta solo los pacientes "
    "a su cargo: un paciente ajeno se rechaza (409 `DATOS_INVALIDOS`). Sin mediciones ni información de salud. Cada intento queda en la "
    "auditoría: EXPORTACION_SOLICITADA, y después EXPORTACION_COMPLETADA o EXPORTACION_FALLIDA.",
)
def exportPatients(idInstitucion: uuid.UUID, body: PatientExportRequest, auth: CurrentAuth, db: DbSession):
    content, filename = patientService.exportPatients(
        db, auth.user, idInstitucion, alcance=body.alcance, ids=body.idsPerfilMedicion, busqueda=body.busqueda,
        idResponsable=body.idResponsable, estado=body.estado,
    )
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/{idInstitucion}/patients/{idPerfilMedicion}", response_model=PatientRead,
            summary="Detalle de un paciente", description="Queda registrado en la auditoría (ACCESO).")
def getPatient(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return resultEmailService.withResultEmail(db, patientService.getPatient(db, auth.user, idInstitucion, idPerfilMedicion))


@router.patch("/{idInstitucion}/patients/{idPerfilMedicion}", response_model=PatientRead,
              summary="Modificar un paciente",
              description="Un operador solo modifica los pacientes a su cargo; propietario y moderador, cualquiera.")
def updatePatient(
    idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, data: PatientUpdateRequest, auth: CurrentAuth, db: DbSession
):
    return patientService.updatePatient(db, auth.user, idInstitucion, idPerfilMedicion, data)


@router.post("/result-email/confirm", dependencies=[rateLimit("resultEmailConfirm")], response_model=ResultEmailConfirmRead,
             summary="El paciente confirma su correo para recibir resultados",
             description="Sin sesión: se autentica con el token firmado del enlace que recibió el paciente (72 h, propósito único). "
             "Guarda el correo (si se pidió) y envía el resultado pendiente (si lo había). Repetirlo no vuelve a enviar nada.")
def confirmPatientResultEmail(data: ResultEmailConfirmRequest, db: DbSession):
    return resultEmailConfirmation.confirm(db, data.token)


@router.put("/{idInstitucion}/patients/{idPerfilMedicion}/result-email", response_model=PatientRead,
            summary="Cargar o cambiar el correo del paciente para sus resultados",
            description="Solo el operador responsable. Exige confirmar que el paciente lo autorizó. Vence a los 12 meses de la carga o del "
            "último cambio; la auditoría no registra el correo.")
def setPatientResultEmail(
    idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, data: PatientResultEmailRequest, auth: CurrentAuth, db: DbSession
):
    return resultEmailService.setResultEmail(db, auth.user, idInstitucion, idPerfilMedicion, data)


@router.delete("/{idInstitucion}/patients/{idPerfilMedicion}/result-email", response_model=PatientRead,
               summary="Quitar el correo del paciente",
               description="Solo el operador responsable. El paciente deja de recibir resultados automáticos.")
def clearPatientResultEmail(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return resultEmailService.clearResultEmail(db, auth.user, idInstitucion, idPerfilMedicion)


@router.put("/{idInstitucion}/patients/{idPerfilMedicion}/responsible", response_model=PatientRead,
            summary="Asignar el operador responsable",
            description="El operador debe estar activo en la misma institución (422 si no). Queda en TransferenciaPerfil.")
def assignResponsible(
    idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, data: PatientAssignRequest, auth: CurrentAuth, db: DbSession
):
    return patientService.assignResponsible(
        db, auth.user, idInstitucion, idPerfilMedicion, data.idInstitucionUsuarioResponsable
    )


@router.get("/{idInstitucion}/patients/{idPerfilMedicion}/measurements", response_model=MeasurementPage,
            summary="Mediciones del paciente",
            description="Mediciones vinculadas por idPerfilMedicion. Filtros por fecha (`desde`, `hasta`), `modo` y "
            "`estado`; orden cronológico `desc` (por defecto) o `asc`. Paginado. El paciente debe ser de la institución.")
def listPatientMeasurements(
    idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    desde: date | None = None, hasta: date | None = None,
    modo: Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"] | None = None,
    estado: Literal["PENDIENTE", "ADQUIRIENDO", "PROCESANDO", "COMPLETADA", "INVALIDA", "CANCELADA"] | None = None,
    orden: Literal["asc", "desc"] = "desc",
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanioPagina: Annotated[int, Query(ge=1, le=patientService.MAX_PAGE_SIZE)] = 20,
    origen: Literal["DEMO", "REAL"] | None = None,
):
    return measurementService.listPatientHistory(
        db, auth.user, idInstitucion, idPerfilMedicion, desde=desde, hasta=hasta, modo=modo, estado=estado,
        orden=orden, pagina=pagina, tamanioPagina=tamanioPagina, origen=origen)


@router.get("/{idInstitucion}/patients/{idPerfilMedicion}/measurements/statistics",
            response_model=SharedStatisticsRead, summary="Estadísticas de las mediciones del paciente",
            description="Promedios, mínimos, máximos y serie diaria solo sobre mediciones COMPLETADA. Últimos "
            "`dias` (7, 30 o 90) o un rango `desde`/`hasta`.")
def patientStatistics(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession,
                      dias: int = 30, desde: date | None = None, hasta: date | None = None):
    return measurementService.patientStatistics(db, auth.user, idInstitucion, idPerfilMedicion, dias, desde, hasta)


@router.get("/{idInstitucion}/patients/{idPerfilMedicion}/measurements/evolution", response_model=EvolutionRead,
            summary="Evolución de las mediciones del paciente",
            description="Solo el operador responsable vigente. Cada medición COMPLETADA (experimental o DEMO, de cualquier modo) es un punto con "
            "todos sus valores. Período: dias (1, 7, 14, 30 o 90) o desde/hasta. `origen`: TODOS (por defecto), EXPERIMENTAL o DEMO; "
            "`modo` opcional. Las estadísticas DEMO y experimentales van separadas y `resumen` trae los conteos y la última medición.")
def patientEvolution(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession, dias: int = 30,
                     desde: date | None = None, hasta: date | None = None, origen: Literal["TODOS", "EXPERIMENTAL", "DEMO"] = "TODOS",
                     modo: Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"] | None = None):
    return measurementService.patientEvolution(db, auth.user, idInstitucion, idPerfilMedicion, dias, desde, hasta, origen, modo)


@router.get("/{idInstitucion}/dashboard", response_model=InstitutionDashboard,
            summary="Dashboard general de la institución",
            description="Propietario y moderador. Indicadores agregados y seudonimizados de ESTA institución: pacientes, "
            "personal, dispositivos, mediciones por período, estados, modos, serie diaria y carga por operador.")
def institutionDashboard(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, dias: int = 30,
                         desde: date | None = None, hasta: date | None = None, operador: uuid.UUID | None = None,
                         modo: Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"] | None = None,
                         estado: Literal["PENDIENTE", "ADQUIRIENDO", "PROCESANDO", "COMPLETADA", "INVALIDA", "CANCELADA"] | None = None,
                         origen: Literal["TODOS", "EXPERIMENTAL", "DEMO"] = "TODOS"):
    return dashboardService.institutionDashboard(db, auth.user, idInstitucion, dias, desde, hasta, operador, modo, estado, origen)


@router.get("/{idInstitucion}/analytics/patients", response_model=PatientAnalytics,
            summary="Análisis de pacientes y mediciones del operador",
            description="SOLO el operador responsable vigente, y solo sobre los pacientes activos que tiene a cargo hoy (no hay parámetro para "
            "consultar a otro operador; propietario y moderador no acceden por su rol). Filtros combinables, rangos de edad configurables (edadCortes), segmentación por sexo, edad, alimentación, modo, origen, dispositivo o matriz; los datos DEMO se excluyen salvo "
            "pedido expreso y nunca se promedian con los experimentales. Los datos ausentes se informan como «sin informar», nunca como 0.")
def patientAnalytics(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, dias: Annotated[int, Query(ge=1, le=365)] = 30,
    desde: date | None = None, hasta: date | None = None, idPerfilMedicion: uuid.UUID | None = None, sexo: str | None = None,
    edad: str | None = None, edadBase: str = "ACTUAL", alimentacion: str | None = None, modo: str | None = None,
    origen: str = "TODOS", estado: str = "TODOS", calidad: str | None = None, variable: str = "spo2",
    granularidad: str = "dia", compararMatriz: bool = False, pagina: Annotated[int, Query(ge=1)] = 1,
    tamanioPagina: Annotated[int, Query(ge=1, le=50)] = 10, edadCortes: str | None = None, segmentar: str = "NINGUNA",
    calidadMinima: float | None = None,
):
    return analyticsService.analyze(
        db, auth.user, idInstitucion, dias=dias, desde=desde, hasta=hasta, idPerfilMedicion=idPerfilMedicion, sexo=sexo, edad=edad,
        edadBase=edadBase, alimentacion=alimentacion, modo=modo, origen=origen, estado=estado, calidad=calidad, variable=variable,
        granularidad=granularidad, compararMatriz=compararMatriz, pagina=pagina, tamanioPagina=tamanioPagina, edadCortes=edadCortes,
        segmentar=segmentar, calidadMinima=calidadMinima)


@router.get("/{idInstitucion}/operators/{idOperador}/dashboard", response_model=OperatorDashboard,
            summary="Dashboard de un operador",
            description="`idOperador` es el vínculo (InstitucionUsuario) o `me`. Un operador consulta solo el suyo; "
            "propietario y moderador, el de cualquier operador de la institución. Distingue pacientes asignados ahora "
            "de mediciones realizadas históricamente.")
def operatorDashboard(idInstitucion: uuid.UUID, idOperador: str, auth: CurrentAuth, db: DbSession, dias: int = 30,
                      desde: date | None = None, hasta: date | None = None):
    return dashboardService.operatorDashboard(db, auth.user, idInstitucion, idOperador, dias, desde, hasta)


@router.get("/{idInstitucion}/patients/{idPerfilMedicion}/dashboard", response_model=PatientDashboard,
            summary="Dashboard de un paciente",
            description="Perfil, indicadores, estadísticas, historial con operador y transferencias de UN PerfilMedicion. "
            "Nombre y apellido solo con autorización; un operador consulta únicamente los pacientes a su cargo.")
def patientDashboard(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession,
                     dias: int = 30, desde: date | None = None, hasta: date | None = None):
    return dashboardService.patientDashboard(db, auth.user, idInstitucion, idPerfilMedicion, dias, desde, hasta)


@router.get("/{idInstitucion}/indicators", response_model=InstitutionIndicators,
            summary="Indicadores agregados de la institución",
            description="PROPIETARIO o MODERADOR. Solo conteos y promedios: no identifica pacientes.")
def institutionIndicators(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return measurementService.institutionIndicators(db, auth.user, idInstitucion)


@router.post("/{idInstitucion}/patients/{idPerfilMedicion}/discharge", response_model=PatientRead,
             summary="Dar de baja un paciente",
             description="PROPIETARIO o MODERADOR. Baja administrativa: inicia la conservación de 12 meses "
             "(fechaExpiracionDatosPersonales); luego los datos personales se desidentifican. Las mediciones se conservan.")
def dischargePatient(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return patientService.dischargePatient(db, auth.user, idInstitucion, idPerfilMedicion)


# --- Transferencia de pacientes entre operadores (RF32) -----------------------------------------


@router.post(
    "/{idInstitucion}/patients/{idPerfilMedicion}/transfers",
    response_model=TransferItem,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar la transferencia de un paciente a otro operador",
    description="Solo el OPERADOR responsable del paciente, hacia otro operador activo de la misma institución. El "
    "paciente sigue a cargo del solicitante hasta que el destinatario acepte. 409 si ya hay una solicitud pendiente.",
)
def requestTransfer(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, data: TransferRequest,
                    auth: CurrentAuth, db: DbSession):
    return transferService.requestTransfer(db, auth.user, idInstitucion, idPerfilMedicion, data.idOperadorDestino,
                                           data.observacion)


@router.get(
    "/{idInstitucion}/transfers",
    response_model=TransferPage,
    summary="Transferencias recibidas, enviadas e historial",
    description="Un operador ve las suyas (`direccion` = recibidas | enviadas | todas) y propietario y moderador el "
    "historial de la institución. Solo el identificador seudónimo, la edad y el sexo del paciente.",
)
def listTransfers(
    idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession,
    direccion: Literal["recibidas", "enviadas", "todas"] = "todas",
    estado: Literal["PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA"] | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1, tamanioPagina: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return transferService.listTransfers(db, auth.user, idInstitucion, direccion=direccion, estado=estado,
                                         pagina=pagina, tamanioPagina=tamanioPagina)


@router.get(
    "/{idInstitucion}/transfers/{idTransferenciaPerfil}",
    response_model=TransferDetail,
    summary="Detalle de una transferencia",
    description="Paciente, operador de origen y de destino, solicitante, fechas, estado e historial. Un operador solo "
    "consulta las suyas; una transferencia de otra institución responde 404.",
)
def getTransfer(idInstitucion: uuid.UUID, idTransferenciaPerfil: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return transferService.getTransfer(db, auth.user, idInstitucion, idTransferenciaPerfil)


@router.post("/{idInstitucion}/transfers/{idTransferenciaPerfil}/accept", response_model=TransferItem,
             summary="Aceptar una transferencia",
             description="Solo el operador destinatario. Cambia el responsable y cierra la solicitud en una sola "
             "transacción; las mediciones no se modifican. 409 si ya no está pendiente o perdió vigencia.")
def acceptTransfer(idInstitucion: uuid.UUID, idTransferenciaPerfil: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return transferService.acceptTransfer(db, auth.user, idInstitucion, idTransferenciaPerfil)


@router.post("/{idInstitucion}/transfers/{idTransferenciaPerfil}/reject", response_model=TransferItem,
             summary="Rechazar una transferencia", description="Solo el operador destinatario. El responsable no cambia.")
def rejectTransfer(idInstitucion: uuid.UUID, idTransferenciaPerfil: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return transferService.rejectTransfer(db, auth.user, idInstitucion, idTransferenciaPerfil)


@router.post("/{idInstitucion}/transfers/{idTransferenciaPerfil}/cancel", response_model=TransferItem,
             summary="Cancelar una transferencia pendiente",
             description="Solo quien la solicitó y mientras siga pendiente. El responsable no cambia.")
def cancelTransfer(idInstitucion: uuid.UUID, idTransferenciaPerfil: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return transferService.cancelTransfer(db, auth.user, idInstitucion, idTransferenciaPerfil)


# --- Matrices de estimación de la institución ---------------------------------------------------


@router.get("/{idInstitucion}/matrices", response_model=InstitutionMatrixOverview,
            summary="Matrices de la institución",
            description="PROPIETARIO o MODERADOR. Matriz institucional activa, matriz global de respaldo, la que se "
            "aplica hoy y todas las versiones institucionales. Operaciones sobre una matriz: `/api/v1/matrices`.")
def institutionMatrices(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.institutionOverview(db, auth.user, idInstitucion)


@router.get("/{idInstitucion}/matrices/effective", response_model=MatrixSummary | None,
            summary="Matriz que se aplica en la institución",
            description="Cualquier integrante (solo informativa, sin reglas): la institucional activa o, si no hay, "
            "la global. La elige el backend para cada medición.")
def effectiveMatrix(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.effectiveForInstitution(db, auth.user, idInstitucion)
