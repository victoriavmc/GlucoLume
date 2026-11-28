# DeviceReport - Inventario de dispositivos en Excel y PDF, con la identidad visual de GlucoLume (exportTemplate).
#
# Este módulo solo presenta los registros ya preparados por deviceExport (el alcance, los filtros y los permisos se resuelven allá).
# Regla de uso: un dispositivo es «institucional» si está asignado a una institución; el resto es «individual» (incluye los que
# todavía no tienen institución). Las columnas institucionales aparecen solo en su sección o su hoja, y no se generan secciones
# ni hojas vacías. Los datos de vinculación incompletos se muestran como «No registrado», sin inventar información.
# Los indicadores se calculan sobre los registros efectivamente exportados.

from dataclasses import dataclass
from datetime import date, datetime
from xml.sax.saxutils import escape

from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer

from app.services import exportTemplate as tpl
from app.services.csvExport import csvDate
from app.utils.timeZone import withArgentinaZone

_EXTENSIONES = {"xlsx": ".xlsx", "pdf": ".pdf"}
SIN_DATO = "No registrado"
_DOCUMENTO = "Inventario de dispositivos"
HOJA_INDIVIDUAL = "Dispositivos individuales"
HOJA_INSTITUCIONAL = "Dispositivos institucionales"
ENCABEZADOS_INDIVIDUAL = ("Código", "Nombre", "Modelo", "Estado", "Tipo de uso", "Responsable", "Sensor", "Firmware", "Fecha de registro")
ENCABEZADOS_INSTITUCIONAL = ("Código", "Nombre", "Modelo", "Estado", "Institución", "Responsable", "Sensor", "Firmware",
                             "Fecha de registro", "Fecha de incorporación a la institución")
_COLUMNA_ESTADO = 3
# Estado → (fondo suave, color del texto). Mismos tonos en el PDF y en el Excel.
_ESTADO_COLORES = {
    "Operativo": ("E3F4E6", "1E6B34"),
    "En mantenimiento": ("FFF1D6", "8A5300"),
    "Fuera de servicio": ("FBEAEC", "A3111F"),
    "Descomisionado": ("ECECEE", "4A4A4F"),
}
_ANCHOS_RESUMEN = (2, 34, 64, 2)


@dataclass(frozen=True)
class DeviceRecord:
    """Un dispositivo exportado, ya con los datos legibles. Las fechas quedan con hora: cada formato decide cómo mostrarlas."""
    codigo: str
    nombre: str | None
    modelo: str | None
    estado: str
    operativo: bool
    uso: str  # «Individual», «Sin asignar» o el nombre de la institución (como en el CSV)
    responsable: str
    sensor: str
    firmware: str | None
    registrado: datetime | None
    institucional: bool
    institucion: str | None
    incorporado: datetime | None


def inventoryFile(formato: str, nombreBase: str, titulo: str, filtros: list[tuple[str, str]], records: list[DeviceRecord],
                  generado: datetime) -> tuple[bytes, str]:
    """(contenido, nombre del archivo) del inventario en Excel o PDF. El CSV no pasa por acá."""
    if formato == "xlsx":
        content = _xlsx(titulo, filtros, records, generado)
    elif formato == "pdf":
        content = _pdf(titulo, filtros, records, generado)
    else:
        raise ValueError(f"Formato de exportación desconocido: {formato}")
    return content, nombreBase + _EXTENSIONES[formato]


# --- Datos compartidos ------------------------------------------------------------------------------------------------------

def _dia(value: datetime | None) -> date | None:
    """Día en la zona horaria de Argentina (la fecha de registro no se confunde con la de incorporación: cada una es su propio dato)."""
    return withArgentinaZone(value).date() if value is not None else None


def _texto(value: str | None) -> str:
    return value.strip() if value and value.strip() else SIN_DATO


def _individuales(records: list[DeviceRecord]) -> list[DeviceRecord]:
    return [record for record in records if not record.institucional]


def _institucionales(records: list[DeviceRecord]) -> list[DeviceRecord]:
    return [record for record in records if record.institucional]


def _indicadores(records: list[DeviceRecord]) -> list[tuple[str, int]]:
    """Calculados sobre los registros exportados (no sobre el inventario completo)."""
    return [
        ("Total de dispositivos", len(records)),
        ("Dispositivos operativos", sum(1 for record in records if record.operativo)),
        ("Dispositivos de uso individual", len(_individuales(records))),
        ("Dispositivos de uso institucional", len(_institucionales(records))),
    ]


def _subtitulo(records: list[DeviceRecord], generado: datetime) -> str:
    cantidad = len(records)
    etiqueta = "dispositivo exportado" if cantidad == 1 else "dispositivos exportados"
    return f"Generado el {csvDate(generado)} · {cantidad} {etiqueta}"


def _filas_individual(records: list[DeviceRecord]) -> list[list]:
    return [[r.codigo, _texto(r.nombre), _texto(r.modelo), r.estado, _texto(r.uso), _texto(r.responsable), _texto(r.sensor),
             _texto(r.firmware), _dia(r.registrado) or SIN_DATO] for r in records]


def _filas_institucional(records: list[DeviceRecord]) -> list[list]:
    return [[r.codigo, _texto(r.nombre), _texto(r.modelo), r.estado, _texto(r.institucion), _texto(r.responsable),
             _texto(r.sensor), _texto(r.firmware), _dia(r.registrado) or SIN_DATO, _dia(r.incorporado) or SIN_DATO]
            for r in records]


# --- PDF --------------------------------------------------------------------------------------------------------------------

def _textos(filas: list[list]) -> list[list[str]]:
    """Fechas en DD/MM/AAAA para el PDF (el Excel conserva fechas nativas)."""
    return [[csvDate(valor) if isinstance(valor, date) else str(valor) for valor in fila] for fila in filas]


def _colorearEstado(fila, indice, valor):
    """Fondo suave según el estado (la palabra del estado también va en la celda: nunca depende solo del color)."""
    if indice != _COLUMNA_ESTADO or valor not in _ESTADO_COLORES:
        return None
    return colors.HexColor("#" + _ESTADO_COLORES[valor][0])


def _pdf(titulo: str, filtros: list[tuple[str, str]], records: list[DeviceRecord], generado: datetime) -> bytes:
    estilos = tpl.estilos()
    contenido = [
        Paragraph(escape(titulo), estilos["titulo"]),
        Paragraph(escape(_subtitulo(records, generado)), estilos["subtitulo"]),
        Spacer(1, 8),
        tpl.datosClave(filtros, estilos),
        tpl.seccion("Resumen del inventario", estilos),
        tpl.tarjetas([(etiqueta, str(valor), True) for etiqueta, valor in _indicadores(records)], estilos),
    ]
    if not records:
        contenido.append(Paragraph("No hay dispositivos para exportar con los filtros aplicados.", estilos["aviso"]))
    individuales, institucionales = _individuales(records), _institucionales(records)
    if individuales:
        contenido += [
            tpl.seccion(f"Dispositivos de uso individual ({len(individuales)})", estilos),
            tpl.tablaInstitucional(ENCABEZADOS_INDIVIDUAL, _textos(_filas_individual(individuales)), estilos,
                                   colorear=_colorearEstado),
        ]
    if institucionales:
        contenido += [
            tpl.seccion(f"Dispositivos de uso institucional ({len(institucionales)})", estilos),
            tpl.tablaInstitucional(ENCABEZADOS_INSTITUCIONAL, _textos(_filas_institucional(institucionales)), estilos,
                                   colorear=_colorearEstado),
        ]
    return tpl.pdfDocument(titulo, "Inventario de dispositivos", _DOCUMENTO, generado, contenido)


# --- Excel ------------------------------------------------------------------------------------------------------------------

def _xlsx(titulo: str, filtros: list[tuple[str, str]], records: list[DeviceRecord], generado: datetime) -> bytes:
    book = tpl.libroExcel(titulo)
    resumen = book.active
    resumen.title = "Resumen"
    resumen.sheet_view.showGridLines = False
    _hojaResumen(resumen, titulo, filtros, records, generado)
    individuales, institucionales = _individuales(records), _institucionales(records)
    if individuales:
        _hojaDetalle(book.create_sheet(HOJA_INDIVIDUAL), ENCABEZADOS_INDIVIDUAL, _filas_individual(individuales))
    if institucionales:
        _hojaDetalle(book.create_sheet(HOJA_INSTITUCIONAL), ENCABEZADOS_INSTITUCIONAL, _filas_institucional(institucionales))
    return tpl.guardarExcel(book)


def _hojaResumen(hoja, titulo: str, filtros: list[tuple[str, str]], records: list[DeviceRecord], generado: datetime) -> None:
    for letra, ancho in zip("ABCD", _ANCHOS_RESUMEN):
        hoja.column_dimensions[letra].width = ancho
    fila = tpl.bannerResumenExcel(hoja, titulo, _subtitulo(records, generado), _ANCHOS_RESUMEN)
    tpl.textoExcel(hoja[f"B{fila}"], "Filtros aplicados")
    hoja[f"B{fila}"].font = Font(bold=True, size=12, color=tpl.ROJO_HEX)
    fila += 1
    for etiqueta, valor in filtros:
        fila = tpl.etiquetaValorExcel(hoja, fila, etiqueta, valor)
    fila += 1
    fila = tpl.encabezadoIndicadoresExcel(hoja, fila, ("Indicador", "Valor"))
    primera = fila
    for etiqueta, valor in _indicadores(records):
        fila = tpl.indicadorExcel(hoja, fila, etiqueta, valor)
    tpl.imprimirExcel(hoja, area=f"A1:D{max(fila, primera) + 1}")


def _hojaDetalle(hoja, encabezados: tuple[str, ...], filas: list[list]) -> None:
    tpl.anchoColumnasExcel(hoja, encabezados, filas)
    tpl.encabezadoExcel(hoja, encabezados)
    for numero, fila in enumerate(filas, start=2):
        for indice, valor in enumerate(fila, start=1):
            formato = tpl.FORMATO_FECHA if isinstance(valor, date) else None
            tpl.celdaExcel(hoja.cell(row=numero, column=indice), valor, formato, zebra=numero % 2 == 1)
    ultima = len(filas) + 1
    for estado, (fondo, letra) in _ESTADO_COLORES.items():
        hoja.conditional_formatting.add(
            f"D2:D{ultima}",
            CellIsRule(operator="equal", formula=[f'"{estado}"'],
                       fill=PatternFill(start_color=fondo, end_color=fondo, fill_type="solid"),
                       font=Font(bold=True, color=letra)),
        )
    tpl.titulosExcel(hoja, encabezados, filas)
    tpl.imprimirExcel(hoja)
