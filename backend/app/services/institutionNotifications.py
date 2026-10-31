# InstitutionNotifications - Avisos de la bandeja sobre la gestión de una institución, según el rol de quien los recibe.
#
# Se disparan después del commit del hecho, igual que sus correos (institution.py, institutionPatients.py, profileTransfers.py). A quién llega:
#   - alta o baja de operador y de moderador: propietarios y moderadores (menos quien lo hizo y la persona afectada);
#   - paciente nuevo: propietarios y moderadores (menos quien lo registró);
#   - paciente a cargo: el operador responsable nuevo (menos quien hizo el cambio);
#   - solicitud de paciente: el operador destino; su resultado (aceptada o rechazada), el operador de origen.
# Nunca incluyen datos del paciente: solo su identificador seudónimo. Cada aviso lo guarda userNotifications.notify, que respeta las
# preferencias de la cuenta y nunca propaga errores (el hecho que avisa ya está confirmado).

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurementProfile import MeasurementProfile
from app.models.notificationEvents import (
    INSTITUCION_MODERADOR_BAJA,
    INSTITUCION_MODERADOR_NUEVO,
    INSTITUCION_OPERADOR_BAJA,
    INSTITUCION_OPERADOR_NUEVO,
    INSTITUCION_PACIENTE_A_CARGO,
    INSTITUCION_PACIENTE_NUEVO,
    INSTITUCION_SOLICITUD_ACEPTADA,
    INSTITUCION_SOLICITUD_NUEVA,
    INSTITUCION_SOLICITUD_RECHAZADA,
)
from app.models.user import User
from app.services import userNotifications

ROL_PROPIETARIO = "PROPIETARIO"
ROL_MODERADOR = "MODERADOR"
ROL_OPERADOR = "OPERADOR"
RELACION_ACTIVO = "ACTIVO"
ROLES_GESTION = (ROL_PROPIETARIO, ROL_MODERADOR)
ETIQUETA_ROL = {ROL_OPERADOR: "operador", ROL_MODERADOR: "moderador"}


def _name(user: User | None) -> str:
    return f"{user.nombre or ''} {user.apellido or ''}".strip() if user else "Una persona"


def _patientId(profile: MeasurementProfile) -> str:
    return profile.identificadorPseudonimo or "sin identificador"


def _institutionUrl(idInstitucion: uuid.UUID) -> str:
    return f"{userNotifications.URL_INSTITUCIONES}/{idInstitucion}"


def _patientUrl(idInstitucion: uuid.UUID, idPerfilMedicion: uuid.UUID) -> str:
    return f"{_institutionUrl(idInstitucion)}/pacientes/{idPerfilMedicion}"


def _transfersUrl(idInstitucion: uuid.UUID) -> str:
    return f"{_institutionUrl(idInstitucion)}/transferencias"


def _managers(db: Session, idInstitucion: uuid.UUID, exclude: set[uuid.UUID]) -> list[User]:
    """Propietarios y moderadores activos de la institución, salvo quienes están en `exclude`."""
    managers = db.scalars(
        select(User).join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario).where(
            InstitutionUser.idInstitucion == idInstitucion,
            InstitutionUser.rolInstitucion.in_(ROLES_GESTION),
            InstitutionUser.estadoRelacion == RELACION_ACTIVO,
            User.estado == userNotifications.ESTADO_ACTIVO,
        )
    ).all()
    return [manager for manager in managers if manager.idUsuario not in exclude]


def _notifyManagers(db: Session, institution: Institution, evento: str, titulo: str, mensaje: str, *, clave: str, url: str,
                    exclude: set[uuid.UUID]) -> None:
    for manager in _managers(db, institution.idInstitucion, exclude):
        userNotifications.notify(db, manager, evento, titulo, mensaje, url=url, clave=clave)


def memberAdded(db: Session, institution: Institution, member: User, rol: str, idInstitucionUsuario: uuid.UUID,
                exclude: set[uuid.UUID]) -> None:
    """Una persona acepta la invitación como operador o moderador. Avisa a propietarios y moderadores."""
    if rol not in ETIQUETA_ROL:
        return
    evento = INSTITUCION_OPERADOR_NUEVO if rol == ROL_OPERADOR else INSTITUCION_MODERADOR_NUEVO
    titulo = "Nuevo operador" if rol == ROL_OPERADOR else "Nuevo moderador"
    _notifyManagers(db, institution, evento, titulo,
                    f"{_name(member)} se incorporó como {ETIQUETA_ROL[rol]} de {institution.nombre}.",
                    clave=f"{evento}:{idInstitucionUsuario}", url=_institutionUrl(institution.idInstitucion),
                    exclude={member.idUsuario, *exclude})


def memberRemoved(db: Session, institution: Institution, member: User, rol: str, idInstitucionUsuario: uuid.UUID,
                  exclude: set[uuid.UUID]) -> None:
    """Se da de baja a un operador o a un moderador. Avisa a propietarios y moderadores (quien lo hizo no; la persona dada de baja, tampoco)."""
    if rol not in ETIQUETA_ROL:
        return
    evento = INSTITUCION_OPERADOR_BAJA if rol == ROL_OPERADOR else INSTITUCION_MODERADOR_BAJA
    titulo = "Baja de operador" if rol == ROL_OPERADOR else "Baja de moderador"
    _notifyManagers(db, institution, evento, titulo,
                    f"{_name(member)} ya no es {ETIQUETA_ROL[rol]} de {institution.nombre}.",
                    clave=f"{evento}:{idInstitucionUsuario}", url=_institutionUrl(institution.idInstitucion),
                    exclude={member.idUsuario, *exclude})


def patientCreated(db: Session, institution: Institution, profile: MeasurementProfile, exclude: set[uuid.UUID]) -> None:
    """Alta de un paciente. Avisa a propietarios y moderadores (menos quien lo registró)."""
    evento = INSTITUCION_PACIENTE_NUEVO
    _notifyManagers(db, institution, evento, "Nuevo paciente",
                    f"Se registró el paciente {_patientId(profile)} en {institution.nombre}.",
                    clave=f"{evento}:{profile.idPerfilMedicion}", url=_patientUrl(institution.idInstitucion, profile.idPerfilMedicion),
                    exclude=exclude)


def patientAssigned(db: Session, institution: Institution, profile: MeasurementProfile, target: InstitutionUser, now: datetime,
                    exclude: set[uuid.UUID]) -> None:
    """El paciente pasa a cargo de `target` (alta, asignación directa, reasignación o transferencia). Avisa solo a ese operador."""
    user = db.get(User, target.idUsuarioInvitado)
    if user is None or user.idUsuario in exclude:
        return
    evento = INSTITUCION_PACIENTE_A_CARGO
    userNotifications.notify(
        db, user, evento, "Paciente a cargo",
        f"Ahora tenés a cargo el paciente {_patientId(profile)} en {institution.nombre}.",
        url=_patientUrl(institution.idInstitucion, profile.idPerfilMedicion),
        clave=f"{evento}:{profile.idPerfilMedicion}:{now:%Y%m%dT%H%M%S%f}",
    )


def transferRequested(db: Session, institution: Institution, profile: MeasurementProfile, idTransferencia: uuid.UUID,
                      destination: InstitutionUser, actor: User) -> None:
    """Una solicitud (o propuesta de gestión) de paciente llega al operador destino."""
    user = db.get(User, destination.idUsuarioInvitado)
    if user is None:
        return
    evento = INSTITUCION_SOLICITUD_NUEVA
    userNotifications.notify(
        db, user, evento, "Nueva solicitud de paciente",
        f"{_name(actor)} te envió una solicitud por el paciente {_patientId(profile)} en {institution.nombre}.",
        url=_transfersUrl(institution.idInstitucion), clave=f"{evento}:{idTransferencia}",
    )


def transferAnswered(db: Session, institution: Institution, profile: MeasurementProfile, idTransferencia: uuid.UUID,
                     origin: User | None, actor: User, accepted: bool) -> None:
    """El operador destino acepta o rechaza la solicitud. Avisa al operador de origen."""
    if origin is None or origin.idUsuario == actor.idUsuario:
        return
    evento = INSTITUCION_SOLICITUD_ACEPTADA if accepted else INSTITUCION_SOLICITUD_RECHAZADA
    titulo = "Solicitud aceptada" if accepted else "Solicitud rechazada"
    verbo = "aceptó" if accepted else "rechazó"
    userNotifications.notify(
        db, origin, evento, titulo,
        f"{_name(actor)} {verbo} el paciente {_patientId(profile)} en {institution.nombre}.",
        url=_transfersUrl(institution.idInstitucion), clave=f"{evento}:{idTransferencia}",
    )
