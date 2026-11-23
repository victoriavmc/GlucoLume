# IndividualDevice - Dispositivo vinculado a cada cuenta individual (una cuenta, UN dispositivo a la vez)
#
# La cuenta individual mide con el dispositivo que tiene vinculado (dbo.VinculoCuentaDispositivo). «Conectar dispositivo» vincula el Arduino
# que está conectado ahora: si el Arduino informa su ID propio, el dispositivo lógico es el de ese ID (se registra si no existe); si no,
# se reutiliza el vinculado (si está OPERATIVO) o se crea uno de prueba. Conectar otro Arduino reemplaza el vínculo; el anterior queda
# intacto (estado, mediciones e historial). Un mismo dispositivo puede estar vinculado a varias cuentas, y cada medición conserva su cuenta
# y su dispositivo. La vinculación es independiente de la asignación institucional, que no se toca.
# Sin la tabla en la base instalada no se vincula nada y la medición sigue como siempre (schemaCompat.hasTable).

from datetime import datetime  # noqa: F401  (se mantiene por compatibilidad con importadores existentes)

import uuid

from sqlalchemy import false, func, select, true
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


def _findDeviceByCode(db: Session, codigo: str) -> Device | None:
    return db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == codigo.strip().lower()))


def _newTestDevice(db: Session, codigo: str) -> Device:
    device = Device(codigoDispositivo=codigo, nombre="Dispositivo de prueba", modelo=MODELO_PRUEBA,
                    modeloSensor="MAX30100", estado=ESTADO_OPERATIVO)
    db.add(device)
    db.flush()
    return device


def _linkDevice(db: Session, actor, device: Device, *, created: bool) -> None:
    """Vincula la cuenta a `device`, reemplazando el vínculo anterior (el dispositivo anterior no se toca)."""
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
    if link is not None and link.idDispositivo == device.idDispositivo:
        return
    now = nowForDb()
    previous = link.idDispositivo if link is not None else None
    if link is None:
        link = AccountDeviceLink(idUsuario=actor.idUsuario, idDispositivo=device.idDispositivo, fechaVinculo=now)
        db.add(link)
    else:
        link.idDispositivo = device.idDispositivo
        link.fechaVinculo = now
    db.flush()
    if created:
        registerEvent(db, "CRUD", "REGISTRAR_DISPOSITIVO", True, actor.idUsuario, "Dispositivo", device.idDispositivo, modulo="DISPOSITIVOS",
                      datosNuevos={"modeloSensor": "MAX30100", "estado": ESTADO_OPERATIVO, "origen": "CONEXION_CUENTA_INDIVIDUAL_PRUEBA",
                                   "registroAutomatico": True, "idInstitucion": None})
    registerEvent(db, "CRUD", "VINCULAR_CUENTA_DISPOSITIVO", True, actor.idUsuario, "VinculoCuentaDispositivo", link.idVinculo,
                  modulo="DISPOSITIVOS", datosPrevios={"idDispositivo": str(previous)} if previous else None,
                  datosNuevos={"idDispositivo": str(device.idDispositivo), "origen": "CONEXION_CUENTA_INDIVIDUAL_PRUEBA"})


def requireLinkedDevice(db: Session, actor, device: Device, *, physical: bool = False) -> None:
    """Cuenta individual: vincula el dispositivo la primera vez. Si ya tiene otro vinculado, solo cambia cuando `physical` es True
    (el Arduino conectado se verificó como ese dispositivo por su ID propio). Sin tabla, no hace nada."""
    if actor.tipoCuenta != TIPO_INDIVIDUAL or not _available(db):
        return
    link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
    if link is not None and link.idDispositivo != device.idDispositivo and not physical:
        raise AuthError("DISPOSITIVO_YA_VINCULADO",
                        "Tu cuenta tiene vinculado otro dispositivo. Conectá este Arduino con «Conectar dispositivo» para usarlo.")
    _linkDevice(db, actor, device, created=False)


def linkedDeviceCount(db: Session) -> int | None:
    """Dispositivos vinculados a al menos una cuenta individual; None si la base no tiene la tabla todavía."""
    if not _available(db):
        return None
    return db.scalar(select(func.count(func.distinct(AccountDeviceLink.idDispositivo)))) or 0


def connectTestDevice(db: Session, actor) -> Device:
    """«Conectar dispositivo» de una cuenta individual. Con Arduino que informa su ID propio, vincula el dispositivo de ese ID (lo registra
    si no existe). Sin ID propio, reutiliza el vinculado si está OPERATIVO o crea uno de prueba (código generado por el sistema). Requiere el
    puente conectado. No reemplaza ninguna validación de identidad ni de autorización."""
    from app.acquisition.telemetry import hub  # import local: el módulo de adquisición importa servicios de medición

    if actor.tipoCuenta != TIPO_INDIVIDUAL:
        raise AuthError("PERMISO_INSUFICIENTE", "Solo las cuentas individuales conectan dispositivos de prueba.")
    if not _available(db):
        raise AuthError("NO_DISPONIBLE", "Los vínculos de dispositivos todavía no están disponibles en esta instalación.")
    if hub.deviceState() != "CONECTADO":
        raise AuthError("PUENTE_NO_CONECTADO", "Conectá el Arduino para continuar.")
    identity = hub.identity()
    created = False
    if identity["nivel"] == "FISICA" and identity["codigo"]:
        device = _findDeviceByCode(db, identity["codigo"])
        if device is None:
            device = _newTestDevice(db, identity["codigo"].strip())
            created = True
        elif device.idInstitucionAsignada is not None or device.estado != ESTADO_OPERATIVO:
            raise AuthError("DISPOSITIVO_NO_DISPONIBLE",
                            "Este Arduino no está disponible para una cuenta individual: pertenece a una institución o no está operativo.")
    else:
        link = db.scalar(select(AccountDeviceLink).where(AccountDeviceLink.idUsuario == actor.idUsuario))
        current = db.get(Device, link.idDispositivo) if link is not None else None
        if current is not None and current.estado == ESTADO_OPERATIVO:
            device = current
        else:
            device = _newTestDevice(db, str(uuid.uuid4()))
            created = True
    _linkDevice(db, actor, device, created=created)
    db.commit()
    hub.confirm(actor.idUsuario, device.idDispositivo)
    return device


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
