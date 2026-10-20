# DeviceConnection - Identificación, alta y vinculación del dispositivo desde la conexión de un operador
#
# Une dos procesos que antes estaban separados: «Conectar dispositivo» (puente, puerto, telemetría) y el inventario institucional.
# No crea estructuras nuevas: usa dbo.Dispositivo (services/device.py) y el estado en vivo del puente (acquisition/telemetry.py).
#
# Flujo del operador:  Conectar dispositivo → identificar o seleccionar → registrar si es nuevo → vincular a la institución → elegir al
# paciente (al medir) → medir.
#
#   1. Identidad: el Arduino informa su ID persistente (EEPROM, `GLUCOLUME,ID=<uuid>,...`). Ese ID —nunca el puerto COM, el medio ni
#      la computadora— es el `codigoDispositivo` del inventario. Si no lo informa (firmware anterior) solo se conoce el código que se
#      configuró en el puente: eso NO prueba qué Arduino es, así que todo lo que lo asocie a la institución (registrar, vincular o
#      seleccionar uno existente) exige que el operador CONFIRME EXPLÍCITAMENTE que ese es el Arduino conectado.
#   2. Registro: con comunicación verificada, un operador registra el dispositivo NUEVO en SU institución (a cargo del propietario vigente).
#   3. Vinculación: un dispositivo que existe pero NO tiene institución (el que dio de alta el puente o usó una cuenta individual) NO se
#      adjudica solo: el operador lo vincula con una confirmación explícita, con el Arduino conectado y verificado. Pasa al inventario de la
#      institución (el propietario lo ve) y conserva todas sus mediciones. Con el uso restringido (ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE=false)
#      deja de estar disponible para las cuentas individuales; con el uso compartido (DEC-01) lo siguen usando todas las cuentas habilitadas.
#   4. Nunca se transfiere: un dispositivo de OTRA institución no se vincula; con el uso restringido tampoco se usa ni se revela a quién
#      pertenece (es un procedimiento administrativo: asignación del administrador). Con el uso compartido se usa sin cambiar su titularidad.
#   5. Medición: con el uso restringido un paciente se mide solo con dispositivos del inventario de su institución; con el uso compartido,
#      con cualquier dispositivo operativo. El paciente se elige recién al medir (services/telemetry.startSession), así que acá no se asocia.
#
# Estados que no se mezclan: administrativo (OPERATIVO, EN_MANTENIMIENTO, FUERA_DE_SERVICIO, BAJA), de comunicación (estado del
# puente: conectado, sin datos, desconectado) y disponibilidad para medir (los dos anteriores más el perfil y que nadie más esté midiendo).

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.institution import Institution
from app.models.user import User
from app.schemas.acquisition import DeviceConnectConfirm, DeviceConnectLink, DeviceConnectRegister
from app.services import device as deviceService
from app.services.audit import registerEvent

MAX_CANDIDATES = 50
UNVERIFIED = ("No se pudo confirmar qué Arduino es: este firmware no informa un identificador propio, y el puerto, el medio o la velocidad no "
              "alcanzan para saberlo.")


def _summary(device: Device) -> dict:
    return {"idDispositivo": device.idDispositivo, "codigoDispositivo": device.codigoDispositivo, "nombre": device.nombre,
            "modeloSensor": device.modeloSensor, "versionFirmware": device.versionFirmware, "estado": device.estado}


def _candidates(db: Session, idInstitucion: uuid.UUID, relationId: uuid.UUID, suggestedCode: str | None) -> list[dict]:
    """Dispositivos que este operador puede usar y que podría ser el que conectó: los DEL INVENTARIO de su institución o, con el uso
    compartido (DEC-01), cualquier dispositivo operativo."""
    query = select(Device).where(Device.estado == deviceService.OPERATIVO)
    if not deviceService.sharedDeviceMode():
        query = query.where(Device.idInstitucionAsignada == idInstitucion)
    devices = db.scalars(query.order_by(Device.nombre, Device.codigoDispositivo).limit(MAX_CANDIDATES)).all()
    suggested = (suggestedCode or "").lower()
    return [{"idDispositivo": d.idDispositivo, "codigoDispositivo": d.codigoDispositivo, "nombre": d.nombre,
             "sugerido": d.codigoDispositivo.lower() == suggested}
            for d in devices if deviceService.usableBy(d, idInstitucion, relationId)[0]]


def _placed(view: dict) -> dict:
    """Disponibilidad EN LA INSTITUCIÓN del operador: un dispositivo sin institución todavía no se puede medir con pacientes (se vincula primero).
    Con el uso compartido (DEC-01) la asignación no restringe el uso: decide solo el estado del dispositivo."""
    if deviceService.sharedDeviceMode():
        return {"usable": view["usable"], "motivo": view["motivo"]}
    if view["situacion"] == "SIN_INSTITUCION":
        return {"usable": False, "motivo": view["motivo"] or "Todavía no pertenece al inventario de tu institución: vinculalo para medir con pacientes."}
    if view["situacion"] == "DE_OTRA_INSTITUCION":
        return {"usable": False, "motivo": "El dispositivo pertenece a otra institución: pedí a la administración su reasignación."}
    return {"usable": view["usable"], "motivo": view["motivo"]}


def identification(db: Session, actor: User, idInstitucion: uuid.UUID, membership=None) -> dict:
    """Qué dispositivo hay conectado y cómo está respecto de la institución del operador. Solo lectura: nunca registra, vincula ni confirma."""
    membership = membership or deviceService.operatorMembership(db, actor, idInstitucion)
    relationId = membership.relation.idInstitucionUsuario
    institution = db.get(Institution, idInstitucion)
    snap = hub.snapshot(actor.idUsuario)
    base = {"institucion": {"idInstitucion": idInstitucion, "nombre": institution.nombre if institution else ""},
            "medio": (snap["puente"] or {}).get("medio"), "compartido": deviceService.sharedDeviceMode()}
    none = {**base, "nivel": "NINGUNA", "codigo": None, "firmware": None, "situacion": "SIN_COMUNICACION", "confirmada": False,
            "dispositivo": None, "usable": False, "motivoNoDisponible": None, "puedeRegistrar": False, "puedeVincular": False,
            "requiereConfirmacion": False, "dispositivoDeclarado": None, "candidatos": []}
    # Sin comunicación verificable no se reconoce ni se ofrece registrar nada: un puerto COM o un emparejamiento no alcanzan.
    if snap["estado"] != "CONECTADO":
        return none
    identity = hub.identity()
    code = identity["codigo"]
    if identity["nivel"] == "NINGUNA" or code is None:
        return none
    shared = {**base, "nivel": identity["nivel"], "codigo": code, "firmware": identity["firmware"]}
    device = deviceService.findByCode(db, code)
    view = deviceService.standing(device, idInstitucion, relationId)
    placed = _placed(view)
    # Con el uso compartido (DEC-01) el equipo es de uso común: se muestra aunque esté asignado a otra institución.
    visible = device if view["situacion"] in ("DE_LA_INSTITUCION", "SIN_INSTITUCION") or deviceService.sharedDeviceMode() else None
    linkable = view["situacion"] == "SIN_INSTITUCION" and device is not None and device.estado != deviceService.BAJA

    if identity["nivel"] == "FISICA":
        return {**shared, "situacion": view["situacion"], "confirmada": True, "dispositivo": _summary(visible) if visible else None,
                "usable": placed["usable"], "motivoNoDisponible": placed["motivo"],
                "puedeRegistrar": view["situacion"] == "NO_REGISTRADO" and identity["sensor"] in ("MAX30100", "MAX30102"),
                "puedeVincular": linkable, "requiereConfirmacion": False, "dispositivoDeclarado": None, "candidatos": []}

    # Identidad solo declarada: nada prueba qué Arduino es. Lo que lo asocia a la institución se confirma a mano.
    chosenId = hub.confirmedDevice(actor.idUsuario)
    chosen = db.get(Device, chosenId) if chosenId is not None else None
    if chosen is not None:
        chosenView = deviceService.standing(chosen, idInstitucion, relationId)
        placedChosen = _placed(chosenView)
        return {**shared, "situacion": chosenView["situacion"], "confirmada": True, "dispositivo": _summary(chosen),
                "usable": placedChosen["usable"], "motivoNoDisponible": placedChosen["motivo"], "puedeRegistrar": False,
                "puedeVincular": False, "requiereConfirmacion": False, "dispositivoDeclarado": None, "candidatos": []}
    return {**shared, "situacion": "IDENTIDAD_NO_CONFIRMADA", "confirmada": False, "dispositivo": None, "usable": False,
            "motivoNoDisponible": UNVERIFIED, "puedeRegistrar": view["situacion"] == "NO_REGISTRADO", "puedeVincular": linkable,
            "requiereConfirmacion": True, "dispositivoDeclarado": _summary(visible) if visible and view["situacion"] == "SIN_INSTITUCION" else None,
            "candidatos": _candidates(db, idInstitucion, relationId, code)}


def _requireCommunication() -> dict:
    if hub.deviceState() != "CONECTADO":
        raise AuthError("DISPOSITIVO_NO_CONECTADO",
                        "No hay comunicación verificada con el Arduino: un puerto COM o un emparejamiento Bluetooth no alcanzan para registrarlo.")
    return hub.identity()


def _requireNotInUseByOthers(actor: User) -> None:
    if hub.session is not None and hub.session.userId != actor.idUsuario:
        raise AuthError("DISPOSITIVO_EN_USO", "El dispositivo está siendo usado por otra cuenta.")


def _requireManualConfirmation(identity: dict, confirmed: bool) -> None:
    """Sin ID propio, asociar el dispositivo a la institución exige que la persona confirme explícitamente que ese es el Arduino conectado."""
    if identity["nivel"] == "FISICA":
        return
    if identity["nivel"] != "DECLARADA" or identity["codigo"] is None:
        raise AuthError("DISPOSITIVO_NO_CONECTADO", "No hay un dispositivo identificado para asociar.")
    if not confirmed:
        raise AuthError("IDENTIDAD_NO_CONFIRMADA",
                        UNVERIFIED + " Confirmá explícitamente que el Arduino conectado es este dispositivo, o cargá el firmware actualizado.")


def _result(db: Session, actor: User, idInstitucion: uuid.UUID, membership, **flags) -> dict:
    return {"creado": False, "vinculado": False, **flags, "identificacion": identification(db, actor, idInstitucion, membership)}


def register(db: Session, actor: User, data: DeviceConnectRegister) -> dict:
    """«Registrar nuevo dispositivo»: alta en la institución del operador con lo que informa el Arduino y el nombre que le pone. Con identidad
    solo declarada (firmware sin ID) hace falta además la confirmación explícita de que el Arduino conectado es este."""
    membership = deviceService.operatorMembership(db, actor, data.idInstitucion)
    identity = _requireCommunication()
    _requireManualConfirmation(identity, data.confirmaIdentidad)
    _requireNotInUseByOthers(actor)
    bridge = hub.bridge
    medium = bridge.medium if bridge else None
    device, created = deviceService.registerFromConnection(
        db, actor, data.idInstitucion, identity["codigo"], nombre=data.nombre, sensor=identity["sensor"] or "MAX30100",
        firmware=identity["firmware"], medio=medium, identidad=identity["nivel"])
    if identity["nivel"] == "DECLARADA":
        hub.confirm(actor.idUsuario, device.idDispositivo)
    elif not created:
        deviceService.syncConnection(db, actor, device, firmware=identity["firmware"], medio=medium, identidad=identity["nivel"])
    return _result(db, actor, data.idInstitucion, membership, creado=created)


def link(db: Session, actor: User, data: DeviceConnectLink) -> dict:
    """«Vincular a la institución» un dispositivo existente que no pertenece a ninguna, con confirmación explícita y autorizada: el operador
    activo de la institución, con el Arduino conectado y verificado (con ID propio, el que informó; sin él, el del código del puente y la
    confirmación manual). No modifica dispositivos de otras instituciones ni los descomisionados y no duplica registros."""
    membership = deviceService.operatorMembership(db, actor, data.idInstitucion)
    if not data.confirmaVinculacion:
        effect = ("con el uso compartido habilitado lo siguen usando las demás cuentas" if deviceService.sharedDeviceMode()
                  else "deja de estar disponible para las cuentas individuales")
        raise AuthError("CONFIRMACION_REQUERIDA",
                        f"Confirmá explícitamente que querés vincular este dispositivo a tu institución: pasa al inventario de la institución, "
                        f"{effect} y sus mediciones anteriores se conservan.")
    identity = _requireCommunication()
    device = db.get(Device, data.idDispositivo)
    # Los de otra institución responden como inexistentes: no se revela que existen.
    if device is None or device.idInstitucionAsignada not in (None, data.idInstitucion):
        raise AuthError("DISPOSITIVO_NO_ENCONTRADO", deviceService.NOT_FOUND)
    _requireManualConfirmation(identity, data.confirmaIdentidad)
    if device.codigoDispositivo.strip().lower() != (identity["codigo"] or "").lower():
        raise AuthError("DISPOSITIVO_NO_COINCIDE", "El Arduino conectado no es este dispositivo: no se puede vincular.")
    _requireNotInUseByOthers(actor)
    bridge = hub.bridge
    medium = bridge.medium if bridge else None
    device, linked = deviceService.linkToInstitution(db, actor, data.idInstitucion, device, nombre=data.nombre, medio=medium,
                                                     identidad=identity["nivel"])
    if identity["nivel"] == "DECLARADA":
        hub.confirm(actor.idUsuario, device.idDispositivo)
    else:
        deviceService.syncConnection(db, actor, device, firmware=identity["firmware"], medio=medium, identidad=identity["nivel"])
    return _result(db, actor, data.idInstitucion, membership, vinculado=linked)


def confirm(db: Session, actor: User, data: DeviceConnectConfirm) -> dict:
    """Selecciona/confirma un dispositivo del inventario de la institución para la conexión actual. Con ID propio solo se acepta el que el
    Arduino informó; sin él, la confirmación manual vale mientras no cambie la conexión (puerto, medio, Arduino) y queda auditada."""
    membership = deviceService.operatorMembership(db, actor, data.idInstitucion)
    relationId = membership.relation.idInstitucionUsuario
    identity = _requireCommunication()
    device = db.get(Device, data.idDispositivo)
    shared = deviceService.sharedDeviceMode()  # DEC-01: con el uso compartido se confirma cualquier dispositivo operativo, sin vincularlo
    # Los de otra institución responden como inexistentes: no se revela que existen.
    if device is None or (not shared and device.idInstitucionAsignada not in (None, data.idInstitucion)):
        raise AuthError("DISPOSITIVO_NO_ENCONTRADO", deviceService.NOT_FOUND)
    if device.idInstitucionAsignada is None and not shared:
        raise AuthError("DISPOSITIVO_SIN_VINCULAR", "El dispositivo todavía no pertenece al inventario de tu institución: vinculalo primero.")
    usable, reason = deviceService.usableBy(device, data.idInstitucion, relationId)
    if not usable:
        raise AuthError("DISPOSITIVO_NO_DISPONIBLE", reason or "El dispositivo no está disponible.")
    bridge = hub.bridge
    medium = bridge.medium if bridge else None
    if identity["nivel"] == "FISICA":
        if device.codigoDispositivo.strip().lower() != (identity["codigo"] or "").lower():
            raise AuthError("DISPOSITIVO_NO_COINCIDE", "El Arduino conectado se identificó como otro dispositivo: no se puede asociar a este.")
        deviceService.syncConnection(db, actor, device, firmware=identity["firmware"], medio=medium, identidad="FISICA")
    else:
        hub.confirm(actor.idUsuario, device.idDispositivo)
        registerEvent(db, "CRUD", "CONFIRMAR_DISPOSITIVO_CONEXION", True, actor.idUsuario, "Dispositivo", device.idDispositivo,
                      modulo="DISPOSITIVOS", idInstitucion=data.idInstitucion,
                      datosNuevos={"identificacion": "DECLARADA", "medio": medium, "confirmacionManual": True},
                      observacion="Identidad física no verificable: el operador confirmó manualmente qué dispositivo es.")
        db.commit()
    return _result(db, actor, data.idInstitucion, membership)
