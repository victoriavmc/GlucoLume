# InstitutionActivity - «Actividad reciente» de una institución
#
# Fuente ÚNICA: la tabla Auditoria. Todas las operaciones administrativas y operativas de la institución ya se registran ahí (con el
# evento de ese momento), así que no hay una segunda fuente que pueda duplicarlas: cada actividad es un evento de auditoría
# reutilizado, con un nombre legible. No se inventan eventos ni se reconstruyen acciones sin evidencia.
#
# Qué muestra (catálogo CATALOG): creación y modificación de la institución, invitaciones, incorporación, modificación y baja de
# moderadores y operadores, pacientes (alta, cambios, baja, transferencias, reasignación), dispositivos (alta, estados,
# asignación, descomisión) y matrices (versiones, reglas, activación). Más, solo para quien puede consultar la auditoría, las
# operaciones RECHAZADAS por permiso o acceso (requieren atención).
# Qué NO muestra: eventos técnicos de bajo valor (mediciones, consultas, avisos por correo) ni eventos secundarios de una misma
# operación (SUPPRESSED): p. ej. el alta de la cuenta invitada ya está en «Invitación» y el aviso de creación ya está en «Institución
# creada». Una misma operación registrada dos veces se muestra una sola vez.
#
# Permisos: se filtra por lo que el rol puede consultar (categoría -> permiso institucional). El operador solo ve lo que él hizo.
# Los pacientes se nombran por su seudónimo; nunca por nombre.

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.audit import Audit
from app.models.user import User
from app.schemas.institutionActivity import ActivityItem, ActivityPage
from app.services import institution as institutions
from app.services.audit import ACCIONES_CRITICAS
from app.models.measurementProfile import MeasurementProfile
from app.models.profileTransfer import ProfileTransfer
from app.services.auditQuery import ACTION_LABELS, ROLE_VALUES, STATE_VALUES, Resolver, _json

MAX_LIMIT = 20
BATCH = 40
MAX_ROWS = 400  # tope de eventos revisados para completar el listado

# Permiso institucional que habilita ver cada categoría.
CATEGORY_PERMISSION = {
    "INSTITUCION": None,  # todos los integrantes consultan los datos de su institución
    "MODERADORES": institutions.P_MODERADORES,
    "OPERADORES": institutions.P_ADMINISTRAR_OPERADORES,
    "PACIENTES": institutions.P_PACIENTES,
    "DISPOSITIVOS": institutions.P_DISPOSITIVOS,
    "MATRICES": institutions.P_MATRICES,
    "SEGURIDAD": institutions.P_AUDITORIA,
    "MEDICIONES": institutions.P_PACIENTES,
}

# acción -> (categoría, título). Las acciones de personal toman su categoría y título del rol del integrante (ver _classify).
CATALOG = {
    "CREAR_INSTITUCION": ("INSTITUCION", "Institución creada"),
    "MODIFICAR_INSTITUCION": ("INSTITUCION", "Datos de la institución actualizados"),
    "REABRIR_INSTITUCION": ("INSTITUCION", "Institución reabierta"),
    "INVITAR_MIEMBRO_INSTITUCION": ("PERSONAL", "invitado"),
    "REENVIAR_INVITACION_INSTITUCION": ("PERSONAL", "Invitación reenviada"),
    "ACEPTAR_INVITACION_INSTITUCION": ("PERSONAL", "incorporado"),
    "RECHAZAR_INVITACION_INSTITUCION": ("PERSONAL", "Invitación rechazada"),
    "CANCELAR_INVITACION_INSTITUCION": ("PERSONAL", "Invitación cancelada"),
    "MODIFICAR_MIEMBRO_INSTITUCION": ("PERSONAL", "actualizado"),
    "REVOCAR_MIEMBRO_INSTITUCION": ("PERSONAL", "desvinculado"),
    "CREAR_PACIENTE": ("PACIENTES", "Paciente registrado"),
    "MODIFICAR_PACIENTE": ("PACIENTES", "Datos de un paciente actualizados"),
    "BAJA_PACIENTE": ("PACIENTES", "Paciente dado de baja"),
    "DEPURAR_DATOS_PACIENTES": ("PACIENTES", "Datos personales de pacientes depurados"),
    "ANONIMIZAR_PACIENTES": ("PACIENTES", "Pacientes anonimizados"),
    "DEPURAR_MEDICIONES_RETENCION": ("PACIENTES", "Mediciones eliminadas por fin de conservación"),
    "ASIGNAR_RESPONSABLE_PACIENTE": ("PACIENTES", "Responsable de un paciente reasignado"),
    "PACIENTES_PENDIENTES_REASIGNACION": ("PACIENTES", "Pacientes pendientes de reasignación"),
    "SOLICITAR_TRANSFERENCIA_PERFIL": ("PACIENTES", "Transferencia de paciente solicitada"),
    "ACEPTAR_TRANSFERENCIA_PERFIL": ("PACIENTES", "Transferencia de paciente aceptada"),
    "RECHAZAR_TRANSFERENCIA_PERFIL": ("PACIENTES", "Transferencia de paciente rechazada"),
    "CANCELAR_TRANSFERENCIA_PERFIL": ("PACIENTES", "Transferencia de paciente cancelada"),
    "REGISTRAR_DISPOSITIVO": ("DISPOSITIVOS", "Dispositivo registrado"),
    "CAMBIAR_ESTADO_DISPOSITIVO": ("DISPOSITIVOS", "Estado de un dispositivo cambiado"),
    "MODIFICAR_DISPOSITIVO": ("DISPOSITIVOS", "Dispositivo actualizado"),
    "ASIGNAR_DISPOSITIVO": ("DISPOSITIVOS", "Dispositivo asignado a la institución"),
    "DESVINCULAR_DISPOSITIVO": ("DISPOSITIVOS", "Dispositivo desvinculado"),
    "CAMBIAR_RESPONSABLE_DISPOSITIVO": ("DISPOSITIVOS", "Responsable de un dispositivo cambiado"),
    # Solo en «Mi actividad» del operador (propias): el resto de los roles ve la actividad administrativa, no cada medición.
    "INICIAR_MEDICION": ("MEDICIONES", "Medición realizada"),
    "DESCOMISIONAR_DISPOSITIVO": ("DISPOSITIVOS", "Dispositivo descomisionado"),
    "CREAR_MATRIZ": ("MATRICES", "Matriz creada"),
    "CREAR_VERSION_MATRIZ": ("MATRICES", "Nueva versión de matriz"),
    "MODIFICAR_MATRIZ": ("MATRICES", "Matriz actualizada"),
    "ACTIVAR_MATRIZ": ("MATRICES", "Matriz activada"),
    "DESACTIVAR_MATRIZ": ("MATRICES", "Matriz desactivada"),
    "ARCHIVAR_MATRIZ": ("MATRICES", "Matriz archivada"),
    "CREAR_REGLA_MATRIZ": ("MATRICES", "Regla de matriz agregada"),
    "MODIFICAR_REGLA_MATRIZ": ("MATRICES", "Regla de matriz actualizada"),
    "ELIMINAR_REGLA_MATRIZ": ("MATRICES", "Regla de matriz eliminada"),
}

# Eventos secundarios de una operación que ya figura con otro evento (no se muestran para no duplicarla):
SUPPRESSED = {
    "NOTIFICAR_CREACION_INSTITUCION": "el aviso por correo acompaña a «Institución creada»",
    "CREAR_CUENTA_INVITADA": "el alta de la cuenta invitada acompaña a la invitación",
    "ASIGNAR_RESPONSABLE_ORIGEN": "es la contraparte de la reasignación de responsable",
    "CAMBIAR_RESPONSABLE_PERFIL": "es la consecuencia de la transferencia aceptada o de la reasignación directa",
}

ROUTES = {"INSTITUCION": "administracion/datos", "MODERADORES": "personal/moderadores", "OPERADORES": "personal/operadores",
          "PACIENTES": "pacientes", "DISPOSITIVOS": "dispositivos", "MATRICES": "matrices"}
DEVICE_STATE_TITLES = {"OPERATIVO": "Dispositivo operativo", "EN_MANTENIMIENTO": "Dispositivo en mantenimiento",
                       "FUERA_DE_SERVICIO": "Dispositivo fuera de servicio"}
ROLE_NOUN = {"MODERADOR": "Moderador", "OPERADOR": "Operador"}


def _memberRole(audit: Audit, resolver: Resolver, snapshot: dict) -> str | None:
    new = _json(audit.datosNuevos)
    if new.get("rolInstitucion"):
        return new["rolInstitucion"]
    if audit.tablaAfectada == "InstitucionUsuario" and audit.idRegistro:
        return resolver.person(audit.idRegistro, snapshot).rol
    return None


def _classify(audit: Audit, resolver: Resolver, snapshot: dict) -> tuple[str, str] | None:
    """(categoría, título) de un evento exitoso del catálogo; None si no corresponde mostrarlo."""
    entry = CATALOG.get(audit.accion)
    if entry is None:
        return None
    category, title = entry
    new, old = _json(audit.datosNuevos), _json(audit.datosPrevios)
    if category == "PERSONAL":
        role = _memberRole(audit, resolver, snapshot)
        if role not in ROLE_NOUN:
            return None  # el propietario no se invita ni se desvincula desde acá
        category = "MODERADORES" if role == "MODERADOR" else "OPERADORES"
        if audit.accion == "MODIFICAR_MIEMBRO_INSTITUCION" and "rolInstitucion" in {**old, **new} and old.get("rolInstitucion") != new.get("rolInstitucion"):
            return category, "Rol de un integrante actualizado"
        if title[0].islower():  # «invitado», «incorporado», «actualizado», «desvinculado»
            return category, f"{ROLE_NOUN[role]} {title}"
        return category, title
    if audit.accion == "CAMBIAR_ESTADO_DISPOSITIVO":
        return category, DEVICE_STATE_TITLES.get(new.get("estado"), title)
    return category, title


def _route(category: str, audit: Audit) -> str | None:
    if category == "INSTITUCION" or category in ("MODERADORES", "OPERADORES"):
        return ROUTES[category]
    if category == "DISPOSITIVOS" and audit.tablaAfectada == "Dispositivo" and audit.idRegistro:
        return f"dispositivos/{audit.idRegistro}"
    if category == "MATRICES" and audit.tablaAfectada == "Matriz" and audit.idRegistro:
        return f"matrices/{audit.idRegistro}"
    if category == "PACIENTES":
        if audit.tablaAfectada == "TransferenciaPerfil" and audit.idRegistro:
            return f"pacientes/transferencias/{audit.idRegistro}"
        if audit.tablaAfectada == "PerfilMedicion" and audit.idRegistro and audit.accion != "BAJA_PACIENTE":
            return f"pacientes/{audit.idRegistro}"
    return ROUTES.get(category)


def _asUuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _ownScope(actor: User, membership: institutions.Membership):
    """Actividad PROPIA del operador, siempre con el identificador del usuario autenticado y de su vínculo (nunca por nombre):
      - lo que él hizo (Audit.idUsuario);
      - las transferencias que otros le solicitaron (él es el operador destino);
      - los pacientes que otro le asignó o le dio de alta a su cargo (su vínculo figura como responsable).
    La institución la fija listActivity (Audit.idInstitucion = ruta validada)."""
    relation = str(membership.relation.idInstitucionUsuario)
    received = and_(
        Audit.accion == "SOLICITAR_TRANSFERENCIA_PERFIL", Audit.tablaAfectada == "TransferenciaPerfil",
        Audit.idRegistro.in_(select(ProfileTransfer.idTransferenciaPerfil).where(
            ProfileTransfer.idOperadorDestino == membership.relation.idInstitucionUsuario)))
    assigned = and_(Audit.accion.in_(("ASIGNAR_RESPONSABLE_PACIENTE", "CREAR_PACIENTE")), Audit.datosNuevos.contains(relation))
    return or_(Audit.idUsuario == actor.idUsuario, received, assigned)


def _signature(audit: Audit) -> tuple:
    """Misma operación registrada dos veces (mismo hecho al mismo segundo): se muestra una sola vez."""
    return (audit.accion, audit.idRegistro, audit.idRelacionado, audit.datosNuevos, audit.fechaHora.replace(microsecond=0))


def listActivity(db: Session, actor: User, idInstitucion: uuid.UUID, limit: int = 5) -> ActivityPage:
    """Últimas actividades relevantes de la institución, ordenadas globalmente de la más reciente a la más antigua."""
    membership = institutions.requireMembership(db, actor, idInstitucion)
    limit = max(1, min(limit, MAX_LIMIT))
    canAudit = membership.can(institutions.P_AUDITORIA)
    ownOnly = membership.role == institutions.ROL_OPERADOR  # el operador ve solo su propia actividad (ver _ownScope)
    shown = or_(and_(Audit.resultado == "EXITO", Audit.accion.in_(list(CATALOG))))
    if canAudit:  # las operaciones rechazadas son para quien audita
        shown = or_(shown, and_(Audit.resultado == "FALLO", Audit.tipoEvento.in_(("PERMISO", "ACCESO"))))
    base = select(Audit).where(Audit.idInstitucion == idInstitucion, shown)
    mine: set[uuid.UUID] = set()
    if ownOnly:
        base = base.where(_ownScope(actor, membership))
        # Pacientes a cargo hoy: solo de esos se ofrece abrir la ficha o la medición (el resto ya no es consultable).
        mine = set(db.scalars(select(MeasurementProfile.idPerfilMedicion).where(
            MeasurementProfile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario)))
    else:
        base = base.where(Audit.accion != "INICIAR_MEDICION")
    # Sin nombres de pacientes: solo su seudónimo; y quien no es el operador responsable no ve de qué paciente es un evento de medición.
    resolver = Resolver(db, idInstitucion, identify=False, maskMeasurements=not ownOnly)
    items: list[ActivityItem] = []
    seen: set = set()
    offset = 0
    while len(items) < limit and offset < MAX_ROWS:
        rows = db.scalars(base.order_by(Audit.fechaHora.desc(), Audit.idAuditoria).offset(offset).limit(BATCH)).all()
        if not rows:
            break
        offset += BATCH
        resolver.prepare(rows)  # una resolución agrupada de nombres por lote, no una consulta por evento
        for audit in rows:
            if len(items) >= limit:
                break
            snapshot = _json(audit.detalle)
            key = _signature(audit)
            if key in seen:
                continue
            if audit.resultado == "FALLO":
                label = ACTION_LABELS.get(audit.accion) or audit.accion.replace("_", " ").capitalize()
                item = ActivityItem(titulo=f"Operación rechazada: {label}", categoria="SEGURIDAD", entidad=resolver.entityLabel(audit, snapshot),
                                    usuario=resolver.actor(audit, snapshot), fechaHora=audit.fechaHora, resultado="FALLO", critica=True,
                                    rechazado=True, ruta=f"auditoria/{audit.idAuditoria}", idAuditoria=audit.idAuditoria)
            else:
                classified = _classify(audit, resolver, snapshot)
                if classified is None:
                    continue
                category, title = classified
                if category == "MEDICIONES" and not ownOnly:
                    continue
                permission = CATEGORY_PERMISSION[category]
                if permission is not None and not membership.can(permission):
                    continue
                entity = None if category == "INSTITUCION" else resolver.entityLabel(audit, snapshot)
                # Solo se ofrece una ruta si el rol puede abrir esa pantalla.
                route = _route(category, audit) if permission is None or membership.can(permission) else None
                if category == "MEDICIONES":
                    patient = _json(audit.datosNuevos).get("idPerfilMedicion")
                    route = f"pacientes/{patient}/mediciones/{audit.idRegistro}" if patient and _asUuid(patient) in mine else None
                elif ownOnly and route and route.startswith("pacientes/") and audit.tablaAfectada == "PerfilMedicion" and audit.idRegistro not in mine:
                    route = None  # un paciente que ya no está a su cargo no se abre
                item = ActivityItem(titulo=title, categoria=category, entidad=entity, usuario=resolver.actor(audit, snapshot),
                                    fechaHora=audit.fechaHora, resultado="EXITO", critica=audit.accion in ACCIONES_CRITICAS, ruta=route,
                                    idAuditoria=audit.idAuditoria if canAudit else None)
            seen.add(key)
            items.append(item)
    return ActivityPage(items=items)
