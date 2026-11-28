# MeasurementReport - Exportación de mis mediciones en CSV, Excel y PDF (identidad de GlucoLume)
#
# Las filas llegan con sus valores TIPADOS (fechas, números, nulos). Cada formato los presenta a su manera:
#   · CSV: texto plano, UTF-8 con BOM, separador «;», encabezados descriptivos y escape de fórmulas. Sin imágenes ni decoración.
#   · Excel: hoja «Resumen» (marca e indicadores) y hoja «Mediciones» (tipos nativos, encabezado rojo, filtros, semáforo condicional).
#   · PDF: informe A4 horizontal con encabezado de marca, indicadores, registros en dos niveles y numeración de páginas.
# Un valor que no existe se muestra como «Sin dato» (o celda vacía); nunca como cero. Un semáforo sin clasificación no tiene color.

import math
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.properties import PageSetupProperties
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, HRFlowable, Image, LongTable, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.services import brandAssets as brand
from app.services.csvExport import csvBytes, csvDate, csvText
from app.utils.timeZone import withArgentinaZone

CSV_COLUMNS = (
    "Fecha y hora", "Modo", "Estado", "Condición de comida", "Última comida", "SpO2 (%)", "Frecuencia cardíaca (lpm)",
    "Glucosa del dispositivo (mg/dL)", "Origen de la glucosa", "Semáforo", "Origen de los datos",
    "Dispositivo", "Observación",
)
_EXTENSIONES = {"csv": ".csv", "xlsx": ".xlsx", "pdf": ".pdf"}
_SEMAFORO_TEXTO = {"ROJO": "Rojo", "AMARILLO": "Amarillo", "VERDE": "Verde"}
# Descripción de cada color con las etiquetas que la app ya usa (Semaforo.jsx): no se inventa un significado nuevo.
_SEMAFORO_DESCRIPCION = {"VERDE": "Está bien", "AMARILLO": "Revisar", "ROJO": "Muy alto"}
_SEMAFORO_COLOR = {"VERDE": "#2E7D4F", "AMARILLO": "#E0A100", "ROJO": "#C62828"}
_SIN_DATO = "Sin dato"
_SIN_INFORMAR = "Sin informar"
_MARGEN_PDF = 14 * mm
_MARGEN_INFERIOR_PDF = _MARGEN_PDF + 22  # deja lugar al pie institucional
# Banner centrado, completo y de tamaño equilibrado: no ocupa todo el ancho para no robar altura a la tabla.
_FRACCION_BANNER = 0.5
_ALTO_CABECERA_SIGUIENTE = 26  # pt: encabezado compacto de las páginas siguientes (sin banner)
_ALTO_FILA_EXCEL = 15  # pt: alto de fila estándar (20 px a 96 dpi)


@dataclass(frozen=True)
class ReportLine:
    """Una medición lista para exportar. `None` = el dato no existe (no es cero)."""
    fecha: datetime | None
    modo: str
    estado: str
    condicion: str
    ultimaComida: datetime | None
    spo2: float | None
    frecuenciaCardiaca: int | None
    glucosa: float | None
    origenGlucosa: str | None
    semaforo: str | None  # ROJO, AMARILLO, VERDE o None (sin clasificación)
    esDemo: bool
    dispositivo: str
    observacion: str


def _numero(value: float | None, decimales: int) -> str:
    """Número con coma decimal (como en pantalla). Vacío si no hay dato."""
    return "" if value is None else f"{float(value):.{decimales}f}".replace(".", ",")


def _csvFila(line: ReportLine) -> list[str]:
    return [
        csvDate(line.fecha),
        csvText(line.modo),
        csvText(line.estado),
        csvText(line.condicion),
        _SIN_INFORMAR if line.ultimaComida is None else csvDate(line.ultimaComida),
        _numero(line.spo2, 2),
        "" if line.frecuenciaCardiaca is None else str(line.frecuenciaCardiaca),
        _numero(line.glucosa, 1),
        csvText(line.origenGlucosa or ""),
        _SEMAFORO_TEXTO.get(line.semaforo or "", ""),
        "Prueba (DEMO)" if line.esDemo else "Real",
        csvText(line.dispositivo),
        csvText(line.observacion),
    ]


def _naive(value: datetime) -> datetime:
    """Hora de Argentina sin zona: lo que Excel guarda como fecha nativa."""
    return withArgentinaZone(value).replace(tzinfo=None)


def _indicadores(lines: list[ReportLine]) -> dict[str, int]:
    return {
        "total": len(lines),
        "completadas": sum(line.estado == "Completada" for line in lines),
        "conGlucosa": sum(line.glucosa is not None for line in lines),
        "demo": sum(line.esDemo for line in lines),
        "verde": sum(line.semaforo == "VERDE" for line in lines),
        "amarillo": sum(line.semaforo == "AMARILLO" for line in lines),
        "rojo": sum(line.semaforo == "ROJO" for line in lines),
        "sinClasificacion": sum(line.semaforo is None for line in lines),
    }


def _fecha(value: date | None) -> str:
    return "" if value is None else value.strftime("%d/%m/%Y")


# --- CSV --------------------------------------------------------------------------------------------------------------


def _csv(lines: list[ReportLine]) -> bytes:
    return csvBytes(CSV_COLUMNS, [_csvFila(line) for line in lines])


# --- Excel ------------------------------------------------------------------------------------------------------------

_ROJO_HEX = brand.ROJO.lstrip("#")
_FILL_ENCABEZADO = PatternFill("solid", fgColor=_ROJO_HEX)
_FILL_ALTERNO = PatternFill("solid", fgColor="FBF4F5")
_FORMATO_FECHA = "dd/mm/yyyy hh:mm"
_ANCHOS_EXCEL = (18, 20, 14, 20, 18, 11, 14, 16, 16, 14, 16, 16, 60)


def _textoExcel(cell, value: str) -> None:
    """Texto que nunca se interpreta como fórmula (un valor que empieza con = queda como texto)."""
    cell.value = value
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        cell.data_type = "s"


def _xlsx(lines: list[ReportLine], generado: datetime, alcance: str, periodo: str, filtros: str) -> bytes:
    book = Workbook()
    book.properties.creator = "GlucoLume"
    book.properties.title = "Informe de mediciones"
    resumen = book.active
    resumen.title = "Resumen"
    resumen.sheet_properties.tabColor = _ROJO_HEX
    resumen.sheet_view.showGridLines = False
    _hojaResumen(resumen, lines, generado, alcance, periodo, filtros)
    hoja = book.create_sheet("Mediciones")
    hoja.sheet_properties.tabColor = _ROJO_HEX
    _hojaMediciones(hoja, lines)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _anchoPx(ancho: float) -> int:
    """Ancho de columna de Excel en píxeles (aproximación con la fuente predeterminada)."""
    return int(ancho * 7 + 5)


def _columnaEnPx(px: int, anchos: tuple[float, ...]) -> tuple[int, int]:
    """Columna (desde 0) y desplazamiento dentro de ella para una posición horizontal, en píxeles."""
    acumulado = 0
    for indice, ancho in enumerate(anchos):
        if px < acumulado + _anchoPx(ancho):
            return indice, px - acumulado
        acumulado += _anchoPx(ancho)
    return len(anchos) - 1, 0


def _hojaResumen(hoja, lines, generado, alcance, periodo, filtros) -> None:
    anchos = (2, 34, 34, 3, 16, 16)
    for letter, width in zip("ABCDEF", anchos):
        hoja.column_dimensions[letter].width = width
    fila = 2
    banner = brand.existing(brand.BANNER_PATH)
    if banner:
        # Banner completo, centrado en el ancho de la hoja y con su proporción original. Las filas que ocupa quedan reservadas.
        total = sum(_anchoPx(ancho) for ancho in anchos)
        ancho_px = round(total * _FRACCION_BANNER)
        alto_px = round(ancho_px / brand.proporcion(banner))
        filas = math.ceil(alto_px / (_ALTO_FILA_EXCEL * 96 / 72))
        for reservada in range(fila, fila + filas):
            hoja.row_dimensions[reservada].height = _ALTO_FILA_EXCEL
        imagen = ExcelImage(str(banner))
        imagen.width, imagen.height = ancho_px, alto_px
        columna, desplazamiento = _columnaEnPx((total - ancho_px) // 2, anchos)
        imagen.anchor = OneCellAnchor(
            _from=AnchorMarker(col=columna, colOff=pixels_to_EMU(desplazamiento), row=fila - 1, rowOff=0),
            ext=XDRPositiveSize2D(pixels_to_EMU(ancho_px), pixels_to_EMU(alto_px)),
        )
        hoja.add_image(imagen)
        fila += filas
        # Regla roja bajo el banner, en una fila corta propia.
        hoja.row_dimensions[fila].height = 8
        for col in "BCDEF":
            hoja[f"{col}{fila}"].border = Border(bottom=Side(style="medium", color=_ROJO_HEX))
        fila += 2
    _textoExcel(hoja[f"B{fila}"], "Informe de mediciones")
    hoja[f"B{fila}"].font = Font(bold=True, size=14, color="1F1F23")
    fila += 2
    datos = [
        ("Generado", None), ("Alcance", alcance), ("Período", periodo), ("Filtros", filtros),
    ]
    for etiqueta, valor in datos:
        _textoExcel(hoja[f"B{fila}"], etiqueta)
        hoja[f"B{fila}"].font = Font(bold=True, color="4A4A4F")
        if valor is None:
            hoja[f"C{fila}"].value = _naive(generado)
            hoja[f"C{fila}"].number_format = _FORMATO_FECHA
            hoja[f"C{fila}"].alignment = Alignment(horizontal="left")
        else:
            _textoExcel(hoja[f"C{fila}"], valor)
        fila += 1
    fila += 1
    cifras = _indicadores(lines)
    _textoExcel(hoja[f"B{fila}"], "Indicadores")
    hoja[f"B{fila}"].font = Font(bold=True, size=12, color=_ROJO_HEX)
    fila += 1
    for col, text in (("B", "Indicador"), ("C", "Cantidad")):
        _textoExcel(hoja[f"{col}{fila}"], text)
        hoja[f"{col}{fila}"].font = Font(bold=True, color="FFFFFF")
        hoja[f"{col}{fila}"].fill = _FILL_ENCABEZADO
    indicadores = [
        ("Registros exportados", cifras["total"]),
        ("Completadas", cifras["completadas"]),
        ("Con glucosa del dispositivo", cifras["conGlucosa"]),
        ("Pruebas DEMO (simuladas)", cifras["demo"]),
        (f"Semáforo verde ({_SEMAFORO_DESCRIPCION['VERDE']})", cifras["verde"]),
        (f"Semáforo amarillo ({_SEMAFORO_DESCRIPCION['AMARILLO']})", cifras["amarillo"]),
        (f"Semáforo rojo ({_SEMAFORO_DESCRIPCION['ROJO']})", cifras["rojo"]),
        ("Sin clasificación de semáforo", cifras["sinClasificacion"]),
    ]
    for etiqueta, cantidad in indicadores:
        fila += 1
        _textoExcel(hoja[f"B{fila}"], etiqueta)
        hoja[f"C{fila}"].value = cantidad  # número nativo
        hoja[f"C{fila}"].alignment = Alignment(horizontal="left")
        if fila % 2 == 0:
            for col in "BC":
                hoja[f"{col}{fila}"].fill = _FILL_ALTERNO
    fila += 2
    _textoExcel(hoja[f"B{fila}"], brand.AVISO_EXPERIMENTAL)
    hoja[f"B{fila}"].font = Font(bold=True, color=_ROJO_HEX)
    fila += 1
    _textoExcel(hoja[f"B{fila}"], "Las clasificaciones de semáforo comparan con el intervalo configurado; no son una clasificación clínica.")
    hoja[f"B{fila}"].font = Font(italic=True, size=9, color="6B6B70")
    hoja.print_area = f"A1:F{fila}"  # imprime el banner, los indicadores y el aviso; no las filas vacías de más
    hoja.print_options.horizontalCentered = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.oddFooter.left.text = brand.AVISO_EXPERIMENTAL
    hoja.oddFooter.left.size = 8
    hoja.oddFooter.right.text = "GlucoLume · Página &P de &N"
    hoja.oddFooter.right.size = 8


def _alturaFila(observacion: str, ancho: int) -> float:
    if not observacion:
        return 16
    lineas = max(1, math.ceil(len(observacion) / max(ancho * 1.15, 1)))
    return max(16, 13.5 * lineas + 3)


def _hojaMediciones(hoja, lines) -> None:
    for index, (titulo, ancho) in enumerate(zip(CSV_COLUMNS, _ANCHOS_EXCEL), start=1):
        letra = get_column_letter(index)
        hoja.column_dimensions[letra].width = ancho
        celda = hoja[f"{letra}1"]
        _textoExcel(celda, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = _FILL_ENCABEZADO
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hoja.row_dimensions[1].height = 34
    for fila, line in enumerate(lines, start=2):
        valores = [
            (_naive(line.fecha) if line.fecha else None, _FORMATO_FECHA),
            (line.modo, None),
            (line.estado, None),
            (line.condicion, None),
            ("Sin informar" if line.ultimaComida is None else _naive(line.ultimaComida), _FORMATO_FECHA),
            (line.spo2, "0.00"),
            (line.frecuenciaCardiaca, "0"),
            (line.glucosa, "0.0"),
            (line.origenGlucosa, None),
            (_SEMAFORO_TEXTO.get(line.semaforo or ""), None),
            ("Prueba (DEMO)" if line.esDemo else "Real", None),
            (line.dispositivo, None),
            (line.observacion, None),
        ]
        for index, (valor, formato) in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=index)
            if isinstance(valor, str):
                _textoExcel(celda, valor)
            else:
                celda.value = valor  # número, fecha o None (vacío: no es cero)
            if formato:
                celda.number_format = formato
            celda.alignment = Alignment(vertical="top", wrap_text=index == 13)
        hoja.row_dimensions[fila].height = _alturaFila(line.observacion, _ANCHOS_EXCEL[12])
        if fila % 2 == 1:
            for index in range(1, 14):
                hoja.cell(row=fila, column=index).fill = _FILL_ALTERNO
    ultima = max(len(lines) + 1, 1)
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:M{ultima}"
    rango = f"J2:J{ultima}"  # columna Semáforo
    hoja.conditional_formatting.add(rango, CellIsRule(operator="equal", formula=['"Verde"'],
                                                      fill=PatternFill("solid", bgColor="E3F2E8"), font=Font(color="1E6B3F", bold=True)))
    hoja.conditional_formatting.add(rango, CellIsRule(operator="equal", formula=['"Amarillo"'],
                                                      fill=PatternFill("solid", bgColor="FFF4CC"), font=Font(color="7A5600", bold=True)))
    hoja.conditional_formatting.add(rango, CellIsRule(operator="equal", formula=['"Rojo"'],
                                                      fill=PatternFill("solid", bgColor="FBE0E3"), font=Font(color="A4001A", bold=True)))
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.print_title_rows = "1:1"
    hoja.print_options.gridLines = False
    hoja.oddFooter.left.text = brand.AVISO_EXPERIMENTAL
    hoja.oddFooter.left.size = 8
    hoja.oddFooter.right.text = "GlucoLume · Página &P de &N"
    hoja.oddFooter.right.size = 8


# --- PDF --------------------------------------------------------------------------------------------------------------

_PAGINA = landscape(A4)
_ANCHO_UTIL = _PAGINA[0] - 2 * _MARGEN_PDF
_ANCHO_COLUMNAS_PRINCIPALES = (70, 90, 64, 60, 72, 52, 58, 116, 80, 100)  # suma = ancho útil del PDF (A4 horizontal, margen de 14 mm)
_ENCABEZADOS_PRINCIPALES = ("Fecha y hora", "Modo", "Estado", "Glucosa (mg/dL)", "Origen de la glucosa", "SpO2 (%)",
                            "Frecuencia cardíaca (lpm)", "Semáforo", "Origen de los datos", "Dispositivo")


def _estilos():
    base = getSampleStyleSheet()["Normal"]
    return {
        "celda": ParagraphStyle("celda", parent=base, fontName="Helvetica", fontSize=7.8, leading=9.6, textColor=colors.HexColor("#1F1F23")),
        "encabezado": ParagraphStyle("encabezado", parent=base, fontName="Helvetica-Bold", fontSize=7.6, leading=9.2,
                                     textColor=colors.white),
        "secundaria": ParagraphStyle("secundaria", parent=base, fontName="Helvetica", fontSize=7.4, leading=9.2,
                                     textColor=colors.HexColor(brand.GRIS_TEXTO)),
        "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22,
                                 textColor=colors.HexColor("#1F1F23"), spaceAfter=2),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontName="Helvetica", fontSize=8.5, leading=11,
                                    textColor=colors.HexColor("#6B6B70")),
        "seccion": ParagraphStyle("seccion", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15,
                                  textColor=colors.HexColor(brand.ROJO), spaceBefore=8, spaceAfter=4),
        "etiqueta": ParagraphStyle("etiqueta", parent=base, fontName="Helvetica", fontSize=7.4, leading=9,
                                   textColor=colors.HexColor("#6B6B70")),
        "numero": ParagraphStyle("numero", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=21,
                                 textColor=colors.HexColor(brand.ROJO)),
        "aviso": ParagraphStyle("aviso", parent=base, fontName="Helvetica", fontSize=8, leading=10.5,
                                textColor=colors.HexColor("#4A4A4F")),
    }


class _Punto(Flowable):
    """Círculo de color para el semáforo (dibujado, no depende de una fuente)."""

    def __init__(self, color: str, diametro: float = 6.5):
        super().__init__()
        self.color = color
        self.width = self.height = diametro

    def draw(self):
        self.canv.setFillColor(colors.HexColor(self.color))
        self.canv.circle(self.width / 2, self.width / 2, self.width / 2, stroke=0, fill=1)


def _semaforoFlowable(code: str | None, estilos):
    if code is None:
        return Paragraph("Sin clasificación", estilos["secundaria"])
    texto = f"<b>{_SEMAFORO_TEXTO[code]}</b>: {_SEMAFORO_DESCRIPCION[code]}"
    fila = Table([[_Punto(_SEMAFORO_COLOR[code]), Paragraph(texto, estilos["celda"])]], colWidths=[10, 106])
    fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                              ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return fila


def _valor(texto: str, estilos, vacio: bool = False):
    return Paragraph(escape(texto), estilos["secundaria"] if vacio else estilos["celda"])


def _registro(line: ReportLine, estilos):
    """Un registro en dos niveles: fila principal con los datos clave y una segunda fila con la condición, la última comida y la
    observación. Así ninguna columna queda angosta y cada registro ocupa un bloque que no se corta entre páginas."""
    glucosa = _SIN_DATO if line.glucosa is None else _numero(line.glucosa, 1)
    principal = [
        _valor(csvDate(line.fecha), estilos),
        _valor(line.modo, estilos),
        _valor(line.estado, estilos),
        _valor(glucosa, estilos, vacio=line.glucosa is None),
        _valor(line.origenGlucosa or _SIN_DATO, estilos, vacio=line.origenGlucosa is None),
        _valor(_SIN_DATO if line.spo2 is None else _numero(line.spo2, 2), estilos, vacio=line.spo2 is None),
        _valor(_SIN_DATO if line.frecuenciaCardiaca is None else str(line.frecuenciaCardiaca), estilos,
               vacio=line.frecuenciaCardiaca is None),
        _semaforoFlowable(line.semaforo, estilos),
        Paragraph("<b>Prueba (DEMO)</b>" if line.esDemo else "Real", estilos["celda"]),
        _valor(line.dispositivo or _SIN_DATO, estilos, vacio=not line.dispositivo),
    ]
    comida = _SIN_INFORMAR if line.ultimaComida is None else csvDate(line.ultimaComida)
    detalle = (f"<b>Condición de comida:</b> {escape(line.condicion)}  ·  <b>Última comida:</b> {escape(comida)}")
    observacion = escape(line.observacion) if line.observacion else "Sin observaciones"
    complementaria = [
        Paragraph(detalle, estilos["secundaria"]),
        Paragraph(f"<b>Observación:</b> {observacion}", estilos["secundaria"]),
    ]
    tabla = Table([principal, [complementaria] + [""] * 9], colWidths=_ANCHO_COLUMNAS_PRINCIPALES)
    tabla.setStyle(TableStyle([
        ("SPAN", (0, 1), (-1, 1)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
        ("LINEBELOW", (0, 1), (-1, 1), 0.25, colors.HexColor(brand.GRIS_LINEA)),
    ]))
    return tabla


def _encabezadoTabla(estilos):
    celdas = [Paragraph(escape(titulo), estilos["encabezado"]) for titulo in _ENCABEZADOS_PRINCIPALES]
    tabla = Table([celdas], colWidths=_ANCHO_COLUMNAS_PRINCIPALES)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(brand.ROJO)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tabla


def _tarjetas(items: list[tuple[str, str, str | None]], estilos) -> Table:
    """Fila de tarjetas compactas: etiqueta (con su punto de color si corresponde) y cifra grande."""
    celdas = []
    for index, (etiqueta, cifra, semaforo) in enumerate(items):
        if semaforo:
            fila = Table([[_Punto(_SEMAFORO_COLOR[semaforo], 6), Paragraph(escape(etiqueta), estilos["etiqueta"])]],
                         colWidths=[9, 150])
            fila.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            contenido = [fila, Paragraph(escape(cifra), estilos["numero"])]
        else:
            contenido = [Paragraph(escape(etiqueta), estilos["etiqueta"]), Paragraph(escape(cifra), estilos["numero"])]
        celdas.append(contenido)
        if index < len(items) - 1:
            celdas.append("")
    columnas = [(_ANCHO_UTIL - 8 * (len(items) - 1)) / len(items) if index % 2 == 0 else 8 for index in range(len(celdas))]
    tabla = Table([celdas], colWidths=columnas)
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for index in range(0, len(celdas), 2):
        estilo.append(("BACKGROUND", (index, 0), (index, 0), colors.HexColor(brand.ROJO_SUAVE)))
    for index in range(1, len(celdas), 2):
        estilo.append(("LEFTPADDING", (index, 0), (index, 0), 0))
    tabla.setStyle(TableStyle(estilo))
    return tabla


class _NumeracionCanvas(pdfcanvas.Canvas):
    """Canvas que espera el final para escribir «Página X de Y» en cada hoja."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for pagina in self._paginas:
            self.__dict__.update(pagina)
            self._dibujarNumero(total)
            super().showPage()
        super().save()

    def _dibujarNumero(self, total: int):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
        self.drawRightString(_PAGINA[0] - _MARGEN_PDF, 22, f"Página {self._pageNumber} de {total}")
        self.restoreState()


def _cabeceraCompacta(canvas) -> None:
    """Encabezado de las páginas siguientes: nombre de la marca en texto, título del informe y una línea roja. Sin banner."""
    arriba = _PAGINA[1] - _MARGEN_PDF
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor("#1F1F23"))
    canvas.drawString(_MARGEN_PDF, arriba - 11, "Gluco")
    ancho = canvas.stringWidth("Gluco", "Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(_MARGEN_PDF + ancho, arriba - 11, "Lume")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawRightString(_PAGINA[0] - _MARGEN_PDF, arriba - 11, "Informe de mediciones")
    canvas.setStrokeColor(colors.HexColor(brand.ROJO))
    canvas.setLineWidth(1.2)
    canvas.line(_MARGEN_PDF, arriba - _ALTO_CABECERA_SIGUIENTE, _PAGINA[0] - _MARGEN_PDF, arriba - _ALTO_CABECERA_SIGUIENTE)


def _pie(canvas, generado: datetime) -> None:
    """Pie institucional: aviso experimental (siempre visible) y fecha de generación."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(brand.GRIS_LINEA))
    canvas.setLineWidth(0.5)
    canvas.line(_MARGEN_PDF, 34, _PAGINA[0] - _MARGEN_PDF, 34)
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(_MARGEN_PDF, 22, brand.AVISO_EXPERIMENTAL + ".")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawCentredString(_PAGINA[0] / 2, 22, f"GlucoLume · {brand.SLOGAN} · Generado el {csvDate(generado)}")
    canvas.restoreState()


def _marco(id: str, sangria_superior: float) -> Frame:
    """Área útil de la hoja. `sangria_superior` reserva el alto del encabezado (0 si lo ocupa el banner en la primera página)."""
    return Frame(
        _MARGEN_PDF, _MARGEN_INFERIOR_PDF, _ANCHO_UTIL,
        _PAGINA[1] - _MARGEN_INFERIOR_PDF - _MARGEN_PDF - sangria_superior,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=id,
    )


def _pdf(lines: list[ReportLine], generado: datetime, alcance: str, periodo: str, filtros: str) -> bytes:
    estilos = _estilos()
    cifras = _indicadores(lines)
    banner = brand.existing(brand.BANNER_PATH)
    cabecera = []
    if banner:
        # El banner completo ocupa su alto real en el flujo: el contenido empieza debajo y nunca se superpone con él.
        ancho = _ANCHO_UTIL * _FRACCION_BANNER
        cabecera = [
            Image(str(banner), width=ancho, height=ancho / brand.proporcion(banner), hAlign="CENTER"),
            HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(brand.ROJO), spaceBefore=8, spaceAfter=10),
        ]
    story = cabecera + [
        NextPageTemplate("siguientes"),  # desde la segunda hoja, encabezado compacto en lugar del banner
        Paragraph("Informe de mediciones", estilos["titulo"]),
        Paragraph(escape(f"{alcance} · Período: {periodo}"), estilos["subtitulo"]),
        Spacer(1, 8),
        _tarjetas([
            ("Registros exportados", str(cifras["total"]), None),
            ("Completadas", str(cifras["completadas"]), None),
            ("Con glucosa del dispositivo", str(cifras["conGlucosa"]), None),
            ("Pruebas DEMO (simuladas)", str(cifras["demo"]), None),
        ], estilos),
        Spacer(1, 6),
        _tarjetas([
            (f"Verde: {_SEMAFORO_DESCRIPCION['VERDE']}", str(cifras["verde"]), "VERDE"),
            (f"Amarillo: {_SEMAFORO_DESCRIPCION['AMARILLO']}", str(cifras["amarillo"]), "AMARILLO"),
            (f"Rojo: {_SEMAFORO_DESCRIPCION['ROJO']}", str(cifras["rojo"]), "ROJO"),
            ("Sin clasificación", str(cifras["sinClasificacion"]), None),
        ], estilos),
        Spacer(1, 8),
        Table([[Paragraph(
            f"<b>{escape(brand.AVISO_EXPERIMENTAL)}.</b> Los valores DEMO son simulados para verificar la comunicación: no son "
            "glucemias reales. El semáforo compara con el intervalo configurado; no es una clasificación clínica. "
            f"Filtros aplicados: {escape(filtros)}.", estilos["aviso"])]],
            colWidths=[_ANCHO_UTIL], style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF6F7")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor(brand.ROJO)),
                ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])),
        Paragraph(f"Mediciones ({len(lines)})", estilos["seccion"]),
    ]
    registros = [[_encabezadoTabla(estilos)]] + [[_registro(line, estilos)] for line in lines]
    if lines:
        tabla = LongTable(registros, colWidths=[_ANCHO_UTIL], repeatRows=1, splitByRow=1)
        tabla.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF4F5")]),
        ]))
        story.append(tabla)
    else:
        story.append(Paragraph("No hay mediciones que coincidan con los filtros elegidos.", estilos["aviso"]))
    buffer = BytesIO()
    document = BaseDocTemplate(buffer, pagesize=_PAGINA, leftMargin=_MARGEN_PDF, rightMargin=_MARGEN_PDF,
                               topMargin=_MARGEN_PDF, bottomMargin=_MARGEN_INFERIOR_PDF,
                               title="Informe de mediciones", author="GlucoLume", subject="Mis mediciones")
    sangria_siguientes = _ALTO_CABECERA_SIGUIENTE + 12
    # Sin banner (archivo ausente), la primera hoja también lleva el encabezado compacto, y el contenido empieza debajo.
    sangria_primera = 0 if banner else sangria_siguientes

    def primera(canvas, doc):
        if not banner:
            _cabeceraCompacta(canvas)
        _pie(canvas, generado)

    def siguientes(canvas, doc):
        _cabeceraCompacta(canvas)
        _pie(canvas, generado)

    document.addPageTemplates([
        PageTemplate(id="primera", frames=[_marco("primera", sangria_primera)], onPage=primera),
        PageTemplate(id="siguientes", frames=[_marco("siguientes", sangria_siguientes)], onPage=siguientes),
    ])
    document.build(story, canvasmaker=_NumeracionCanvas)
    return buffer.getvalue()


# --- Punto de entrada -------------------------------------------------------------------------------------------------


def measurementFile(formato: str, nombreBase: str, lines: list[ReportLine], generado: datetime, *, alcance: str, periodo: str,
                    filtros: str) -> tuple[bytes, str]:
    """(contenido, nombre del archivo) de mis mediciones en el formato pedido."""
    if formato == "csv":
        content = _csv(lines)
    elif formato == "xlsx":
        content = _xlsx(lines, generado, alcance, periodo, filtros)
    elif formato == "pdf":
        content = _pdf(lines, generado, alcance, periodo, filtros)
    else:
        raise ValueError(f"Formato de exportación desconocido: {formato}")
    return content, nombreBase + _EXTENSIONES[formato]


def periodoTexto(desde: date | None, hasta: date | None) -> str:
    if desde and hasta:
        return f"del {_fecha(desde)} al {_fecha(hasta)}"
    if desde:
        return f"desde el {_fecha(desde)}"
    if hasta:
        return f"hasta el {_fecha(hasta)}"
    return "todas las fechas"
