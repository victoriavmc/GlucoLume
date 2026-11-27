# MeasurementExport - Exportación del historial propio de mediciones (CSV, Excel o PDF)
#
# Solo la cuenta individual exporta SUS mediciones (perfil propio). Sale lo mismo que filtra el historial (`historyQuery`), con las
# mismas reglas: las canceladas/inválidas vencidas no salen. Toda exportación pasa por `auditedExport`: la auditoría guarda cuántas
# mediciones salieron, nunca sus valores. El formato y la presentación de cada archivo viven en `measurementReport`.

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.measurement import ORIGEN_DEMO, Measurement
from app.models.user import User
from app.services import glucoseReference
from app.services import measurement as measurements
from app.services import measurementReport as report
from app.services.exportAudit import auditedExport
from app.services.measurementProfile import TIPO_CONSUMIDOR_FINAL, getConsumerProfile
from app.utils.timeZone import nowForDb

EXPORT_TIPO_DATOS = "MEDICIONES_PROPIAS"
MAX_EXPORT_ROWS = 5000  # una exportación de más que esto se acota con el período: un archivo gigante no es el objetivo
EXPORT_COLUMNS = report.CSV_COLUMNS  # encabezados del CSV (y las columnas de la hoja «Mediciones» del Excel)
_MODOS = {"OXIMETRIA": "Oximetría", "GLUCOSA_EXPERIMENTAL": "Glucosa (experimental)"}
_ESTADOS = {"PENDIENTE": "Pendiente", "ADQUIRIENDO": "Adquiriendo datos", "PROCESANDO": "Procesando", "COMPLETADA": "Completada",
            "INVALIDA": "Inválida", "CANCELADA": "Cancelada"}
_COMIDAS = {"AYUNO": "En ayunas", "POSTPRANDIAL": "Después de comer", "NO_INFORMADA": "Comida sin informar"}
_ORIGENES_GLUCOSA = {"DEMO": "DEMO (prueba)", "EXPERIMENTAL": "Experimental", "SIN_CALIBRAR": "Sin calibrar"}
_SEMAFOROS = {"ROJO", "AMARILLO", "VERDE"}


def _label(labels: dict, code: str | None) -> str:
    return "" if code is None else labels.get(code, code)


def _line(measurement: Measurement, codigoDispositivo: str | None, semaforo: str | None) -> report.ReportLine:
    return report.ReportLine(
        fecha=measurement.fechaHoraInicio,
        modo=_label(_MODOS, measurement.modoMedicion),
        estado=_label(_ESTADOS, measurement.estadoMedicion),
        condicion=_label(_COMIDAS, measurement.condicionComida),
        ultimaComida=measurement.fechaHoraUltimaComida,
        spo2=None if measurement.spo2 is None else float(measurement.spo2),
        frecuenciaCardiaca=measurement.frecuenciaCardiaca,
        glucosa=None if measurement.glucosaDispositivo is None else float(measurement.glucosaDispositivo),
        origenGlucosa=_label(_ORIGENES_GLUCOSA, measurement.origenGlucosa) or None,
        semaforo=semaforo if semaforo in _SEMAFOROS else None,
        esDemo=measurement.origenGlucosa == ORIGEN_DEMO,
        dispositivo=codigoDispositivo or "",
        observacion=measurement.observacion or "",
    )


def _rows(db: Session, found: list[Measurement]) -> list[report.ReportLine]:
    if len(found) > MAX_EXPORT_ROWS:
        raise AuthError("DATOS_INVALIDOS", f"Hay más de {MAX_EXPORT_ROWS} mediciones con esos filtros. Acotá el período y volvé a exportar.")
    codes = {d.idDispositivo: d.codigoDispositivo for d in db.scalars(
        select(Device).where(Device.idDispositivo.in_({m.idDispositivo for m in found}))).all()} if found else {}
    preloaded = glucoseReference.preload(db, [m for m in found if measurements._needsSemaphore(m)])
    return [_line(m, codes.get(m.idDispositivo), measurements._semaphoreOf(db, m, preloaded)) for m in found]


def _alcanceTexto(alcance: str, cantidad: int) -> str:
    return f"Mediciones seleccionadas ({cantidad})" if alcance == "SELECCION" else "Historial de mediciones"


def _filtrosTexto(modo, estado, origen, condicion) -> str:
    partes = []
    if modo:
        partes.append(f"modo {_MODOS.get(modo, modo)}")
    if estado:
        partes.append(f"estado {_ESTADOS.get(estado, estado)}")
    if origen == ORIGEN_DEMO:
        partes.append("solo pruebas DEMO")
    elif origen == "REAL":
        partes.append("solo mediciones reales")
    if condicion:
        partes.append(f"condición {_COMIDAS.get(condicion, condicion)}")
    return ", ".join(partes) if partes else "sin filtros adicionales"


def exportOwnMeasurements(db: Session, actor: User, *, alcance: str, ids: list[uuid.UUID] | None = None, desde=None, hasta=None,
                          modo: str | None = None, estado: str | None = None, origen: str | None = None, orden: str = "desc",
                          formato: str = "csv", condicion: str | None = None) -> tuple[bytes, str]:
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
                                                  origen=origen, hideExpired=True, condicion=condicion)
            query = query.order_by(Measurement.fechaHoraInicio.asc() if orden == "asc" else Measurement.fechaHoraInicio.desc(),
                                   Measurement.idMedicion)
            found = list(db.scalars(query).all())
        if alcance == "SELECCION" and len(found) != len(wanted):
            raise AuthError("DATOS_INVALIDOS", "Alguna de las mediciones seleccionadas ya no está disponible. Actualizá el historial.")
        rows = _rows(db, found)
        export.registros = len(rows)
        if alcance == "SELECCION":
            periodo, filtros = "según la selección", "mediciones elegidas a mano"
        else:
            periodo = report.periodoTexto(desde if isinstance(desde, date) else None, hasta if isinstance(hasta, date) else None)
            filtros = _filtrosTexto(modo, estado, origen, condicion)
        return report.measurementFile(formato, f"mis-mediciones-{now:%Y%m%d-%H%M}", rows, now,
                                      alcance=_alcanceTexto(alcance, len(rows)), periodo=periodo, filtros=filtros)
