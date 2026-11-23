# IndividualDevice - Dispositivo vinculado a cada cuenta individual (una cuenta, UN dispositivo)
#
# La primera medición de una cuenta individual con un dispositivo lo deja vinculado a esa cuenta (dbo.VinculoCuentaDispositivo). Después,
# esa cuenta solo puede medir con ESE dispositivo: con otro se rechaza. Un mismo dispositivo puede estar vinculado a varias cuentas, y cada
# medición conserva su cuenta y su dispositivo, así que nada se mezcla. La vinculación es independiente de la asignación institucional,
# que no se toca. El vínculo no se muestra a la propia cuenta; el administrador lo ve en el inventario global, con una referencia corta
# de la cuenta (nunca su nombre ni su correo).
# Sin la tabla en la base instalada no se vincula nada y la medición sigue como siempre (schemaCompat.hasTable).

import uuid
from datetime import datetime

from sqlalchemy import false, func, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.accountDeviceLink import AccountDeviceLink
from app.models.device import Device
from app.models.user import User
from app.services import device as deviceService
from app.services import schemaCompat
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

TIPO_INDIVIDUAL = "CONSUMIDOR_FINAL"
ESTADO_OPERATIVO = "OPERATIVO"
MODELO_PRUEBA = "Arduino UNO + MAX30100 (prueba)"
TABLE = "VinculoCuentaDispositivo"
LIST_LIMIT = 500


def _available(db: Session) -> bool:
    return schemaCompat.hasTable(db, TABLE)


def hasLinkTable(db: Session) -> bool:
    return _available(db)


def requireLinkedDevice(db: Session, actor, device: Device) -> None:
    """Cuenta individual: vincula el dispositivo la primera vez y después exige ese mismo. Sin tabla, no hace nada."""
    if actor.tipoCuenta != TIPO_INDIVIDUAL or not _available(db):
        return
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
    if link is None:
        db.add(AccountDeviceLink(idUsuario=actor.idUsuario, idDispositivo=device.idDispositivo))
        db.flush()
        return
    if link.idDispositivo != device.idDispositivo:
        raise AuthError("DISPOSITIVO_YA_VINCULADO", "Tu cuenta ya tiene vinculado otro dispositivo: medí con ese.")


def linkedDeviceCount(db: Session) -> int | None:
    """Dispositivos vinculados a al menos una cuenta individual; None si la base no tiene la tabla todavía."""
    if not _available(db):
        return None
    return db.scalar(select(func.count(func.distinct(AccountDeviceLink.idDispositivo)))) or 0


def connectTestDevice(db: Session, actor) -> Device:
    """«Conectar dispositivo» de una cuenta individual de prueba. Sin cambios si el dispositivo vinculado está OPERATIVO (solo confirma que
    el Arduino conectado es ese registro). Si NO está operativo, crea un dispositivo de prueba nuevo (código único, generado por el sistema,
    OPERATIVO), lo vincula a la cuenta y deja el anterior intacto (estado, mediciones e historial). Requiere el puente conectado. El
    código generado identifica el registro de prueba: no reemplaza ninguna validación de identidad ni de autorización."""
    from app.acquisition.telemetry import hub  # import local: el módulo de adquisición importa servicios de medición

    if actor.tipoCuenta != TIPO_INDIVIDUAL:
        raise AuthError("PERMISO_INSUFICIENTE", "Solo las cuentas individuales conectan dispositivos de prueba.")
    if not _available(db):
        raise AuthError("NO_DISPONIBLE", "Los vínculos de dispositivos todavía no están disponibles en esta instalación.")
    if hub.deviceState() != "CONECTADO":
        raise AuthError("PUENTE_NO_CONECTADO", "Conectá el Arduino para continuar.")
    # Serializa las conexiones de ESTA cuenta: dos pedidos simultáneos no crean dos dispositivos lógicos (el segundo ve el vínculo del primero).
    db.scalar(lockAccountQuery(actor.idUsuario))
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
    current = db.get(Device, link.idDispositivo) if link is not None else None
    if current is not None and current.estado == ESTADO_OPERATIVO:
        db.commit()  # solo libera el bloqueo: se reutiliza el dispositivo lógico de la cuenta, sin crear otro
        hub.confirm(actor.idUsuario, current.idDispositivo)
        return current
    # Sin vínculo (primera conexión) o con un dispositivo que ya no está OPERATIVO: se registra uno nuevo. El anterior queda intacto.
    # Si otra conexión de la misma cuenta ganó la carrera (UQ por cuenta), se deshace esta y se reutiliza la que quedó.
    try:
        # Sin vínculo (primera conexión) o con un dispositivo que ya no está OPERATIVO: se registra uno nuevo. El anterior queda intacto.
        now = nowForDb()
        device = Device(codigoDispositivo=str(uuid.uuid4()), nombre="Dispositivo de prueba", modelo=MODELO_PRUEBA,
                        modeloSensor="MAX30100", estado=ESTADO_OPERATIVO)
        db.add(device)
        db.flush()
        previous = link.idDispositivo if link is not None else None
        if link is None:
            link = AccountDeviceLink(idUsuario=actor.idUsuario, idDispositivo=device.idDispositivo, fechaVinculo=now)
            db.add(link)
            db.flush()
        else:
            link.idDispositivo = device.idDispositivo
            link.fechaVinculo = now
        registerEvent(db, "CRUD", "REGISTRAR_DISPOSITIVO", True, actor.idUsuario, "Dispositivo", device.idDispositivo, modulo="DISPOSITIVOS",
                      datosNuevos={"modeloSensor": "MAX30100", "estado": ESTADO_OPERATIVO, "origen": "CONEXION_CUENTA_INDIVIDUAL_PRUEBA",
                                   "registroAutomatico": True, "idInstitucion": None})
        registerEvent(db, "CRUD", "VINCULAR_CUENTA_DISPOSITIVO", True, actor.idUsuario, "VinculoCuentaDispositivo", link.idVinculo,
                      modulo="DISPOSITIVOS", datosPrevios={"idDispositivo": str(previous)} if previous else None,
                      datosNuevos={"idDispositivo": str(device.idDispositivo), "origen": "CONEXION_CUENTA_INDIVIDUAL_PRUEBA"})
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
        existing = db.get(Device, winner.idDispositivo) if winner is not None else None
        if existing is None or existing.estado != ESTADO_OPERATIVO:
            raise
        hub.confirm(actor.idUsuario, existing.idDispositivo)
        return existing
    hub.confirm(actor.idUsuario, device.idDispositivo)
    return device


def lockAccountQuery(userId):
    """Bloqueo de la fila de la cuenta hasta el commit. SQLAlchemy NO traduce with_for_update() a SQL Server (lo ignora), así que se
    pide el hint de T-SQL explícitamente; en otros motores (pruebas SQLite) el hint no se usa."""
    return (select(User.idUsuario).where(User.idUsuario == userId)
            .with_hint(User.__table__, "WITH (UPDLOCK, ROWLOCK)", dialect_name="mssql"))


def ownLinkedDevice(db: Session, actor) -> Device | None:
    """El dispositivo lógico vinculado a la cuenta individual (None si no tiene o si la base no tiene la tabla)."""
    if not _available(db):
        return None
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
    return db.get(Device, link.idDispositivo) if link is not None else None


def isOwnLinkedDevice(db: Session, actor, device: Device) -> bool:
    """¿Es ESTE dispositivo el vinculado a la cuenta? Solo esto autoriza medir con él (nunca el código físico del Arduino)."""
    linked = ownLinkedDevice(db, actor)
    return linked is not None and linked.idDispositivo == device.idDispositivo


def linked(db: Session, column):
    """Condición: el dispositivo de esa columna está vinculado a al menos una cuenta individual (sin la tabla, nunca)."""
    if not _available(db):
        return false()
    return column.in_(select(AccountDeviceLink.idDispositivo))


def notLinked(db: Session, column):
    """Condición: el dispositivo de esa columna NO está vinculado a ninguna cuenta individual (sin la tabla, siempre se cumple)."""
    if not _available(db):
        return true()
    return column.not_in(select(AccountDeviceLink.idDispositivo))


def isLinked(db: Session, idDispositivo) -> bool:
    """¿El dispositivo tiene al menos una cuenta individual vinculada? Sin la tabla, no."""
    if not _available(db):
        return False
    return db.scalar(select(func.count()).select_from(AccountDeviceLink).where(AccountDeviceLink.idDispositivo == idDispositivo)) > 0


def accountsOf(db: Session, idDispositivo) -> list[dict]:
    """Cuentas individuales vinculadas a un dispositivo: nombre, apellido y correo. Sin la tabla, ninguna."""
    if not _available(db):
        return []
    rows = db.execute(
        select(User.nombre, User.apellido, User.correoElectronico)
        .join(AccountDeviceLink, AccountDeviceLink.idUsuario == User.idUsuario)
        .where(AccountDeviceLink.idDispositivo == idDispositivo)
        .order_by(AccountDeviceLink.fechaVinculo)).all()
    return [{"nombre": r.nombre, "apellido": r.apellido, "correoElectronico": r.correoElectronico} for r in rows]


def listLinks(db: Session, actor) -> list[dict]:
    """Vínculos de cuentas individuales con cada dispositivo, para el inventario global. Cuenta por referencia corta, sin datos personales."""
    scope = deviceService.platformScope(db, actor)
    if not scope.can("ver"):
        raise AuthError("PERMISO_INSUFICIENTE", "No tenés permiso para ver el inventario de dispositivos.")
    if not _available(db):
        return []
    rows = db.execute(
        select(AccountDeviceLink.idUsuario, AccountDeviceLink.fechaVinculo, Device.idDispositivo, Device.codigoDispositivo, Device.nombre)
        .join(Device, Device.idDispositivo == AccountDeviceLink.idDispositivo)
        .order_by(Device.codigoDispositivo, AccountDeviceLink.fechaVinculo)
        .limit(LIST_LIMIT)).all()
    return [{"idDispositivo": row.idDispositivo, "codigoDispositivo": row.codigoDispositivo, "nombre": row.nombre,
             "cuentaRef": str(row.idUsuario)[-8:], "fechaVinculo": row.fechaVinculo} for row in rows]
