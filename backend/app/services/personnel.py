# Personnel - Módulo «Personal» de una institución: listado unificado, indicadores y perfil con historial
#
# Fuentes (sin tablas nuevas): InstitucionUsuario (vínculos: rol, estado, legajo, matrícula, función profesional, fechas de invitación,
# incorporación y baja, quién invitó), Usuario (nombre y correo de la cuenta; si fue eliminada, solo la identidad histórica del vínculo)
# y Auditoria (acontecimientos con su responsable). El rol de un vínculo es fijo: un «cambio de rol» no existe como operación; una
# persona que vuelve con otro rol tiene un vínculo nuevo, y sus períodos anteriores se conservan en el perfil.
#
# QUIÉN FIGURA COMO PERSONAL. Solo quien se incorporó de verdad (evidencia: `fechaIncorporacion`, que se escribe al aceptar la
# invitación o al crear la institución; CK_InstitucionUsuario_incorporacion obliga a tenerla a todo vínculo ACTIVO) o quien tiene una
# invitación PENDIENTE vigente (se muestra como «Pendiente»). Un vínculo en BAJA sin incorporación NO es una desvinculación: es una
# invitación cancelada, rechazada o cerrada, y una PENDIENTE vencida tampoco se incorporó; ninguna figura como personal, en el
# listado, los indicadores, el perfil ni el historial (siguen en la auditoría y en las invitaciones). «BAJA» queda reservada a
# quien se incorporó y después fue desvinculado.
#
# Una persona aparece UNA vez (agrupada por cuenta): se muestra su vínculo vigente o el último. Los filtros por rol consideran
# también los roles que tuvo; el filtro por estado, su estado actual.
#
# Permisos: el equipo (CONSULTAR_EQUIPO: propietario y moderador). El correo se muestra solo a ellos, y desaparece si la cuenta fue
# eliminada. Las acciones del perfil dependen del permiso de gestión del rol de la persona (el mismo que ya exigen las operaciones).

import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.personnel import (
    PersonnelActions,
    PersonnelEvent,
    PersonnelItem,
    PersonnelPage,
    PersonnelPeriod,
    PersonnelProfile,
    PersonnelSummary,
    SentInvitation,
    SentInvitationsPage,
)
from app.services import institution as institutions
from app.services.audit import personName, registerEvent
from app.services.auditQuery import ROLE_VALUES, STATE_VALUES, Resolver, _json
from app.services.csvExport import csvBytes, csvDate, csvText
from app.services.exportAudit import auditedExport, rejectExport
from app.utils.timeZone import nowForDb

MAX_PAGE_SIZE = 100
ROLES = (institutions.ROL_PROPIETARIO, institutions.ROL_MODERADOR, institutions.ROL_OPERADOR)
STATES = ("ACTIVO", "PENDIENTE", "SUSPENDIDO", "BAJA")  # CK_InstitucionUsuario_estado
ROLE_ORDER = {institutions.ROL_PROPIETARIO: 0, institutions.ROL_MODERADOR: 1, institutions.ROL_OPERADOR: 2}
ADMIN_FIELD_NAMES = {
    "matriculaProfesional": "matrícula profesional", "legajoInstitucional": "legajo", "funcionProfesional": "función profesional",
    "nombreProfesionalHistorico": "nombre profesional", "apellidoProfesionalHistorico": "apellido profesional",
}
NOT_FOUND = "No encontramos a esa persona en la institución."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


def _fold(text: str | None) -> str:
    """Minúsculas y sin tildes: la búsqueda no distingue «Pérez» de «perez»."""
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def _name(relation: InstitutionUser, user: User) -> tuple[str | None, str | None]:
    if relation.fechaMinimizacionDatos is not None:
        return (None, None)  # plazo de conservación vencido: el vínculo ya no identifica a la persona (ni siquiera con el nombre de su cuenta vigente)
    return (user.nombre or relation.nombreProfesionalHistorico, user.apellido or relation.apellidoProfesionalHistorico)


def _fullName(relation: InstitutionUser, user: User) -> str:
    first, last = _name(relation, user)
    return " ".join(part for part in (first, last) if part) or "Usuario eliminado"


def _joined(relation: InstitutionUser) -> bool:
    """Evidencia de incorporación efectiva: se incorporó (aceptó la invitación o creó la institución)."""
    return relation.fechaIncorporacion is not None


def _isPersonnel(relation: InstitutionUser, now: datetime) -> bool:
    """Forma o formó parte de la institución, o es una invitación pendiente vigente (todavía sin incorporación)."""
    if _joined(relation):
        return True
    return relation.estadoRelacion == institutions.RELACION_PENDIENTE and not institutions._isExpiredInvitation(relation, now)


def _representative(relations: list[InstitutionUser]) -> InstitutionUser:
    """El vínculo vigente (uno solo por cuenta, UX_InstitucionUsuario_vinculoVigente) o, si no hay, el más reciente."""
    live = [r for r in relations if r.estadoRelacion != institutions.RELACION_BAJA]
    if live:
        return live[0]
    return max(relations, key=lambda r: (r.fechaBaja or r.fechaInvitacion, r.fechaInvitacion))


def _groups(db: Session, idInstitucion: uuid.UUID, now: datetime) -> list[tuple[InstitutionUser, User, list[InstitutionUser]]]:
    """(vínculo mostrado, cuenta, todos los vínculos de la persona) para cada persona, en una sola consulta."""
    rows = db.execute(
        select(InstitutionUser, User).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion).order_by(InstitutionUser.fechaInvitacion)
    ).all()
    byUser: dict[uuid.UUID, list[InstitutionUser]] = defaultdict(list)
    accounts: dict[uuid.UUID, User] = {}
    for relation, user in rows:
        if not _isPersonnel(relation, now):
            continue  # invitación cancelada, rechazada, vencida o cerrada: nunca fue personal
        byUser[relation.idUsuarioInvitado].append(relation)
        accounts[relation.idUsuarioInvitado] = user
    return [(_representative(relations), accounts[userId], relations) for userId, relations in byUser.items()]


def _item(relation: InstitutionUser, user: User, relations: list[InstitutionUser], now: datetime) -> PersonnelItem:
    first, last = _name(relation, user)
    before = sorted({r.rolInstitucion for r in relations if r.rolInstitucion != relation.rolInstitucion}, key=ROLE_ORDER.get)
    pending = relation.estadoRelacion == institutions.RELACION_PENDIENTE
    return PersonnelItem(
        idInstitucionUsuario=relation.idInstitucionUsuario, nombre=first, apellido=last, nombreCompleto=_fullName(relation, user),
        correoElectronico=None if relation.fechaMinimizacionDatos else user.correoElectronico, rolInstitucion=relation.rolInstitucion, rolesAnteriores=before,
        estadoRelacion=relation.estadoRelacion, cuentaPendiente=pending and user.estado == institutions.ESTADO_CUENTA_PENDIENTE,
        invitacionVencida=institutions._isExpiredInvitation(relation, now), legajoInstitucional=relation.legajoInstitucional,
        matriculaProfesional=relation.matriculaProfesional, funcionProfesional=relation.funcionProfesional,
        fechaInvitacion=relation.fechaInvitacion, fechaIncorporacion=relation.fechaIncorporacion, fechaBaja=relation.fechaBaja,
        periodos=len(relations), datosEliminados=relation.fechaMinimizacionDatos is not None,
    )


def _summary(groups, now: datetime) -> PersonnelSummary:
    active = [rep for rep, _, _ in groups if rep.estadoRelacion == institutions.RELACION_ACTIVO]
    return PersonnelSummary(
        totalActivos=len(active),
        moderadoresActivos=sum(1 for r in active if r.rolInstitucion == institutions.ROL_MODERADOR),
        operadoresActivos=sum(1 for r in active if r.rolInstitucion == institutions.ROL_OPERADOR),
        propietariosActivos=sum(1 for r in active if r.rolInstitucion == institutions.ROL_PROPIETARIO),
        bajas=sum(1 for rep, _, _ in groups if rep.estadoRelacion == institutions.RELACION_BAJA),
        invitacionesPendientes=sum(1 for rep, _, _ in groups if rep.estadoRelacion == institutions.RELACION_PENDIENTE
                                   and not institutions._isExpiredInvitation(rep, now)),
    )


def _matches(term: str, user: User, relations: list[InstitutionUser]) -> bool:
    """Nombre, apellido, correo, legajo o matrícula, en cualquier período de la persona."""
    # Una persona cuyos datos históricos se eliminaron no se encuentra por los de su cuenta vigente.
    haystack = [] if all(r.fechaMinimizacionDatos is not None for r in relations) else [user.nombre, user.apellido, user.correoElectronico]
    for relation in relations:
        haystack += [relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico, relation.legajoInstitucional,
                     relation.matriculaProfesional]
    return any(term in _fold(value) for value in haystack if value)


def _select(groups, rol: str | None, estado: str | None, term: str) -> list[tuple[InstitutionUser, User, list[InstitutionUser]]]:
    """Las personas que cumplen los filtros del listado (rol, estado y búsqueda ya normalizada), en el orden de la lista."""
    chosen = [
        (rep, user, relations) for rep, user, relations in groups
        if (rol is None or any(r.rolInstitucion == rol for r in relations))
        and (estado is None or rep.estadoRelacion == estado)
        and (not term or _matches(term, user, relations))
    ]
    chosen.sort(key=lambda g: (ROLE_ORDER.get(g[0].rolInstitucion, 3), _fold(_name(g[0], g[1])[1]), _fold(_name(g[0], g[1])[0])))
    return chosen


def listPersonnel(db: Session, actor: User, idInstitucion: uuid.UUID, *, rol: str | None = None, estado: str | None = None,
                  busqueda: str | None = None, pagina: int = 1, tamanioPagina: int = 20) -> PersonnelPage:
    """Todo el personal (incluye al propietario y a las personas dadas de baja) con filtros combinables."""
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    if rol is not None and rol not in ROLES:
        raise _error("DATOS_INVALIDOS", "El rol indicado no es válido.")
    if estado is not None and estado not in STATES:
        raise _error("DATOS_INVALIDOS", "El estado indicado no es válido.")
    now = nowForDb()
    groups = _groups(db, idInstitucion, now)
    summary = _summary(groups, now)
    chosen = _select(groups, rol, estado, _fold(busqueda).strip())
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    page = chosen[(pagina - 1) * tamanioPagina: pagina * tamanioPagina]
    return PersonnelPage(items=[_item(rep, user, relations, now) for rep, user, relations in page], total=len(chosen), pagina=pagina,
                         tamanioPagina=tamanioPagina, resumen=summary)


# --- Perfil e historial ------------------------------------------------------------------------------------------


def _role(value: str | None) -> str:
    return ROLE_VALUES.get(value or "", value or "")


def _describe(audit: Audit, resolver: Resolver, snapshot: dict) -> tuple[str, str | None, str | None] | None:
    """(tipo, título, descripción) de un evento de auditoría de un vínculo; None si no es un hecho de la persona."""
    new = _json(audit.datosNuevos)
    role = new.get("rolInstitucion")
    action = audit.accion
    if action == "INVITAR_MIEMBRO_INSTITUCION":
        extra = " Se creó una cuenta pendiente de activación." if new.get("cuenta") == "NUEVA" else ""
        return "INVITACION", "Invitación enviada", f"Invitada como {_role(role)}.{extra}".strip()
    if action == "REENVIAR_INVITACION_INSTITUCION":
        return "INVITACION_REENVIADA", "Invitación reenviada", "Se renovó el vencimiento de la invitación."
    if action == "ACEPTAR_INVITACION_INSTITUCION":
        return "INCORPORACION", "Invitación aceptada", f"La persona se incorporó como {_role(role)}." if role else "La persona se incorporó."
    if action == "RECHAZAR_INVITACION_INSTITUCION":
        return "INVITACION_RECHAZADA", "Invitación rechazada", "La persona rechazó la invitación."
    if action == "CANCELAR_INVITACION_INSTITUCION":
        return "INVITACION_CANCELADA", "Invitación cancelada", "La invitación fue cancelada antes de ser aceptada."
    if action == "MODIFICAR_MIEMBRO_INSTITUCION":
        fields = [ADMIN_FIELD_NAMES.get(f, f) for f in (new.get("campos") or [])]
        return "DATOS_LABORALES", "Modificación de datos laborales", ("Se modificaron: " + ", ".join(fields) + ".") if fields else None
    if action == "REVOCAR_MIEMBRO_INSTITUCION":
        return "DESVINCULACION", "Desvinculación", "La persona dejó de integrar la institución y perdió sus accesos."
    return None


def _timeline(db: Session, idInstitucion: uuid.UUID, relations: list[InstitutionUser], inviters: dict) -> list[PersonnelEvent]:
    ids = [r.idInstitucionUsuario for r in relations]
    audits = db.scalars(select(Audit).where(
        Audit.idInstitucion == idInstitucion, Audit.tablaAfectada == "InstitucionUsuario", Audit.idRegistro.in_(ids),
        Audit.resultado == "EXITO").order_by(Audit.fechaHora.desc(), Audit.idAuditoria)).all()
    resolver = Resolver(db, idInstitucion, identify=False)
    resolver.prepare(list(audits))  # nombres de quienes realizaron cada operación, en una resolución agrupada
    events: list[PersonnelEvent] = []
    seen: dict[uuid.UUID, set] = defaultdict(set)
    for audit in audits:
        described = _describe(audit, resolver, _json(audit.detalle))
        if described is None:
            continue
        kind, title, text = described
        seen[audit.idRegistro].add(kind)
        events.append(PersonnelEvent(fechaHora=audit.fechaHora, tipo=kind, titulo=title, descripcion=text, resultado="EXITO",
                                     realizadoPor=resolver.actor(audit, _json(audit.detalle)), origen="AUDITORIA",
                                     rolInstitucion=_json(audit.datosNuevos).get("rolInstitucion")))
    # Hechos que el vínculo registra por sí mismo (sus fechas reales) y que no tienen un evento de auditoría: no se duplican los que sí.
    for relation in relations:
        done = seen[relation.idInstitucionUsuario]
        role = _role(relation.rolInstitucion)
        if relation.origenVinculo == "CREACION_INSTITUCION":
            if relation.fechaIncorporacion:
                events.append(PersonnelEvent(fechaHora=relation.fechaIncorporacion, tipo="INCORPORACION", titulo="Alta como propietario/a",
                                             descripcion="Creó la institución y quedó como propietario/a.", origen="REGISTRO",
                                             rolInstitucion=relation.rolInstitucion))
        else:
            if "INVITACION" not in done:
                events.append(PersonnelEvent(fechaHora=relation.fechaInvitacion, tipo="INVITACION", titulo="Invitación enviada",
                                             descripcion=f"Invitada como {role}.", origen="REGISTRO", rolInstitucion=relation.rolInstitucion,
                                             realizadoPor=inviters.get(relation.idUsuarioInvitador)))
            if relation.fechaIncorporacion and "INCORPORACION" not in done:
                events.append(PersonnelEvent(fechaHora=relation.fechaIncorporacion, tipo="INCORPORACION", titulo="Incorporación a la institución",
                                             descripcion=f"La persona se incorporó como {role}.", origen="REGISTRO",
                                             rolInstitucion=relation.rolInstitucion))
        if relation.fechaBaja and relation.fechaIncorporacion and "DESVINCULACION" not in done:
            events.append(PersonnelEvent(fechaHora=relation.fechaBaja, tipo="DESVINCULACION", titulo="Desvinculación",
                                         descripcion="La persona dejó de integrar la institución.", origen="REGISTRO",
                                         rolInstitucion=relation.rolInstitucion))
    events.sort(key=lambda e: e.fechaHora, reverse=True)
    return events


def getProfile(db: Session, actor: User, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID) -> PersonnelProfile:
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    target = db.get(InstitutionUser, idInstitucionUsuario)
    if target is None or target.idInstitucion != idInstitucion:
        raise _error("MIEMBRO_NO_ENCONTRADO", NOT_FOUND)  # un vínculo de otra institución no existe para este ámbito
    user = db.get(User, target.idUsuarioInvitado)
    now = nowForDb()
    relations = [r for r in db.scalars(select(InstitutionUser).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.idUsuarioInvitado == target.idUsuarioInvitado)
        .order_by(InstitutionUser.fechaInvitacion)) if _isPersonnel(r, now)]
    if not relations:
        # Una invitación cancelada, rechazada o vencida (sin incorporación) no genera perfil de trabajador.
        raise _error("MIEMBRO_NO_ENCONTRADO", NOT_FOUND)
    rep = _representative(relations)  # el perfil muestra a la persona con su situación vigente aunque se abra un período anterior
    # Quién invitó a cada período: la identidad de esa persona en esta institución (una sola consulta).
    inviterIds = {r.idUsuarioInvitador for r in relations if r.idUsuarioInvitador}
    inviters: dict = {}
    if inviterIds:
        for relation, inviter in db.execute(select(InstitutionUser, User).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                                            .where(InstitutionUser.idInstitucion == idInstitucion,
                                                   InstitutionUser.idUsuarioInvitado.in_(inviterIds))
                                            .order_by(InstitutionUser.fechaInvitacion)).all():
            inviters[relation.idUsuarioInvitado] = personName(relation, inviter) or _fullName(relation, inviter)
    base = _item(rep, user, relations, now)
    history = _timeline(db, idInstitucion, relations, inviters)
    modifications = [e.fechaHora for e in history if e.tipo == "DATOS_LABORALES"]
    pending = rep.estadoRelacion == institutions.RELACION_PENDIENTE
    role = rep.rolInstitucion
    manage = institutions.REVOKE_PERMISSION.get(role)
    live = rep.estadoRelacion != institutions.RELACION_BAJA
    actions = PersonnelActions(
        puedeEliminarDatos=_canErase(membership, relations),
        puedeEditar=bool(manage and live and membership.can(manage)),
        puedeDesvincular=bool(manage and live and membership.can(manage)),
        puedeReenviar=bool(pending and role in institutions.INVITE_PERMISSION and membership.can(institutions.INVITE_PERMISSION[role])),
        puedeVerDashboard=bool(role == institutions.ROL_OPERADOR and rep.estadoRelacion in ("ACTIVO", "BAJA")
                               and membership.can(institutions.P_ADMINISTRAR_OPERADORES)),
    )
    others = [PersonnelPeriod(idInstitucionUsuario=r.idInstitucionUsuario, rolInstitucion=r.rolInstitucion, estadoRelacion=r.estadoRelacion,
                              origenVinculo=r.origenVinculo, invitadoPor=inviters.get(r.idUsuarioInvitador),
                              fechaInvitacion=r.fechaInvitacion, fechaIncorporacion=r.fechaIncorporacion, fechaBaja=r.fechaBaja,
                              vigente=r.idInstitucionUsuario == rep.idInstitucionUsuario)
              for r in sorted(relations, key=lambda r: r.fechaInvitacion, reverse=True) if r.idInstitucionUsuario != rep.idInstitucionUsuario]
    return PersonnelProfile(
        **base.model_dump(), nombreInstitucion=membership.institution.nombre,
        nombreProfesionalHistorico=rep.nombreProfesionalHistorico, apellidoProfesionalHistorico=rep.apellidoProfesionalHistorico,
        origenVinculo=rep.origenVinculo, invitadoPor=inviters.get(rep.idUsuarioInvitador),
        fechaVencimientoInvitacion=institutions._invitationExpiry(rep) if pending else None,
        fechaCuentaCreada=user.fechaCreacion if user.estado != "ELIMINADO" else None,
        fechaUltimaModificacion=max(modifications) if modifications else None,
        periodosAnteriores=others, acciones=actions, historial=history,
    )


# --- Eliminación de los datos históricos de una persona ---------------------------------------------------------------------
#
# Los datos de nómina (nombre profesional, legajo, matrícula) quedan con la institución sin vencimiento propio. Cuando la institución lo
# decide, el propietario (o un moderador, para operadores) los suprime acá. Es el mismo tratamiento que la minimización por plazo
# (personnelRetention): el vínculo no se borra —rol, función, fechas, origen e invitador siguen, y la autoría de las mediciones y la
# auditoría siguen apuntando a él— pero deja de identificar a la persona. Solo aplica a personas ya desvinculadas: a quien sigue
# vinculada primero se la desvincula. El permiso es el mismo que exige desvincular a alguien de ese rol (el propietario no tiene).

_ERASABLE = ("nombreProfesionalHistorico", "apellidoProfesionalHistorico", "legajoInstitucional", "matriculaProfesional")


def _canErase(membership, relations: list[InstitutionUser]) -> bool:
    if any(r.estadoRelacion != institutions.RELACION_BAJA for r in relations):
        return False  # sigue vinculada o con invitación pendiente
    if all(r.fechaMinimizacionDatos is not None for r in relations):
        return False  # ya no queda nada por eliminar
    return all((p := institutions.REVOKE_PERMISSION.get(r.rolInstitucion)) is not None and membership.can(p) for r in relations)


def erasePersonalData(db: Session, actor: User, idInstitucion: uuid.UUID, idInstitucionUsuario: uuid.UUID) -> None:
    """Suprime nombre profesional, legajo y matrícula de todos los períodos (ya cerrados) de la persona en esta institución."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    target = db.get(InstitutionUser, idInstitucionUsuario)
    if target is None or target.idInstitucion != idInstitucion or target.idUsuarioInvitado == actor.idUsuario:
        raise _error("MIEMBRO_NO_ENCONTRADO", NOT_FOUND)
    now = nowForDb()
    relations = [r for r in db.scalars(select(InstitutionUser).where(
        InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.idUsuarioInvitado == target.idUsuarioInvitado)
        .order_by(InstitutionUser.fechaInvitacion)) if _isPersonnel(r, now)]
    if not relations or target not in relations:
        raise _error("MIEMBRO_NO_ENCONTRADO", NOT_FOUND)  # una invitación que nunca se incorporó no es personal
    if any(r.estadoRelacion != institutions.RELACION_BAJA for r in relations):
        raise _error("PERSONA_VIGENTE", "La persona todavía está vinculada a la institución. Primero desvinculala; después podés eliminar sus datos históricos.")
    if all(r.fechaMinimizacionDatos is not None for r in relations):
        raise _error("DATOS_YA_ELIMINADOS", "Los datos históricos de esta persona ya fueron eliminados.")
    roles = sorted({r.rolInstitucion for r in relations}, key=ROLE_ORDER.get)
    if not _canErase(membership, relations):
        registerEvent(db, "PERMISO", "ELIMINAR_DATOS_PERSONAL_HISTORICO", False, actor.idUsuario, "InstitucionUsuario",
                      target.idInstitucionUsuario, observacion=f"Sin permiso para eliminar datos históricos de {', '.join(roles)}")
        db.commit()
        raise institutions._forbidden()

    erased = sorted({f for r in relations for f in _ERASABLE if getattr(r, f) is not None})
    for relation in relations:
        for field in _ERASABLE:
            setattr(relation, field, None)
        relation.fechaMinimizacionDatos = relation.fechaMinimizacionDatos or now
    registerEvent(db, "PERMISO", "ELIMINAR_DATOS_PERSONAL_HISTORICO", True, actor.idUsuario, "InstitucionUsuario",
                  target.idInstitucionUsuario, datosNuevos={"roles": roles, "periodos": len(relations), "campos": erased})
    db.commit()


# --- Exportación del personal (CSV) ---------------------------------------------------------------------------------------
#
# Permiso: CONSULTAR_EQUIPO (propietario y moderador), validado en el servidor en cada pedido: el botón del frontend solo presenta la opción.
# Quien no lo tiene (operador, o quien no pertenece a la institución) recibe 403 y el intento queda en la auditoría como
# EXPORTACION_FALLIDA. Toda exportación pasa por `auditedExport` (ExportAudit): nunca queda una sin evento.
# Formato: CSV separado por punto y coma, en UTF-8 con BOM, para que Excel en español muestre bien las tildes. Los valores que empiezan con
# = + - @ se escapan con una comilla simple: no pueden ejecutarse como fórmula al abrir el archivo.

EXPORT_TIPO_DATOS = "PERSONAL_INSTITUCION"
EXPORT_COLUMNS = (
    "Nombre", "Apellido", "Correo electrónico", "Rol", "Roles anteriores", "Estado", "Legajo", "Matrícula profesional",
    "Fecha de invitación", "Fecha de incorporación", "Fecha de baja",
)
def _csvRow(item: PersonnelItem) -> list[str]:
    return [
        csvText(item.nombre), csvText(item.apellido), csvText(item.correoElectronico), csvText(_role(item.rolInstitucion)),
        csvText(", ".join(_role(r) for r in item.rolesAnteriores)), csvText(STATE_VALUES.get(item.estadoRelacion, item.estadoRelacion)),
        csvText(item.legajoInstitucional), csvText(item.matriculaProfesional), csvDate(item.fechaInvitacion),
        csvDate(item.fechaIncorporacion), csvDate(item.fechaBaja),
    ]


def _exportItems(db: Session, idInstitucion: uuid.UUID, alcance: str, ids: list[uuid.UUID], rol: str | None, estado: str | None,
                 busqueda: str | None) -> list[PersonnelItem]:
    now = nowForDb()
    groups = _groups(db, idInstitucion, now)
    if alcance == "SELECCION":
        if not ids:
            raise _error("DATOS_INVALIDOS", "Elegí al menos una persona para exportar.")
        byRep = {rep.idInstitucionUsuario: (rep, user, relations) for rep, user, relations in groups}
        if any(i not in byRep for i in ids):
            # Un id que no es personal de esta institución (ajeno, dado de baja sin incorporación o inexistente) no se exporta.
            raise _error("DATOS_INVALIDOS", "Alguna persona seleccionada ya no figura en el personal de esta institución. Actualizá el listado.")
        chosen = [byRep[i] for i in dict.fromkeys(ids)]  # sin repetidos, en el orden elegido
    else:
        chosen = _select(groups, rol, estado, _fold(busqueda).strip())
    return [_item(rep, user, relations, now) for rep, user, relations in chosen]


def exportPersonnel(db: Session, actor: User, idInstitucion: uuid.UUID, *, alcance: str, idsInstitucionUsuario: list[uuid.UUID] | None = None,
                    rol: str | None = None, estado: str | None = None, busqueda: str | None = None) -> tuple[bytes, str]:
    """CSV del personal (`SELECCION` o `TODOS`). Devuelve (contenido, nombre del archivo)."""
    try:
        institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    except AuthError as error:
        rejectExport(db, actor, EXPORT_TIPO_DATOS, ambito="INSTITUCION", idInstitucion=idInstitucion, formato="CSV", motivo=error.code)
        db.commit()
        raise
    with auditedExport(db, actor, EXPORT_TIPO_DATOS, ambito="INSTITUCION", idInstitucion=idInstitucion, formato="CSV") as export:
        items = _exportItems(db, idInstitucion, alcance, idsInstitucionUsuario or [], rol, estado, busqueda)
        export.registros = len(items)
        content = csvBytes(EXPORT_COLUMNS, [_csvRow(item) for item in items])
        return content, f"personal-institucion-{nowForDb():%Y%m%d-%H%M}.csv"


# --- Invitaciones enviadas por la institución -----------------------------------------------------------------------------
#
# Las invitaciones sin incorporación no son personal: se administran acá. Estado de cada una (sin tablas nuevas):
#   ACEPTADA   -> el vínculo tiene `fechaIncorporacion` (ya forma parte del personal)
#   PENDIENTE  -> sin responder y vigente;  VENCIDA -> sin responder y pasado su plazo
#   RECHAZADA  -> BAJA sin incorporación con el evento RECHAZAR_INVITACION_INSTITUCION de la propia cuenta
#   CANCELADA  -> BAJA sin incorporación por cualquier otro motivo (cancelada por la institución, reemplazada o cerrada)
# La cancelación y el rechazo no borran nada: el vínculo y la auditoría se conservan.

INVITATION_STATES = ("PENDIENTE", "ACEPTADA", "RECHAZADA", "CANCELADA", "VENCIDA")


def _invitationState(relation: InstitutionUser, rejected: set, now: datetime) -> str:
    if relation.fechaIncorporacion is not None:
        return "ACEPTADA"
    if relation.estadoRelacion == institutions.RELACION_PENDIENTE:
        return "VENCIDA" if institutions._isExpiredInvitation(relation, now) else "PENDIENTE"
    return "RECHAZADA" if relation.idInstitucionUsuario in rejected else "CANCELADA"


def listSentInvitations(db: Session, actor: User, idInstitucion: uuid.UUID, *, estado: str | None = None, pagina: int = 1,
                        tamanioPagina: int = 20) -> SentInvitationsPage:
    """Invitaciones que emitió la institución (no incluye al propietario, que creó la institución), más recientes primero."""
    membership = institutions.requireMembership(db, actor, idInstitucion, institutions.P_EQUIPO)
    if estado is not None and estado not in INVITATION_STATES:
        raise _error("DATOS_INVALIDOS", "El estado indicado no es válido.")
    rows = db.execute(
        select(InstitutionUser, User).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.origenVinculo != "CREACION_INSTITUCION")
        .order_by(InstitutionUser.fechaInvitacion.desc())
    ).all()
    ids = [relation.idInstitucionUsuario for relation, _ in rows]
    rejected = set(db.scalars(select(Audit.idRegistro).where(
        Audit.idInstitucion == idInstitucion, Audit.tablaAfectada == "InstitucionUsuario", Audit.idRegistro.in_(ids),
        Audit.accion == "RECHAZAR_INVITACION_INSTITUCION", Audit.resultado == "EXITO"))) if ids else set()
    now = nowForDb()
    inviterIds = {relation.idUsuarioInvitador for relation, _ in rows if relation.idUsuarioInvitador}
    inviters: dict = {}
    if inviterIds:
        for relation, inviter in db.execute(select(InstitutionUser, User).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                                            .where(InstitutionUser.idInstitucion == idInstitucion,
                                                   InstitutionUser.idUsuarioInvitado.in_(inviterIds))
                                            .order_by(InstitutionUser.fechaInvitacion)).all():
            inviters[relation.idUsuarioInvitado] = personName(relation, inviter) or _fullName(relation, inviter)
    items, counts = [], dict.fromkeys(INVITATION_STATES, 0)
    for relation, user in rows:
        state = _invitationState(relation, rejected, now)
        counts[state] += 1
        if estado is not None and state != estado:
            continue
        role = relation.rolInstitucion
        open_ = state in ("PENDIENTE", "VENCIDA")
        items.append(SentInvitation(
            idInstitucionUsuario=relation.idInstitucionUsuario, nombreCompleto=_fullName(relation, user),
            correoElectronico=user.correoElectronico, rolInstitucion=role, estado=state, cuentaPendiente=user.estado == institutions.ESTADO_CUENTA_PENDIENTE,
            invitadoPor=inviters.get(relation.idUsuarioInvitador), fechaInvitacion=relation.fechaInvitacion,
            fechaVencimiento=institutions._invitationExpiry(relation) if relation.estadoRelacion == institutions.RELACION_PENDIENTE else None,
            fechaRespuesta=relation.fechaIncorporacion if state == "ACEPTADA" else (relation.fechaBaja if state in ("RECHAZADA", "CANCELADA") else None),
            puedeReenviar=bool(open_ and role in institutions.INVITE_PERMISSION and membership.can(institutions.INVITE_PERMISSION[role])),
            puedeCancelar=bool(open_ and role in institutions.REVOKE_PERMISSION and membership.can(institutions.REVOKE_PERMISSION[role])),
            idPersonal=relation.idInstitucionUsuario if state == "ACEPTADA" else None,
        ))
    tamanioPagina = max(1, min(tamanioPagina, MAX_PAGE_SIZE))
    pagina = max(1, pagina)
    return SentInvitationsPage(items=items[(pagina - 1) * tamanioPagina: pagina * tamanioPagina], total=len(items), pagina=pagina,
                               tamanioPagina=tamanioPagina, resumen=counts)
