# Groups - Rutas del módulo Grupo familiar (/api/v1/groups)
#
# Solo traduce HTTP <-> servicios; reglas, autorización y consentimientos viven en backend/app/services/group.py.
# La identidad sale siempre de la sesión: ningún endpoint acepta un idUsuario para actuar sobre datos ajenos.

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentAuth, DbSession
from app.schemas.dashboard import GroupDashboard
from app.schemas.group import (
    FamilyGroupCreateRequest,
    FamilyGroupDetail,
    FamilyGroupUpdateRequest,
    GroupCandidate,
    GroupDeletionRequest,
    GroupEmailRequest,
    GroupInvitationRead,
    GroupMemberRead,
    MyGroupResponse,
    MySharingRead,
    ReceivedGroupInvitation,
    SharedHistoryPage,
    SharedMeasurementDetail,
    SharedLatestRead,
    SharedMemberSummary,
    SharedNoticesRead,
    SharedProfileRead,
    SharedStatisticsRead,
    SharingSettings,
    TransferAdminRequest,
)
from app.services import dashboard as dashboardService
from app.services import group as groupService

router = APIRouter(prefix="/groups", tags=["groups"])

NO_CONTENT = status.HTTP_204_NO_CONTENT


def _empty() -> Response:
    return Response(status_code=NO_CONTENT)


# --- Mi grupo e invitaciones recibidas -------------------------------------------------------


@router.get("/mine", response_model=MyGroupResponse, summary="Grupo activo de la cuenta",
            description="Cuenta individual: su único grupo ACTIVO o `grupo: null`.")
def myGroup(auth: CurrentAuth, db: DbSession):
    return MyGroupResponse(grupo=groupService.getMine(db, auth.user))


@router.get("/invitations", response_model=list[ReceivedGroupInvitation], summary="Invitaciones recibidas")
def receivedInvitations(auth: CurrentAuth, db: DbSession):
    return groupService.listReceivedInvitations(db, auth.user)


@router.post("/invitations/{idGrupoUsuario}/accept", response_model=FamilyGroupDetail, summary="Aceptar invitación",
             description="Solo la cuenta invitada. Queda MIEMBRO ACTIVO con todos los permisos de compartición "
             "desactivados. 409 `YA_PERTENECE_A_GRUPO` si ya pertenece a un grupo (aun por una aceptación simultánea).")
def acceptInvitation(idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.respondInvitation(db, auth.user, idGrupoUsuario, accept=True)


@router.post("/invitations/{idGrupoUsuario}/reject", status_code=NO_CONTENT, summary="Rechazar invitación")
def rejectInvitation(idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    groupService.respondInvitation(db, auth.user, idGrupoUsuario, accept=False)
    return _empty()


# --- Grupo --------------------------------------------------------------------------------------


@router.post("", response_model=FamilyGroupDetail, status_code=status.HTTP_201_CREATED, summary="Crear grupo",
             description="Solo cuentas individuales sin grupo activo (409 `YA_PERTENECE_A_GRUPO`). El creador queda "
             "ADMINISTRADOR, sin compartir nada.")
def createGroup(data: FamilyGroupCreateRequest, auth: CurrentAuth, db: DbSession):
    return groupService.createGroup(db, auth.user, data)


@router.post("/{idGrupo}/creation-notice", status_code=NO_CONTENT, summary="Reenviar la confirmación de creación",
             description="Administrador. Solo si el correo de confirmación no se pudo enviar (409 "
             "`NOTIFICACION_YA_ENVIADA` si ya se envió; 503 `NOTIFICACION_NO_ENVIADA` si vuelve a fallar).")
def resendCreationNotice(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    groupService.resendCreationNotice(db, auth.user, idGrupo)
    return _empty()


@router.get("/{idGrupo}", response_model=FamilyGroupDetail, summary="Panel del grupo")
def getGroup(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.getDetail(db, auth.user, idGrupo)


@router.patch("/{idGrupo}", response_model=FamilyGroupDetail, summary="Modificar nombre y descripción (administrador)")
def updateGroup(idGrupo: uuid.UUID, data: FamilyGroupUpdateRequest, auth: CurrentAuth, db: DbSession):
    return groupService.updateGroup(db, auth.user, idGrupo, data)


@router.post("/{idGrupo}/deletion", status_code=NO_CONTENT, summary="Eliminar grupo (administrador)",
             description="Baja lógica con el nombre exacto como confirmación. No elimina cuentas, perfiles ni "
             "mediciones.")
def deleteGroup(idGrupo: uuid.UUID, data: GroupDeletionRequest, auth: CurrentAuth, db: DbSession):
    groupService.deleteGroup(db, auth.user, idGrupo, data.confirmacionNombre)
    return _empty()


@router.post("/{idGrupo}/leave", status_code=NO_CONTENT, summary="Abandonar el grupo",
             description="409 `TRANSFERENCIA_REQUERIDA` si el administrador tiene otros integrantes; "
             "409 `ELIMINACION_REQUERIDA` si es el único.")
def leaveGroup(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    groupService.leaveGroup(db, auth.user, idGrupo)
    return _empty()


@router.post("/{idGrupo}/transfer", response_model=FamilyGroupDetail, summary="Designar nuevo administrador")
def transferAdmin(idGrupo: uuid.UUID, data: TransferAdminRequest, auth: CurrentAuth, db: DbSession):
    return groupService.transferAdmin(db, auth.user, idGrupo, data.idGrupoUsuario)


# --- Integrantes e invitaciones enviadas ---------------------------------------------------------


@router.get("/{idGrupo}/members", response_model=list[GroupMemberRead], summary="Integrantes activos")
def listMembers(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.listMembers(db, auth.user, idGrupo)


@router.delete("/{idGrupo}/members/{idGrupoUsuario}", status_code=NO_CONTENT,
               summary="Desvincular integrante (administrador)")
def removeMember(idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    groupService.removeMember(db, auth.user, idGrupo, idGrupoUsuario)
    return _empty()


@router.get("/{idGrupo}/invitations", response_model=list[GroupInvitationRead],
            summary="Invitaciones pendientes (administrador)")
def sentInvitations(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.listSentInvitations(db, auth.user, idGrupo)


@router.post("/{idGrupo}/invitations/lookup", response_model=GroupCandidate, summary="Buscar cuenta individual",
             description="Administrador. Correo exacto; devuelve solo nombre y apellido si se puede invitar.")
def lookupCandidate(idGrupo: uuid.UUID, data: GroupEmailRequest, auth: CurrentAuth, db: DbSession):
    return groupService.lookupCandidate(db, auth.user, idGrupo, data.correoElectronico)


@router.post("/{idGrupo}/invitations", response_model=GroupInvitationRead, status_code=status.HTTP_201_CREATED,
             summary="Invitar (administrador)")
def invite(idGrupo: uuid.UUID, data: GroupEmailRequest, auth: CurrentAuth, db: DbSession):
    return groupService.invite(db, auth.user, idGrupo, data.correoElectronico)


@router.delete("/{idGrupo}/invitations/{idGrupoUsuario}", status_code=NO_CONTENT,
               summary="Cancelar invitación (administrador)")
def cancelInvitation(idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    groupService.cancelInvitation(db, auth.user, idGrupo, idGrupoUsuario)
    return _empty()


# --- Mis permisos y datos compartidos -------------------------------------------------------------


@router.get("/{idGrupo}/sharing/me", response_model=MySharingRead, summary="Mis permisos de compartición")
def mySharing(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.getMySharing(db, auth.user, idGrupo)


@router.put("/{idGrupo}/sharing/me", response_model=MySharingRead, summary="Modificar mis permisos",
            description="Solo los de la cuenta autenticada. Cuatro permisos independientes; todos en false revoca.")
def updateMySharing(idGrupo: uuid.UUID, data: SharingSettings, auth: CurrentAuth, db: DbSession):
    return groupService.updateMySharing(db, auth.user, idGrupo, data)


@router.get("/{idGrupo}/shared", response_model=list[SharedMemberSummary], summary="Qué comparte cada integrante")
def sharedMembers(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.sharedMembers(db, auth.user, idGrupo)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/profile", response_model=SharedProfileRead,
            summary="Datos básicos compartidos", description="403 `DATOS_NO_COMPARTIDOS` sin ese permiso.")
def sharedProfile(idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.sharedProfile(db, auth.user, idGrupo, idGrupoUsuario)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/latest", response_model=SharedLatestRead,
            summary="Última medición compartida")
def sharedLatest(idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.sharedLatest(db, auth.user, idGrupo, idGrupoUsuario)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/history", response_model=SharedHistoryPage,
            summary="Historial compartido")
def sharedHistory(
    idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanioPagina: Annotated[int, Query(ge=1, le=groupService.MAX_PAGE_SIZE)] = 20,
):
    return groupService.sharedHistory(db, auth.user, idGrupo, idGrupoUsuario, pagina, tamanioPagina)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/notices", response_model=SharedNoticesRead,
            summary="Avisos de medición compartidos",
            description="Solo fecha y hora de las mediciones, sin valores. Lo autoriza únicamente `notificaMedicion` "
            "(independiente de última medición e historial). 403 `DATOS_NO_COMPARTIDOS` sin ese permiso.")
def sharedNotices(
    idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession,
    limite: Annotated[int, Query(ge=1, le=groupService.MAX_PAGE_SIZE)] = 10,
    pagina: Annotated[int, Query(ge=1)] = 1,
):
    return groupService.sharedNotices(db, auth.user, idGrupo, idGrupoUsuario, limite, pagina)


@router.get("/{idGrupo}/dashboard", response_model=GroupDashboard, summary="Dashboard del grupo familiar",
            description="Resumen por rol, qué comparte cada integrante, actividad reciente autorizada y estadísticas agrupadas "
            "SOLO con quienes compartieron su historial. Los permisos se evalúan en cada consulta.")
def groupDashboard(idGrupo: uuid.UUID, auth: CurrentAuth, db: DbSession, dias: int = 30,
                   desde: date | None = None, hasta: date | None = None):
    return dashboardService.groupDashboard(db, auth.user, idGrupo, dias, desde, hasta)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/measurements/{idMedicion}", response_model=SharedMeasurementDetail,
            summary="Vista ampliada de una medición compartida",
            description="Vuelve a verificar la autorización: con historial compartido, cualquier medición completada de esa persona; con solo "
            "«última medición», únicamente la última.")
def sharedMeasurement(idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, idMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return groupService.sharedMeasurement(db, auth.user, idGrupo, idGrupoUsuario, idMedicion)


@router.get("/{idGrupo}/shared/{idGrupoUsuario}/statistics", response_model=SharedStatisticsRead,
            summary="Estadísticas compartidas", description="Solo agregados de 7, 30 o 90 días.")
def sharedStatistics(
    idGrupo: uuid.UUID, idGrupoUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession,
    dias: Annotated[int, Query()] = 30,
):
    return groupService.sharedStatistics(db, auth.user, idGrupo, idGrupoUsuario, dias)
