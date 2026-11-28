# MatrixExport - Exportación de la matriz de referencia en Excel y PDF, con la identidad visual de GlucoLume.
#
# El CSV de la matriz lo arma el servicio de matrices (sin cambios). Este módulo solo presenta los datos ya preparados:
#   · Excel: hoja «Resumen» (banner completo, datos de la matriz e indicadores) y hoja «Matriz» (una fila por regla, con tipos
#     nativos, encabezado rojo, paneles congelados, filtros e impresión A4 horizontal con el encabezado repetido).
#   · PDF: A4 horizontal. La primera hoja lleva el banner completo centrado; las siguientes, un encabezado compacto. Tarjetas de
#     resumen, datos de la matriz y reglas en una tabla con grupos de columnas. El texto sigue siendo seleccionable.
# Un límite que no existe se muestra como «Sin límite»; una glucosa o un dato ausente nunca se muestra como cero.

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.worksheet.properties import PageSetupProperties
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.services import brandAssets as brand
from app.services.csvExport import csvDate

SIN_LIMITE = "Sin límite"
_EXTENSIONES = {"xlsx": ".xlsx", "pdf": ".pdf"}
_ROJO_HEX = brand.ROJO.lstrip("#")
_ZEBRA_HEX = "FBF4F5"
_LINEA_HEX = brand.GRIS_LINEA.lstrip("#")

# Banner: ocupa una fracción del ancho útil, centrado, con su proporción original. Las filas/alto que ocupa quedan reservados.
_FRACCION_BANNER = 0.6
_ALTO_FILA_EXCEL = 15  # pt: alto de fila estándar (20 px a 96 dpi)

_ANCHOS_RESUMEN = (2, 30, 80, 2)  # columnas de la hoja Resumen (caracteres de Excel)
_ANCHOS_MATRIZ = (34, 12, 24, 12, 13, 13, 34, 44, 13, 14, 12, 12, 20, 16, 16, 16, 16)  # una por columna de MATRIX_EXPORT_COLUMNS
_FORMATO_FECHA = "dd/mm/yyyy"
_FORMATO_GLUCOSA = "0.00"
_FORMATO_NUMERO = "0"

_MARGEN = 14 * mm
_MARGEN_INFERIOR = _MARGEN + 22  # deja lugar al pie institucional
_PAGINA = landscape(A4)
_ANCHO_UTIL = _PAGINA[0] - 2 * _MARGEN
_ALTO_CABECERA_SIGUIENTE = 26  # pt: encabezado compacto de las páginas siguientes (sin banner)
_ANCHOS_REGLAS = (84, 84, 66, 66, 118, 86, 86, 86, 86)  # se escalan al ancho útil
_ANCHOS_TARJETAS = (118, 118, 128, 180)  # la última tarjeta ocupa lo que sobra
_ESPACIO_TARJETAS = 8
_ANCHOS_DATOS = (110, 290, 110, 252)
_SLOGAN_PIE = f"GlucoLume · {brand.SLOGAN}"
_TEXTO_SIN_ESPACIOS_LARGO = 20  # desde acá, un texto sin espacios (una URL) se corta dentro de la celda


@dataclass(frozen=True)
class MatrixHeader:
    """Datos de la matriz ya en texto legible (estado y origen traducidos)."""
    nombre: str
    version: str
    origen: str
    estado: str
    vigenciaDesde: date | None
    vigenciaHasta: date | None
    referenciaBase: str
    urlReferencia: str


@dataclass(frozen=True)
class MatrixRuleRow:
    """Una regla. Los números quedan tipados (None = no hay límite o no hay dato)."""
    codigo: str
    sexo: str
    edadDesde: int | None
    edadHasta: int | None
    condicion: str
    minutosMin: int | None
    minutosMax: int | None
    glucosaMin: Decimal | None
    glucosaMax: Decimal | None


def matrixFile(formato: str, nombreBase: str, titulo: str, columns: tuple[str, ...], header: MatrixHeader,
               rules: list[MatrixRuleRow], generado: datetime) -> tuple[bytes, str]:
    """(contenido, nombre del archivo) de la matriz en Excel o PDF. El CSV no pasa por acá."""
    if formato == "xlsx":
        content = _xlsx(titulo, columns, header, rules, generado)
    elif formato == "pdf":
        content = _pdf(titulo, header, rules, generado)
    else:
        raise ValueError(f"Formato de exportación desconocido: {formato}")
    return content, nombreBase + _EXTENSIONES[formato]


def _condiciones(rules: list[MatrixRuleRow]) -> str:
    return " · ".join(dict.fromkeys(rule.condicion for rule in rules)) or "Sin reglas"


def _fecha(value: date | None) -> str:
    return SIN_LIMITE if value is None else value.strftime("%d/%m/%Y")


def _limite(value: int | None) -> str:
    return SIN_LIMITE if value is None else str(value)


def _glucosa(value: Decimal | None) -> str:
    return SIN_LIMITE if value is None else f"{value:.2f}".replace(".", ",")


def _subtitulo(header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> str:
    return f"Generado el {csvDate(generado)} · {len(rules)} registros · Versión {header.version} · Estado: {header.estado}"


# --- Excel ------------------------------------------------------------------------------------------------------------

_FILL_ENCABEZADO = PatternFill("solid", fgColor=_ROJO_HEX)
_FILL_ZEBRA = PatternFill("solid", fgColor=_ZEBRA_HEX)
_BORDE_FINO = Border(bottom=Side(style="thin", color=_LINEA_HEX))


def _textoExcel(cell, value: str) -> None:
    """Texto que nunca se interpreta como fórmula (un valor que empieza con = queda como texto)."""
    cell.value = value
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        cell.data_type = "s"


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


def _banner(hoja, anchos: tuple[float, ...], fila: int) -> int:
    """Banner completo centrado en el ancho de la hoja, con su proporción. Devuelve la primera fila libre debajo de él."""
    banner = brand.existing(brand.BANNER_PATH)
    if not banner:
        return fila
    total = sum(_anchoPx(ancho) for ancho in anchos)
    anchoPx = round(total * _FRACCION_BANNER)
    altoPx = round(anchoPx / brand.proporcion(banner))
    filas = math.ceil(altoPx / (_ALTO_FILA_EXCEL * 96 / 72))
    for reservada in range(fila, fila + filas):
        hoja.row_dimensions[reservada].height = _ALTO_FILA_EXCEL
    imagen = ExcelImage(str(banner))
    imagen.width, imagen.height = anchoPx, altoPx
    columna, desplazamiento = _columnaEnPx((total - anchoPx) // 2, anchos)
    imagen.anchor = OneCellAnchor(
        _from=AnchorMarker(col=columna, colOff=pixels_to_EMU(desplazamiento), row=fila - 1, rowOff=0),
        ext=XDRPositiveSize2D(pixels_to_EMU(anchoPx), pixels_to_EMU(altoPx)),
    )
    hoja.add_image(imagen)
    fila += filas
    hoja.row_dimensions[fila].height = 8
    for letra in "BC":
        hoja[f"{letra}{fila}"].border = Border(bottom=Side(style="medium", color=_ROJO_HEX))
    return fila + 2


def _xlsx(titulo: str, columns: tuple[str, ...], header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> bytes:
    book = Workbook()
    book.properties.creator = "GlucoLume"
    book.properties.title = titulo
    resumen = book.active
    resumen.title = "Resumen"
    resumen.sheet_properties.tabColor = _ROJO_HEX
    resumen.sheet_view.showGridLines = False
    _hojaResumen(resumen, titulo, header, rules, generado)
    hoja = book.create_sheet("Matriz")
    hoja.sheet_properties.tabColor = _ROJO_HEX
    _hojaMatriz(hoja, columns, header, rules)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _hojaResumen(hoja, titulo: str, header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> None:
    for letra, ancho in zip("ABCD", _ANCHOS_RESUMEN):
        hoja.column_dimensions[letra].width = ancho
    fila = _banner(hoja, _ANCHOS_RESUMEN, 2)
    _textoExcel(hoja[f"B{fila}"], titulo)
    hoja[f"B{fila}"].font = Font(bold=True, size=14, color="1F1F23")
    fila += 1
    _textoExcel(hoja[f"B{fila}"], _subtitulo(header, rules, generado))
    hoja[f"B{fila}"].font = Font(size=9, color="6B6B70")
    fila += 2
    datos = [
        ("Origen / alcance", header.origen), ("Versión", header.version), ("Estado", header.estado),
        ("Vigencia desde", _fecha(header.vigenciaDesde)), ("Vigencia hasta", _fecha(header.vigenciaHasta)),
        ("Referencia base", header.referenciaBase), ("URL de referencia", header.urlReferencia or "Sin URL"),
    ]
    for etiqueta, valor in datos:
        _textoExcel(hoja[f"B{fila}"], etiqueta)
        hoja[f"B{fila}"].font = Font(bold=True, color="4A4A4F")
        _textoExcel(hoja[f"C{fila}"], valor)
        hoja[f"C{fila}"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        fila += 1
    fila += 1
    _textoExcel(hoja[f"B{fila}"], "Indicadores")
    hoja[f"B{fila}"].font = Font(bold=True, size=12, color=_ROJO_HEX)
    fila += 1
    for col, texto in (("B", "Indicador"), ("C", "Valor")):
        _textoExcel(hoja[f"{col}{fila}"], texto)
        hoja[f"{col}{fila}"].font = Font(bold=True, color="FFFFFF")
        hoja[f"{col}{fila}"].fill = _FILL_ENCABEZADO
    indicadores = [("Registros exportados", len(rules)), ("Condiciones de comida contempladas", _condiciones(rules))]
    for etiqueta, valor in indicadores:
        fila += 1
        _textoExcel(hoja[f"B{fila}"], etiqueta)
        _textoExcel(hoja[f"C{fila}"], valor)
        hoja[f"C{fila}"].alignment = Alignment(horizontal="left", wrap_text=True)
        hoja[f"B{fila}"].border = _BORDE_FINO
        hoja[f"C{fila}"].border = _BORDE_FINO
    hoja.print_area = f"A1:D{fila + 1}"
    hoja.print_options.horizontalCentered = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.oddFooter.left.text = _SLOGAN_PIE
    hoja.oddFooter.left.size = 8
    hoja.oddFooter.right.text = "Página &P de &N"
    hoja.oddFooter.right.size = 8


def _valorFecha(value: date | None) -> tuple:
    return (value, _FORMATO_FECHA) if value is not None else (SIN_LIMITE, None)


def _valorLimite(value: int | None) -> tuple:
    return (value, _FORMATO_NUMERO) if value is not None else (SIN_LIMITE, None)


def _valorGlucosa(value: Decimal | None) -> tuple:
    return (float(value), _FORMATO_GLUCOSA) if value is not None else (SIN_LIMITE, None)


def _filasMatriz(header: MatrixHeader, rules: list[MatrixRuleRow]) -> list[list[tuple]]:
    """Cada fila: (valor, formato numérico). Los datos de la matriz se repiten en cada regla para poder filtrar."""
    comun = [
        (header.nombre, None), (header.version, None), (header.origen, None), (header.estado, None),
        _valorFecha(header.vigenciaDesde), _valorFecha(header.vigenciaHasta),
        (header.referenciaBase, None), (header.urlReferencia, None),
    ]
    if not rules:
        return [comun + [(None, None)] * 9]
    return [comun + [
        (rule.codigo, None), (rule.sexo, None), _valorLimite(rule.edadDesde), _valorLimite(rule.edadHasta),
        (rule.condicion, None), _valorLimite(rule.minutosMin), _valorLimite(rule.minutosMax),
        _valorGlucosa(rule.glucosaMin), _valorGlucosa(rule.glucosaMax),
    ] for rule in rules]


def _hojaMatriz(hoja, columns: tuple[str, ...], header: MatrixHeader, rules: list[MatrixRuleRow]) -> None:
    for indice, (titulo, ancho) in enumerate(zip(columns, _ANCHOS_MATRIZ), start=1):
        letra = get_column_letter(indice)
        hoja.column_dimensions[letra].width = ancho
        celda = hoja[f"{letra}1"]
        _textoExcel(celda, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = _FILL_ENCABEZADO
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hoja.row_dimensions[1].height = 34
    filas = _filasMatriz(header, rules)
    for numero, valores in enumerate(filas, start=2):
        for indice, (valor, formato) in enumerate(valores, start=1):
            celda = hoja.cell(row=numero, column=indice)
            if valor is None:
                continue
            if isinstance(valor, str):
                _textoExcel(celda, valor)
            else:
                celda.value = valor
            if formato:
                celda.number_format = formato
            esNumero = not isinstance(valor, str)
            celda.alignment = Alignment(horizontal="center" if esNumero else "left", vertical="top", wrap_text=True)
            celda.border = _BORDE_FINO
            if numero % 2 == 1:
                celda.fill = _FILL_ZEBRA
    ultima = get_column_letter(len(columns))
    hoja.freeze_panes = "B2"  # encabezado y nombre de la matriz quedan visibles al desplazarse
    hoja.auto_filter.ref = f"A1:{ultima}{len(filas) + 1}"
    hoja.print_title_rows = "1:1"  # el encabezado se repite en cada hoja impresa
    hoja.print_options.horizontalCentered = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.oddFooter.left.text = _SLOGAN_PIE
    hoja.oddFooter.left.size = 8
    hoja.oddFooter.right.text = "Página &P de &N"
    hoja.oddFooter.right.size = 8


# --- PDF --------------------------------------------------------------------------------------------------------------


def _estilos():
    base = getSampleStyleSheet()["Normal"]
    oscuro = colors.HexColor("#1F1F23")
    gris = colors.HexColor(brand.GRIS_TEXTO)
    rojo = colors.HexColor(brand.ROJO)
    return {
        "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=oscuro,
                                 spaceAfter=2),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontName="Helvetica", fontSize=8.5, leading=11,
                                    textColor=colors.HexColor("#6B6B70")),
        "seccion": ParagraphStyle("seccion", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=rojo,
                                  spaceBefore=6, spaceAfter=4),
        "etiqueta": ParagraphStyle("etiqueta", parent=base, fontName="Helvetica", fontSize=7.4, leading=9,
                                   textColor=colors.HexColor("#6B6B70")),
        "tarjetaNumero": ParagraphStyle("tarjetaNumero", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=21,
                                        textColor=rojo),
        "tarjetaTexto": ParagraphStyle("tarjetaTexto", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                                       textColor=oscuro),
        "celda": ParagraphStyle("celda", parent=base, fontName="Helvetica", fontSize=8, leading=10, textColor=oscuro),
        "celdaCentrada": ParagraphStyle("celdaCentrada", parent=base, fontName="Helvetica", fontSize=8, leading=10,
                                        textColor=oscuro, alignment=TA_CENTER),
        "encabezado": ParagraphStyle("encabezado", parent=base, fontName="Helvetica-Bold", fontSize=7.8, leading=9.4,
                                     textColor=colors.white, alignment=TA_CENTER),
        "aviso": ParagraphStyle("aviso", parent=base, fontName="Helvetica", fontSize=8.5, leading=11, textColor=gris),
    }


def _texto(value: str, style: ParagraphStyle) -> Paragraph:
    """Párrafo seguro: el texto se escapa y un enlace largo sin espacios se corta dentro de la celda."""
    if " " not in value and len(value) > _TEXTO_SIN_ESPACIOS_LARGO:
        style = ParagraphStyle(style.name + "Cortado", parent=style, wordWrap="CJK")
    return Paragraph(escape(value), style)


def _escala(anchos, total: float) -> list[float]:
    factor = total / sum(anchos)
    return [ancho * factor for ancho in anchos]


def _tarjetas(items: list[tuple[str, str, bool]], estilos) -> Table:
    """Fila de tarjetas compactas: etiqueta y valor. Las de texto usan una letra menor que las cifras."""
    anchos = list(_ANCHOS_TARJETAS)
    anchos.append(_ANCHO_UTIL - sum(anchos) - _ESPACIO_TARJETAS * len(anchos))
    celdas, columnas, tarjetas = [], [], []
    for indice, (etiqueta, valor, esCifra) in enumerate(items):
        celdas.append([Paragraph(escape(etiqueta), estilos["etiqueta"]),
                       Paragraph(escape(valor), estilos["tarjetaNumero" if esCifra else "tarjetaTexto"])])
        columnas.append(anchos[indice])
        tarjetas.append(len(celdas) - 1)
        if indice < len(items) - 1:
            celdas.append("")
            columnas.append(_ESPACIO_TARJETAS)
    tabla = Table([celdas], colWidths=columnas)
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for columna in tarjetas:
        estilo += [("BACKGROUND", (columna, 0), (columna, 0), colors.HexColor(brand.ROJO_SUAVE)),
                   ("LINEBEFORE", (columna, 0), (columna, 0), 2.5, colors.HexColor(brand.ROJO))]
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _datos(header: MatrixHeader, estilos) -> Table:
    """Datos de la matriz que no son tarjetas: referencia, versión, vigencia y URL de la fuente."""
    etiqueta = lambda texto: Paragraph(escape(texto), estilos["etiqueta"])  # noqa: E731
    filas = [
        [etiqueta("Referencia base"), _texto(header.referenciaBase, estilos["celda"]), etiqueta("Versión"),
         _texto(header.version, estilos["celda"])],
        [etiqueta("Vigencia desde"), _texto(_fecha(header.vigenciaDesde), estilos["celda"]), etiqueta("Vigencia hasta"),
         _texto(_fecha(header.vigenciaHasta), estilos["celda"])],
        [etiqueta("URL de referencia"), _texto(header.urlReferencia or "Sin URL", estilos["celda"]), "", ""],
    ]
    tabla = Table(filas, colWidths=_escala(_ANCHOS_DATOS, _ANCHO_UTIL))
    tabla.setStyle(TableStyle([
        ("SPAN", (1, 2), (3, 2)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(brand.GRIS_LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def _tablaReglas(rules: list[MatrixRuleRow], estilos) -> Table:
    """Reglas en dos niveles de encabezado: grupos (rango etario, ventana temporal, glucosa) y columnas dentro de cada grupo."""
    enc = lambda texto: Paragraph(escape(texto), estilos["encabezado"])  # noqa: E731
    cabecera = [
        [enc("Código de regla"), enc("Sexo"), enc("Rango etario"), "", enc("Condición de comida"),
         enc("Ventana desde la comida (min.)"), "", enc("Glucosa de referencia (mg/dL)"), ""],
        ["", "", enc("Desde"), enc("Hasta"), "", enc("Mínimo"), enc("Máximo"), enc("Mínima"), enc("Máxima")],
    ]
    cuerpo = []
    for rule in rules:
        valores = [rule.codigo, rule.sexo, _limite(rule.edadDesde), _limite(rule.edadHasta), rule.condicion,
                   _limite(rule.minutosMin), _limite(rule.minutosMax), _glucosa(rule.glucosaMin), _glucosa(rule.glucosaMax)]
        cuerpo.append([Paragraph(escape(valor), estilos["celdaCentrada"]) for valor in valores])
    tabla = Table(cabecera + cuerpo, colWidths=_escala(_ANCHOS_REGLAS, _ANCHO_UTIL), repeatRows=2)
    tabla.setStyle(TableStyle([
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (3, 0)), ("SPAN", (4, 0), (4, 1)),
        ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor(brand.ROJO)),
        ("LINEBELOW", (2, 0), (3, 0), 0.5, colors.white), ("LINEBELOW", (5, 0), (6, 0), 0.5, colors.white),
        ("LINEBELOW", (7, 0), (8, 0), 0.5, colors.white),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#" + _ZEBRA_HEX)]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(brand.GRIS_LINEA)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla



def _cabeceraCompacta(canvas) -> None:
    """Encabezado de las páginas siguientes: nombre de la marca en texto, título y una línea roja. Sin banner."""
    arriba = _PAGINA[1] - _MARGEN
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor("#1F1F23"))
    canvas.drawString(_MARGEN, arriba - 11, "Gluco")
    ancho = canvas.stringWidth("Gluco", "Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(_MARGEN + ancho, arriba - 11, "Lume")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawRightString(_PAGINA[0] - _MARGEN, arriba - 11, "Matriz de referencia de glucosa")
    canvas.setStrokeColor(colors.HexColor(brand.ROJO))
    canvas.setLineWidth(1.2)
    canvas.line(_MARGEN, arriba - _ALTO_CABECERA_SIGUIENTE, _PAGINA[0] - _MARGEN, arriba - _ALTO_CABECERA_SIGUIENTE)


def _pie(canvas, generado: datetime) -> None:
    """Pie discreto: marca y eslogan a la izquierda, fecha de generación al centro (el número de página lo agrega el canvas)."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(brand.GRIS_LINEA))
    canvas.setLineWidth(0.5)
    canvas.line(_MARGEN, 34, _PAGINA[0] - _MARGEN, 34)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(_MARGEN, 22, _SLOGAN_PIE)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawCentredString(_PAGINA[0] / 2, 22, f"Generado el {csvDate(generado)}")
    canvas.restoreState()


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
            self.saveState()
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
            self.drawRightString(_PAGINA[0] - _MARGEN, 22, f"Página {self._pageNumber} de {total}")
            self.restoreState()
            super().showPage()
        super().save()


def _marco(id: str, sangria_superior: float) -> Frame:
    """Área útil de la hoja. `sangria_superior` reserva el alto del encabezado compacto (0 si lo ocupa el banner)."""
    return Frame(_MARGEN, _MARGEN_INFERIOR, _ANCHO_UTIL, _PAGINA[1] - _MARGEN_INFERIOR - _MARGEN - sangria_superior,
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=id)


def _pdf(titulo: str, header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> bytes:
    estilos = _estilos()
    banner = brand.existing(brand.BANNER_PATH)
    story = []
    if banner:
        # Banner completo, centrado y con su proporción original: ocupa su alto real y el contenido empieza debajo.
        ancho = _ANCHO_UTIL * _FRACCION_BANNER
        story += [
            Image(str(banner), width=ancho, height=ancho / brand.proporcion(banner), hAlign="CENTER"),
            HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(brand.ROJO), spaceBefore=8, spaceAfter=10),
        ]
    story += [
        NextPageTemplate("siguientes"),  # desde la segunda hoja, encabezado compacto en lugar del banner
        Paragraph(escape(titulo), estilos["titulo"]),
        Paragraph(escape(_subtitulo(header, rules, generado)), estilos["subtitulo"]),
        Spacer(1, 10),
        _tarjetas([
            ("Registros exportados", str(len(rules)), True),
            ("Reglas de la matriz", str(len(rules)), True),
            ("Vigencia desde", _fecha(header.vigenciaDesde), False),
            ("Origen / alcance", header.origen, False),
            ("Condiciones de comida contempladas", _condiciones(rules), False),
        ], estilos),
        Spacer(1, 10),
        _datos(header, estilos),
        Paragraph(f"Reglas ({len(rules)})", estilos["seccion"]),
    ]
    if rules:
        story.append(_tablaReglas(rules, estilos))
    else:
        story.append(Paragraph("La matriz no tiene reglas cargadas.", estilos["aviso"]))
    sangria = _ALTO_CABECERA_SIGUIENTE + 12
    sangria_primera = 0 if banner else sangria  # sin banner, la primera hoja también lleva el encabezado compacto

    def primera(canvas, doc):
        if not banner:
            _cabeceraCompacta(canvas)
        _pie(canvas, generado)

    def siguientes(canvas, doc):
        _cabeceraCompacta(canvas)
        _pie(canvas, generado)

    buffer = BytesIO()
    document = BaseDocTemplate(buffer, pagesize=_PAGINA, leftMargin=_MARGEN, rightMargin=_MARGEN, topMargin=_MARGEN,
                               bottomMargin=_MARGEN_INFERIOR, title=titulo, author="GlucoLume", subject="Matriz de referencia de glucosa")
    document.addPageTemplates([
        PageTemplate(id="primera", frames=[_marco("primera", sangria_primera)], onPage=primera),
        PageTemplate(id="siguientes", frames=[_marco("siguientes", sangria)], onPage=siguientes),
    ])
    document.build(story, canvasmaker=_NumeracionCanvas)
    return buffer.getvalue()
