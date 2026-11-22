# MeasurementExport - Exportación del historial propio de mediciones (CSV, Excel o PDF)
#
# Solo la cuenta individual exporta SUS mediciones (perfil propio). Sale lo mismo que filtra el historial (`historyQuery`), con las
# mismas reglas: las canceladas/inválidas vencidas no salen. Toda exportación pasa por `auditedExport`: la auditoría guarda cuántas
# mediciones salieron, nunca sus valores.

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.measurement import ORIGEN_DEMO, Measurement
from app.models.user import User
from app.services import glucoseReference
from app.services import measurement as measurements
from app.services.csvExport import csvDate, csvText
from app.services.exportAudit import auditedExport
from app.services.measurementProfile import TIPO_CONSUMIDOR_FINAL, getConsumerProfile
from app.services.tableExport import tableFile
from app.utils.timeZone import nowForDb

EXPORT_TIPO_DATOS = "MEDICIONES_PROPIAS"
MAX_EXPORT_ROWS = 5000  # una exportación de más que esto se acota con el período: un archivo gigante no es el objetivo
EXPORT_COLUMNS = (
    "Fecha y hora", "Modo", "Estado", "Condición de comida", "Última comida", "SpO2 (%)", "Frecuencia cardíaca (lpm)",
    "Glucosa del dispositivo (mg/dL)", "Origen de la glucosa", "Semáforo", "Origen de los datos",
    "Dispositivo", "Observación",
)
_MODOS = {"OXIMETRIA": "Oximetría", "GLUCOSA_EXPERIMENTAL": "Glucosa (experimental)"}
_ESTADOS = {"PENDIENTE": "Pendiente", "ADQUIRIENDO": "Adquiriendo datos", "PROCESANDO": "Procesando", "COMPLETADA": "Completada",
            "INVALIDA": "Inválida", "CANCELADA": "Cancelada"}
_COMIDAS = {"AYUNO": "En ayunas", "POSTPRANDIAL": "Después de comer", "NO_INFORMADA": "Comida sin informar"}
_ORIGENES_GLUCOSA = {"DEMO": "DEMO (prueba)", "EXPERIMENTAL": "Experimental", "SIN_CALIBRAR": "Sin calibrar"}
_SEMAFOROS = {"ROJO": "Rojo", "AMARILLO": "Amarillo", "VERDE": "Verde"}


def _number(value: Decimal | float | int | None, decimals: int = 2) -> str:
    """Número con coma decimal (como se ve en pantalla). Vacío si no hay dato."""
    if value is None:
        return ""
    return f"{float(value):.{decimals}f}".replace(".", ",")


def _label(labels: dict, code: str | None) -> str:
    return "" if code is None else labels.get(code, code)


def _row(measurement: Measurement, codigoDispositivo: str | None, semaforo: str | None) -> list[str]:
    return [
        csvDate(measurement.fechaHoraInicio),
        _label(_MODOS, measurement.modoMedicion),
        _label(_ESTADOS, measurement.estadoMedicion),
        _label(_COMIDAS, measurement.condicionComida),
        "Sin informar" if measurement.fechaHoraUltimaComida is None else csvDate(measurement.fechaHoraUltimaComida),
        _number(measurement.spo2),
        "" if measurement.frecuenciaCardiaca is None else str(measurement.frecuenciaCardiaca),
        _number(measurement.glucosaDispositivo, 1),
        _label(_ORIGENES_GLUCOSA, measurement.origenGlucosa),
        _label(_SEMAFOROS, semaforo),
        "Prueba (DEMO)" if measurement.origenGlucosa == ORIGEN_DEMO else "Real",
        csvText(codigoDispositivo or ""),
        csvText(measurement.observacion or ""),
    ]


def _rows(db: Session, found: list[Measurement]) -> list[list[str]]:
    if len(found) > MAX_EXPORT_ROWS:
        raise AuthError("DATOS_INVALIDOS", f"Hay más de {MAX_EXPORT_ROWS} mediciones con esos filtros. Acotá el período y volvé a exportar.")
    codes = {d.idDispositivo: d.codigoDispositivo for d in db.scalars(
        select(Device).where(Device.idDispositivo.in_({m.idDispositivo for m in found}))).all()} if found else {}
    preloaded = glucoseReference.preload(db, [m for m in found if measurements._needsSemaphore(m)])
    return [_row(m, codes.get(m.idDispositivo), measurements._semaphoreOf(db, m, preloaded)) for m in found]


def exportOwnMeasurements(db: Session, actor: User, *, alcance: str, ids: list[uuid.UUID] | None = None, desde=None, hasta=None,
                          modo: str | None = None, estado: str | None = None, origen: str | None = None, orden: str = "desc",
                          formato: str = "csv") -> tuple[bytes, str]:
    """Mis mediciones (`SELECCION` o `TODOS`) en CSV, Excel o PDF. Devuelve (contenido, nombre del archivo)."""
    with auditedExport(db, actor, EXPORT_TIPO_DATOS, ambito="CUENTA", formato=formato.upper()) as export:
        if actor.tipoCuenta != TIPO_CONSUMIDOR_FINAL:
            raise AuthError("PERFIL_NO_DISPONIBLE", "Solo una cuenta individual tiene un historial de mediciones propio.")
        now = nowForDb()
        profile = getConsumerProfile(db, actor)
        wanted = list(dict.fromkeys(ids or []))
        if alcance == "SELECCION" and not wanted:
            raise AuthError("DATOS_INVALIDOS", "Elegí al menos una medición para exportar.")
        found: list[Measurement] = []
        if profile is not None:  # sin perfil no hay mediciones: el archivo sale vacío, como el historial
            if alcance == "SELECCION":
                query = measurements.historyQuery(profile.idPerfilMedicion, desde=None, hasta=None, modo=None, estado=None,
                                                  hideExpired=True).where(Measurement.idMedicion.in_(wanted))
            else:
                query = measurements.historyQuery(profile.idPerfilMedicion, desde=desde, hasta=hasta, modo=modo, estado=estado,
                                                  origen=origen, hideExpired=True)
            query = query.order_by(Measurement.fechaHoraInicio.asc() if orden == "asc" else Measurement.fechaHoraInicio.desc(),
                                   Measurement.idMedicion)
            found = list(db.scalars(query).all())
        if alcance == "SELECCION" and len(found) != len(wanted):
            raise AuthError("DATOS_INVALIDOS", "Alguna de las mediciones seleccionadas ya no está disponible. Actualizá el historial.")
        rows = _rows(db, found)
        export.registros = len(rows)
        return tableFile(formato, f"mis-mediciones-{now:%Y%m%d-%H%M}",
                         "Mis mediciones · prototipo experimental, no es un diagnóstico", EXPORT_COLUMNS, rows, now)
