# MatrixExpiryAlerts - Aviso al administrador de la plataforma cuando una matriz GLOBAL activa está por vencer o ya venció
#
# Quién llama: app/jobs/reminders.py (servicio «notifications» de Compose, una pasada cada NOTIFICATIONS_INTERVAL_SECONDS).
# Qué avisa: solo matrices GLOBAL en estado ACTIVA con fecha de fin. Las institucionales no: las administra cada institución y la
# plataforma no las ve.
#   - Antes del vencimiento: un aviso al llegar a 10, 5, 3, 2 y 1 día (y el mismo día del vencimiento). Cada umbral avisa una sola vez,
#     aunque la pasada encuentre varios días juntos o se haya retrasado: si faltan 4 días, el aviso es el de 5.
#   - Vencida: un aviso y luego uno cada 24 h.
#   - El administrador elige en cualquier momento si los recibe (Matriz.avisoVencimientoSilenciado, desde el detalle de la matriz).
#     Mientras estén desactivados no sale ningún aviso de esa matriz. Al volver a activarlos, sale el que corresponda a la fecha de hoy
#     (los umbrales ya avisados no se repiten). Nada de esto cambia la matriz.
# Cada aviso se reserva antes de enviarse con un UPDATE condicional sobre Matriz (como los recordatorios), así que varias pasadas o
# réplicas a la vez no lo repiten. Si todavía no hay administrador activo, no se reserva nada: el aviso sale cuando lo haya.
#
# Los días se cuentan con la fecha de hoy en hora de Argentina (utils/timeZone.py). La vigencia incluye su último día.

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.emails.eventTypes import EmailEventType
from app.models.matrix import Matrix
from app.models.notificationEvents import PLATAFORMA_MATRIZ_VENCIMIENTO
from app.models.user import User
from app.services import email as emailService
from app.services import userNotifications
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.notifications")

AMBITO_GLOBAL = "GLOBAL"
ESTADO_ACTIVA = "ACTIVA"
UMBRALES = (10, 5, 3, 2, 1)  # días antes del vencimiento (el 0 cae en el 1: «vence hoy»)
VENTANA_DIAS = max(UMBRALES)
REPETIR_CADA = timedelta(hours=24)  # matriz vencida: un aviso por día mientras el administrador los reciba
URL_MATRIZ = "/app/matrices/{idMatriz}"


def umbralPara(diasRestantes: int) -> int | None:
    """Umbral más ajustado que corresponde: 10 o menos → 10, 4 → 5, 0 → 1. None si faltan más días que la ventana o ya venció."""
    if diasRestantes < 0 or diasRestantes > VENTANA_DIAS:
        return None
    return min(umbral for umbral in UMBRALES if diasRestantes <= umbral)


def _administradores(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(
        User.tipoCuenta == userNotifications.TIPO_ADMINISTRADOR, User.estado == userNotifications.ESTADO_ACTIVO)).all())


def _candidatas(db: Session, hoy: date) -> list[Matrix]:
    return list(db.scalars(select(Matrix).where(
        Matrix.ambito == AMBITO_GLOBAL, Matrix.estado == ESTADO_ACTIVA, Matrix.fechaVigenciaHasta.is_not(None),
        Matrix.fechaVigenciaHasta <= hoy + timedelta(days=VENTANA_DIAS),
        Matrix.avisoVencimientoSilenciado == False,  # noqa: E712 - bit de SQL Server: «= 0», no «IS 0» (ver test_mssql_boolean_comparisons)
    )).all())


def _reservarUmbral(db: Session, matrix: Matrix, umbral: int) -> bool:
    """Reserva el umbral solo si todavía no se avisó igual o uno más ajustado (los umbrales van bajando)."""
    result = db.execute(update(Matrix).where(
        Matrix.idMatriz == matrix.idMatriz, Matrix.estado == ESTADO_ACTIVA,
        Matrix.avisoVencimientoSilenciado == False,  # noqa: E712
        or_(Matrix.avisoVencimientoNivel.is_(None), Matrix.avisoVencimientoNivel > umbral),
    ).values(avisoVencimientoNivel=umbral).execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount == 1


def _reservarVencida(db: Session, matrix: Matrix, ahora: datetime) -> bool:
    """Reserva el aviso diario de una matriz vencida (que el administrador recibe y sin aviso en las últimas 24 h)."""
    result = db.execute(update(Matrix).where(
        Matrix.idMatriz == matrix.idMatriz, Matrix.estado == ESTADO_ACTIVA,
        Matrix.avisoVencimientoSilenciado == False,  # noqa: E712 - bit de SQL Server: «= 0», no «IS 0» (ver test_mssql_boolean_comparisons)
        or_(Matrix.avisoVencimientoUltimo.is_(None), Matrix.avisoVencimientoUltimo <= ahora - REPETIR_CADA),
    ).values(avisoVencimientoUltimo=ahora).execution_options(synchronize_session=False))
    db.commit()
    return result.rowcount == 1


def _textoProximo(matrix: Matrix, diasRestantes: int) -> tuple[str, str]:
    if diasRestantes == 0:
        cuando = "vence hoy"
    elif diasRestantes == 1:
        cuando = "vence mañana"
    else:
        cuando = f"faltan {diasRestantes} días para que venza"
    titulo = "Matriz por vencer"
    mensaje = (f"La matriz «{matrix.nombre}» (versión {matrix.version}) está activa y {cuando}"
               f" ({matrix.fechaVigenciaHasta:%d/%m/%Y}).")
    return titulo, mensaje


def _textoVencida(matrix: Matrix) -> tuple[str, str]:
    titulo = "Matriz vencida"
    mensaje = (f"La matriz «{matrix.nombre}» (versión {matrix.version}) sigue activa, pero su vigencia venció el"
               f" {matrix.fechaVigenciaHasta:%d/%m/%Y}. Si ya no corresponde, marcala desde su detalle para dejar de recibir este aviso.")
    return titulo, mensaje


def _correo(matrix: Matrix, mensaje: str, url: str) -> tuple[EmailEventType, dict]:
    """Correo con enlace a la matriz: ahí el administrador puede dejar de recibir el aviso o crear una versión nueva."""
    return EmailEventType.MATRIZ_VENCIMIENTO, {
        "descripcion": mensaje, "nombreMatriz": matrix.nombre, "version": matrix.version,
        "fechaVencimiento": f"{matrix.fechaVigenciaHasta:%d/%m/%Y}", "fechaEvento": nowForDb(),
        "urlMatriz": emailService.frontendUrl(url),
    }


def _avisar(db: Session, administradores: list[User], matrix: Matrix, titulo: str, mensaje: str, clave: str) -> None:
    # notify() es la vía común de la bandeja y del correo: respeta el canal que eligió cada cuenta, la clave evita el duplicado
    # y nunca lanza.
    url = URL_MATRIZ.format(idMatriz=matrix.idMatriz)
    for admin in administradores:
        userNotifications.notify(db, admin, PLATAFORMA_MATRIZ_VENCIMIENTO, titulo, mensaje, url=url, clave=clave,
                                 email=_correo(matrix, mensaje, url))


def run(db: Session, now: datetime | None = None) -> dict:
    """Una pasada: avisa de las matrices globales activas que están por vencer o ya vencieron. Devuelve cuántos avisos reservó."""
    if not userNotifications.ready(db):
        return {"avisos": 0}
    now = now or nowForDb()
    hoy = now.date()
    administradores = _administradores(db)
    if not administradores:
        return {"avisos": 0}
    avisos = 0  # matrices con un aviso reservado en esta pasada
    for matrix in _candidatas(db, hoy):
        diasRestantes = (matrix.fechaVigenciaHasta - hoy).days
        if diasRestantes >= 0:
            umbral = umbralPara(diasRestantes)
            if umbral is None or not _reservarUmbral(db, matrix, umbral):
                continue
            titulo, mensaje = _textoProximo(matrix, diasRestantes)
            _avisar(db, administradores, matrix, titulo, mensaje, f"{PLATAFORMA_MATRIZ_VENCIMIENTO}:{matrix.idMatriz}:{umbral}")
        else:
            if not _reservarVencida(db, matrix, now):
                continue
            titulo, mensaje = _textoVencida(matrix)
            _avisar(db, administradores, matrix, titulo, mensaje,
                    f"{PLATAFORMA_MATRIZ_VENCIMIENTO}:{matrix.idMatriz}:VENCIDA:{now:%Y%m%d%H%M%S%f}")
        avisos += 1
    return {"avisos": avisos}
