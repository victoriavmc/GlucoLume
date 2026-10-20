# AuthAccess - Accesos (intentos de autenticación) del período, segmentados por tipo de cuenta
#
# Una sola definición de «acceso fallido» y «ingreso correcto» y una sola consulta: el tablero de la plataforma muestra el total y cada tipo de
# cuenta a partir de las mismas filas, de modo que individuales + institucionales + plataforma + sin clasificar == total, siempre.
#
# Qué es un intento (un evento de auditoría = un intento, nunca dos):
#   fallido   un intento de autenticación RECHAZADO (ver FAILED_ATTEMPT_ACTIONS): contraseña o Google, estado de la cuenta, bloqueo, código MFA o de
#             recuperación incorrecto. No es el bloqueo temporal (evento propio del MISMO intento, services/auth.py) ni un token de sesión reutilizado.
#   correcto  el evento que ENTREGA una sesión válida: LOGIN_<método> (sin MFA), LOGIN_<método>_MFA (TOTP o código de recuperación guardado) o
#             LOGIN_RECUPERACION_MFA (recuperación por correo desde el login) o LOGIN_ACTIVACION_CUENTA (primera sesión al activar la cuenta con
#             el enlace del correo, sin MFA que la intercale). El paso intermedio LOGIN_<método>_MFA_PENDIENTE (primer factor correcto,
#             falta el segundo) no abre sesión: lo sigue LOGIN_<método>_MFA, o un código inválido que cuenta como fallido. La recuperación de MFA hecha
#             desde Seguridad (con sesión) no es un ingreso.
#   Sesiones que no suman a propósito: la rotación del refresh token y el canje de un código de traspaso de sesión (ya auditado en el ingreso original).
#   Las sesiones anteriores a estos eventos nuevos (recuperación y activación) NO se reconstruyen: no hay evidencia para distinguirlas (ver el doc).
#
# A qué tipo de cuenta pertenece un intento: a la cuenta que se autenticó (Auditoria.idUsuario → Usuario.tipoCuenta), NUNCA al nombre de un rol
# ni a lo que escribió la persona. «Moderador» existe como rol institucional y como cuenta de plataforma; solo el tipo de cuenta los distingue.
#   INDIVIDUAL      CONSUMIDOR_FINAL (con o sin grupo familiar: pertenecer a un grupo no cambia el tipo de cuenta).
#   INSTITUCIONAL   USUARIO_INSTITUCIONAL, tenga una o varias instituciones (un propietario, administrador u operador cuenta una vez en este tipo).
#   PLATAFORMA      ADMINISTRADOR_PLATAFORMA y MODERADOR_PLATAFORMA.
#   SIN_CLASIFICAR  no hay una cuenta identificable (identificador inexistente: el evento no guarda idUsuario) o el contexto registrado se contradice
#                   (una cuenta individual o de plataforma con un vínculo institucional, o con una institución anotada en el propio evento).
#                   Esos intentos se informan aparte: no se reparten en ninguna categoría.
# Si la base ya tiene Auditoria.tipoCuentaActor (esquema v5), el tipo que registró el propio evento manda sobre el vigente; los eventos que no lo
# registran (todos los anteriores a la migración, y los que no tienen cuenta) se infieren como se describe arriba. No se rellena nada hacia atrás.
# El tipo de cuenta se lee al consultar. Una cuenta solo cambia de tipo entre ADMINISTRADOR_PLATAFORMA y MODERADOR_PLATAFORMA (relevo de la
# administración): las dos son PLATAFORMA, así que ningún evento histórico cambia de categoría. No hay historial de tipos de cuenta que consultar.

from datetime import datetime

from sqlalchemy import and_, case, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models.audit import Audit
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.schemas.platform import AccessBreakdown, AccessCount
from app.services import auditClassification as classification
from app.services import dashboard as dashboards
from app.services import schemaCompat

INDIVIDUAL, INSTITUCIONAL, PLATAFORMA, SIN_CLASIFICAR = "INDIVIDUAL", "INSTITUCIONAL", "PLATAFORMA", "SIN_CLASIFICAR"
ACCOUNT_INDIVIDUAL, ACCOUNT_INSTITUTIONAL = "CONSUMIDOR_FINAL", "USUARIO_INSTITUCIONAL"
ACCOUNTS_PLATFORM = ("ADMINISTRADOR_PLATAFORMA", "MODERADOR_PLATAFORMA")
FAILED, SUCCESSFUL = "FALLIDO", "CORRECTO"


# Eventos LOGIN fallidos que SON un intento de autenticación rechazado: el login (contraseña o Google, también por estado de la cuenta o bloqueo),
# un código del segundo factor o de la recuperación incorrecto y el ingreso con Google rechazado al vincular. Quedan fuera, aunque sean LOGIN/FALLO:
# el bloqueo temporal (mismo intento), la reutilización de un token de sesión (REFRESH_REUTILIZADO: no se presentó ninguna credencial) y los pasos de
# la recuperación que no son un intento de ingreso (pedir el código, fallo del envío del correo).
FAILED_ATTEMPT_ACTIONS = ("MFA_CODIGO_INVALIDO", "MFA_RECUPERACION_CODIGO_INVALIDO", "VINCULACION_GOOGLE")


def failedCondition():
    return and_(Audit.tipoEvento == "LOGIN", Audit.resultado == "FALLO",
                or_(Audit.accion.startswith("LOGIN_", autoescape=True), Audit.accion.in_(FAILED_ATTEMPT_ACTIONS)))


def successfulCondition():
    """Solo el evento que ENTREGA una sesión: LOGIN_PWD / LOGIN_GOOGLE (sin MFA), LOGIN_<método>_MFA (con TOTP o código de recuperación guardado) y
    LOGIN_RECUPERACION_MFA (recuperación por correo desde el login) y LOGIN_ACTIVACION_CUENTA. MFA_RECUPERACION_COMPLETADA no sirve: la deja también la recuperación hecha desde
    Seguridad, que no abre sesión."""
    return and_(Audit.tipoEvento == "LOGIN", Audit.resultado == "EXITO", Audit.accion.startswith("LOGIN_", autoescape=True),
                not_(Audit.accion.endswith("_MFA_PENDIENTE", autoescape=True)))


def _category(bonded, recorded=None):
    """Tipo de cuenta del intento. `bonded`: cuentas con algún vínculo institucional (cualquier estado). `recorded`: Auditoria.tipoCuentaActor (script
    034), solo si ya existe: el tipo que el propio evento registró manda; los eventos sin él (todos los anteriores) se infieren del tipo vigente."""
    noBond = bonded.c.idUsuarioInvitado.is_(None)
    noInstitutionInEvent = Audit.idInstitucion.is_(None)
    fromEvent = [] if recorded is None else [
        (recorded == ACCOUNT_INSTITUTIONAL, INSTITUCIONAL),
        (and_(recorded == ACCOUNT_INDIVIDUAL, noInstitutionInEvent), INDIVIDUAL),
        (and_(recorded.in_(ACCOUNTS_PLATFORM), noInstitutionInEvent), PLATAFORMA),
        (recorded.is_not(None), SIN_CLASIFICAR),  # registrado pero contradictorio con la institución anotada en el mismo evento
    ]
    return case(
        *fromEvent,
        (User.tipoCuenta == ACCOUNT_INSTITUTIONAL, INSTITUCIONAL),
        (and_(User.tipoCuenta == ACCOUNT_INDIVIDUAL, noBond, noInstitutionInEvent), INDIVIDUAL),
        (and_(User.tipoCuenta.in_(ACCOUNTS_PLATFORM), noBond, noInstitutionInEvent), PLATAFORMA),
        else_=SIN_CLASIFICAR,
    )


def breakdown(db: Session, start: datetime, end: datetime | None) -> AccessBreakdown:
    """Intentos fallidos y correctos del período por tipo de cuenta, en UNA consulta. El período se aplica igual a todas las categorías."""
    bonded = select(InstitutionUser.idUsuarioInvitado).distinct().subquery()
    failed, successful = failedCondition(), successfulCondition()
    attempts = (
        select(_category(bonded, Audit.__table__.c.tipoCuentaActor if schemaCompat.auditAccountTypeReady(db) else None).label("categoria"), case((failed, FAILED), else_=SUCCESSFUL).label("resultado"))
        .select_from(Audit)
        .outerjoin(User, User.idUsuario == Audit.idUsuario)
        .outerjoin(bonded, bonded.c.idUsuarioInvitado == Audit.idUsuario)
        .where(or_(failed, successful), *dashboards._inPeriod(Audit.fechaHora, start, end))
        .subquery()
    )  # derivada: SQL Server no admite agrupar por una expresión con subconsultas
    counts = {(row[0], row[1]): row[2] for row in db.execute(
        select(attempts.c.categoria, attempts.c.resultado, func.count()).group_by(attempts.c.categoria, attempts.c.resultado)).all()}

    def count(category: str) -> AccessCount:
        return AccessCount(fallidos=counts.get((category, FAILED), 0), exitosos=counts.get((category, SUCCESSFUL), 0))

    return AccessBreakdown(individual=count(INDIVIDUAL), institucional=count(INSTITUCIONAL), plataforma=count(PLATAFORMA),
                           sinClasificar=count(SIN_CLASIFICAR))
