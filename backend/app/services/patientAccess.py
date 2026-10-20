# PatientAccess - Servicio central de autorización sobre pacientes institucionales
#
# Separa DOS niveles de información (Ley 25.326, datos de salud; Ley 26.529, derechos del paciente):
#
#   1. ADMINISTRATIVA (todo integrante con CONSULTAR_PACIENTES: propietario, moderador y operador de la institución): identificación
#      administrativa del paciente, su operador responsable, su fecha de registro y su estado. Solo dentro de su institución.
#   2. DE SALUD (mediciones experimentales individuales: última medición, historial, gráficos, estadísticas individuales, detalle de
#      una medición, registro de nuevas mediciones, resultados por correo): únicamente el OPERADOR RESPONSABLE VIGENTE del paciente
#      (su vínculo está ACTIVO, es el responsable hoy y tiene GESTIONAR_PACIENTES). El rol administrativo (moderador, propietario) NO
#      autoriza por sí solo a consultar información de salud individual. Un acceso por una persona de salud con función específica
#      requeriría un permiso adicional expreso y una finalidad justificada: esa excepción NO existe en esta versión.
#
# Autoría histórica de una medición (quién la registró; Auditoria INICIAR_MEDICION) no es autorización vigente: tras una transferencia,
# el operador anterior conserva su traza pero pierde el acceso a las mediciones. Lo decide el backend en cada consulta con el vínculo
# del usuario autenticado y el responsable ACTUAL del paciente, nunca con datos que envíe el cliente.
#
# El intento rechazado queda en Auditoria (ACCESO, FALLO) con quién, qué operación y el motivo; nunca con valores de salud.
#
# Estadísticas agregadas (institución): un conjunto con menos de MIN_AGGREGATE_PATIENTS pacientes distintos no se informa
# (suppressSmallGroup), para que los filtros por período o los grupos pequeños no identifiquen a una persona.

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.institution import Institution
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.services import institution as institutions
from app.services.audit import registerEvent

MEASUREMENTS_NOT_AUTHORIZED = "Las mediciones de este paciente están disponibles únicamente para su operador responsable autorizado."
MIN_AGGREGATE_PATIENTS = 5  # k mínimo de pacientes distintos para informar una estadística de salud agregada


def currentPeriod(relation, idInstitucion):
    """Condición SQL: `relation` (vínculo de un operador) pertenece al período operativo VIGENTE de la institución, es decir, no se dio de baja
    antes de la última reapertura. La reapertura no devuelve el acceso a los pacientes archivados del período anterior (ni a sus transferencias y
    tareas de reasignación): toda vista con identificación de pacientes debe aplicar esta condición, como el padrón (institutionPatients._patientsOf)."""
    reopened = select(Institution.fechaUltimaReapertura).where(Institution.idInstitucion == idInstitucion).scalar_subquery()
    return or_(reopened.is_(None), relation.fechaBaja.is_(None), relation.fechaBaja > reopened)


def isResponsibleOperator(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    """El usuario autenticado es el OPERADOR a cargo hoy del paciente, con vínculo activo y permiso de operar pacientes."""
    relation = membership.relation
    return (
        membership.role == institutions.ROL_OPERADOR
        and relation.estadoRelacion == institutions.RELACION_ACTIVO
        and profile.idInstitucionUsuarioResponsable == relation.idInstitucionUsuario
        and membership.can(institutions.P_GESTIONAR_PACIENTES)
    )


def canViewMeasurements(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    """Información de salud individual: solo el operador responsable vigente."""
    return isResponsibleOperator(membership, profile)


def ownsPatient(membership: institutions.Membership, profile: MeasurementProfile) -> bool:
    """Paciente asignado al vínculo del usuario autenticado (para «Mis pacientes»; no habilita por sí solo información de salud)."""
    return profile.idInstitucionUsuarioResponsable == membership.relation.idInstitucionUsuario


def deny(db: Session, actor: User, profile: MeasurementProfile, operation: str) -> AuthError:
    """Registra el intento no autorizado (quién, sobre qué paciente y qué operación; sin valores) y devuelve el 403."""
    registerEvent(db, "ACCESO", "CONSULTAR_MEDICIONES_PACIENTE", False, actor.idUsuario, "PerfilMedicion", profile.idPerfilMedicion,
                  observacion=f"Operación: {operation}. Motivo: SIN_ASIGNACION_VIGENTE")
    db.commit()
    return AuthError("MEDICIONES_NO_AUTORIZADAS", MEASUREMENTS_NOT_AUTHORIZED)


def requireMeasurementAccess(db: Session, actor: User, membership: institutions.Membership, profile: MeasurementProfile,
                             operation: str) -> None:
    """Se llama con la membresía ya validada (usuario autenticado, institución y relación activa) y el perfil ya acotado a esa
    institución. Verifica rol y asignación vigente antes de devolver cualquier dato de salud."""
    if not canViewMeasurements(membership, profile):
        raise deny(db, actor, profile, operation)


def suppressSmallGroup(db: Session, scope, extra=()) -> bool:
    """True si los pacientes DISTINTOS con mediciones en `scope` (+ condiciones extra) son menos que el mínimo: no se informan
    estadísticas de salud de un grupo que permitiría identificar a una persona."""
    distinctPatients = db.scalar(select(func.count(distinct(Measurement.idPerfilMedicion))).where(scope, *extra)) or 0
    return distinctPatients < MIN_AGGREGATE_PATIENTS
