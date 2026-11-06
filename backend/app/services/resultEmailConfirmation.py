# ResultEmailConfirmation - Confirmación del destinatario de los resultados de un paciente institucional (GL-08)
#
# Un operador no puede hacer que se envíen resultados de salud a una dirección que el propio destinatario no confirmó. Cargar el correo del
# paciente, o pedir un envío puntual a una dirección que no es la confirmada, solo dispara un correo con un enlace firmado (72 h, propósito
# único). Al abrirlo, el paciente confirma con un botón (nunca al cargar la página, para que un escáner de enlaces no confirme solo):
#   - correo para los envíos automáticos: recién entonces se guarda (12 meses desde la confirmación) y empieza a recibir resultados;
#   - envío puntual: se envía ESE resultado y la dirección no se guarda.
# No hay columnas nuevas: el enlace lleva el pedido firmado con la clave del servidor (perfil, institución, correo, operador y, si
# corresponde, la medición). Repetir el enlace no vuelve a enviar nada: ya confirmado, no hace nada (idempotente).

import logging
import uuid
from datetime import datetime, timedelta

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.emails.formatting import maskEmail
from app.models.institution import Institution
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.resultDelivery import ResultDelivery
from app.models.user import User
from app.services import email as emailService
from app.services import resultEmailStore
from app.services.audit import registerEvent
from app.services.rateLimiter import RateLimiter
from app.utils.timeZone import ARGENTINA_TZ, nowForDb

TOKEN_TYPE = "confirmar_correo_resultados"
VALID_HOURS = 72
FRONTEND_ROUTE = "/confirmar-correo-resultados"
# Pedidos de confirmación por operador: evita usar el sistema para enviar correos en masa a direcciones arbitrarias.
_requests = RateLimiter(10, 60 * 60, name="correo-resultados:pedidos")

INVALID = "El enlace no es válido o venció. Pedile al operador que te lo envíe de nuevo."
logger = logging.getLogger(__name__)


def resetLimits() -> None:
    _requests._events.clear()


def requestConfirmation(db: Session, actor: User, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, email: str, *,
                        keep: bool, idMedicion: uuid.UUID | None = None) -> None:
    """Pide la confirmación: el correo sale en segundo plano (la solicitud no espera al servidor de correo). `keep`: guardar el correo
    para los envíos automáticos; `idMedicion`: resultado a enviar al confirmar. Un fallo del envío no se devuelve a quien pidió: queda
    en la auditoría (SOLICITAR_CONFIRMACION_CORREO_RESULTADOS, resultado FALLO) y el operador puede volver a pedirla."""
    if not _requests.allow(str(actor.idUsuario)):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Pediste muchas confirmaciones de correo seguidas. Probá de nuevo en una hora.")
    # Un buzón que no existe nunca recibe el enlace: se rechaza ya, en la solicitud, y no como un «enviando…» que después no llega.
    # Igual que en el registro: solo NO_EXISTE rechaza; si el servidor no se puede consultar, la solicitud sigue.
    emailService.requireMailboxExists(email)
    claims = {"sub":str(idPerfilMedicion), "typ": TOKEN_TYPE, "inst": str(idInstitucion), "mail": email, "op": str(actor.idUsuario),
              "keep": keep, "med": str(idMedicion) if idMedicion else None, "jti": uuid.uuid4().hex}
    token = security.encodeScopedToken(claims, timedelta(hours=VALID_HOURS))
    institution = db.get(Institution, idInstitucion)
    context = {"institucion": institution.nombre if institution else "GlucoLume", "horas": VALID_HOURS,
               "guardaCorreo": keep, "incluyeResultado": idMedicion is not None,
               "urlConfirmacion": emailService.frontendUrl(FRONTEND_ROUTE) + f"#token={token}"}
    actorId = actor.idUsuario
    db.commit()  # el SMTP corre fuera de la transacción de la solicitud
    emailService.runInBackground(_sendConfirmation, db.get_bind(), actorId, idPerfilMedicion, email, keep, idMedicion is not None, context)


def _sendConfirmation(bind, idUsuario: uuid.UUID, idPerfilMedicion: uuid.UUID, email: str, keep: bool, conResultado: bool,
                      context: dict) -> None:
    """Hilo auxiliar: envía el correo y anota el pedido con una sesión propia (no comparte la de la solicitud)."""
    try:
        sent = emailService.sendEmailEvent(EmailEventType.CONFIRMAR_CORREO_RESULTADOS, email, context)
    except Exception:  # noqa: BLE001 - un dato inválido se anota como fallido, no deja el hilo caído
        sent = False
    try:
        with Session(bind) as session:
            registerEvent(session, "CRUD", "SOLICITAR_CONFIRMACION_CORREO_RESULTADOS", sent, idUsuario, "PerfilMedicion", idPerfilMedicion,
                          datosNuevos={"guardaCorreo": keep, "conResultado": conResultado})
            session.commit()
    except Exception as error:  # noqa: BLE001 - el correo ya salió o falló; solo se pierde el rastro
        logger.error("No se pudo anotar el pedido de confirmación (%s).", type(error).__name__)


def _issuedAt(claims: dict) -> datetime:
    return datetime.fromtimestamp(claims["iat"], tz=ARGENTINA_TZ).replace(tzinfo=None)


def confirm(db: Session, token: str) -> dict:
    """El paciente confirma desde el enlace. Guarda el correo (si se pidió) y envía el resultado pendiente (si lo había y quien lo pidió
    todavía puede enviarlo). Idempotente."""
    try:
        claims = security.decodeScopedToken(token, TOKEN_TYPE)
        idPerfilMedicion, idInstitucion, operatorId = uuid.UUID(claims["sub"]), uuid.UUID(claims["inst"]), uuid.UUID(claims["op"])
        email = str(claims["mail"])
        idMedicion = uuid.UUID(claims["med"]) if claims.get("med") else None
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as error:
        raise AuthError("ENLACE_INVALIDO", INVALID) from error
    profile = db.get(MeasurementProfile, idPerfilMedicion)
    if profile is None or profile.fechaExpiracionDatosPersonales is not None or profile.fechaDepuracionDatosPersonales is not None:
        raise AuthError("ENLACE_INVALIDO", INVALID)  # paciente dado de baja o depurado: ya no recibe nada
    issued = _issuedAt(claims)
    stored = False
    if claims.get("keep"):
        if not resultEmailStore.ready(db):
            raise AuthError("ESQUEMA_DESACTUALIZADO", "Por ahora no se pueden guardar correos para recibir resultados.")
        current = resultEmailStore.authorization(db, idPerfilMedicion)
        if current is None or current[0].lower() != email.lower() or current[1] < issued:
            from app.services import institution as institutions

            now = nowForDb()
            resultEmailStore.save(db, idPerfilMedicion, email, now, institutions.addMonths(now, resultEmailStore.RETENTION_MONTHS))
            registerEvent(db, "CRUD", "CAMBIAR_CORREO_RESULTADOS_PACIENTE" if current else "CARGAR_CORREO_RESULTADOS_PACIENTE", True,
                          operatorId, "PerfilMedicion", idPerfilMedicion, datosNuevos={"confirmadoPorDestinatario": True})
            db.commit()
            stored = True
    pending = _sendPending(db, operatorId, idInstitucion, idPerfilMedicion, idMedicion, email, issued) if idMedicion else False
    return {"confirmado": True, "correoEnmascarado": maskEmail(email), "correoGuardado": stored, "resultadoEnCamino": pending}


def _sendPending(db: Session, operatorId: uuid.UUID, idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID, idMedicion: uuid.UUID,
                 email: str, issued: datetime) -> bool:
    """Encola el resultado pendiente (en segundo plano). Devuelve si quedó encolado; el resultado sale después."""
    from app.services import measurement as measurements

    operator = db.get(User, operatorId)
    measurement = db.get(Measurement, idMedicion)
    if operator is None or measurement is None or measurement.idPerfilMedicion != idPerfilMedicion:
        return False
    # ENVIADO o PENDIENTE: un doble clic en el enlace no encola dos veces el mismo resultado.
    already = db.scalar(select(func.count()).select_from(ResultDelivery).where(
        ResultDelivery.idMedicion == idMedicion, ResultDelivery.estadoEnvio.in_(("ENVIADO", "PENDIENTE")),
        ResultDelivery.fechaSolicitud >= issued))
    if already:
        return False  # el enlace ya se usó (o el resultado ya salió o está saliendo después del pedido): no se reenvía
    try:
        measurement, access = measurements._measurementAccess(db, operator, idMedicion)  # quien lo pidió debe seguir siendo responsable
        measurements._requireOperate(access)
    except AuthError:
        return False
    if access.idInstitucion != idInstitucion or measurement.estadoMedicion != measurements.COMPLETADA:
        return False
    measurements._queueResult(db, operator, measurement, access, email, modo="MANUAL", avisar=False)
    return True
