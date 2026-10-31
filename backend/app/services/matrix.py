# Matrix - Matrices de referencia y reglas para la estimación experimental de glucosa (RF42, RF43, RF47-RF49)
#
# Ámbitos (Matriz.ambito):
#   GLOBAL       catálogo de GlucoLume. Lo administran las cuentas de plataforma (MODERADOR_PLATAFORMA y
#                ADMINISTRADOR_PLATAFORMA). Es la referencia de los usuarios individuales y de las instituciones sin
#                matriz propia activa.
#   INSTITUCION  propia de una institución (idInstitucion). La administran el PROPIETARIO y el MODERADOR de esa
#                institución, que además pueden consultarla; nadie de otra institución la ve ni la modifica, ni
#                siquiera la plataforma. Tiene prioridad sobre la global dentro de su institución.
# Un moderador de plataforma NO adquiere permisos sobre matrices institucionales, y un propietario institucional
# NO puede editar una matriz global.
#
# Ciclo de vida (CK_Matriz_estado): BORRADOR → ACTIVA ⇄ INACTIVA, y ARCHIVADA (terminal; desde BORRADOR o INACTIVA).
#   - Solo un BORRADOR se edita (datos y reglas). Una versión ACTIVA/INACTIVA/ARCHIVADA es inmutable: para cambiarla
#     se crea una versión nueva (copia en BORRADOR). Así las mediciones, que guardan idMatriz, conservan siempre la
#     configuración con la que se calcularon.
#   - Activar = en una transacción, la ACTIVA del mismo ámbito pasa a INACTIVA y esta pasa a ACTIVA. Los índices
#     únicos filtrados de 016_matriz_unica_activa.sql impiden dos activas aun con pedidos simultáneos.
#   - Solo se activa una matriz válida (con reglas, sin solapamientos) y dentro de su vigencia.
#
# Reglas: dos reglas de la misma población (sexo y condición de comida) no pueden pisarse en edad ni en tiempo desde la comida, y
# no puede haber dos con las mismas condiciones. No existe «precedencia»: una configuración ambigua NO se puede guardar ni activar
# (REGLA_SOLAPADA / REGLA_DUPLICADA), así que la regla aplicable a una medición es siempre única. Una regla sin edad («edad no
# especificada», NULL) es otra población: no se pisa con las que tienen rango de edad. Los huecos de cobertura (edades sin regla)
# no bloquean: se informan como advertencias para que se revisen, y una medición sin regla aplicable no se inicia.
#
# Selección para una medición (la decide siempre el backend; el cliente nunca envía idMatriz): perfil institucional →
# matriz ACTIVA vigente de su institución y, si no existe, la global ACTIVA vigente; perfil individual → la global.
# Una matriz de rangos de referencia NO es un algoritmo de estimación: seleccionar una regla no produce ningún valor.
#
# Auditoría (Auditoria.idRegistro = idMatriz; idRelacionado = institución): solo el PROPIETARIO consulta la de su
# institución (el moderador puede modificar pero no auditar) y solo las cuentas de plataforma consultan la global.

import re
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.institution import Institution
from app.models.matrix import Matrix
from app.models.matrixRule import SEXO_CUALQUIERA, MatrixRule
from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.matrix import (
    InstitutionMatrixOverview,
    MatrixAuditEntry,
    MatrixCreateRequest,
    MatrixDetail,
    MatrixDraftUpdateRequest,
    MatrixIssue,
    MatrixItem,
    MatrixModifier,
    MatrixPermissions,
    MatrixRuleInput,
    MatrixRuleUpdateRequest,
    MatrixRuleView,
    MatrixSummary,
    MatrixValidation,
)
from app.services import institution as institutions
from app.services.audit import registerEvent
from app.services.csvExport import csvBytes, csvDate, csvText
from app.services.exportAudit import auditedExport, rejectExport
from app.utils.timeZone import nowForDb

GLOBAL, INSTITUCION = "GLOBAL", "INSTITUCION"
BORRADOR, ACTIVA, INACTIVA, ARCHIVADA = "BORRADOR", "ACTIVA", "INACTIVA", "ARCHIVADA"
PLATFORM_ACCOUNTS = ("MODERADOR_PLATAFORMA", "ADMINISTRADOR_PLATAFORMA")
ACTIVE_INDEXES = ("UX_Matriz_globalActiva", "UX_Matriz_institucionActiva")

NOT_FOUND = "No encontramos esa matriz."
RULE_NOT_FOUND = "No encontramos esa regla en la matriz."
NOT_DRAFT = "Solo se puede modificar una matriz en borrador. Para cambiar una versión ya utilizada, creá una versión nueva."
DENIED = "No tenés permiso para administrar esta matriz."


def _error(code: str, message: str) -> AuthError:
    return AuthError(code, message)


# --- Autorización por ámbito ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Access:
    matrix: Matrix
    canManage: bool
    canAudit: bool


def _isPlatform(actor: User) -> bool:
    return actor.tipoCuenta in PLATFORM_ACCOUNTS


def _institutionalRole(db: Session, actor: User, idInstitucion: uuid.UUID) -> institutions.Membership | None:
    """Vínculo ACTIVO con la institución ACTIVA (sin lanzar): quien no pertenece no existe para este módulo."""
    try:
        return institutions.requireMembership(db, actor, idInstitucion)
    except AuthError:
        return None


def _access(db: Session, actor: User, idMatriz: uuid.UUID, *, forDetail: bool = True) -> Access:
    """Resuelve qué puede hacer `actor` con la matriz. Lo que no puede ni ver se informa como inexistente."""
    matrix = db.get(Matrix, idMatriz)
    if matrix is None:
        raise _error("MATRIZ_NO_ENCONTRADA", NOT_FOUND)
    if matrix.ambito == GLOBAL:
        if _isPlatform(actor):
            # Gestionan: moderación y administración. Auditan: solo el administrador del sistema.
            return Access(matrix, True, actor.tipoCuenta == "ADMINISTRADOR_PLATAFORMA")
        # Propietario y moderador de cualquier institución consultan la matriz global ACTIVA (la que les aplica).
        if matrix.estado == ACTIVA and actor.tipoCuenta == institutions.TIPO_INSTITUCIONAL:
            for membership in _activeMemberships(db, actor):
                if membership.can(institutions.P_MATRICES):
                    return Access(matrix, False, False)
        raise _error("MATRIZ_NO_ENCONTRADA", NOT_FOUND)
    membership = _institutionalRole(db, actor, matrix.idInstitucion) if actor.tipoCuenta == institutions.TIPO_INSTITUCIONAL else None
    if membership is None:
        raise _error("MATRIZ_NO_ENCONTRADA", NOT_FOUND)
    if not membership.can(institutions.P_MATRICES):
        # Integrante sin permiso (operador): se responde como inexistente, pero el intento queda en la auditoría de
        # la institución para que su propietario lo vea.
        registerEvent(db, "PERMISO", "ACCEDER_MATRIZ", False, actor.idUsuario, "Matriz", matrix.idMatriz,
                      observacion="Motivo: PERMISO_INSUFICIENTE")
        db.commit()
        raise _error("MATRIZ_NO_ENCONTRADA", NOT_FOUND)
    return Access(matrix, True, membership.role == institutions.ROL_PROPIETARIO)


def _activeMemberships(db: Session, actor: User) -> list[institutions.Membership]:
    rows = db.execute(
        select(Institution, institutions.InstitutionUser)
        .join(institutions.InstitutionUser, institutions.InstitutionUser.idInstitucion == Institution.idInstitucion)
        .where(Institution.estado == institutions.INSTITUCION_ACTIVA,
               institutions.InstitutionUser.idUsuarioInvitado == actor.idUsuario,
               institutions.InstitutionUser.estadoRelacion == institutions.RELACION_ACTIVO)
    ).all()
    return [institutions.Membership(*row) for row in rows]


def _requireManage(db: Session, actor: User, access: Access, action: str) -> None:
    if not access.canManage:
        registerEvent(db, "PERMISO", action, False, actor.idUsuario, "Matriz", access.matrix.idMatriz,
                      observacion="Motivo: PERMISO_INSUFICIENTE",
                      tablaRelacionada="Institucion" if access.matrix.idInstitucion else None,
                      idRelacionado=access.matrix.idInstitucion)
        db.commit()
        raise _error("PERMISO_INSUFICIENTE", DENIED)


def _audit(db: Session, actor: User, action: str, matrix: Matrix, **new) -> None:
    registerEvent(db, "CRUD", action, True, actor.idUsuario, "Matriz", matrix.idMatriz,
                  datosNuevos={"ambito": matrix.ambito, "version": matrix.version, **new},
                  tablaRelacionada="Institucion" if matrix.idInstitucion else None, idRelacionado=matrix.idInstitucion)


# --- Lectura -----------------------------------------------------------------------------------------------


def _ruleCount(db: Session, idMatriz: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(MatrixRule).where(MatrixRule.idMatriz == idMatriz))


def _usage(db: Session, idMatriz: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idMatriz == idMatriz))


def _item(db: Session, matrix: Matrix) -> MatrixItem:
    return MatrixItem(
        idMatriz=matrix.idMatriz, nombre=matrix.nombre, version=matrix.version, ambito=matrix.ambito,
        estado=matrix.estado, fechaVigenciaDesde=matrix.fechaVigenciaDesde, fechaVigenciaHasta=matrix.fechaVigenciaHasta,
        descripcion=matrix.descripcion, referenciaBase=matrix.referenciaBase, urlReferencia=matrix.urlReferencia,
        fechaCreacion=matrix.fechaCreacion, cantidadReglas=_ruleCount(db, matrix.idMatriz),
        medicionesRegistradas=_usage(db, matrix.idMatriz),
    )


def summary(matrix: Matrix | None) -> MatrixSummary | None:
    if matrix is None:
        return None
    return MatrixSummary(idMatriz=matrix.idMatriz, nombre=matrix.nombre, version=matrix.version, ambito=matrix.ambito,
                         estado=matrix.estado, referenciaBase=matrix.referenciaBase, urlReferencia=matrix.urlReferencia)


def _versionOrder(matrix: Matrix):
    try:
        return (matrix.nombre.casefold(), int(matrix.version))
    except ValueError:
        return (matrix.nombre.casefold(), -1)


def _modifier(db: Session, idMatriz: uuid.UUID, first: bool) -> MatrixModifier | None:
    query = select(Audit, User).outerjoin(User, User.idUsuario == Audit.idUsuario).where(
        Audit.tablaAfectada == "Matriz", Audit.idRegistro == idMatriz, Audit.resultado == "EXITO", Audit.tipoEvento == "CRUD")
    row = db.execute(query.order_by(Audit.fechaHora.asc() if first else Audit.fechaHora.desc()).limit(1)).first()
    if row is None:
        return None
    audit, user = row
    return MatrixModifier(fecha=audit.fechaHora, por=f"{user.nombre or ''} {user.apellido or ''}".strip() if user else None)


def _permissions(db: Session, access: Access) -> MatrixPermissions:
    matrix = access.matrix
    manage = access.canManage
    return MatrixPermissions(
        puedeEditar=manage and matrix.estado == BORRADOR,
        puedeActivar=manage and matrix.estado in (BORRADOR, INACTIVA),
        puedeDesactivar=manage and matrix.estado == ACTIVA,
        puedeArchivar=manage and matrix.estado in (BORRADOR, INACTIVA),
        puedeCrearVersion=manage and matrix.estado != BORRADOR,
        puedeVerAuditoria=access.canAudit,
    )


def _detail(db: Session, access: Access) -> MatrixDetail:
    matrix = access.matrix
    rules = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == matrix.idMatriz)
                       .order_by(MatrixRule.codigoRegla)).all()
    institution = db.get(Institution, matrix.idInstitucion) if matrix.idInstitucion else None
    return MatrixDetail(
        **_item(db, matrix).model_dump(), idInstitucion=matrix.idInstitucion,
        nombreInstitucion=institution.nombre if institution else None,
        reglas=[MatrixRuleView(
            idReglaMatriz=r.idReglaMatriz, codigoRegla=r.codigoRegla, sexoModelo=r.sexoModelo, edadDesde=r.edadDesde,
            edadHasta=r.edadHasta, condicionComida=r.condicionComida, minutosComidaMin=r.minutosComidaMin,
            minutosComidaMax=r.minutosComidaMax, glucosaMinReferencia=r.glucosaMinReferencia,
            glucosaMaxReferencia=r.glucosaMaxReferencia) for r in rules],
        permisos=_permissions(db, access),
        creadaPor=_modifier(db, matrix.idMatriz, True) if access.canAudit else None,
        ultimaModificacion=_modifier(db, matrix.idMatriz, False) if access.canAudit else None,
    )


def getMatrix(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixDetail:
    return _detail(db, _access(db, actor, idMatriz))


def listGlobal(db: Session, actor: User) -> list[MatrixItem]:
    """Todas las versiones globales (solo cuentas de plataforma), de la más reciente a la más antigua."""
    if not _isPlatform(actor):
        raise _error("PERMISO_INSUFICIENTE", "Solo la moderación de la plataforma administra las matrices globales.")
    matrices = db.scalars(select(Matrix).where(Matrix.ambito == GLOBAL)).all()
    return [_item(db, m) for m in sorted(matrices, key=_versionOrder, reverse=True)]


def institutionOverview(db: Session, actor: User, idInstitucion: uuid.UUID) -> InstitutionMatrixOverview:
    """Propietario y moderador: matriz propia activa, global de respaldo, la que se aplica hoy y todas las versiones."""
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_MATRICES)
    today = nowForDb().date()
    own = resolveMatrix(db, idInstitucion, today, includeGlobal=False)
    globalActive = resolveMatrix(db, None, today)
    versions = db.scalars(select(Matrix).where(Matrix.ambito == INSTITUCION, Matrix.idInstitucion == idInstitucion)).all()
    return InstitutionMatrixOverview(
        institucionActiva=summary(own), globalActiva=summary(globalActive), efectiva=summary(own or globalActive),
        versiones=[_item(db, m) for m in sorted(versions, key=_versionOrder, reverse=True)],
    )


def effectiveForInstitution(db: Session, actor: User, idInstitucion: uuid.UUID) -> MatrixSummary | None:
    """Cualquier integrante: qué matriz se aplica a las mediciones de glucosa de la institución (sin reglas)."""
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_MATRIZ)
    return summary(resolveMatrix(db, idInstitucion, nowForDb().date()))


def auditTrail(db: Session, actor: User, idMatriz: uuid.UUID) -> list[MatrixAuditEntry]:
    """Auditoría de la matriz: la global solo para la plataforma; la institucional solo para su PROPIETARIO."""
    access = _access(db, actor, idMatriz)
    if not access.canAudit:
        raise _error("PERMISO_INSUFICIENTE", "Solo el administrador del sistema (matrices globales) o el propietario de la "
                                             "institución (matrices institucionales) puede consultar la auditoría.")
    rows = db.execute(
        select(Audit, User).outerjoin(User, User.idUsuario == Audit.idUsuario)
        .where(Audit.tablaAfectada == "Matriz", Audit.idRegistro == idMatriz).order_by(Audit.fechaHora.desc())
    ).all()
    return [MatrixAuditEntry(fechaHora=a.fechaHora, accion=a.accion, resultado=a.resultado,
                             usuario=f"{u.nombre or ''} {u.apellido or ''}".strip() if u else None) for a, u in rows]


# --- Selección de la matriz y de la regla (las usa Medicion) ---------------------------------------------------


def resolveMatrix(db: Session, idInstitucion: uuid.UUID | None, today: date, *, includeGlobal: bool = True) -> Matrix | None:
    """Matriz ACTIVA y vigente que se aplica: la de la institución y, si no tiene, la global. Nunca la de otra."""
    def active(scope):
        return db.scalar(select(Matrix).where(
            scope, Matrix.estado == ACTIVA, Matrix.fechaVigenciaDesde <= today,
            or_(Matrix.fechaVigenciaHasta.is_(None), Matrix.fechaVigenciaHasta >= today)))
    if idInstitucion is not None:
        own = active((Matrix.ambito == INSTITUCION) & (Matrix.idInstitucion == idInstitucion))
        if own is not None or not includeGlobal:
            return own
    return active(Matrix.ambito == GLOBAL) if includeGlobal or idInstitucion is None else None


def resolveRule(db: Session, idMatriz: uuid.UUID, sexo: str | None, edad: int, condicion: str,
                minutos: int | None) -> MatrixRule | None:
    """Regla de la matriz para el contexto de la medición. Sin regla aplicable devuelve None: nunca se inventa una.

    Una regla CUALQUIER_SEXO vale para cualquier sexo, informado o no. Las reglas por sexo solo coinciden con ese sexo: un sexo no
    informado nunca se reemplaza por femenino o masculino. La comida «sin informar» no coincide con reglas de comida concreta."""
    sexo = sexo or "NO_INFORMADO"
    rules = db.scalars(
        select(MatrixRule).where(
            MatrixRule.idMatriz == idMatriz, MatrixRule.sexoModelo.in_((sexo, SEXO_CUALQUIERA)),
            MatrixRule.condicionComida == condicion,
            MatrixRule.edadDesde <= edad, MatrixRule.edadHasta >= edad,
        ).order_by(MatrixRule.codigoRegla)
    ).all()
    for rule in rules:
        if minutos is None:
            if rule.minutosComidaMin is None and rule.minutosComidaMax is None:
                return rule
            continue
        if (rule.minutosComidaMin is None or minutos >= rule.minutosComidaMin) and (
                rule.minutosComidaMax is None or minutos <= rule.minutosComidaMax):
            return rule
    return None


# --- Validación de reglas ----------------------------------------------------------------------------------


def _minutes(rule) -> tuple[int, float]:
    low = rule.minutosComidaMin if rule.minutosComidaMin is not None else 0
    high = rule.minutosComidaMax if rule.minutosComidaMax is not None else float("inf")
    return low, high


def _sameConditions(a, b) -> bool:
    return (a.sexoModelo == b.sexoModelo and a.condicionComida == b.condicionComida
            and a.edadDesde == b.edadDesde and a.edadHasta == b.edadHasta
            and a.minutosComidaMin == b.minutosComidaMin and a.minutosComidaMax == b.minutosComidaMax)


def _hasAge(rule) -> bool:
    return rule.edadDesde is not None and rule.edadHasta is not None


def _sexesOverlap(a, b) -> bool:
    return a == b or SEXO_CUALQUIERA in (a, b)


def _overlap(a, b) -> bool:
    """Misma población (sexo y condición) con rangos de edad y de tiempo desde la comida que se pisan."""
    if not _sexesOverlap(a.sexoModelo, b.sexoModelo) or a.condicionComida != b.condicionComida:
        return False
    if _hasAge(a) != _hasAge(b):
        return False  # «edad no especificada» es otra población, no un rango que se pise
    if _hasAge(a) and (a.edadDesde > b.edadHasta or b.edadDesde > a.edadHasta):
        return False
    (aLow, aHigh), (bLow, bHigh) = _minutes(a), _minutes(b)
    return not (aLow > bHigh or bLow > aHigh)


def _ruleProblem(candidate, others, code: str | None = None) -> MatrixIssue | None:
    for other in others:
        if _sameConditions(candidate, other):
            return MatrixIssue(codigo="REGLA_DUPLICADA", codigoRegla=other.codigoRegla,
                               mensaje=f"Ya existe una regla con las mismas condiciones ({other.codigoRegla}).")
        if _overlap(candidate, other):
            return MatrixIssue(codigo="REGLA_SOLAPADA", codigoRegla=other.codigoRegla,
                               mensaje=f"La regla se solapa con {other.codigoRegla}: mismo sexo y condición con edades y "
                                       "tiempos desde la comida que se pisan.")
    return None


def _validate(db: Session, matrix: Matrix) -> list[MatrixIssue]:
    rules = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == matrix.idMatriz)
                       .order_by(MatrixRule.codigoRegla)).all()
    issues: list[MatrixIssue] = []
    if not rules:
        issues.append(MatrixIssue(codigo="SIN_REGLAS", mensaje="La matriz no tiene reglas: agregá al menos una."))
    for index, rule in enumerate(rules):
        if (_hasAge(rule) and rule.edadHasta < rule.edadDesde) or (
                rule.glucosaMinReferencia is not None and rule.glucosaMaxReferencia < rule.glucosaMinReferencia) or (
                rule.minutosComidaMin is not None and rule.minutosComidaMax is not None
                and rule.minutosComidaMax < rule.minutosComidaMin):
            issues.append(MatrixIssue(codigo="REGLA_INCOHERENTE", codigoRegla=rule.codigoRegla,
                                      mensaje="Los rangos de la regla no son coherentes."))
        problem = _ruleProblem(rule, rules[:index])
        if problem is not None:
            issues.append(MatrixIssue(codigo=problem.codigo, codigoRegla=rule.codigoRegla, mensaje=problem.mensaje))
    return issues


SEX_NAMES = {"FEMENINO": "femenino", "MASCULINO": "masculino", "NO_INFORMADO": "sexo no informado",
             SEXO_CUALQUIERA: "cualquier sexo"}
MEAL_NAMES = {"AYUNO": "en ayunas", "POSTPRANDIAL": "posprandial", "NO_INFORMADA": "sin dato de comida"}
MEASURABLE_SEXES = ("FEMENINO", "MASCULINO")  # una medición de glucosa exige edad y sexo (femenino o masculino)


def _coverageWarnings(rules) -> list[MatrixIssue]:
    """Huecos de cobertura que no bloquean: edades sin regla entre dos reglas contiguas de la misma población y sexos sin ninguna."""
    warnings: list[MatrixIssue] = []
    groups: dict[tuple, list] = {}
    for rule in rules:
        if _hasAge(rule):
            groups.setdefault((rule.sexoModelo, rule.condicionComida, rule.minutosComidaMin, rule.minutosComidaMax), []).append(rule)
    for (sex, meal, _, _), members in groups.items():
        members.sort(key=lambda r: r.edadDesde)
        reach = members[0].edadHasta  # hasta qué edad llega la cobertura (las reglas que se pisan no suman huecos)
        for after in members[1:]:
            if after.edadDesde > reach + 1:
                warnings.append(MatrixIssue(
                    codigo="SIN_COBERTURA", codigoRegla=getattr(after, "codigoRegla", None),
                    mensaje=f"Sin regla para {SEX_NAMES.get(sex, sex)}, {MEAL_NAMES.get(meal, meal)}: edades de "
                            f"{reach + 1} a {after.edadDesde - 1} años."))
            reach = max(reach, after.edadHasta)
    present = {rule.sexoModelo for rule in rules}
    for sex in MEASURABLE_SEXES:
        if rules and sex not in present and SEXO_CUALQUIERA not in present:
            warnings.append(MatrixIssue(
                codigo="SIN_COBERTURA", mensaje=f"No hay reglas para el sexo {SEX_NAMES[sex]}: esas mediciones no tendrían regla aplicable."))
    return warnings


def validateMatrix(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixValidation:
    access = _access(db, actor, idMatriz)
    if not access.canManage:
        raise _error("PERMISO_INSUFICIENTE", DENIED)
    issues = _validate(db, access.matrix)
    rules = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == idMatriz)).all()
    return MatrixValidation(valida=not issues, problemas=issues, advertencias=_coverageWarnings(rules))


def _checkRules(rules: list[MatrixRuleInput]) -> list[MatrixIssue]:
    """Problemas de un conjunto de reglas todavía sin guardar (las mismas reglas que al validar una matriz guardada)."""
    issues: list[MatrixIssue] = []
    if not rules:
        issues.append(MatrixIssue(codigo="SIN_REGLAS", mensaje="La matriz no tiene reglas: agregá al menos una."))
    named = [SimpleNamespace(**rule.model_dump(), codigoRegla=f"Regla {number}") for number, rule in enumerate(rules, start=1)]
    for index, rule in enumerate(named):
        problem = _ruleProblem(rule, named[:index])
        if problem is not None:
            issues.append(MatrixIssue(codigo=problem.codigo, codigoRegla=rule.codigoRegla, mensaje=f"{rule.codigoRegla}: {problem.mensaje}"))
    return issues


def checkRules(db: Session, actor: User, rules: list[MatrixRuleInput]) -> MatrixValidation:
    """Revisión previa al guardado de una matriz nueva: no persiste nada. Propietario o moderador de alguna institución, o la plataforma."""
    if not _isPlatform(actor) and not (actor.tipoCuenta == institutions.TIPO_INSTITUCIONAL and any(
            membership.can(institutions.P_MATRICES) for membership in _activeMemberships(db, actor))):
        raise _error("PERMISO_INSUFICIENTE", DENIED)
    issues = _checkRules(rules)
    return MatrixValidation(valida=not issues, problemas=issues, advertencias=_coverageWarnings(rules))


# --- Crear y versionar -------------------------------------------------------------------------------------


def _authorizeCreate(db: Session, actor: User, ambito: str, idInstitucion: uuid.UUID | None) -> None:
    if ambito == GLOBAL:
        if not _isPlatform(actor):
            raise _error("PERMISO_INSUFICIENTE", "Solo la moderación de la plataforma administra las matrices globales.")
        return
    # Institucional: propietario o moderador DE ESA institución (404 si no pertenece; 403 si es operador).
    institutions.requireMembership(db, actor, idInstitucion, institutions.P_MATRICES)


def _nextVersion(db: Session, ambito: str, idInstitucion: uuid.UUID | None, nombre: str) -> str:
    scope = (Matrix.ambito == GLOBAL) if ambito == GLOBAL else (Matrix.ambito == INSTITUCION) & (Matrix.idInstitucion == idInstitucion)
    versions = db.scalars(select(Matrix.version).where(scope, func.lower(Matrix.nombre) == nombre.lower())).all()
    numbers = [int(v) for v in versions if str(v).isdigit()]
    return str(max(numbers, default=0) + 1)


def _insert(db: Session, actor: User, matrix: Matrix, action: str, **extra) -> None:
    try:
        db.add(matrix)
        db.flush()
        _audit(db, actor, action, matrix, **extra)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("MATRIZ_DUPLICADA", "Ya existe una versión con ese nombre y número. Volvé a intentarlo.") from error


def createMatrix(db: Session, actor: User, data: MatrixCreateRequest) -> MatrixDetail:
    _authorizeCreate(db, actor, data.ambito, data.idInstitucion)
    issues = _checkRules(data.reglas) if data.reglas else []
    if issues:  # una configuración inválida o ambigua no se guarda: ni la matriz ni ninguna regla
        raise _error(issues[0].codigo if len(issues) == 1 else "MATRIZ_INVALIDA", " ".join(issue.mensaje for issue in issues))
    matrix = Matrix(
        idInstitucion=data.idInstitucion, nombre=data.nombre, version=_nextVersion(db, data.ambito, data.idInstitucion, data.nombre),
        ambito=data.ambito, descripcion=data.descripcion, referenciaBase=data.referenciaBase, urlReferencia=data.urlReferencia,
        estado=BORRADOR,
        fechaVigenciaDesde=data.fechaVigenciaDesde or nowForDb().date(), fechaVigenciaHasta=data.fechaVigenciaHasta,
    )
    try:
        db.add(matrix)
        db.flush()
        for number, rule in enumerate(data.reglas, start=1):
            db.add(MatrixRule(idMatriz=matrix.idMatriz, codigoRegla=f"R-{number:03d}", **rule.model_dump()))
        db.flush()
        _audit(db, actor, "CREAR_MATRIZ", matrix, estado=BORRADOR, cantidadReglas=len(data.reglas))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("MATRIZ_DUPLICADA", "Ya existe una versión con ese nombre y número. Volvé a intentarlo.") from error
    return _detail(db, _access(db, actor, matrix.idMatriz))


def newVersion(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixDetail:
    """Copia una versión ya utilizada (o archivada) como nuevo BORRADOR con sus reglas. La original no cambia."""
    access = _access(db, actor, idMatriz)
    _requireManage(db, actor, access, "CREAR_VERSION_MATRIZ")
    source = access.matrix
    if source.estado == BORRADOR:
        raise _error("MATRIZ_ESTADO_INVALIDO", "Esa matriz ya es un borrador: editala directamente.")
    copy = Matrix(
        idInstitucion=source.idInstitucion, nombre=source.nombre, ambito=source.ambito, descripcion=source.descripcion,
        referenciaBase=source.referenciaBase, urlReferencia=source.urlReferencia,
        version=_nextVersion(db, source.ambito, source.idInstitucion, source.nombre), estado=BORRADOR,
        fechaVigenciaDesde=nowForDb().date(), fechaVigenciaHasta=None,
    )
    try:
        db.add(copy)
        db.flush()
        for rule in db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == source.idMatriz)
                               .order_by(MatrixRule.codigoRegla)).all():
            db.add(MatrixRule(
                idMatriz=copy.idMatriz, codigoRegla=rule.codigoRegla, sexoModelo=rule.sexoModelo, edadDesde=rule.edadDesde,
                edadHasta=rule.edadHasta, condicionComida=rule.condicionComida, minutosComidaMin=rule.minutosComidaMin,
                minutosComidaMax=rule.minutosComidaMax, glucosaMinReferencia=rule.glucosaMinReferencia,
                glucosaMaxReferencia=rule.glucosaMaxReferencia))
        _audit(db, actor, "CREAR_VERSION_MATRIZ", copy, estado=BORRADOR, basadaEn=str(source.idMatriz),
               versionOrigen=source.version)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("MATRIZ_DUPLICADA", "Ya existe una versión con ese número. Volvé a intentarlo.") from error
    return _detail(db, _access(db, actor, copy.idMatriz))


# --- Borrador: datos y reglas ------------------------------------------------------------------------------


def _editableDraft(db: Session, actor: User, idMatriz: uuid.UUID, action: str) -> Access:
    access = _access(db, actor, idMatriz)
    _requireManage(db, actor, access, action)
    if access.matrix.estado != BORRADOR:
        raise _error("MATRIZ_NO_EDITABLE", NOT_DRAFT)
    return access


def updateDraft(db: Session, actor: User, idMatriz: uuid.UUID, data: MatrixDraftUpdateRequest) -> MatrixDetail:
    access = _editableDraft(db, actor, idMatriz, "MODIFICAR_MATRIZ")
    matrix = access.matrix
    changes = data.model_dump(exclude_unset=True)
    if "nombre" in changes and changes["nombre"] != matrix.nombre:
        matrix.version = _nextVersion(db, matrix.ambito, matrix.idInstitucion, changes["nombre"])
    for field, value in changes.items():
        if field == "fechaVigenciaDesde" and value is None:
            continue
        setattr(matrix, field, value)
    if matrix.fechaVigenciaHasta is not None and matrix.fechaVigenciaHasta < matrix.fechaVigenciaDesde:
        db.rollback()
        raise _error("PERIODO_INVALIDO", "La vigencia no puede terminar antes de empezar.")
    try:
        _audit(db, actor, "MODIFICAR_MATRIZ", matrix, campos=sorted(changes))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("MATRIZ_DUPLICADA", "Ya existe una matriz con ese nombre y versión.") from error
    return _detail(db, _access(db, actor, idMatriz))


def _nextRuleCode(db: Session, idMatriz: uuid.UUID) -> str:
    codes = db.scalars(select(MatrixRule.codigoRegla).where(MatrixRule.idMatriz == idMatriz)).all()
    numbers = [int(c[2:]) for c in codes if c.startswith("R-") and c[2:].isdigit()]
    return f"R-{max(numbers, default=0) + 1:03d}"


def _rejectProblem(db: Session, problem: MatrixIssue | None) -> None:
    if problem is not None:
        db.rollback()
        raise _error(problem.codigo, problem.mensaje)


def addRule(db: Session, actor: User, idMatriz: uuid.UUID, data: MatrixRuleInput) -> MatrixDetail:
    access = _editableDraft(db, actor, idMatriz, "CREAR_REGLA_MATRIZ")
    others = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == idMatriz)).all()
    _rejectProblem(db, _ruleProblem(data, others))
    rule = MatrixRule(idMatriz=idMatriz, codigoRegla=_nextRuleCode(db, idMatriz), **data.model_dump())
    try:
        db.add(rule)
        db.flush()
        _audit(db, actor, "CREAR_REGLA_MATRIZ", access.matrix, idReglaMatriz=str(rule.idReglaMatriz),
               codigoRegla=rule.codigoRegla)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error("REGLA_DUPLICADA", "No se pudo guardar la regla: volvé a intentarlo.") from error
    return _detail(db, _access(db, actor, idMatriz))


def _loadRule(db: Session, idMatriz: uuid.UUID, idRegla: uuid.UUID) -> MatrixRule:
    rule = db.get(MatrixRule, idRegla)
    if rule is None or rule.idMatriz != idMatriz:
        raise _error("REGLA_NO_ENCONTRADA", RULE_NOT_FOUND)
    return rule


def updateRule(db: Session, actor: User, idMatriz: uuid.UUID, idRegla: uuid.UUID,
               data: MatrixRuleUpdateRequest) -> MatrixDetail:
    access = _editableDraft(db, actor, idMatriz, "MODIFICAR_REGLA_MATRIZ")
    rule = _loadRule(db, idMatriz, idRegla)
    merged = {field: getattr(rule, field) for field in MatrixRuleInput.model_fields}
    merged.update(data.model_dump(exclude_unset=True))
    try:
        validated = MatrixRuleInput(**merged)  # misma validación de rangos que el alta
    except ValueError as error:
        db.rollback()
        raise _error("REGLA_INCOHERENTE", "Los rangos de la regla no son coherentes.") from error
    others = [r for r in db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == idMatriz)).all()
              if r.idReglaMatriz != idRegla]
    _rejectProblem(db, _ruleProblem(validated, others))
    changed = [field for field, value in validated.model_dump().items() if getattr(rule, field) != value]
    for field in changed:
        setattr(rule, field, getattr(validated, field))
    if changed:
        _audit(db, actor, "MODIFICAR_REGLA_MATRIZ", access.matrix, idReglaMatriz=str(idRegla), campos=sorted(changed))
        db.commit()
    return _detail(db, _access(db, actor, idMatriz))


def deleteRule(db: Session, actor: User, idMatriz: uuid.UUID, idRegla: uuid.UUID) -> MatrixDetail:
    access = _editableDraft(db, actor, idMatriz, "ELIMINAR_REGLA_MATRIZ")
    rule = _loadRule(db, idMatriz, idRegla)
    code = rule.codigoRegla
    db.delete(rule)
    _audit(db, actor, "ELIMINAR_REGLA_MATRIZ", access.matrix, codigoRegla=code)
    db.commit()
    return _detail(db, _access(db, actor, idMatriz))


# --- Activar, desactivar y archivar --------------------------------------------------------------------------


def _scope(matrix: Matrix):
    return (Matrix.ambito == GLOBAL) if matrix.ambito == GLOBAL else (
        (Matrix.ambito == INSTITUCION) & (Matrix.idInstitucion == matrix.idInstitucion))


def _setState(db: Session, matrix: Matrix, expected: tuple[str, ...], new: str) -> bool:
    result = db.execute(
        update(Matrix).where(Matrix.idMatriz == matrix.idMatriz, Matrix.estado.in_(expected))
        .values(estado=new).execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def activate(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixDetail:
    """Activa la versión en una sola transacción: la ACTIVA del mismo ámbito pasa a INACTIVA y esta pasa a ACTIVA."""
    access = _access(db, actor, idMatriz)
    _requireManage(db, actor, access, "ACTIVAR_MATRIZ")
    matrix = access.matrix
    if matrix.estado not in (BORRADOR, INACTIVA):
        raise _error("MATRIZ_ESTADO_INVALIDO", "Solo se puede activar un borrador o una versión inactiva.")
    issues = _validate(db, matrix)
    if issues:
        raise _error(issues[0].codigo if len(issues) == 1 else "MATRIZ_INVALIDA",
                     "La matriz no se puede activar: " + " ".join(issue.mensaje for issue in issues))
    today = nowForDb().date()
    if matrix.fechaVigenciaDesde > today or (matrix.fechaVigenciaHasta is not None and matrix.fechaVigenciaHasta < today):
        raise _error("MATRIZ_FUERA_DE_VIGENCIA",
                     "La matriz solo se activa dentro de su vigencia: ajustá las fechas del borrador.")
    previous = db.scalar(select(Matrix).where(_scope(matrix), Matrix.estado == ACTIVA, Matrix.idMatriz != idMatriz))
    expected = (matrix.estado,)
    try:
        if previous is not None and not _setState(db, previous, (ACTIVA,), INACTIVA):
            db.rollback()
            raise _error("MATRIZ_ESTADO_INVALIDO", "La matriz activa cambió mientras tanto: volvé a intentarlo.")
        if not _setState(db, matrix, expected, ACTIVA):
            db.rollback()
            raise _error("MATRIZ_ESTADO_INVALIDO", "La matriz cambió de estado mientras tanto: volvé a intentarlo.")
        if previous is not None:
            _audit(db, actor, "DESACTIVAR_MATRIZ", previous, motivo="Reemplazada por otra versión",
                   reemplazadaPor=matrix.version)
        _audit(db, actor, "ACTIVAR_MATRIZ", matrix, desactiva=previous.version if previous else None)
        db.commit()
    except IntegrityError as error:
        # Dos activaciones simultáneas: el índice único filtrado deja pasar una sola.
        db.rollback()
        raise _error("MATRIZ_ESTADO_INVALIDO", "Otra activación se aplicó al mismo tiempo: volvé a intentarlo.") from error
    db.expire_all()
    return _detail(db, _access(db, actor, idMatriz))


def deactivate(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixDetail:
    access = _access(db, actor, idMatriz)
    _requireManage(db, actor, access, "DESACTIVAR_MATRIZ")
    matrix = access.matrix
    if not _setState(db, matrix, (ACTIVA,), INACTIVA):
        db.rollback()
        raise _error("MATRIZ_ESTADO_INVALIDO", "Solo se puede desactivar una matriz activa.")
    _audit(db, actor, "DESACTIVAR_MATRIZ", matrix)
    db.commit()
    db.expire_all()
    return _detail(db, _access(db, actor, idMatriz))


def archive(db: Session, actor: User, idMatriz: uuid.UUID) -> MatrixDetail:
    """Retira una versión sin borrarla: se conserva para la trazabilidad (una ACTIVA se desactiva primero)."""
    access = _access(db, actor, idMatriz)
    _requireManage(db, actor, access, "ARCHIVAR_MATRIZ")
    matrix = access.matrix
    if not _setState(db, matrix, (BORRADOR, INACTIVA), ARCHIVADA):
        db.rollback()
        raise _error("MATRIZ_ESTADO_INVALIDO", "Solo se archiva un borrador o una versión inactiva; desactivá primero la activa.")
    _audit(db, actor, "ARCHIVAR_MATRIZ", matrix)
    db.commit()
    db.expire_all()
    return _detail(db, _access(db, actor, idMatriz))


# --- Exportación de una matriz con sus reglas (CSV) ----------------------------------------------------------------------------
#
# Quién exporta: exactamente quien puede VER la matriz (`_access`): la plataforma, para las globales; el propietario y el moderador de
# la institución, para las suyas y para la global ACTIVA. Un operador o un integrante de otra institución no exporta, y su intento queda
# en la auditoría de exportaciones (EXPORTACION_FALLIDA). Toda exportación pasa por `auditedExport`.
# Formato: una fila por regla, con los datos de la matriz repetidos en cada fila; una matriz sin reglas sale en una sola fila con las
# reglas vacías. Un límite sin valor sale como «Sin límite» (así lo define el modelo). Glucosa con coma decimal, para Excel en español.

EXPORT_TIPO_DATOS = "MATRIZ_REGLAS"
MATRIX_EXPORT_COLUMNS = (
    "Matriz", "Versión", "Origen", "Estado", "Vigencia desde", "Vigencia hasta", "Referencia base", "URL de referencia",
    "Código de regla", "Sexo", "Edad desde", "Edad hasta", "Condición de comida", "Minutos desde la comida (mín.)",
    "Minutos desde la comida (máx.)", "Glucosa mínima de referencia", "Glucosa máxima de referencia",
)
_ESTADO_LABELS = {BORRADOR: "Borrador", ACTIVA: "Activa", INACTIVA: "Inactiva", ARCHIVADA: "Archivada"}
_SEXO_LABELS = {"MASCULINO": "Masculino", "FEMENINO": "Femenino", "NO_INFORMADO": "No informado"}
_CONDICION_LABELS = {"NO_INFORMADA": "No informada", "POSTPRANDIAL": "Posprandial", "AYUNO": "Ayuno"}


def _exportAmbito(matrix: Matrix) -> str:
    return "PLATAFORMA" if matrix.ambito == GLOBAL else "INSTITUCION"


def _limit(value) -> str:
    return "Sin límite" if value is None else str(value)


def _glucose(value: Decimal | None) -> str:
    return "Sin límite" if value is None else f"{value:.2f}".replace(".", ",")


def _safeName(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "matriz"


def _matrixRows(matrix: Matrix, institutionName: str | None, rules: list[MatrixRule]) -> list[list[str]]:
    origin = "Global (GlucoLume)" if matrix.ambito == GLOBAL else (institutionName or "Institución")
    common = [
        csvText(matrix.nombre), csvText(matrix.version), csvText(origin), csvText(_ESTADO_LABELS.get(matrix.estado, matrix.estado)),
        csvDate(matrix.fechaVigenciaDesde), csvDate(matrix.fechaVigenciaHasta), csvText(matrix.referenciaBase), csvText(matrix.urlReferencia),
    ]
    if not rules:
        return [common + [""] * 9]
    return [common + [
        csvText(r.codigoRegla), csvText(_SEXO_LABELS.get(r.sexoModelo, r.sexoModelo)), csvText(_limit(r.edadDesde)),
        csvText(_limit(r.edadHasta)), csvText(_CONDICION_LABELS.get(r.condicionComida, r.condicionComida)),
        csvText(_limit(r.minutosComidaMin)), csvText(_limit(r.minutosComidaMax)), csvText(_glucose(r.glucosaMinReferencia)),
        csvText(_glucose(r.glucosaMaxReferencia)),
    ] for r in rules]


def exportMatrix(db: Session, actor: User, idMatriz: uuid.UUID) -> tuple[bytes, str]:
    """CSV de la matriz y sus reglas, si la cuenta puede verla. Devuelve (contenido, nombre del archivo)."""
    matrix = db.get(Matrix, idMatriz)
    try:
        access = _access(db, actor, idMatriz)
    except AuthError as error:
        if matrix is not None:  # existe, pero no le corresponde: el intento queda en la auditoría de exportaciones
            rejectExport(db, actor, EXPORT_TIPO_DATOS, ambito=_exportAmbito(matrix), idInstitucion=matrix.idInstitucion, formato="CSV",
                         motivo=error.code)
            db.commit()
        raise
    matrix = access.matrix
    institution = db.get(Institution, matrix.idInstitucion) if matrix.idInstitucion else None
    rules = db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == matrix.idMatriz).order_by(MatrixRule.codigoRegla)).all()
    with auditedExport(db, actor, EXPORT_TIPO_DATOS, ambito=_exportAmbito(matrix), idInstitucion=matrix.idInstitucion, formato="CSV") as export:
        export.registros = len(rules)
        content = csvBytes(MATRIX_EXPORT_COLUMNS, _matrixRows(matrix, institution.nombre if institution else None, rules))
        filename = f"matriz-{_safeName(matrix.nombre)}-{_safeName(matrix.version)}-{nowForDb():%Y%m%d-%H%M}.csv"
        return content, filename
