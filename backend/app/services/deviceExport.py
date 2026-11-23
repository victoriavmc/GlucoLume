# DeviceExport - Exportación del inventario de dispositivos (CSV, Excel o PDF)
#
# Exporta lo mismo que el listado del que sale el pedido: el alcance (inventario global o de una institución), el permiso de consulta,
# los filtros y lo que cada cuenta puede ver (un operador ve menos) salen de device.py. Nadie exporta más de lo que ve en pantalla.
# No incluye datos de pacientes ni los datos personales de las cuentas individuales vinculadas (solo si el dispositivo está vinculado).
# Cada exportación queda en la auditoría (ver exportAudit.py).

import re
import uuid

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.institution import Institution
from app.services import device as deviceService
from app.services import schemaCompat
from app.services.csvExport import csvDate, csvText
from app.services.exportAudit import auditedExport
from app.services.tableExport import FormatoExportacion, tableFile
from app.utils.timeZone import nowForDb

EXPORT_TIPO_DATOS = "DISPOSITIVOS"
COLUMNS = ("Código", "Nombre", "Modelo", "Estado", "Uso", "Responsable", "Sensor", "Firmware", "Registrado",
           "Asignado a la institución desde")
_ESTADO = {"OPERATIVO": "Operativo", "EN_MANTENIMIENTO": "En mantenimiento", "FUERA_DE_SERVICIO": "Fuera de servicio", "BAJA": "Descomisionado"}


def _ambito(scope: deviceService.Scope) -> str:
    return "INSTITUCION" if scope.idInstitucion is not None else "PLATAFORMA"


def _personName(person) -> str:
    return " ".join(part for part in (person.nombre, person.apellido) if part) or "Sin nombre"


def _uso(item, institutionName: str | None) -> str:
    """Igual que la columna «Uso» del listado: la institución asignada, «Individual» o «Sin asignar»."""
    if item.idInstitucionAsignada:
        return item.nombreInstitucion or institutionName or "Institución"
    return "Individual" if item.vinculadoCuentasIndividuales else "Sin asignar"


def _responsable(item, scope: deviceService.Scope) -> str:
    """Igual que la columna «Responsable» del listado de cada ámbito (plataforma: correo; institución: nombre)."""
    responsable = item.responsable
    if scope.idInstitucion is None:
        if responsable:
            return responsable.correoElectronico or _personName(responsable)
        if item.correosIndividuales:
            return ", ".join(item.correosIndividuales)
        return "Sin responsable" if item.idInstitucionAsignada else "No responsable"
    if responsable:
        return _personName(responsable)
    return "Vos" if item.esMio else "Sin asignar"


def _rows(db: Session, scope: deviceService.Scope, devices: list[Device]) -> list[list[str]]:
    institutionName = None
    if scope.idInstitucion is not None:
        institution = db.get(Institution, scope.idInstitucion)
        institutionName = institution.nombre if institution else None
    rows = []
    for device in devices:
        item = deviceService._item(db, device, scope)
        rows.append([
            csvText(device.codigoDispositivo), csvText(device.nombre), csvText(device.modelo),
            csvText(_ESTADO.get(device.estado, device.estado)), csvText(_uso(item, institutionName)),
            csvText(_responsable(item, scope)), csvText(device.modeloSensor), csvText(device.versionFirmware),
            csvDate(item.fechaRegistro), csvDate(item.fechaAsignacionInstitucional),
        ])
    return rows


def exportDevices(db: Session, scope: deviceService.Scope, *, alcance: str, ids: list[uuid.UUID] | None = None, busqueda: str | None = None,
                  estado: str | None = None, asignado: bool | None = None, uso: str | None = None,
                  formato: FormatoExportacion = "csv") -> tuple[bytes, str]:
    """Inventario (`SELECCION` o `TODOS`) en CSV, Excel o PDF. Devuelve (contenido, nombre del archivo)."""
    with auditedExport(db, scope.actor, EXPORT_TIPO_DATOS, ambito=_ambito(scope), idInstitucion=scope.idInstitucion,
                       formato=formato.upper()) as export:
        deviceService._require(db, scope, "ver", "CONSULTAR_INVENTARIO_DISPOSITIVOS")
        deviceService._checkFilters(estado)
        linksAvailable = schemaCompat.hasTable(db, "VinculoCuentaDispositivo")
        if alcance == "SELECCION":
            selected = list(dict.fromkeys(ids or []))
            base = select(Device).where(Device.idDispositivo.in_(selected)) if selected else select(Device).where(false())
            query = deviceService._filtered(base, scope, busqueda=None, estado=None, asignado=None, idInstitucion=None,
                                            linksAvailable=linksAvailable)
        else:
            query = deviceService._filtered(select(Device), scope, busqueda=busqueda, estado=estado, asignado=asignado,
                                            idInstitucion=None, uso=uso, linksAvailable=linksAvailable)
        devices = list(db.scalars(query.order_by(Device.fechaRegistro.desc(), Device.codigoDispositivo)).all())
        export.registros = len(devices)
        now = nowForDb()
        return tableFile(formato, f"dispositivos-{now:%Y%m%d-%H%M}", "Inventario de dispositivos", COLUMNS, _rows(db, scope, devices), now)


def exportDevice(db: Session, scope: deviceService.Scope, idDispositivo: uuid.UUID, formato: FormatoExportacion = "csv") -> tuple[bytes, str]:
    """Datos de un dispositivo (el mismo alcance que su detalle) en CSV, Excel o PDF. Devuelve (contenido, nombre del archivo)."""
    with auditedExport(db, scope.actor, EXPORT_TIPO_DATOS, ambito=_ambito(scope), idInstitucion=scope.idInstitucion,
                       formato=formato.upper()) as export:
        deviceService._require(db, scope, "ver", "CONSULTAR_DISPOSITIVO")
        device = deviceService._load(db, scope, idDispositivo)
        export.registros = 1
        now = nowForDb()
        safe = re.sub(r"[^A-Za-z0-9]+", "-", device.codigoDispositivo or "dispositivo").strip("-")[:40] or "dispositivo"
        return tableFile(formato, f"dispositivo-{safe}-{now:%Y%m%d-%H%M}", f"Dispositivo {device.codigoDispositivo}", COLUMNS,
                         _rows(db, scope, [device]), now)
