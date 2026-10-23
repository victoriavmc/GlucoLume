# Telemetry - Rutas de la telemetría procesada del dispositivo (/api/v1/acquisition/...)
#
# Solo traduce HTTP <-> app/services/telemetry.py. Dos clientes distintos:
#   - el PUENTE SERIE (acquisition/bridge, en el equipo con el Arduino): POST /bridge/ingest, autenticado con el token
#     compartido BRIDGE_TOKEN en el encabezado X-Bridge-Token (comparación en tiempo constante). Sin token configurado la
#     recepción queda deshabilitada (503). El puente nunca recibe datos de usuarios ni comandos para el Arduino.
#   - React, con la sesión del usuario (Bearer): estado, flujo en vivo (SSE), sesión de medición, guardar y cancelar.

import asyncio
import hmac
import json
import queue
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.acquisition.telemetry import hub
from app.api import rateLimit
from app.api.deps import CurrentAuth, DbSession, StreamAuth
from app.api.streams import Revalidator, openStreamSlot
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.db.session import getSessionFactory
from app.schemas.acquisition import (
    BridgeCheckRead,
    BridgeCheckRequest,
    BridgeCommandRequest,
    BridgeIngest,
    BridgeIngestRead,
    DeviceConnectConfirm,
    DeviceConnectLink,
    DeviceConnectRegister,
    DeviceConnectResult,
    TelemetryReadiness,
    TelemetrySessionStart,
    TelemetryStatus,
)
from app.schemas.measurement import MeasurementDetail
from app.services import deviceConnection
from app.services import telemetry as telemetryService
from app.services.acquisition import _requireMeasurer

router = APIRouter(prefix="/acquisition", tags=["acquisition-telemetry"])


def requireBridge(request: Request, token: Annotated[str | None, Header(alias="X-Bridge-Token")] = None) -> None:
    settings = getSettings()
    if settings.BRIDGE_TOKEN is None:
        raise AuthError("PUENTE_NO_CONFIGURADO", "La recepción de datos del puente serie no está habilitada en este servidor.")
    ip = rateLimit.clientIp(request)
    if rateLimit.bridgeFailures.exceeded(ip):
        raise AuthError("DEMASIADAS_SOLICITUDES", rateLimit.TOO_MANY_REQUESTS, retryAfterSeconds=rateLimit.BRIDGE_FAILURES[1],
                        motivo="bridgeAuth")
    accepted = [secret.get_secret_value().encode() for secret in settings.bridgeTokens]
    given = (token or "").encode()
    # Se comparan todos (sin cortar en el primero) para no revelar por tiempo cuál coincide.
    if not token or not any([hmac.compare_digest(given, secret) for secret in accepted]):
        rateLimit.bridgeFailures.allow(ip)
        raise AuthError("PUENTE_NO_AUTORIZADO", "El puente serie no está autorizado.")


@router.post("/bridge/ingest", response_model=BridgeIngestRead, summary="Recepción de lecturas del puente serie",
             description="Latido y líneas del firmware tal como las escribe el Arduino (hasta 200 por pedido). Idempotente: "
             "un `seq` ya recibido se cuenta como duplicado. Autenticado con X-Bridge-Token; no usa la sesión de un usuario. "
             "409 `PUENTE_DUPLICADO` si otro puente activo ya atiende el dispositivo.")
def ingest(data: BridgeIngest, db: DbSession, _: Annotated[None, Depends(requireBridge)]):
    return telemetryService.ingest(db, data)


@router.post("/bridge/check", response_model=BridgeCheckRead, summary="Comprobar un código de dispositivo (instalación del puente)",
             dependencies=[rateLimit.rateLimit("bridgeCheck")],
             description="Para la instalación del puente: indica si el código figura en el inventario y está operativo. Autenticado con "
             "X-Bridge-Token; no devuelve datos de personas.")
def bridgeCheck(data: BridgeCheckRequest, db: DbSession, _: Annotated[None, Depends(requireBridge)]):
    return telemetryService.check(db, data)


@router.post("/bridge/command", response_model=TelemetryStatus, summary="Pedir una orden al puente serie",
             description="Con la sesión del usuario (Bearer, cuentas que pueden medir). Solo acciones acotadas: CONFIGURAR (puerto que el "
             "propio puente informó + medio USB/BLUETOOTH), PAUSAR, REANUDAR, DETENER y REINICIAR. El backend no ejecuta nada local: deja "
             "la orden pendiente y el puente la toma en su próximo latido. No se admite durante una sesión de medición. Queda auditado.")
def bridgeCommand(data: BridgeCommandRequest, auth: CurrentAuth, db: DbSession):
    return telemetryService.command(db, auth.user, data)


@router.post("/telemetry/control", response_model=TelemetryStatus, summary="Tomar el control temporal del dispositivo («Usar dispositivo»)",
             description="Acción explícita y atómica: con el equipo libre lo controla una sola cuenta (DISPOSITIVO_EN_USO si otra lo tiene). "
             "Solo quien controla recibe las lecturas en vivo y da órdenes al puente. Sin medición vence a los 5 min de la última acción "
             "o a los 30 s sin consultar el estado; volver a pedirlo lo renueva. Quién puede tomarlo depende del modo de uso (DEC-01).")
def takeDeviceControl(auth: CurrentAuth, db: DbSession):
    return telemetryService.takeControl(db, auth.user)


@router.delete("/telemetry/control", response_model=TelemetryStatus, summary="Soltar el control del dispositivo («Dejar de usar»)",
               description="Libera el control sin medición para que otra cuenta habilitada pueda usar el equipo. Con una medición en curso "
               "responde SESION_EN_CURSO: se guarda o se cancela.")
def releaseDeviceControl(auth: CurrentAuth, db: DbSession):
    return telemetryService.releaseControl(db, auth.user)


@router.get("/telemetry/readiness", response_model=TelemetryReadiness, summary="¿Qué falta para poder medir?",
            description="Comprobaciones reales y ordenadas: puente, puerto abierto, telemetría reciente, sensor, dispositivo registrado y "
            "asociado al perfil. Un puerto COM abierto no alcanza para marcarlo como listo.")
def telemetryReadiness(auth: CurrentAuth, db: DbSession, idPerfilMedicion: uuid.UUID | None = None,
                       idInstitucion: uuid.UUID | None = None):
    return telemetryService.readiness(db, auth.user, idPerfilMedicion, idInstitucion)


@router.post("/telemetry/device/register", response_model=DeviceConnectResult, status_code=status.HTTP_201_CREATED,
             summary="Registrar el dispositivo conectado en la institución del operador",
             description="Primera conexión: con comunicación verificada y el ID propio del Arduino, un OPERADOR de la institución lo registra "
             "(queda en su inventario, a cargo del propietario vigente). Idempotente: si ya estaba registrado en esa institución se devuelve "
             "el mismo (`creado: false`) y no se duplica. 403/404 si no es operador de la institución; 409 `DISPOSITIVO_NO_DISPONIBLE` si "
             "pertenece a otra institución o no tiene institución (en ese caso se vincula con `/device/link`); 409 `IDENTIDAD_NO_CONFIRMADA` sin ID "
             "propio salvo `confirmaIdentidad: true`.")
def registerConnectedDevice(data: DeviceConnectRegister, auth: CurrentAuth, db: DbSession):
    return deviceConnection.register(db, auth.user, data)


@router.post("/telemetry/device/link", response_model=DeviceConnectResult,
             summary="Vincular a la institución un dispositivo existente que no tiene institución",
             description="Un OPERADOR de la institución, con el Arduino conectado y verificado, pasa al inventario de su institución un dispositivo que existía "
             "sin institución (p. ej. el que dio de alta el puente). Exige `confirmaVinculacion: true`; con firmware sin ID propio también "
             "`confirmaIdentidad: true`. Queda a cargo del propietario, deja de estar disponible para cuentas individuales y conserva sus "
             "mediciones. Nunca toca uno de otra institución (404) ni uno descomisionado. Idempotente.")
def linkConnectedDevice(data: DeviceConnectLink, auth: CurrentAuth, db: DbSession):
    return deviceConnection.link(db, auth.user, data)


@router.post("/telemetry/device/confirm", response_model=DeviceConnectResult,
             summary="Seleccionar y confirmar el dispositivo existente de la conexión actual",
             description="Con ID propio solo se acepta el dispositivo que el Arduino informó. Sin él (firmware anterior) el operador confirma "
             "a mano cuál es; vale para esta conexión y queda auditado. No asocia ningún paciente.")
def confirmConnectedDevice(data: DeviceConnectConfirm, auth: CurrentAuth, db: DbSession):
    return deviceConnection.confirm(db, auth.user, data)


@router.get("/telemetry/status", response_model=TelemetryStatus, summary="Estado del dispositivo y última lectura",
            description="SIN_PUENTE · PUERTO_DESCONECTADO (Bluetooth/USB sin conexión) · SIN_DATOS · CONECTADO. Solo cuentas "
            "que pueden medir. Si otra cuenta tiene una sesión en curso, `ocupado` es true y no se devuelven lecturas.")
def telemetryStatus(auth: CurrentAuth, db: DbSession):
    return telemetryService.status(db, auth.user)


def _checkMeasurer(actor) -> None:
    db = getSessionFactory()()
    try:
        _requireMeasurer(db, actor)
    finally:
        db.close()


@router.get("/telemetry/stream", summary="Estado y lecturas en tiempo real (SSE)",
            description="Un evento `estado` con el mismo contenido que /telemetry/status cada vez que llega una lectura o "
            "cambia la conexión (y al menos cada 2 s). Misma autenticación Bearer que el resto de la API.")
async def telemetryStream(request: Request, auth: StreamAuth):
    actor = auth.user
    userId = actor.idUsuario
    slot = openStreamSlot(userId)  # 429 si la cuenta o el servidor superan el tope de streams
    try:
        await run_in_threadpool(_checkMeasurer, actor)
        channel = hub.subscribe(userId)
    except BaseException:
        slot.release()
        raise
    revalidator = Revalidator(userId, auth.session.idSesion)

    def frame() -> str:
        return f"data: {json.dumps({'tipo': 'estado', **hub.snapshot(userId)}, default=str)}\n\n"

    async def events():
        try:
            yield frame()
            idle = 0
            while not await request.is_disconnected():
                if not await revalidator.stillAuthorized():
                    break  # sesión revocada, vencida o cuenta no activa
                woke = False
                try:
                    while True:  # vacía la cola: una ráfaga de eventos produce un solo cuadro
                        channel.get_nowait()
                        woke = True
                except queue.Empty:
                    pass
                idle += 1
                if woke or idle % 10 == 0:  # 10 × 0,2 s = 2 s
                    yield frame()
                elif idle % 75 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
        finally:
            hub.unsubscribe(channel)
            slot.release()

    return StreamingResponse(events(), media_type="text/event-stream", background=BackgroundTask(slot.release),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/telemetry/session", response_model=MeasurementDetail, status_code=status.HTTP_201_CREATED,
             summary="Iniciar una sesión de medición con el dispositivo",
             description="Crea la medición (oximetría + datos del dispositivo, estado ADQUIRIENDO) para un perfil que la "
             "cuenta puede operar y reserva el dispositivo para esta cuenta. El dispositivo elegido debe ser el que atiende "
             "el puente. Solo se atribuyen a la sesión las lecturas posteriores a este momento.")
def startSession(data: TelemetrySessionStart, auth: CurrentAuth, db: DbSession):
    return telemetryService.startSession(db, auth.user, data)


@router.post("/telemetry/session/save", response_model=MeasurementDetail, summary="Guardar la medición",
             description="Toma una lectura estabilizada de la sesión (mediana de las últimas 8 lecturas consecutivas válidas "
             "con poca variación), completa la medición en una transacción y libera el dispositivo. 409 `LECTURA_NO_ESTABLE` "
             "si falta dedo, señal válida o estabilidad.")
def saveSession(auth: CurrentAuth, db: DbSession):
    return telemetryService.saveSession(db, auth.user)


@router.post("/telemetry/session/cancel", response_model=MeasurementDetail, summary="Cancelar la sesión de medición",
             description="Cancela la medición en curso y libera el dispositivo. No guarda lecturas.")
def cancelSession(auth: CurrentAuth, db: DbSession):
    return telemetryService.cancelSession(db, auth.user)
