# PlatformInstitutions - Control operativo de instituciones desde la administración de la plataforma (administrador y moderador del sistema)
#
# Reutiliza los estados existentes (Institucion.estado: ACTIVA, INACTIVA, CERRADA) y la auditoría; no crea estructuras nuevas.
#   - Pausar:     ACTIVA → INACTIVA. Desde ese instante institution.requireMembership rechaza todo contexto institucional (INSTITUCION_PAUSADA) en
#                 CADA pedido con cualquier token ya emitido, porque el estado se lee de la base; además acquisition y telemetry solo reconocen
#                 instituciones ACTIVAS. No se elimina ni se modifica ningún dato: cuentas, pacientes, mediciones, dispositivos e historiales siguen.
#   - Reactivar:  INACTIVA → ACTIVA. No toca bloqueos individuales de cuentas ni sesiones revocadas (son controles independientes).
#   - Cupos:      cambia el máximo de cuentas internas (no pacientes ni grupos). Puede quedar por debajo de las cuentas activas: se conservan, la
#                 institución queda EXCEDIDA y no admite cuentas nuevas que consuman cupo (quota.requireSlot) hasta regularizarse.
#   - Auditoría:  eventos administrativos y de seguridad de la institución, también si está pausada o cerrada, sin datos clínicos ni secretos.
#
# La transición de estado y su evidencia se confirman en UNA transacción (UPDATE condicionado al estado vigente + registerEvent + commit): no
# existe un cambio sin su registro. El motivo vigente de una pausa se lee del último evento PAUSAR_INSTITUCION.

import json
import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.audit import Audit
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.platform import (
    AdministrativeClosure, CapacityChange, InstitutionAction, InstitutionAuditItem, InstitutionAuditPage, InstitutionDeletion, Suspension,
)
from app.services import institution as institutions
from app.services import accountGrace, platform, quota, schemaCompat
from app.services import email as emailService
from app.services.audit import ACCIONES_CRITICAS, registerEvent
from app.utils.timeZone import nowForDb

MODULE = "INSTITUCIONES"
ACTIVA, INACTIVA, CERRADA = "ACTIVA", "INACTIVA", "CERRADA"
MAX_AUDIT_PAGE = 50

ROLE_LABEL = {platform.ADMIN: "Administrador del sistema", platform.MOD: "Moderador del sistema"}

# Categorías de la auditoría de una institución -> acciones que las componen (el filtro de categoría usa SOLO esta lista cerrada).
CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "REGISTRO": ("Registro de la institución", ("CREAR_INSTITUCION", "MODIFICAR_INSTITUCION")),
    "PAUSA": ("Pausa y reactivación", ("PAUSAR_INSTITUCION", "REACTIVAR_INSTITUCION", "SOLICITAR_SOPORTE_INSTITUCION")),
    "CIERRE": ("Cierre y eliminación", ("ELIMINAR_INSTITUCION", "REABRIR_INSTITUCION", "ELIMINAR_INSTITUCION_ADMINISTRATIVA")),
    "CUPOS": ("Modificación de cupos", ("MODIFICAR_CUPOS_INSTITUCION",)),
    "CUENTAS": ("Alta y baja de cuentas", ("INVITAR_MIEMBRO_INSTITUCION", "REENVIAR_INVITACION_INSTITUCION", "CANCELAR_INVITACION_INSTITUCION",
                                           "ACEPTAR_INVITACION_INSTITUCION", "RECHAZAR_INVITACION_INSTITUCION", "RESPONDER_INVITACION_INSTITUCION",
                                           "CREAR_CUENTA_INVITADA", "ACTIVAR_CUENTA_INVITADA", "REVOCAR_MIEMBRO_INSTITUCION",
                                           "MODIFICAR_MIEMBRO_INSTITUCION")),
    "EXPORTACIONES": ("Exportaciones de datos", ()),  # acciones EXPORT*: hoy GlucoLume no tiene función de exportación
    "AUTENTICACION": ("Intentos fallidos de autenticación", ()),
    "SEGURIDAD": ("Eventos de seguridad", ()),
}
LABELS = {
    "CREAR_INSTITUCION": "Registro de la institución", "MODIFICAR_INSTITUCION": "Modificación de datos de la institución",
    "SOLICITAR_SOPORTE_INSTITUCION": "Consulta del propietario al soporte", "PAUSAR_INSTITUCION": "Pausa de la institución", "REACTIVAR_INSTITUCION": "Reactivación de la institución",
    "ELIMINAR_INSTITUCION": "Cierre de la institución", "REABRIR_INSTITUCION": "Reapertura de la institución",
    "ELIMINAR_INSTITUCION_ADMINISTRATIVA": "Eliminación administrativa", "MODIFICAR_CUPOS_INSTITUCION": "Modificación del límite de cuentas",
    "INVITAR_MIEMBRO_INSTITUCION": "Invitación de una cuenta", "REENVIAR_INVITACION_INSTITUCION": "Reenvío de invitación",
    "CANCELAR_INVITACION_INSTITUCION": "Invitación cancelada", "ACEPTAR_INVITACION_INSTITUCION": "Invitación aceptada (alta de cuenta)",
    "RECHAZAR_INVITACION_INSTITUCION": "Invitación rechazada", "RESPONDER_INVITACION_INSTITUCION": "Respuesta a una invitación",
    "CREAR_CUENTA_INVITADA": "Cuenta creada por invitación", "ACTIVAR_CUENTA_INVITADA": "Cuenta activada",
    "REVOCAR_MIEMBRO_INSTITUCION": "Baja de una cuenta", "MODIFICAR_MIEMBRO_INSTITUCION": "Datos administrativos de una cuenta",
    "LOGIN_LOCAL": "Inicio de sesión", "LOGIN_GOOGLE": "Inicio de sesión con Google",
}
SAFE_KEYS = {"estado", "capacidadMaximaUsuarios", "usuariosActivos", "excedente", "rolActor", "motivo"}
# Módulos que muestra la auditoría de la institución: administrativos y de seguridad. Nunca los de pacientes y mediciones.
ADMIN_MODULES = ("INSTITUCIONES", "CUENTA", "DISPOSITIVOS", "MATRICES", "AUDITORIA")


def _institution(db: Session, idInstitucion: uuid.UUID) -> Institution:
    institution = db.get(Institution, idInstitucion)
    if institution is None:
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución.")
    return institution


def _require(db: Session, actor: User, permission: str) -> None:
    platform.requirePermission(db, actor, permission)
    platform.requireMfaEnabled(db, actor)


def _owners(db: Session, idInstitucion: uuid.UUID) -> list[User]:
    return list(db.scalars(
        select(User).join(InstitutionUser, InstitutionUser.idUsuarioInvitado == User.idUsuario).where(
            InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == "PROPIETARIO",
            InstitutionUser.estadoRelacion == "ACTIVO", User.estado == "ACTIVO", User.correoElectronico.is_not(None))))


def _notifyOwners(db: Session, institution: Institution, event: EmailEventType, now: datetime, motivo: str | None = None) -> None:
    for owner in _owners(db, institution.idInstitucion):
        context = {"nombre": owner.nombre, "nombreInstitucion": institution.nombre, "fechaEvento": now}
        if motivo is not None:
            context["motivo"] = motivo
        emailService.sendEmailEventInBackground(event, owner.correoElectronico, context)


def _deny(db: Session, actor: User, action: str, idInstitucion: uuid.UUID, error: AuthError) -> AuthError:
    """Un intento rechazado también deja evidencia (con el código del rechazo)."""
    db.rollback()
    registerEvent(db, "PERMISO", action, False, actor.idUsuario, "Institucion", idInstitucion, idInstitucion=idInstitucion, modulo=MODULE,
                  observacion=f"Rechazada: {error.code}", datosNuevos={"rolActor": actor.tipoCuenta})
    db.commit()
    return error


def _transition(db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionAction, *, action: str, source: str, target: str,
                notFound: str, message: str) -> Institution:
    institution = _institution(db, idInstitucion)
    now = nowForDb()
    # Condicionado al estado vigente: dos pausas (o una pausa y una eliminación) simultáneas no se aplican ambas.
    changed = db.execute(update(Institution).where(Institution.idInstitucion == idInstitucion, Institution.estado == source)
                         .values(estado=target, fechaActualizacion=now).execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        db.refresh(institution)
        raise _deny(db, actor, action, idInstitucion, AuthError(notFound, f"{message} Estado actual: {institution.estado}."))
    # La evidencia va en la MISMA transacción: si registrar o confirmar falla, el estado no cambia.
    try:
        registerEvent(db, "CRUD", action, True, actor.idUsuario, "Institucion", idInstitucion, idInstitucion=idInstitucion, modulo=MODULE,
                      observacion=f"Motivo: {data.motivo}", datosPrevios={"estado": source},
                      datosNuevos={"estado": target, "rolActor": actor.tipoCuenta, "motivo": data.motivo})
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(institution)
    return institution


def pause(db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionAction) -> Institution:
    """ACTIVA → INACTIVA con motivo. Efecto inmediato y total sobre el contexto institucional (ver el encabezado)."""
    _require(db, actor, "GESTIONAR_ESTADO_INSTITUCIONES")
    institution = _transition(db, actor, idInstitucion, data, action="PAUSAR_INSTITUCION", source=ACTIVA, target=INACTIVA,
                              notFound="INSTITUCION_NO_PAUSABLE", message="Solo se puede pausar una institución activa.")
    _notifyOwners(db, institution, EmailEventType.INSTITUCION_PAUSADA, institution.fechaActualizacion, data.motivo)
    return institution


def reactivate(db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionAction) -> Institution:
    """INACTIVA → ACTIVA con motivo. No levanta bloqueos individuales de cuentas ni restablece sesiones revocadas: no los toca."""
    _require(db, actor, "GESTIONAR_ESTADO_INSTITUCIONES")
    institution = _transition(db, actor, idInstitucion, data, action="REACTIVAR_INSTITUCION", source=INACTIVA, target=ACTIVA,
                              notFound="INSTITUCION_NO_REACTIVABLE", message="Solo se puede reactivar una institución pausada.")
    _notifyOwners(db, institution, EmailEventType.INSTITUCION_REACTIVADA, institution.fechaActualizacion)
    return institution


def _data(value: str | None) -> dict:
    try:
        loaded = json.loads(value) if value else {}
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def currentSuspension(db: Session, institution: Institution) -> Suspension | None:
    """Motivo, fecha y rol del actor de la pausa vigente: el último PAUSAR_INSTITUCION exitoso de la institución (None si el estado se cambió
    fuera de la aplicación y no hay evidencia)."""
    event = db.scalar(select(Audit).where(Audit.idInstitucion == institution.idInstitucion, Audit.accion == "PAUSAR_INSTITUCION",
                                          Audit.resultado == "EXITO").order_by(Audit.fechaHora.desc(), Audit.idAuditoria).limit(1))
    if event is None:
        return None
    new = _data(event.datosNuevos)
    return Suspension(motivo=new.get("motivo"), fecha=event.fechaHora, rolActor=new.get("rolActor"))


def administrativeClosure(db: Session, institution: Institution) -> AdministrativeClosure | None:
    """Cierre hecho por la plataforma, leído de la FILA de la institución (fuente de verdad; no depende de la auditoría, que la política de
    conservación puede depurar). None si la cerró su propietario, si no está cerrada o si la base instalada no tiene las columnas de cierre administrativo (esquema v5)."""
    if institution.estado != CERRADA or not schemaCompat.administrativeClosureReady(db):
        return None
    table = Institution.__table__
    row = db.execute(select(table.c.cierreAdministrativo, table.c.fechaCierreAdministrativo, table.c.motivoCierreAdministrativo,
                            table.c.idUsuarioCierreAdministrativo).where(table.c.idInstitucion == institution.idInstitucion)).one()
    if not row.cierreAdministrativo:
        return None
    role = db.scalar(select(User.tipoCuenta).where(User.idUsuario == row.idUsuarioCierreAdministrativo))
    return AdministrativeClosure(motivo=row.motivoCierreAdministrativo, fecha=row.fechaCierreAdministrativo, rolActor=role)


def deleteInstitution(db: Session, actor: User, idInstitucion: uuid.UUID, data: InstitutionDeletion) -> Institution:
    """Eliminación ADMINISTRATIVA (solo el administrador, `ELIMINAR_INSTITUCIONES`, con MFA obligatoria y reautenticación reforzada). Es el MISMO cierre
    lógico del propietario (institution.applyLogicalClosure: vínculos de baja, recursos liberados, período de gracia, retención de pacientes; nunca un
    DELETE físico ni se destruyen datos clínicos) más la marca de cierre administrativo (actor, fecha y motivo), todo y la auditoría en UNA transacción.
    Una institución así cerrada no la puede reabrir su último propietario. Admite ACTIVA o INACTIVA (pausada)."""
    _require(db, actor, "ELIMINAR_INSTITUCIONES")
    if not schemaCompat.administrativeClosureReady(db):
        raise AuthError("ELIMINACION_ADMINISTRATIVA_NO_DISPONIBLE",
                        "La base de datos instalada no tiene el cierre administrativo del esquema vigente: no se puede eliminar la institución desde la plataforma. Consultá a la administración del sistema.")
    institution = _institution(db, idInstitucion)
    if institution.estado not in (ACTIVA, INACTIVA):
        raise _deny(db, actor, "ELIMINAR_INSTITUCION_ADMINISTRATIVA", idInstitucion,
                    AuthError("INSTITUCION_NO_ELIMINABLE", "La institución ya está cerrada."))
    if data.confirmacionNombre.strip().casefold() != institution.nombre.strip().casefold():
        raise _deny(db, actor, "ELIMINAR_INSTITUCION_ADMINISTRATIVA", idInstitucion,
                    AuthError("CONFIRMACION_INVALIDA", "Escribí el nombre exacto de la institución para confirmar."))
    platform.reauthenticate(db, actor, data.reautenticacion, "ELIMINAR_INSTITUCION_ADMINISTRATIVA")  # registra sus propios fallos

    now = nowForDb()
    previous = institution.estado
    name = institution.nombre
    try:
        closure = institutions.applyLogicalClosure(
            db, idInstitucion, actor.idUsuario, now, fromStates=(ACTIVA, INACTIVA),
            extraValues={"cierreAdministrativo": True, "fechaCierreAdministrativo": now, "idUsuarioCierreAdministrativo": actor.idUsuario,
                         "motivoCierreAdministrativo": data.motivo})
        if closure is None:  # otra solicitud la cerró entre medio
            raise _deny(db, actor, "ELIMINAR_INSTITUCION_ADMINISTRATIVA", idInstitucion,
                        AuthError("INSTITUCION_NO_ELIMINABLE", "La institución ya está cerrada."))
        registerEvent(db, "CRUD", "ELIMINAR_INSTITUCION_ADMINISTRATIVA", True, actor.idUsuario, "Institucion", idInstitucion,
                      idInstitucion=idInstitucion, modulo=MODULE, observacion=f"Motivo: {data.motivo}", datosPrevios={"estado": previous},
                      datosNuevos={"estado": CERRADA, "cierreAdministrativo": True, "rolActor": actor.tipoCuenta, "motivo": data.motivo,
                                   "vinculosDadosDeBaja": closure.ended, "perfilesEnConservacion": closure.profiles,
                                   "finConservacionDatos": closure.retentionEnd.isoformat(), "cuentasEnPeriodoGracia": len(closure.graced)})
        db.commit()
    except AuthError:
        raise
    except Exception:
        db.rollback()
        raise
    for user in closure.graced:
        accountGrace.notifyStarted(user, now)
    for member in closure.members:
        if member.correoElectronico:
            emailService.sendEmailEventInBackground(EmailEventType.INSTITUCION_ELIMINADA_ADMINISTRATIVAMENTE, member.correoElectronico,
                                                    {"nombre": member.nombre, "nombreInstitucion": name, "fechaEvento": now})
    db.expire_all()
    return _institution(db, idInstitucion)


def changeCapacity(db: Session, actor: User, idInstitucion: uuid.UUID, data: CapacityChange):
    """Cambia el máximo de cuentas internas. Puede ser menor que las activas (quedan excedidas y nada se elimina ni se suspende). Bloquea la
    institución con el mismo mecanismo de las altas (quota.lockInstitution), así que un alta concurrente ve el límite viejo o el nuevo, nunca
    una mezcla. Audita el límite anterior y el nuevo."""
    _require(db, actor, "GESTIONAR_CUPOS_INSTITUCIONES")
    institution = _institution(db, idInstitucion)
    if institution.estado == CERRADA:
        raise AuthError("INSTITUCION_CERRADA", "La institución está cerrada: no se modifica su límite de cuentas.")
    if not schemaCompat.hasColumn(db, "Institucion", "capacidadMaximaUsuarios"):
        raise AuthError("CAPACIDAD_NO_DISPONIBLE", "La base de datos instalada no tiene el límite de cuentas del esquema vigente: no se puede modificar. Consultá a la administración del sistema.")
    quota.validateNewCapacity(db, idInstitucion, data.capacidadMaxima)
    quota.lockInstitution(db, idInstitucion)
    previous = quota.capacityOf(db, idInstitucion)
    active = quota.activeCount(db, idInstitucion)
    table = Institution.__table__
    try:
        db.execute(update(table).where(table.c.idInstitucion == idInstitucion)
                   .values(capacidadMaximaUsuarios=data.capacidadMaxima, fechaActualizacion=nowForDb()))
        registerEvent(db, "CRUD", "MODIFICAR_CUPOS_INSTITUCION", True, actor.idUsuario, "Institucion", idInstitucion, idInstitucion=idInstitucion,
                      modulo=MODULE, observacion=f"Motivo: {data.motivo}", datosPrevios={"capacidadMaximaUsuarios": previous},
                      datosNuevos={"capacidadMaximaUsuarios": data.capacidadMaxima, "usuariosActivos": active,
                                   "excedente": max(0, active - data.capacidadMaxima), "rolActor": actor.tipoCuenta, "motivo": data.motivo})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return quota.usage(db, idInstitucion)


# --- Auditoría de una institución ---------------------------------------------------------------------------------------------------


def _memberIds(idInstitucion: uuid.UUID):
    return select(InstitutionUser.idUsuarioInvitado).where(InstitutionUser.idInstitucion == idInstitucion)


def _scope(idInstitucion: uuid.UUID):
    """Eventos de la institución (módulos administrativos y de seguridad) y los intentos fallidos de acceso de sus integrantes."""
    own = and_(Audit.idInstitucion == idInstitucion, Audit.modulo.in_(ADMIN_MODULES))
    failedLogins = and_(Audit.tipoEvento == "LOGIN", Audit.resultado == "FALLO", Audit.idUsuario.in_(_memberIds(idInstitucion)))
    return or_(own, failedLogins)


def _category(audit: Audit) -> str:
    action = audit.accion or ""
    for key, (_, actions) in CATEGORIES.items():
        if action in actions:
            return key
    if action.startswith("EXPORT"):
        return "EXPORTACIONES"
    if audit.tipoEvento == "LOGIN":
        return "AUTENTICACION"
    return "SEGURIDAD" if audit.resultado == "FALLO" or action in ACCIONES_CRITICAS else "OTROS"


def _categoryFilter(key: str):
    if key not in CATEGORIES:
        raise AuthError("DATOS_INVALIDOS", "La categoría de auditoría no es válida.")
    actions = CATEGORIES[key][1]
    if key == "EXPORTACIONES":
        return Audit.accion.like("EXPORT%")
    if key == "AUTENTICACION":
        return and_(Audit.tipoEvento == "LOGIN", Audit.resultado == "FALLO")
    if key == "SEGURIDAD":
        return or_(Audit.resultado == "FALLO", Audit.accion.in_(ACCIONES_CRITICAS))
    return Audit.accion.in_(actions)


def _actorLabel(actor: User | None) -> str:
    if actor is None:
        return "Sistema"
    return ROLE_LABEL.get(actor.tipoCuenta) or ("Cuenta institucional" if actor.tipoCuenta == "USUARIO_INSTITUCIONAL" else "Cuenta")


def auditPage(db: Session, actor: User, idInstitucion: uuid.UUID, *, categoria: str | None = None, resultado: str | None = None,
              desde: datetime | None = None, hasta: datetime | None = None, pagina: int = 1, tamanio: int = 20) -> InstitutionAuditPage:
    """Eventos administrativos y de seguridad de la institución, disponibles aunque esté pausada o cerrada. Devuelve solo atributos de una
    lista cerrada: nada de pacientes, mediciones, contraseñas, tokens, códigos ni IP; el actor, solo por su tipo."""
    _require(db, actor, "AUDITAR_INSTITUCIONES")
    _institution(db, idInstitucion)
    if resultado is not None and resultado not in ("EXITO", "FALLO"):
        raise AuthError("DATOS_INVALIDOS", "El resultado no es válido.")
    tamanio = max(1, min(tamanio, MAX_AUDIT_PAGE))
    pagina = max(1, pagina)
    conditions = [_scope(idInstitucion)]
    if categoria:
        conditions.append(_categoryFilter(categoria))
    if resultado:
        conditions.append(Audit.resultado == resultado)
    if desde:
        conditions.append(Audit.fechaHora >= desde)
    if hasta:
        conditions.append(Audit.fechaHora <= hasta)
    total = db.scalar(select(func.count()).select_from(Audit).where(*conditions)) or 0
    rows = db.execute(select(Audit, User).outerjoin(User, User.idUsuario == Audit.idUsuario).where(*conditions)
                      .order_by(Audit.fechaHora.desc(), Audit.idAuditoria).offset((pagina - 1) * tamanio).limit(tamanio)).all()
    items = []
    for audit, user in rows:
        previous, new = _data(audit.datosPrevios), _data(audit.datosNuevos)
        items.append(InstitutionAuditItem(
            idAuditoria=audit.idAuditoria, fechaHora=audit.fechaHora, categoria=_category(audit), accion=audit.accion,
            etiqueta=LABELS.get(audit.accion) or audit.accion.replace("_", " ").capitalize(), resultado=audit.resultado, actor=_actorLabel(user),
            motivo=new.get("motivo") if audit.accion in ("PAUSAR_INSTITUCION", "REACTIVAR_INSTITUCION", "MODIFICAR_CUPOS_INSTITUCION") else None,
            estadoAnterior=previous.get("estado"), estadoNuevo=new.get("estado"),
            limiteAnterior=previous.get("capacidadMaximaUsuarios"), limiteNuevo=new.get("capacidadMaximaUsuarios"),
            cuentasActivas=new.get("usuariosActivos"), excedente=new.get("excedente")))
    return InstitutionAuditPage(items=items, total=total, pagina=pagina, tamanioPagina=tamanio,
                                categorias={key: label for key, (label, _) in CATEGORIES.items()})
