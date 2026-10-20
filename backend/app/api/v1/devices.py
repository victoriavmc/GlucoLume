# Devices - Rutas del inventario de dispositivos
#   /api/v1/devices                          inventario global (cuentas de plataforma) y resolución durante la adquisición
#   /api/v1/institutions/{id}/devices        inventario de una institución (sus integrantes, según su rol)
# Solo traducen HTTP <-> servicios. Los permisos, el aislamiento por institución y las reglas de estado y asignación
# viven en backend/app/services/device.py. Ninguna ruta elimina dispositivos: el retiro es el estado BAJA.

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentAuth, DbSession, PlatformMfaGate
from app.schemas.device import (
    DeviceAssignRequest,
    DeviceDetail,
    DeviceEditRequest,
    DeviceInstitutionOption,
    DeviceMeasurementPage,
    DevicePage,
    DeviceRegisterRequest,
    DeviceResolveRequest,
    DeviceResolveResult,
    DeviceResponsible,
    DeviceResponsibleRequest,
    DeviceStateRequest,
    DeviceSummaryCounts,
)
from app.services import device as deviceService

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[PlatformMfaGate])
institutionRouter = APIRouter(prefix="/institutions/{idInstitucion}/devices", tags=["devices"])

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=deviceService.MAX_PAGE_SIZE)]


# --- Identificación durante la adquisición ---------------------------------------------------------------------


@router.post("/resolve", response_model=DeviceResolveResult, summary="Resolver el dispositivo al conectarse",
             description="Lo usa el servicio de adquisición con el identificador PROPIO del dispositivo (nunca el puerto "
             "COM). Reutiliza el registro existente; si no existe, lo registra solo si el contexto lo autoriza. No "
             "afirma que esté conectado.")
def resolveDevice(data: DeviceResolveRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.resolveDevice(db, auth.user, data)


# --- Inventario global (plataforma) ------------------------------------------------------------------------------


@router.get("", response_model=DevicePage, summary="Inventario global",
            description="Administrador del sistema y moderación de plataforma. Búsqueda, filtros y paginación en SQL.")
def listGlobal(auth: CurrentAuth, db: DbSession, busqueda: str | None = None, estado: str | None = None,
               asignado: bool | None = None, idInstitucion: uuid.UUID | None = None, pagina: PageNumber = 1,
               tamanioPagina: PageSize = 20):
    scope = deviceService.platformScope(db, auth.user)
    return deviceService.listDevices(db, scope, busqueda=busqueda, estado=estado, asignado=asignado,
                                     idInstitucion=idInstitucion, pagina=pagina, tamanioPagina=tamanioPagina)


@router.get("/summary", response_model=DeviceSummaryCounts, summary="Indicadores del inventario global")
def summaryGlobal(auth: CurrentAuth, db: DbSession, idInstitucion: uuid.UUID | None = None):
    return deviceService.summary(db, deviceService.platformScope(db, auth.user), idInstitucion=idInstitucion)


@router.post("", response_model=DeviceDetail, status_code=status.HTTP_201_CREATED, summary="Registrar un dispositivo",
             description="409 `DISPOSITIVO_DUPLICADO` si el código ya existe. Asignarlo a una institución en el alta es "
             "solo del administrador del sistema.")
def registerGlobal(data: DeviceRegisterRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.registerDevice(db, deviceService.platformScope(db, auth.user), data)


@router.get("/institutions", response_model=list[DeviceInstitutionOption], summary="Instituciones donde asignar",
            description="Solo el administrador del sistema: instituciones activas (búsqueda por nombre, hasta 50).")
def institutionOptions(auth: CurrentAuth, db: DbSession, busqueda: str | None = None):
    return deviceService.institutionOptions(db, deviceService.platformScope(db, auth.user), busqueda)


@router.get("/institutions/{idInstitucion}/responsibles", response_model=list[DeviceResponsible],
            summary="Integrantes activos de una institución", description="Solo el administrador del sistema.")
def institutionResponsibles(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.responsiblesOf(db, deviceService.platformScope(db, auth.user), idInstitucion)


@router.get("/{idDispositivo}", response_model=DeviceDetail, summary="Detalle de un dispositivo")
def getGlobal(idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.getDevice(db, deviceService.platformScope(db, auth.user), idDispositivo)


@router.patch("/{idDispositivo}", response_model=DeviceDetail, summary="Modificar datos de un dispositivo")
def editGlobal(idDispositivo: uuid.UUID, data: DeviceEditRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.editDevice(db, deviceService.platformScope(db, auth.user), idDispositivo, data)


@router.post("/{idDispositivo}/state", response_model=DeviceDetail, summary="Cambiar el estado operativo",
             description="OPERATIVO, EN_MANTENIMIENTO o FUERA_DE_SERVICIO. El retiro definitivo es `/decommission`.")
def stateGlobal(idDispositivo: uuid.UUID, data: DeviceStateRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.changeState(db, deviceService.platformScope(db, auth.user), idDispositivo, data.estado, data.motivo)


@router.post("/{idDispositivo}/assign", response_model=DeviceDetail, summary="Asignar a una institución",
             description="Solo el administrador del sistema. Institución activa y responsable activo de esa institución.")
def assignGlobal(idDispositivo: uuid.UUID, data: DeviceAssignRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.assignInstitution(db, deviceService.platformScope(db, auth.user), idDispositivo, data)


@router.post("/{idDispositivo}/responsible", response_model=DeviceDetail, summary="Cambiar el responsable")
def responsibleGlobal(idDispositivo: uuid.UUID, data: DeviceResponsibleRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.changeResponsible(db, deviceService.platformScope(db, auth.user), idDispositivo,
                                           data.idInstitucionUsuarioResponsable)


@router.post("/{idDispositivo}/unassign", response_model=DeviceDetail, summary="Desvincular de la institución",
             description="Conserva el dispositivo y sus mediciones. 409 si tiene mediciones en curso.")
def unassignGlobal(idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.unassign(db, deviceService.platformScope(db, auth.user), idDispositivo)


@router.post("/{idDispositivo}/decommission", response_model=DeviceDetail, summary="Descomisionar",
             description="Solo el administrador del sistema. Desvincula y pasa a BAJA en una transacción; conserva el "
             "registro y las mediciones.")
def decommissionGlobal(idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.decommission(db, deviceService.platformScope(db, auth.user), idDispositivo)


@router.get("/{idDispositivo}/measurements", response_model=DeviceMeasurementPage, summary="Mediciones hechas con el dispositivo",
            description="Sin datos del paciente. Firmware y sensor son los de cada medición.")
def measurementsGlobal(idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession, pagina: PageNumber = 1,
                       tamanioPagina: PageSize = 20):
    return deviceService.listMeasurements(db, deviceService.platformScope(db, auth.user), idDispositivo, pagina, tamanioPagina)


# --- Inventario institucional --------------------------------------------------------------------------------


@institutionRouter.get("", response_model=DevicePage, summary="Inventario de la institución",
                       description="404 si la cuenta no pertenece a la institución. El operador ve solo los dispositivos "
                       "operativos que puede usar, con datos técnicos mínimos.")
def listInstitution(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, busqueda: str | None = None,
                    estado: str | None = None, asignado: bool | None = None, pagina: PageNumber = 1,
                    tamanioPagina: PageSize = 20):
    scope = deviceService.institutionScope(db, auth.user, idInstitucion)
    return deviceService.listDevices(db, scope, busqueda=busqueda, estado=estado, asignado=asignado, pagina=pagina,
                                     tamanioPagina=tamanioPagina)


@institutionRouter.get("/summary", response_model=DeviceSummaryCounts, summary="Indicadores del inventario de la institución")
def summaryInstitution(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.summary(db, deviceService.institutionScope(db, auth.user, idInstitucion))


@institutionRouter.get("/responsibles", response_model=list[DeviceResponsible], summary="Posibles responsables",
                       description="Integrantes activos de la institución. Propietario y moderador.")
def responsibles(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.listResponsibles(db, deviceService.institutionScope(db, auth.user, idInstitucion))


@institutionRouter.post("", response_model=DeviceDetail, status_code=status.HTTP_201_CREATED,
                        summary="Registrar un dispositivo de la institución",
                        description="Propietario y moderador. Queda asignado a esta institución; el responsable debe ser "
                        "un integrante activo de ella.")
def registerInstitution(idInstitucion: uuid.UUID, data: DeviceRegisterRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.registerDevice(db, deviceService.institutionScope(db, auth.user, idInstitucion), data)


@institutionRouter.get("/{idDispositivo}", response_model=DeviceDetail, summary="Detalle de un dispositivo de la institución",
                       description="404 si el dispositivo no está asignado a esta institución.")
def getInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.getDevice(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo)


@institutionRouter.patch("/{idDispositivo}", response_model=DeviceDetail, summary="Modificar un dispositivo de la institución")
def editInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, data: DeviceEditRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.editDevice(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo, data)


@institutionRouter.post("/{idDispositivo}/state", response_model=DeviceDetail, summary="Cambiar el estado operativo")
def stateInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, data: DeviceStateRequest, auth: CurrentAuth, db: DbSession):
    return deviceService.changeState(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo,
                                     data.estado, data.motivo)


@institutionRouter.post("/{idDispositivo}/responsible", response_model=DeviceDetail, summary="Cambiar el responsable",
                        description="Propietario y moderador. El responsable debe ser integrante activo de la misma institución.")
def responsibleInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, data: DeviceResponsibleRequest,
                           auth: CurrentAuth, db: DbSession):
    return deviceService.changeResponsible(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo,
                                           data.idInstitucionUsuarioResponsable)


@institutionRouter.post("/{idDispositivo}/unassign", response_model=DeviceDetail, summary="Desvincular de la institución",
                        description="Solo el propietario. El dispositivo y sus mediciones se conservan.")
def unassignInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.unassign(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo)


@institutionRouter.post("/{idDispositivo}/decommission", response_model=DeviceDetail, summary="Descomisionar",
                        description="Solo el propietario. Desvincula y retira definitivamente; conserva las mediciones.")
def decommissionInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return deviceService.decommission(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo)


@institutionRouter.get("/{idDispositivo}/measurements", response_model=DeviceMeasurementPage,
                       summary="Mediciones de pacientes de esta institución hechas con el dispositivo")
def measurementsInstitution(idInstitucion: uuid.UUID, idDispositivo: uuid.UUID, auth: CurrentAuth, db: DbSession,
                            pagina: PageNumber = 1, tamanioPagina: PageSize = 20):
    return deviceService.listMeasurements(db, deviceService.institutionScope(db, auth.user, idInstitucion), idDispositivo,
                                          pagina, tamanioPagina)
