# Measurements - Rutas del módulo Medición (/api/v1/measurements)
#
# Solo traduce HTTP <-> servicios; la autorización (perfil propio u operador responsable), las transiciones de
# estado y las validaciones viven en backend/app/services/measurement.py. La identidad sale de la sesión.
# El historial de pacientes institucionales está en /institutions/{id}/patients/{perfil}/measurements.

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentAuth, DbSession
from app.schemas.dashboard import PersonalDashboard
from app.schemas.group import SharedStatisticsRead
from app.schemas.matrix import MatrixSummary
from app.schemas.resultDelivery import ResultSendRead, ResultSendRequest
from app.schemas.measurement import (
    CapillaryReferenceRequest,
    EvolutionRead,
    DeviceSummary,
    MeasurementDetail,
    MeasurementFinish,
    MeasurementPage,
    MeasurementStart,
    OwnProfileRead,
    SamplesRequest,
)
from app.services import dashboard as dashboardService
from app.services import measurement as measurementService

router = APIRouter(prefix="/measurements", tags=["measurements"])

Mode = Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"]
State = Literal["PENDIENTE", "ADQUIRIENDO", "PROCESANDO", "COMPLETADA", "INVALIDA", "CANCELADA"]
Origin = Literal["DEMO", "REAL"]


@router.get("/profile", response_model=OwnProfileRead, summary="Mi perfil de medición",
            description="Solo cuentas individuales. Lo crea desde los datos de la cuenta la primera vez; si faltan "
            "fecha de nacimiento o sexo, `perfilDisponible` es false y `datosFaltantes` los indica.")
def ownProfile(auth: CurrentAuth, db: DbSession):
    return measurementService.getOwnProfile(db, auth.user)


@router.get("/devices", response_model=list[DeviceSummary], summary="Dispositivos disponibles para medir un perfil",
            description="Dispositivos OPERATIVOS que puede usar quien opera ese perfil (solo lectura).")
def listDevices(idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return measurementService.listDevices(db, auth.user, idPerfilMedicion)


@router.get("/matrix", response_model=MatrixSummary | None, summary="Matriz que se aplicaría a una medición de glucosa",
            description="Informativo y decidido por el backend: la matriz activa de la institución del perfil o, si no "
            "tiene, la global (perfiles individuales: la global). No se puede elegir ni cambiar desde el cliente.")
def matrixPreview(idPerfilMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return measurementService.matrixPreview(db, auth.user, idPerfilMedicion)


@router.post("", response_model=MeasurementDetail, status_code=status.HTTP_201_CREATED, summary="Iniciar una medición",
             description="El consumidor final mide su propio perfil; un operador, los pacientes a su cargo. Estado "
             "inicial PENDIENTE. El servidor fija edad, sexo, firmware, sensor y, en glucosa experimental, la matriz; "
             "409 `SIN_REGLA_APLICABLE` si no hay una regla vigente aplicable.")
def startMeasurement(data: MeasurementStart, auth: CurrentAuth, db: DbSession):
    return measurementService.startMeasurement(db, auth.user, data)


@router.get("", response_model=MeasurementPage, summary="Mi historial de mediciones",
            description="Mediciones del perfil propio con filtros por fecha, modo y estado y orden cronológico.")
def ownHistory(
    auth: CurrentAuth, db: DbSession, desde: date | None = None, hasta: date | None = None, modo: Mode | None = None,
    estado: State | None = None, orden: Literal["asc", "desc"] = "desc",
    pagina: Annotated[int, Query(ge=1)] = 1, tamanioPagina: Annotated[int, Query(ge=1, le=50)] = 20,
    origen: Origin | None = None,
):
    return measurementService.listOwnHistory(db, auth.user, desde=desde, hasta=hasta, modo=modo, estado=estado,
                                             orden=orden, pagina=pagina, tamanioPagina=tamanioPagina, origen=origen)


@router.delete("/demo", summary="Eliminar mis datos de prueba (DEMO)",
               description="Elimina las mediciones DEMO completadas del perfil propio. No toca ninguna medición real. "
               "Devuelve cuántas se eliminaron.")
def deleteOwnDemo(auth: CurrentAuth, db: DbSession):
    return {"eliminadas": measurementService.deleteOwnDemoMeasurements(db, auth.user)}


@router.get("/statistics", response_model=SharedStatisticsRead, summary="Estadísticas de mis mediciones",
            description="Promedios, mínimos, máximos y serie diaria solo sobre mediciones COMPLETADA.")
def ownStatistics(auth: CurrentAuth, db: DbSession, dias: int = 30, desde: date | None = None,
                  hasta: date | None = None):
    return measurementService.ownStatistics(db, auth.user, dias, desde, hasta)


@router.get("/evolution", response_model=EvolutionRead, summary="Evolución histórica de mis mediciones",
            description="Cada medición completada es un punto (fecha, modo, origen y valores). Período: dias (1, 7, 14, 30 o 90) o "
            "desde/hasta. origen: EXPERIMENTAL (por defecto), DEMO o TODOS; las estadísticas de DEMO y experimentales van separadas.")
def ownEvolution(auth: CurrentAuth, db: DbSession, dias: int = 30, desde: date | None = None, hasta: date | None = None,
                 origen: str = "EXPERIMENTAL", modo: Literal["OXIMETRIA", "GLUCOSA_EXPERIMENTAL"] | None = None):
    return measurementService.ownEvolution(db, auth.user, dias, desde, hasta, origen, modo)


@router.get("/dashboard", response_model=PersonalDashboard, summary="Mi dashboard personal",
            description="Resumen, estadísticas del período y mediciones recientes de MI perfil, calculados sobre Medicion. "
            "Período: dias (7, 30 o 90) o desde/hasta.")
def personalDashboard(auth: CurrentAuth, db: DbSession, dias: int = 30, desde: date | None = None, hasta: date | None = None):
    return dashboardService.personalDashboard(db, auth.user, dias, desde, hasta)


@router.get("/{idMedicion}", response_model=MeasurementDetail, summary="Detalle y estado de una medición",
            description="Perfil propio, o paciente de la institución de la cuenta (CONSULTAR_PACIENTES). 404 si no "
            "corresponde.")
def getMeasurement(idMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return measurementService.getMeasurement(db, auth.user, idMedicion)


@router.delete("/{idMedicion}", summary="Eliminar una medición de prueba (DEMO)",
               description="Solo mediciones DEMO completadas que la cuenta puede operar. Una medición real responde 409 "
               "`DATO_NO_ELIMINABLE`: las mediciones reales no se eliminan.")
def deleteDemoMeasurement(idMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return {"eliminadas": measurementService.deleteDemoMeasurement(db, auth.user, idMedicion)}


@router.post("/{idMedicion}/samples", response_model=MeasurementDetail, summary="Registrar muestras del sensor",
             description="Muestras de los canales rojo e infrarrojo (MuestraSensor). La primera pasa la medición a "
             "ADQUIRIENDO. Solo quien opera el perfil.")
def addSamples(idMedicion: uuid.UUID, data: SamplesRequest, auth: CurrentAuth, db: DbSession):
    return measurementService.addSamples(db, auth.user, idMedicion, data)


@router.post("/{idMedicion}/finish", response_model=MeasurementDetail, summary="Finalizar y procesar la adquisición",
             description="ADQUIRIENDO → PROCESANDO → COMPLETADA o INVALIDA. La glucosa estimada nunca se recibe: la "
             "calcula el servidor con la matriz y su regla (INVALIDA si no hay algoritmo o regla).")
def finishMeasurement(idMedicion: uuid.UUID, data: MeasurementFinish, auth: CurrentAuth, db: DbSession):
    return measurementService.finishMeasurement(db, auth.user, idMedicion, data)


@router.post("/{idMedicion}/cancel", response_model=MeasurementDetail, summary="Cancelar una medición",
             description="Solo desde PENDIENTE o ADQUIRIENDO.")
def cancelMeasurement(idMedicion: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return measurementService.cancelMeasurement(db, auth.user, idMedicion)


@router.post("/{idMedicion}/capillary-reference", response_model=MeasurementDetail,
             status_code=status.HTTP_201_CREATED, summary="Registrar la referencia capilar",
             description="Valor real de un glucómetro capilar sobre una medición de glucosa COMPLETADA. Queda "
             "separado de la glucosa estimada; una sola por medición.")
def capillaryReference(idMedicion: uuid.UUID, data: CapillaryReferenceRequest, auth: CurrentAuth, db: DbSession):
    return measurementService.registerCapillaryReference(db, auth.user, idMedicion, data)


@router.post("/{idMedicion}/send-result", response_model=ResultSendRead, summary="Enviar el resultado por correo",
             description="Medición COMPLETADA. Cuenta individual: va a su propio correo. Paciente institucional: el "
             "operador a cargo indica el correo que el paciente informó y confirma su autorización (el correo no se guarda).")
def sendResult(idMedicion: uuid.UUID, data: ResultSendRequest, auth: CurrentAuth, db: DbSession):
    return measurementService.sendResultByEmail(db, auth.user, idMedicion, data)
