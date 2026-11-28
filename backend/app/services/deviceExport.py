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
from app.services.deviceReport import DeviceRecord, inventoryFile
from app.services.exportAudit import auditedExport
from app.services.tableExport import FormatoExportacion, tableFile
from app.utils.timeZone import nowForDb

EXPORT_TIPO_DATOS = "DISPOSITIVOS"
COLUMNS = ("Código", "Nombre", "Modelo", "Estado", "Uso", "Responsable", "Sensor", "Firmware", "Registrado",
           "Asignado a la institución desde")
_ESTADO = {"OPERATIVO": "Operativo", "EN_MANTENIMIENTO": "En mantenimiento", "FUERA_DE_SERVICIO": "Fuera de servicio", "BAJA": "Descomisionado"}
_TITULO = "Inventario de dispositivos"


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


def _records(db: Session, scope: deviceService.Scope, devices: list[Device]) -> list[DeviceRecord]:
    """Un registro por dispositivo, con los mismos datos que muestra el listado para el alcance de la cuenta."""
    institutionName = None
    if scope.idInstitucion is not None:
        institution = db.get(Institution, scope.idInstitucion)
        institutionName = institution.nombre if institution else None
    records = []
    for device in devices:
        item = deviceService._item(db, device, scope)
        institucional = item.idInstitucionAsignada is not None
        records.append(DeviceRecord(
            codigo=device.codigoDispositivo, nombre=device.nombre, modelo=device.modelo,
            estado=_ESTADO.get(device.estado, device.estado), operativo=device.estado == "OPERATIVO",
            uso=_uso(item, institutionName), responsable=_responsable(item, scope), sensor=device.modeloSensor,
            firmware=device.versionFirmware, registrado=item.fechaRegistro, institucional=institucional,
            institucion=(item.nombreInstitucion or institutionName) if institucional else None,
            incorporado=item.fechaAsignacionInstitucional,
        ))
    return records


def _csvRows(records: list[DeviceRecord]) -> list[list[str]]:
    """El CSV conserva sus columnas y su formato de siempre."""
    return [[csvText(r.codigo), csvText(r.nombre), csvText(r.modelo), csvText(r.estado), csvText(r.uso), csvText(r.responsable),
             csvText(r.sensor), csvText(r.firmware), csvDate(r.registrado), csvDate(r.incorporado)] for r in records]


def _filtros(alcance: str, cantidad: int, busqueda: str | None, estado: str | None, asignado: bool | None,
             uso: str | None) -> list[tuple[str, str]]:
    """Solo los filtros que de verdad se aplicaron, en el mismo lenguaje que el listado."""
    if alcance == "SELECCION":
        return [("Alcance", f"Selección manual ({cantidad} marcados)")]
    filtros = []
    if busqueda and busqueda.strip():
        filtros.append(("Búsqueda", busqueda.strip()))
    if estado:
        filtros.append(("Estado", _ESTADO.get(deviceService.ESTADO_ALIAS.get(estado, estado), estado)))
    if asignado is True:
        filtros.append(("Asignación", "Con institución"))
    elif asignado is False:
        filtros.append(("Asignación", "Sin institución"))
    if uso == "INSTITUCION":
        filtros.append(("Tipo de uso", "Uso institucional"))
    elif uso == "INDIVIDUAL":
        filtros.append(("Tipo de uso", "Uso individual"))
    return filtros or [("Filtros", "Ninguno: todos los dispositivos que puede ver")]


def _archivo(formato: str, nombreBase: str, titulo: str, filtros: list[tuple[str, str]], records: list[DeviceRecord], now):
    if formato == "csv":
        return tableFile("csv", nombreBase, titulo, COLUMNS, _csvRows(records), now)
    return inventoryFile(formato, nombreBase, titulo, filtros, records, now)


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
        filtros = _filtros(alcance, len(devices), busqueda, estado, asignado, uso)
        return _archivo(formato, f"dispositivos-{now:%Y%m%d-%H%M}", _TITULO, filtros, _records(db, scope, devices), now)


def exportDevice(db: Session, scope: deviceService.Scope, idDispositivo: uuid.UUID, formato: FormatoExportacion = "csv") -> tuple[bytes, str]:
    """Datos de un dispositivo (el mismo alcance que su detalle) en CSV, Excel o PDF. Devuelve (contenido, nombre del archivo)."""
    with auditedExport(db, scope.actor, EXPORT_TIPO_DATOS, ambito=_ambito(scope), idInstitucion=scope.idInstitucion,
                       formato=formato.upper()) as export:
        deviceService._require(db, scope, "ver", "CONSULTAR_DISPOSITIVO")
        device = deviceService._load(db, scope, idDispositivo)
        export.registros = 1
        now = nowForDb()
        safe = re.sub(r"[^A-Za-z0-9]+", "-", device.codigoDispositivo or "dispositivo").strip("-")[:40] or "dispositivo"
        filtros = [("Código", device.codigoDispositivo)]
        return _archivo(formato, f"dispositivo-{safe}-{now:%Y%m%d-%H%M}", f"Dispositivo {device.codigoDispositivo}", filtros,
                        _records(db, scope, [device]), now)
