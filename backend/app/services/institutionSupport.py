# InstitutionSupport - Consulta del propietario de una institución PAUSADA al soporte de GlucoLume
#
# Una institución pausada no permite operar (requireMembership responde INSTITUCION_PAUSADA), pero su propietario necesita poder pedir ayuda. Este es el
# ÚNICO contexto institucional que sigue abierto durante la pausa, y es mínimo: solo el propietario, solo si la institución está pausada, y lo único
# que hace es enviar un correo por el servicio de contacto existente (CONTACT_EMAIL; Reply-To el correo de la cuenta). No lee ni modifica datos de
# la institución. Queda un evento de auditoría (sin el texto del mensaje) que la plataforma ve en la auditoría de la institución.

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.contact import ContactRequest
from app.schemas.institution import SupportRequest
from app.services import contact as contactService
from app.services import platformInstitutions
from app.services.audit import registerEvent

ACTION = "SOLICITAR_SOPORTE_INSTITUCION"
# Límite por cuenta (además del límite por IP del servicio de contacto): evita usar la casilla de soporte para enviar en masa.
_limiter = contactService.RateLimiter(3, 60 * 60)
SUBJECT_PREFIX = "[Institución pausada] "


def requestSupport(db: Session, actor: User, idInstitucion: uuid.UUID, data: SupportRequest, clientIp: str | None) -> bool:
    """Envía la consulta. Devuelve si además se envió la confirmación al correo del propietario."""
    institution = db.get(Institution, idInstitucion)
    isOwner = institution is not None and db.scalar(select(InstitutionUser.idInstitucionUsuario).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.idUsuarioInvitado == actor.idUsuario,
        InstitutionUser.rolInstitucion == "PROPIETARIO", InstitutionUser.estadoRelacion == "ACTIVO")) is not None
    if not isOwner:  # no se revela si la institución existe
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución entre las tuyas.")
    if institution.estado != "INACTIVA":
        raise AuthError("INSTITUCION_NO_PAUSADA", "Esta consulta es solo para instituciones pausadas. Si tu institución está activa, usá el formulario de contacto.")
    if not _limiter.allow(str(actor.idUsuario)):
        raise AuthError("DEMASIADAS_SOLICITUDES", "Enviaste varias consultas seguidas. Esperá un rato antes de volver a escribir al soporte.")
    suspension = platformInstitutions.currentSuspension(db, institution)
    context = [f"Institución: {institution.nombre}", f"{institution.tipoIdentificadorLegal}: {institution.identificadorLegal}",
               f"Id: {institution.idInstitucion}", "Estado: pausada"]
    if suspension and suspension.motivo:
        context.append(f"Motivo registrado de la pausa: {suspension.motivo}")
    request = ContactRequest(
        nombre=f"{actor.nombre} {actor.apellido}".strip(), email=actor.correoElectronico, tipoConsulta="INSTITUCIONES",
        asunto=SUBJECT_PREFIX + data.asunto, mensaje=data.mensaje + "\n\n— Datos de la institución —\n" + "\n".join(context))
    confirmed = contactService.sendContactMessage(request, clientIp)  # lanza 503 si la consulta no pudo salir
    registerEvent(db, "ACCESO", ACTION, True, actor.idUsuario, "Institucion", idInstitucion, idInstitucion=idInstitucion, modulo="INSTITUCIONES",
                  observacion="Consulta del propietario al soporte", datosNuevos={"estado": institution.estado})
    db.commit()
    return confirmed
