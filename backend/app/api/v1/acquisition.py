# Acquisition - Rutas de la conexión con el Arduino (/api/v1/acquisition)
#
# Solo traduce HTTP <-> app/services/acquisition.py. El puerto lo abre el backend (pySerial) en el equipo con acceso
# físico al dispositivo; React solo usa estas rutas. Las muestras se guardan en la medición (MuestraSensor) y el resultado
# se consulta con GET /measurements/{id}. El avance llega por SSE (GET /stream), con la misma autenticación Bearer.

import asyncio
import json
import queue

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.acquisition.link import link
from app.api.deps import CurrentAuth, DbSession, StreamAuth
from app.api.streams import Revalidator, openStreamSlot
from app.schemas.acquisition import ConnectRequest, LinkStatus, PortRead, ProbeRead, StartRequest
from app.schemas.measurement import MeasurementDetail
from app.services import acquisition as acquisitionService

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.get("/ports", response_model=list[PortRead], summary="Puertos serie disponibles",
            description="USB y puertos COM virtuales del HC-06 (emparejado antes con el sistema operativo). No asume COM3 ni COM4.")
def listPorts(auth: CurrentAuth, db: DbSession):
    return acquisitionService.listPorts(db, auth.user)


@router.get("/status", response_model=LinkStatus, summary="Estado del enlace con el Arduino")
def status(auth: CurrentAuth):
    return acquisitionService.status(auth.user)


@router.post("/connect", response_model=LinkStatus, summary="Conectar un puerto",
             description="Abre el puerto (USB 115200 baudios, Bluetooth HC-06 9600 por defecto). 409 si está ocupado.")
def connect(data: ConnectRequest, auth: CurrentAuth, db: DbSession):
    return acquisitionService.connect(db, auth.user, data)


@router.post("/disconnect", response_model=LinkStatus, summary="Desconectar y liberar el puerto")
def disconnect(auth: CurrentAuth, db: DbSession):
    return acquisitionService.disconnect(db, auth.user)


@router.post("/probe", response_model=ProbeRead, summary="Probar la comunicación (PING)")
def probe(auth: CurrentAuth, db: DbSession):
    return ProbeRead(latenciaMs=acquisitionService.probe(db, auth.user))


@router.post("/identify", response_model=LinkStatus, summary="Identificar el dispositivo conectado",
             description="Pide al Arduino su identificador, el sensor (MAX30100/MAX30102) y la versión del firmware.")
def identify(auth: CurrentAuth, db: DbSession):
    return acquisitionService.identify(db, auth.user)


@router.post("/start", response_model=LinkStatus, summary="Iniciar la adquisición de una medición",
             description="La medición debe estar PENDIENTE y el Arduino conectado debe ser el dispositivo elegido.")
def start(data: StartRequest, auth: CurrentAuth, db: DbSession):
    return acquisitionService.start(db, auth.user, data.idMedicion)


@router.post("/finish", response_model=MeasurementDetail, summary="Finalizar y procesar",
             description="Detiene el Arduino, guarda las muestras y calcula SpO₂ y frecuencia cardíaca en el servidor.")
def finish(auth: CurrentAuth, db: DbSession):
    return acquisitionService.finish(db, auth.user)


@router.post("/cancel", response_model=MeasurementDetail, summary="Cancelar la adquisición")
def cancel(auth: CurrentAuth, db: DbSession):
    return acquisitionService.cancel(db, auth.user)


@router.get("/stream", summary="Avance en tiempo real (SSE)",
            description="Eventos: conexion, estadoDispositivo, muestra, indicadores (provisorios), error, fin, resultado.")
async def stream(request: Request, auth: StreamAuth):
    userId = auth.user.idUsuario
    slot = openStreamSlot(userId)  # 429 si la cuenta o el servidor superan el tope de streams
    try:
        snapshot = acquisitionService.status(auth.user)
        channel = link.subscribe()
    except BaseException:
        slot.release()
        raise
    revalidator = Revalidator(userId, auth.session.idSesion)

    async def events():
        try:
            yield f"data: {json.dumps({'tipo': 'estado', **snapshot}, default=str)}\n\n"
            idle = 0
            while not await request.is_disconnected():
                if not await revalidator.stillAuthorized():
                    break  # sesión revocada, vencida o cuenta no activa
                try:
                    event = channel.get_nowait()
                except queue.Empty:
                    idle += 1
                    if idle % 75 == 0:
                        yield ": keep-alive\n\n"
                    await asyncio.sleep(0.2)
                    continue
                idle = 0
                # Solo el dueño del enlace recibe el avance (muestras, indicadores); los demás, nada.
                if link.owner == userId or (event.get("tipo") == "conexion" and not event.get("conectado")):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            link.unsubscribe(channel)
            slot.release()

    # `background`: si el cliente se va antes de que el generador arranque, el cupo igualmente se libera (release es idempotente).
    return StreamingResponse(events(), media_type="text/event-stream", background=BackgroundTask(slot.release),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
