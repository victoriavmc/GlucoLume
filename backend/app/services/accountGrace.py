# AccountGrace - Período de gracia de las cuentas institucionales sin vinculaciones
#
# Una cuenta USUARIO_INSTITUCIONAL puede pertenecer a varias instituciones a la vez. Una baja institucional afecta SOLO a esa relación:
# mientras la cuenta conserve al menos un vínculo ACTIVO en otra institución no pasa nada más. Cuando pierde su ÚLTIMA vinculación activa
# comienza un período de gracia de GRACE_DAYS días corridos (Usuario.fechaInicioGracia / fechaVencimientoGracia):
#
#   - la cuenta sigue existiendo y puede aceptar invitaciones o eliminarse voluntariamente, pero no tiene acceso a ninguna institución;
#   - iniciar sesión NO reinicia el plazo y una invitación pendiente tampoco lo cancela;
#   - si acepta una invitación y queda efectivamente incorporada (vínculo ACTIVO) el vencimiento se cancela, con el mismo idUsuario;
#   - si vuelve a quedar sin instituciones empieza un plazo nuevo;
#   - vencido el plazo, el job de ciclo de vida (services/accountLifecycle.py) elimina y anonimiza la cuenta.
#
# El plazo también empieza cuando una cuenta institucional queda HABILITADA sin ninguna vinculación (startIfOrphaned con origen
# ALTA_DE_CUENTA / ACTIVACION_DE_CUENTA): al verificar el correo, al registrarse con Google o al activar una cuenta creada por una invitación.
# Una cuenta PENDIENTE (correo sin verificar o invitación sin activar) todavía no existe operativamente: no tiene plazo, y las no verificadas
# se purgan por su propia regla de 24 h. Crear una institución (quedar como propietario) o aceptar una invitación cancelan el plazo.
#
# Todo se decide en el backend con el estado de la base: nunca con lo que envíe el navegador. Las funciones de este módulo no confirman la
# transacción: lo hace quien las llama junto con la baja o la incorporación, para que el plazo y el vínculo cambien juntos.

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.emails.eventTypes import EmailEventType
from app.models.institutionUser import InstitutionUser
from app.models.user import User
from app.services import email as emailService
from app.services.audit import registerEvent

GRACE_DAYS = 30
TIPO_INSTITUCIONAL = "USUARIO_INSTITUCIONAL"
ESTADO_ACTIVO = "ACTIVO"
RELACION_ACTIVO = "ACTIVO"

ACCION_INICIO = "INICIAR_PERIODO_GRACIA"
ACCION_CANCELACION = "CANCELAR_PERIODO_GRACIA"
ORIGEN_ALTA = "ALTA_DE_CUENTA"
ORIGEN_ACTIVACION = "ACTIVACION_DE_CUENTA"


@dataclass(frozen=True)
class Grace:
    fechaInicio: datetime
    fechaVencimiento: datetime
    diasRestantes: int


def graceOf(user: User, now: datetime) -> Grace | None:
    """El período en curso de la cuenta, con los días restantes (se cuentan por día entero: 1 = vence en menos de 24 h; 0 = vencido)."""
    if user.fechaVencimientoGracia is None or user.fechaInicioGracia is None or user.estado != ESTADO_ACTIVO:
        return None
    remaining = max(0, ceil((user.fechaVencimientoGracia - now).total_seconds() / 86400))
    return Grace(user.fechaInicioGracia, user.fechaVencimientoGracia, remaining)


def lockUser(db: Session, idUsuario: uuid.UUID) -> User | None:
    """Relee el Usuario con bloqueo de fila hasta el commit: serializa bajas, incorporaciones y la eliminación automática de la cuenta."""
    return db.execute(
        select(User)
        .where(User.idUsuario == idUsuario)
        .with_hint(User, "WITH (UPDLOCK, ROWLOCK)", "mssql")
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().first()


def activeBondCount(db: Session, idUsuario: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(InstitutionUser).where(
            InstitutionUser.idUsuarioInvitado == idUsuario, InstitutionUser.estadoRelacion == RELACION_ACTIVO)
    ) or 0


def startIfOrphaned(db: Session, idUsuario: uuid.UUID, now: datetime, idActor: uuid.UUID | None, origin: str,
                    idInstitucion: uuid.UUID | None = None) -> User | None:
    """Tras terminar vínculos (ya enviados a la base con flush): si la cuenta institucional quedó sin ninguno ACTIVO, inicia su período de
    gracia. Devuelve la cuenta SOLO si lo inició ahora (para avisarle después del commit); None si conserva otras instituciones, si no es
    institucional o activa, o si su plazo ya corre (el plazo no se reinicia)."""
    db.flush()  # el alta o la activación de la cuenta (si es de esta misma transacción) debe estar en la base antes del bloqueo
    user = lockUser(db, idUsuario)
    if user is None or user.tipoCuenta != TIPO_INSTITUCIONAL or user.estado != ESTADO_ACTIVO:
        return None
    if activeBondCount(db, idUsuario) > 0 or user.fechaVencimientoGracia is not None:
        return None
    user.fechaInicioGracia = now
    user.fechaVencimientoGracia = now + timedelta(days=GRACE_DAYS)
    user.fechaActualizacion = now
    registerEvent(
        db, "PERMISO", ACCION_INICIO, True, idActor, "Usuario", user.idUsuario, idInstitucion=idInstitucion,
        datosNuevos={"origen": origin, "dias": GRACE_DAYS, "fechaInicio": now.isoformat(),
                     "fechaVencimiento": user.fechaVencimientoGracia.isoformat()},
    )
    return user


def confirmStillActive(db: Session, idUsuario: uuid.UUID, now: datetime) -> None:
    """Última barrera antes de confirmar una incorporación (aceptar una invitación, crear o reabrir una institución): un UPDATE condicionado a
    que la cuenta siga ACTIVA. Si la eliminación automática ganó la carrera, no actualiza nada y la incorporación se deshace por completo;
    si la incorporación gana, el reclamo de la eliminación (condicionado a que el plazo siga vigente) deja de aplicarse. No depende de que el
    motor bloquee la fila: el resultado es el mismo con o sin UPDLOCK."""
    touched = db.execute(
        update(User).where(User.idUsuario == idUsuario, User.estado == ESTADO_ACTIVO).values(fechaActualizacion=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if touched != 1:
        db.rollback()
        raise AuthError("CUENTA_NO_ACTIVA", "La cuenta no está activa.")


def confirmNotDeleted(db: Session, idUsuario: uuid.UUID, now: datetime) -> bool:
    """Última barrera de una invitación a una cuenta existente: un UPDATE condicionado a que la cuenta no haya sido eliminada o depurada entre
    tanto. False = perdió la carrera (quien llama deshace todo y reintenta invitando como a una cuenta nueva)."""
    return db.execute(
        update(User).where(User.idUsuario == idUsuario, User.estado != "ELIMINADO").values(fechaActualizacion=now)
        .execution_options(synchronize_session=False)
    ).rowcount == 1


def cancelOnIncorporation(db: Session, user: User, now: datetime, idInstitucion: uuid.UUID | None = None) -> bool:
    """La cuenta quedó efectivamente incorporada (vínculo ACTIVO, en la misma transacción): se cancela el vencimiento. Solo recupera los
    accesos de la nueva vinculación. Devuelve True si había un plazo en curso."""
    if user.fechaVencimientoGracia is None:
        return False
    previous = {"fechaInicio": user.fechaInicioGracia.isoformat(), "fechaVencimiento": user.fechaVencimientoGracia.isoformat()}
    user.fechaInicioGracia = None
    user.fechaVencimientoGracia = None
    user.fechaActualizacion = now
    registerEvent(db, "PERMISO", ACCION_CANCELACION, True, user.idUsuario, "Usuario", user.idUsuario, idInstitucion=idInstitucion,
                  datosPrevios=previous, datosNuevos={"motivo": "INCORPORACION_A_INSTITUCION"})
    return True


def welcomeContext(user: User) -> dict:
    """Datos del correo de bienvenida de una cuenta institucional. `fechaVencimiento` solo existe si hay un plazo EN CURSO: quien ya quedó
    incorporado (p. ej. como propietario) no recibe un vencimiento inexistente. Las cuentas de otro tipo no reciben nada de esto."""
    if user.tipoCuenta != TIPO_INSTITUCIONAL:
        return {}
    return {"esInstitucional": True, "fechaVencimiento": user.fechaVencimientoGracia, "diasGracia": GRACE_DAYS}


def notifyStarted(user: User, now: datetime) -> None:
    """Correo de aviso del plazo (después del commit; un fallo de SMTP nunca revierte la baja)."""
    if not user.correoElectronico or user.fechaVencimientoGracia is None:
        return
    emailService.sendEmailEventInBackground(
        EmailEventType.PERIODO_GRACIA_INICIADO, user.correoElectronico,
        {"nombre": user.nombre, "fechaEvento": now, "fechaVencimiento": user.fechaVencimientoGracia, "diasGracia": GRACE_DAYS,
         "urlInvitaciones": emailService.frontendUrl("invitacionesInstitucion")},
    )
