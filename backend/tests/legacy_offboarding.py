# Ayuda de pruebas: reproduce una baja ANTERIOR a la reasignación obligatoria.
#
# Hoy institution.revokeMember rechaza desvincular a un operador con pacientes a cargo (PACIENTES_ASIGNADOS). Las pruebas del tablero de
# «pacientes pendientes de reasignación» y de los operadores ya desvinculados necesitan ese estado heredado (operador en BAJA con pacientes
# todavía a su cargo y sus tareas pendientes), que existe en bases creadas antes del control: se arma igual que lo hacía la baja de entonces.

import uuid

from app.services import accountGrace, reassignments
from app.services import institution as institutions
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User


def legacyRevoke(db, actor, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID, *, openTasks: bool = True) -> int:
    """Da de baja al operador SIN exigir la reasignación. Con `openTasks` crea las tareas pendientes (como la baja heredada); sin ellas deja
    la asignación inconsistente (pacientes a cargo de un operador en BAJA y sin tarea) que `regularize` detecta. Devuelve las tareas creadas."""
    relation = db.get(InstitutionUser, idInstitucionUsuario)
    now = nowForDb()
    relation.estadoRelacion = institutions.RELACION_BAJA
    relation.fechaBaja = now
    db.flush()
    institutions._releaseMemberResources(db, [idInstitucionUsuario])
    created = reassignments.openForOperator(db, relation, actor.idUsuario, now) if openTasks else 0
    graceUser = accountGrace.startIfOrphaned(db, relation.idUsuarioInvitado, now, actor.idUsuario, "BAJA_INSTITUCIONAL")
    registerEvent(db, "PERMISO", "REVOCAR_MIEMBRO_INSTITUCION", True, actor.idUsuario, "InstitucionUsuario", idInstitucionUsuario,
                  datosNuevos={"estadoRelacion": institutions.RELACION_BAJA})
    db.commit()
    member = db.get(User, relation.idUsuarioInvitado)
    if created:
        institution = db.get(Institution, idInstitucion)
        reassignments.notifyManagers(db, institution, f"{member.nombre} {member.apellido}", created, now)
    if graceUser is not None:
        accountGrace.notifyStarted(graceUser, now)
    return created
