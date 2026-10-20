# PlatformDashboard - Indicadores globales de GlucoLume para el panel de administración
#
# Solo agregados calculados con consultas reales: ni nombres, ni correos, ni resultados clínicos identificables. El
# administrador del sistema ve todo; el moderador, solo la parte técnica (dispositivos, mediciones agregadas, estado del
# sistema). Los eventos de actividad muestran módulo, acción y resultado, nunca quién los hizo.

import socket
import time
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import getSettings
from app.models.audit import Audit
from app.models.device import Device
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.technicalAudit import TechnicalAudit
from app.models.measurement import NOT_DEMO, Measurement
from app.models.user import User
from app.schemas.dashboard import DayCount
from app.core.exceptions import AuthError
from app.schemas.platform import (
    ActivityEvent,
    CountBy,
    DeviceCounters,
    GroupCounters,
    InstitutionCounters,
    InstitutionDetail,
    InstitutionDevice,
    InstitutionPage,
    InstitutionRow,
    MeasurementCounters,
    ModuleActivity,
    PlatformDashboard,
    SecuritySummary,
    SystemComponent,
    SystemStatus,
    UserCounters,
)
from app.services import auditClassification as classification
from app.services import authAccess
from app.services import dashboard as dashboards
from app.services import institution as institutions
from app.services import platform, quota, schemaCompat
from app.services.audit import ACCIONES_CRITICAS
from app.utils.timeZone import nowForDb

RECENT = 10
INVALID_WINDOW_DAYS = 7
COMPLETADA = "COMPLETADA"


def _count(db: Session, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def _users(db: Session, start: datetime, end: datetime | None) -> UserCounters:
    live = User.estado != "ELIMINADO"
    byType = dict(db.execute(select(User.tipoCuenta, func.count()).where(live).group_by(User.tipoCuenta)).all())
    platformAccounts = byType.get("ADMINISTRADOR_PLATAFORMA", 0) + byType.get("MODERADOR_PLATAFORMA", 0)
    institutional = byType.get("USUARIO_INSTITUCIONAL", 0)
    # «Cuentas internas»: personas con vínculo ACTIVO en alguna institución, contadas una sola vez aunque tengan varios roles o instituciones.
    withBond = db.scalar(select(func.count(func.distinct(InstitutionUser.idUsuarioInvitado)))
                         .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
                         .where(InstitutionUser.estadoRelacion == "ACTIVO", live)) or 0
    return UserCounters(
        total=sum(byType.values()), individuales=byType.get("CONSUMIDOR_FINAL", 0), institucionales=institutional, plataforma=platformAccounts,
        activas=_count(db, User, User.estado == "ACTIVO"), inactivas=_count(db, User, User.estado.in_(["PENDIENTE", "BLOQUEADO"])),
        conVinculoInstitucional=withBond, institucionalesSinVinculo=max(0, institutional - withBond),
        registradasPeriodo=_count(db, User, live, *dashboards._inPeriod(User.fechaCreacion, start, end)),
        registradas7Dias=_count(db, User, live, User.fechaCreacion >= nowForDb() - timedelta(days=7)),
    )


def _institutions(db: Session) -> InstitutionCounters:
    active = InstitutionUser.estadoRelacion == "ACTIVO"
    states = dict(db.execute(select(Institution.estado, func.count()).group_by(Institution.estado)).all())
    return InstitutionCounters(
        total=sum(states.values()), activas=states.get("ACTIVA", 0), cerradas=states.get("CERRADA", 0), inactivas=states.get("INACTIVA", 0),
        moderadores=_count(db, InstitutionUser, active, InstitutionUser.rolInstitucion == "MODERADOR"),
        operadores=_count(db, InstitutionUser, active, InstitutionUser.rolInstitucion == "OPERADOR"),
    )


def _groups(db: Session) -> GroupCounters:
    activeGroups = select(Group.idGrupo).where(Group.estado == "ACTIVO")
    return GroupCounters(
        total=_count(db, Group), activos=_count(db, Group, Group.estado == "ACTIVO"),
        usuariosAgrupados=_count(db, GroupUser, GroupUser.estadoRelacion == "ACTIVO", GroupUser.idGrupo.in_(activeGroups)),
    )


def _devices(db: Session) -> DeviceCounters:
    states = dict(db.execute(select(Device.estado, func.count()).group_by(Device.estado)).all())
    live = Device.estado != "BAJA"
    recentInvalid = db.scalar(select(func.count(func.distinct(Measurement.idDispositivo))).where(
        Measurement.estadoMedicion == "INVALIDA", Measurement.fechaHoraInicio >= nowForDb() - timedelta(days=INVALID_WINDOW_DAYS))) or 0
    return DeviceCounters(
        total=sum(states.values()), operativos=states.get("OPERATIVO", 0), enMantenimiento=states.get("EN_MANTENIMIENTO", 0),
        fueraDeServicio=states.get("FUERA_DE_SERVICIO", 0), descomisionados=states.get("BAJA", 0),
        asignados=_count(db, Device, live, Device.idInstitucionAsignada.is_not(None)),
        sinAsignar=_count(db, Device, live, Device.idInstitucionAsignada.is_(None)),
        conLecturasInvalidasRecientes=recentInvalid, desconectados=None, conexionVerificable=False,
    )


def _measurements(db: Session, start: datetime, end: datetime | None) -> MeasurementCounters:
    states = dict(db.execute(select(Measurement.estadoMedicion, func.count()).where(NOT_DEMO)
                             .group_by(Measurement.estadoMedicion)).all())
    modes = dict(db.execute(select(Measurement.modoMedicion, func.count()).where(NOT_DEMO)
                            .group_by(Measurement.modoMedicion)).all())
    rows = db.execute(select(Measurement.fechaHoraInicio, Measurement.estadoMedicion).where(
        NOT_DEMO, *dashboards._inPeriod(Measurement.fechaHoraInicio, start, end))).all()
    byDay: dict[date, list[int]] = {}
    for moment, state in rows:
        bucket = byDay.setdefault(moment.date(), [0, 0])
        bucket[0] += 1
        bucket[1] += state == COMPLETADA
    techInPeriod = dashboards._inPeriod(TechnicalAudit.fechaHora, start, end)
    reasons = db.execute(select(TechnicalAudit.motivo, func.count()).where(*techInPeriod).group_by(TechnicalAudit.motivo)
                         .order_by(func.count().desc()).limit(8)).all()
    return MeasurementCounters(
        demo=_count(db, Measurement, Measurement.origenGlucosa == "DEMO", *dashboards._inPeriod(Measurement.fechaHoraInicio, start, end)),
        erroresTecnicos=_count(db, TechnicalAudit, *techInPeriod), motivosTecnicos=[CountBy(clave=r[0], total=r[1]) for r in reasons],
        total=sum(states.values()), enPeriodo=len(rows), oximetria=modes.get("OXIMETRIA", 0),
        glucosaExperimental=modes.get("GLUCOSA_EXPERIMENTAL", 0), completadas=states.get(COMPLETADA, 0),
        canceladas=states.get("CANCELADA", 0), invalidas=states.get("INVALIDA", 0), porEstado=states,
        serie=[DayCount(fecha=day, total=total, completadas=done) for day, (total, done) in sorted(byDay.items())],
    )


def _events(db: Session, *conditions) -> list[ActivityEvent]:
    rows = db.scalars(select(Audit).where(*conditions).order_by(Audit.fechaHora.desc(), Audit.idAuditoria).limit(RECENT)).all()
    return [ActivityEvent(idAuditoria=r.idAuditoria, fechaHora=r.fechaHora, modulo=r.modulo, accion=r.accion, resultado=r.resultado)
            for r in rows]


def _security(db: Session, start: datetime, end: datetime | None) -> SecuritySummary:
    """Solo conteos del período, a partir de la auditoría real (LOGIN / PLATAFORMA) y del estado actual de las cuentas."""
    inPeriod = dashboards._inPeriod(Audit.fechaHora, start, end)
    # Qué es un acceso fallido o correcto y a qué tipo de cuenta pertenece: services/authAccess.py (una definición y una consulta para el total y los tipos).
    access = authAccess.breakdown(db, start, end)
    failed = and_(authAccess.failedCondition(), *inPeriod)
    reasons = db.execute(select(func.coalesce(Audit.observacion, Audit.accion), func.count()).where(failed)
                         .group_by(func.coalesce(Audit.observacion, Audit.accion)).order_by(func.count().desc()).limit(5)).all()
    repeated = db.scalar(select(func.count()).select_from(
        select(Audit.idUsuario).where(failed, Audit.accion == "LOGIN_LOCAL", Audit.idUsuario.is_not(None))
        .group_by(Audit.idUsuario).having(func.count() >= 3).subquery())) or 0
    now = nowForDb()
    return SecuritySummary(
        loginsFallidos=access.fallidos, loginsExitosos=access.exitosos, accesosPorTipo=access,
        motivosFallo=[CountBy(clave=r[0] or "SIN_MOTIVO", total=r[1]) for r in reasons],
        cuentasBloqueadas=_count(db, User, User.estado == "BLOQUEADO"),
        bloqueosTemporales=_count(db, LocalCredential, LocalCredential.bloqueadoHasta > now),
        cuentasConFallosRepetidos=repeated,
        eventosCriticos=_count(db, Audit, Audit.accion.in_(ACCIONES_CRITICAS), *inPeriod),
        operacionesAdministrativas=_count(db, Audit, Audit.modulo == "PLATAFORMA", *inPeriod),
        exportaciones=_count(db, Audit, Audit.accion == classification.ACCION_EXPORT_COMPLETADA, *inPeriod),  # las completadas: una por exportación
    )


def dashboard(db: Session, actor, dias: int = 30, desde: date | None = None, hasta: date | None = None) -> PlatformDashboard:
    platform.requirePlatformAccount(db, actor)
    platform.requireMfaEnabled(db, actor)
    start, end, period = dashboards._range(dias, desde, hasta)
    result = PlatformDashboard(
        alcance="ADMINISTRADOR" if actor.tipoCuenta == platform.ADMIN else "TECNICO",
        periodo=period.model_dump(mode="json"), dispositivos=_devices(db), mediciones=_measurements(db, start, end), generadoEn=nowForDb())
    if actor.tipoCuenta != platform.ADMIN:
        return result
    inPeriod = dashboards._inPeriod(Audit.fechaHora, start, end)
    result.usuarios, result.instituciones, result.grupos = _users(db, start, end), _institutions(db), _groups(db)
    result.seguridad = _security(db, start, end)
    result.actividadPorModulo = [
        ModuleActivity(modulo=row[0] or "SISTEMA", total=row[1], fallidos=row[2] or 0)
        for row in db.execute(select(Audit.modulo, func.count(), func.sum(case((Audit.resultado == "FALLO", 1), else_=0)))
                              .where(*inPeriod).group_by(Audit.modulo).order_by(func.count().desc())).all()
    ]
    result.eventosRecientes = _events(db, *inPeriod)
    result.erroresRecientes = _events(db, *inPeriod, Audit.resultado == "FALLO")
    result.operacionesAdministrativas = _events(db, *inPeriod, Audit.modulo == "PLATAFORMA")
    return result


# --- Estado de los componentes: verificaciones REALES al consultar ------------------------------------------------------------------

CONNECT_TIMEOUT = 2.0
SLOW_DB_MS = 1500


def _tcp(host: str, port: int) -> tuple[bool, int | None, str | None]:
    """Intento real de conexión TCP (sin enviar nada): (alcanzable, milisegundos, motivo del fallo)."""
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True, int((time.monotonic() - started) * 1000), None
    except OSError as error:
        return False, None, type(error).__name__


def _component(name: str, state: str, detail: str | None, verification: str, latency: int | None = None) -> SystemComponent:
    return SystemComponent(nombre=name, estado=state, detalle=detail, verificacion=verification, latenciaMs=latency)


def systemStatus(db: Session, actor) -> SystemStatus:
    """Cada componente informa lo que se comprobó DE VERDAD en este pedido: consulta a la base, cifrado de MFA, conexión TCP a SMTP y a Google,
    módulo de puerto serie y matriz global activa con reglas. OPERATIVO / DEGRADADO (responde con problemas o lento) / NO_DISPONIBLE (no
    configurado o no responde) / DESCONOCIDO (no se puede verificar desde acá)."""
    platform.requirePermission(db, actor, "CONSULTAR_ESTADO_SISTEMA")
    platform.requireMfaEnabled(db, actor)
    from concurrent.futures import ThreadPoolExecutor

    settings = getSettings()
    smtpTarget = (settings.SMTP_HOST, settings.SMTP_PORT) if settings.SMTP_HOST else None
    with ThreadPoolExecutor(max_workers=2) as pool:  # las dos conexiones de red se prueban en paralelo
        smtpFuture = pool.submit(_tcp, *smtpTarget) if smtpTarget else None
        googleFuture = pool.submit(_tcp, "accounts.google.com", 443) if settings.googleEnabled else None
        components: list[SystemComponent] = []

        started = time.monotonic()
        try:
            db.execute(text("SELECT 1"))
            ms = int((time.monotonic() - started) * 1000)
            components.append(_component("Base de datos", "DEGRADADO" if ms > SLOW_DB_MS else "OPERATIVO",
                                         f"Responde lento ({ms} ms)." if ms > SLOW_DB_MS else None, "Consulta de prueba a SQL Server", ms))
        except Exception:  # noqa: BLE001
            components.append(_component("Base de datos", "NO_DISPONIBLE", "No responde la consulta de prueba.", "Consulta de prueba a SQL Server"))

        if not settings.mfaEnabled:
            components.append(_component("Verificación en dos pasos (MFA)", "NO_DISPONIBLE", "Falta MFA_ENCRYPTION_KEY.", "Clave de cifrado configurada"))
        else:
            try:
                from app.core import security

                ok = security.decryptTotpSecret(security.encryptTotpSecret("verificacion")) == "verificacion"
                components.append(_component("Verificación en dos pasos (MFA)", "OPERATIVO" if ok else "DEGRADADO",
                                             None if ok else "El cifrado de secretos no devuelve el valor original.", "Cifrado y descifrado de un secreto de prueba"))
            except Exception:  # noqa: BLE001
                components.append(_component("Verificación en dos pasos (MFA)", "NO_DISPONIBLE", "La clave de cifrado no sirve.", "Cifrado y descifrado de un secreto de prueba"))

        if smtpFuture is None:
            components.append(_component("Correo (SMTP)", "NO_DISPONIBLE", "Falta SMTP_HOST.", "Servidor SMTP configurado"))
        else:
            reachable, ms, reason = smtpFuture.result()
            if not reachable:
                components.append(_component("Correo (SMTP)", "NO_DISPONIBLE", f"No se pudo conectar a {settings.SMTP_HOST}:{settings.SMTP_PORT} ({reason}).", "Conexión TCP al servidor SMTP"))
            elif not settings.smtpEnabled:
                components.append(_component("Correo (SMTP)", "DEGRADADO", "El servidor responde, pero faltan usuario o contraseña.", "Conexión TCP al servidor SMTP", ms))
            else:
                components.append(_component("Correo (SMTP)", "OPERATIVO", None, "Conexión TCP al servidor SMTP y credenciales configuradas", ms))

        if googleFuture is None:
            components.append(_component("Acceso con Google", "NO_DISPONIBLE", "Faltan las credenciales de Google.", "Credenciales configuradas"))
        else:
            reachable, ms, reason = googleFuture.result()
            components.append(_component("Acceso con Google", "OPERATIVO" if reachable else "DEGRADADO",
                                         None if reachable else f"No se alcanza accounts.google.com ({reason}).", "Credenciales y conexión TCP a Google", ms))

        try:
            import serial  # noqa: F401
            from serial.tools import list_ports

            ports = len(list(list_ports.comports()))
            components.append(_component("Adquisición por puerto serie (pySerial)", "OPERATIVO",
                                         f"{ports} puerto(s) serie detectado(s) en este servidor." if ports else
                                         "Sin puertos serie locales: el puente de adquisición se conecta por la API.", "Módulo pySerial y listado de puertos"))
        except ImportError:
            components.append(_component("Adquisición por puerto serie (pySerial)", "NO_DISPONIBLE", "pySerial no está instalado.", "Módulo pySerial"))
        except Exception:  # noqa: BLE001
            components.append(_component("Adquisición por puerto serie (pySerial)", "DESCONOCIDO", "No se pudieron listar los puertos.", "Módulo pySerial"))

    matrix = db.scalar(select(Matrix.idMatriz).where(Matrix.ambito == "GLOBAL", Matrix.estado == "ACTIVA").limit(1))
    if matrix is None:
        components.append(_component("Matriz global activa", "NO_DISPONIBLE", "No hay una matriz global activa.", "Matriz global en estado ACTIVA"))
    else:
        rules = db.scalar(select(func.count()).select_from(MatrixRule).where(MatrixRule.idMatriz == matrix)) or 0
        components.append(_component("Matriz global activa", "OPERATIVO" if rules else "DEGRADADO", None if rules else "La matriz activa no tiene reglas.",
                                     "Matriz global ACTIVA con sus reglas"))
    return SystemStatus(componentes=components, fecha=nowForDb())


# --- Instituciones: listado y detalle (administrador y moderador del sistema; conteos y estado técnico, nunca pacientes) -----------------------------------

MAX_INSTITUTIONS_PAGE = 100


def _requireSupervision(db: Session, actor) -> None:
    platform.requirePermission(db, actor, "SUPERVISAR_INSTITUCIONES")
    platform.requireMfaEnabled(db, actor)


def _rows(db: Session, institutionsList: list[Institution]) -> list[InstitutionRow]:
    """Una fila por institución con TODOS los conteos en consultas agrupadas (sin N+1)."""
    ids = [item.idInstitucion for item in institutionsList]
    if not ids:
        return []
    live = User.estado != "ELIMINADO"
    byRole: dict[tuple, int] = {}
    for institution, role, total in db.execute(
            select(InstitutionUser.idInstitucion, InstitutionUser.rolInstitucion, func.count(func.distinct(InstitutionUser.idUsuarioInvitado)))
            .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
            .where(InstitutionUser.idInstitucion.in_(ids), InstitutionUser.estadoRelacion == "ACTIVO", live)
            .group_by(InstitutionUser.idInstitucion, InstitutionUser.rolInstitucion)):
        byRole[(institution, role)] = total
    internal = dict(db.execute(
        select(InstitutionUser.idInstitucion, func.count(func.distinct(InstitutionUser.idUsuarioInvitado)))
        .join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion.in_(ids), InstitutionUser.estadoRelacion == "ACTIVO", live)
        .group_by(InstitutionUser.idInstitucion)).all())
    devices = dict(db.execute(select(Device.idInstitucionAsignada, func.count()).where(
        Device.idInstitucionAsignada.in_(ids), Device.estado != "BAJA").group_by(Device.idInstitucionAsignada)).all())
    closedAt = dict(db.execute(select(Audit.idInstitucion, func.max(Audit.fechaHora)).where(
        Audit.idInstitucion.in_(ids), Audit.accion == "ELIMINAR_INSTITUCION", Audit.resultado == "EXITO").group_by(Audit.idInstitucion)).all())
    table = Institution.__table__
    capacities = (dict(db.execute(select(table.c.idInstitucion, table.c.capacidadMaximaUsuarios).where(table.c.idInstitucion.in_(ids))).all())
                  if schemaCompat.hasColumn(db, "Institucion", "capacidadMaximaUsuarios") else {})
    return [
        InstitutionRow(
            idInstitucion=item.idInstitucion, nombre=item.nombre, tipoInstitucion=item.tipoInstitucion, estado=item.estado,
            fechaInicio=item.fechaCreacion, fechaFin=(closedAt.get(item.idInstitucion) or item.fechaActualizacion) if item.estado == "CERRADA" else None,
            propietarios=byRole.get((item.idInstitucion, "PROPIETARIO"), 0), moderadores=byRole.get((item.idInstitucion, "MODERADOR"), 0),
            operadores=byRole.get((item.idInstitucion, "OPERADOR"), 0), cuentasInternas=internal.get(item.idInstitucion, 0),
            limiteCuentas=capacities.get(item.idInstitucion) or quota.DEFAULT_CAPACITY,
            dispositivos=devices.get(item.idInstitucion, 0))
        for item in institutionsList
    ]


def listInstitutions(db: Session, actor, busqueda: str | None = None, estado: str | None = None, pagina: int = 1,
                     tamanio: int = 15) -> InstitutionPage:
    _requireSupervision(db, actor)
    if estado is not None and estado not in ("ACTIVA", "INACTIVA", "CERRADA"):
        raise AuthError("DATOS_INVALIDOS", "El estado de la institución no es válido.")
    tamanio = max(1, min(tamanio, MAX_INSTITUTIONS_PAGE))
    pagina = max(1, pagina)
    conditions = []
    term = (busqueda or "").strip()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Institution.nombre.like(f"%{escaped}%", escape="\\"))
    counts = dict(db.execute(select(Institution.estado, func.count()).where(*conditions).group_by(Institution.estado)).all())
    query = select(Institution).where(*conditions, *([Institution.estado == estado] if estado else []))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = db.scalars(query.order_by(Institution.nombre, Institution.idInstitucion).offset((pagina - 1) * tamanio).limit(tamanio)).all()
    return InstitutionPage(items=_rows(db, list(page)), total=total, pagina=pagina, tamanioPagina=tamanio, porEstado=counts)


def institutionDetail(db: Session, actor, idInstitucion: uuid.UUID, dias: int = 30) -> InstitutionDetail:
    _requireSupervision(db, actor)
    institution = db.get(Institution, idInstitucion)
    if institution is None:
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución.")
    row = _rows(db, [institution])[0]
    start, end, _ = dashboards._range(dias, None, None)
    profiles = dashboards._institutionProfileIds(idInstitucion)
    scope = Measurement.idPerfilMedicion.in_(profiles)
    states = dict(db.execute(select(Measurement.estadoMedicion, func.count()).where(scope).group_by(Measurement.estadoMedicion)).all())
    assigned = db.scalars(select(Device).where(Device.idInstitucionAsignada == idInstitucion, Device.estado != "BAJA")
                          .order_by(Device.codigoDispositivo)).all()
    invalid = dict(db.execute(select(Measurement.idDispositivo, func.count()).where(
        Measurement.idDispositivo.in_([d.idDispositivo for d in assigned] or [uuid.UUID(int=0)]), Measurement.estadoMedicion == "INVALIDA",
        Measurement.fechaHoraInicio >= nowForDb() - timedelta(days=INVALID_WINDOW_DAYS)).group_by(Measurement.idDispositivo)).all())
    usage = quota.usage(db, idInstitucion)
    from app.services import platformInstitutions

    suspension = platformInstitutions.currentSuspension(db, institution) if institution.estado == "INACTIVA" else None
    return InstitutionDetail(
        fila=row, suspension=suspension, estadoSinEvidencia=institution.estado == "INACTIVA" and suspension is None, excedente=usage.excedente,
        cierreAdministrativo=platformInstitutions.administrativeClosure(db, institution),
        eliminacionDisponible=schemaCompat.administrativeClosureReady(db), identificador=institution.identificadorLegal, tipoIdentificador=institution.tipoIdentificadorLegal,
        reaperturas=institution.cantidadReaperturas or 0, cupoUtilizado=usage.usuariosActivos, cuposDisponibles=usage.cuposDisponibles,
        porcentajeUtilizacion=usage.porcentajeUtilizacion,
        invitacionesPendientes=_count(db, InstitutionUser, InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.estadoRelacion == "PENDIENTE"),
        pacientesActivos=institutions._activePatientCount(db, idInstitucion),
        pacientesRegistrados=db.scalar(select(func.count()).select_from(profiles.subquery())) or 0,
        dispositivosAsignados=[InstitutionDevice(
            idDispositivo=d.idDispositivo, codigoDispositivo=d.codigoDispositivo, nombre=d.nombre, modelo=d.modelo, modeloSensor=d.modeloSensor,
            versionFirmware=d.versionFirmware, estado=d.estado, fechaAsignacion=d.fechaAsignacionInstitucional,
            lecturasInvalidasRecientes=invalid.get(d.idDispositivo, 0)) for d in assigned],
        medicionesTotal=sum(states.values()), completadas=states.get(COMPLETADA, 0), canceladas=states.get("CANCELADA", 0),
        invalidas=states.get("INVALIDA", 0),
        medicionesPeriodo=db.scalar(select(func.count()).select_from(Measurement).where(scope, *dashboards._inPeriod(Measurement.fechaHoraInicio, start, end))) or 0,
        ultimaActividad=db.scalar(select(func.max(Measurement.fechaHoraInicio)).where(scope)),
    )
