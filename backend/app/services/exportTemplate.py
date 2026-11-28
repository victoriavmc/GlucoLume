# ExportTemplate - Plantilla institucional de GlucoLume para las exportaciones PDF y Excel.
#
# Acá viven la identidad visual y la estructura común: banner completo, colores, encabezado compacto de las páginas siguientes,
# pie con fecha y «Página X de Y», tarjetas de resumen, tablas con encabezado rojo, anchos dinámicos y, en Excel, el banner, la
# impresión A4 y el pie. Cada módulo (inventario, matrices, mediciones) define solo su contenido: campos, secciones y hojas.
# No se agregan estilos propios en los módulos de exportación: si algo visual hace falta, se suma acá.

import math
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

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
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.services import brandAssets as brand
from app.services.csvExport import csvDate

# --- Página y colores -------------------------------------------------------------------------------------------------------

PAGINA = landscape(A4)
MARGEN = 14 * mm
MARGEN_INFERIOR = MARGEN + 22  # deja lugar al pie institucional
ANCHO_UTIL = PAGINA[0] - 2 * MARGEN
ALTO_CABECERA_SIGUIENTE = 26  # pt: encabezado compacto de las páginas siguientes (sin banner)
FRACCION_BANNER = 0.6  # el banner ocupa esta fracción del ancho útil, centrado y con su proporción original
SLOGAN_PIE = f"GlucoLume · {brand.SLOGAN}"
TEXTO_SIN_ESPACIOS_LARGO = 20  # desde acá, un texto sin espacios (un correo o un enlace) se corta dentro de la celda
ESPACIO_TARJETAS = 8

TINTA_HEX = "1F1F23"
SUAVE_HEX = "6B6B70"
ZEBRA_HEX = "FBF4F5"
ROJO_HEX = brand.ROJO.lstrip("#")
LINEA_HEX = brand.GRIS_LINEA.lstrip("#")

# --- Excel: constantes ------------------------------------------------------------------------------------------------------

ALTO_FILA_EXCEL = 15  # pt: alto de fila estándar (20 px a 96 dpi)
FORMATO_FECHA = "dd/mm/yyyy"
FILL_ENCABEZADO = PatternFill("solid", fgColor=ROJO_HEX)
FILL_ZEBRA = PatternFill("solid", fgColor=ZEBRA_HEX)
BORDE_FINO = Border(bottom=Side(style="thin", color=LINEA_HEX))
_ANCHO_MAXIMO_EXCEL = 60  # caracteres


# --- Estilos de texto (PDF) -------------------------------------------------------------------------------------------------

def estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    oscuro = colors.HexColor("#" + TINTA_HEX)
    gris = colors.HexColor(brand.GRIS_TEXTO)
    rojo = colors.HexColor(brand.ROJO)
    suave = colors.HexColor("#" + SUAVE_HEX)
    return {
        "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=oscuro,
                                 spaceAfter=2),
        "subtitulo": ParagraphStyle("subtitulo", parent=base, fontName="Helvetica", fontSize=8.5, leading=11, textColor=suave),
        "seccion": ParagraphStyle("seccion", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=rojo,
                                  spaceBefore=6, spaceAfter=4),
        "etiqueta": ParagraphStyle("etiqueta", parent=base, fontName="Helvetica", fontSize=7.4, leading=9, textColor=suave),
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


def texto(value: str, style: ParagraphStyle) -> Paragraph:
    """Párrafo seguro: el texto se escapa y un valor largo sin espacios se corta dentro de la celda (nunca se superpone)."""
    if " " not in value and len(value) > TEXTO_SIN_ESPACIOS_LARGO:
        style = ParagraphStyle(style.name + "Cortado", parent=style, wordWrap="CJK")
    return Paragraph(escape(value), style)


def escalar(anchos) -> list[float]:
    """Reparte el ancho útil entre las columnas en la misma proporción en que están definidas."""
    factor = ANCHO_UTIL / sum(anchos)
    return [ancho * factor for ancho in anchos]


# --- Bloques PDF ------------------------------------------------------------------------------------------------------------

def bannerFlowables(banner) -> list:
    """Banner completo, centrado y con su proporción original, seguido de la línea roja institucional."""
    ancho = ANCHO_UTIL * FRACCION_BANNER
    return [
        Image(str(banner), width=ancho, height=ancho / brand.proporcion(banner), hAlign="CENTER"),
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(brand.ROJO), spaceBefore=8, spaceAfter=10),
    ]


def tarjetas(items: list[tuple[str, str, bool]], estilos_: dict) -> Table:
    """Fila de tarjetas del resumen, repartidas en el ancho útil. Cada una: etiqueta y valor; las cifras van en letra grande."""
    ancho = (ANCHO_UTIL - ESPACIO_TARJETAS * (len(items) - 1)) / len(items)
    celdas, columnas, tarjetasIdx = [], [], []
    for indice, (etiqueta, valor, esCifra) in enumerate(items):
        celdas.append([Paragraph(escape(etiqueta), estilos_["etiqueta"]),
                       Paragraph(escape(valor), estilos_["tarjetaNumero" if esCifra else "tarjetaTexto"])])
        columnas.append(ancho)
        tarjetasIdx.append(len(celdas) - 1)
        if indice < len(items) - 1:
            celdas.append("")
            columnas.append(ESPACIO_TARJETAS)
    tabla = Table([celdas], colWidths=columnas)
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for columna in tarjetasIdx:
        estilo += [("BACKGROUND", (columna, 0), (columna, 0), colors.HexColor(brand.ROJO_SUAVE)),
                   ("LINEBEFORE", (columna, 0), (columna, 0), 2.5, colors.HexColor(brand.ROJO))]
    tabla.setStyle(TableStyle(estilo))
    return tabla


def datosClave(filas: list[tuple[str, str]], estilos_: dict) -> Table:
    """Pares etiqueta-valor (filtros, datos de la matriz) en dos columnas por fila, con filetes discretos."""
    mitad = math.ceil(len(filas) / 2)
    izquierda, derecha = filas[:mitad], filas[mitad:]
    cuerpo = []
    for indice in range(mitad):
        par = izquierda[indice]
        otro = derecha[indice] if indice < len(derecha) else ("", "")
        cuerpo.append([Paragraph(escape(par[0]), estilos_["etiqueta"]), texto(par[1], estilos_["celda"]),
                       Paragraph(escape(otro[0]), estilos_["etiqueta"]), texto(otro[1], estilos_["celda"])])
    anchoEtiqueta = ANCHO_UTIL * 0.14
    anchoValor = (ANCHO_UTIL - 2 * anchoEtiqueta) / 2
    tabla = Table(cuerpo, colWidths=[anchoEtiqueta, anchoValor, anchoEtiqueta, anchoValor])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(brand.GRIS_LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def anchosDinamicos(encabezados: tuple[str, ...], filas: list[list[str]], ancho: float) -> list[float]:
    """Ancho de cada columna en puntos. Ninguna columna queda más angosta que su palabra más larga (no se corta una palabra); lo que
    sobra se reparte según cuánto texto tiene cada columna. Si no alcanza, se achican todas en la misma proporción."""
    minimos, deseados = [], []
    for indice, encabezado in enumerate(encabezados):
        valores = [fila[indice] for fila in filas]
        palabrasEncabezado = [stringWidth(p, "Helvetica-Bold", 8) for p in encabezado.split()] or [0]
        palabras = [stringWidth(p, "Helvetica", 8) for valor in valores for p in valor.split()] or [0]
        minimo = max(palabrasEncabezado + palabras) + 10
        mayor = max([stringWidth(encabezado, "Helvetica-Bold", 8)] + [stringWidth(valor, "Helvetica", 8) for valor in valores])
        minimos.append(minimo)
        deseados.append(min(max(mayor + 10, minimo), 260))
    if sum(minimos) >= ancho:
        return [ancho * minimo / sum(minimos) for minimo in minimos]
    sobra = ancho - sum(minimos)
    holguras = [d - m for d, m in zip(deseados, minimos)]
    total = sum(holguras)
    if total == 0:
        return [m + sobra / len(minimos) for m in minimos]
    return [m + sobra * h / total for m, h in zip(minimos, holguras)]


def tablaInstitucional(encabezados: tuple[str, ...], filas: list[list[str]], estilos_: dict, colorear=None) -> Table:
    """Tabla con encabezado rojo y texto blanco, filas alternadas con contraste sutil y filetes discretos. El encabezado se repite
    en cada página. `colorear(fila, indice, celda)` devuelve un estilo adicional para una celda (por ejemplo, un estado)."""
    cabecera = [[Paragraph(escape(titulo), estilos_["encabezado"]) for titulo in encabezados]]
    cuerpo = [[texto(valor, estilos_["celda"]) for valor in fila] for fila in filas]
    tabla = Table(cabecera + cuerpo, colWidths=anchosDinamicos(encabezados, filas, ANCHO_UTIL), repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + ROJO_HEX)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#" + ZEBRA_HEX)]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(brand.GRIS_LINEA)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if colorear:
        for indice_fila, fila in enumerate(filas, start=1):
            for indice, valor in enumerate(fila):
                extra = colorear(fila, indice, valor)
                if extra:
                    estilo.append(("BACKGROUND", (indice, indice_fila), (indice, indice_fila), extra))
    tabla.setStyle(TableStyle(estilo))
    return tabla


# --- Encabezado y pie (PDF) -------------------------------------------------------------------------------------------------

def cabeceraCompacta(canvas, documento: str) -> None:
    """Encabezado de las páginas siguientes: nombre de la marca en texto, nombre del documento y una línea roja. Sin banner."""
    arriba = PAGINA[1] - MARGEN
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor("#" + TINTA_HEX))
    canvas.drawString(MARGEN, arriba - 11, "Gluco")
    ancho = canvas.stringWidth("Gluco", "Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(MARGEN + ancho, arriba - 11, "Lume")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawRightString(PAGINA[0] - MARGEN, arriba - 11, documento)
    canvas.setStrokeColor(colors.HexColor(brand.ROJO))
    canvas.setLineWidth(1.2)
    canvas.line(MARGEN, arriba - ALTO_CABECERA_SIGUIENTE, PAGINA[0] - MARGEN, arriba - ALTO_CABECERA_SIGUIENTE)


def pie(canvas, generado: datetime) -> None:
    """Pie discreto: marca y eslogan a la izquierda, fecha de generación al centro (el número de página lo agrega el canvas)."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(brand.GRIS_LINEA))
    canvas.setLineWidth(0.5)
    canvas.line(MARGEN, 34, PAGINA[0] - MARGEN, 34)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor(brand.ROJO))
    canvas.drawString(MARGEN, 22, SLOGAN_PIE)
    canvas.setFillColor(colors.HexColor(brand.GRIS_TEXTO))
    canvas.drawCentredString(PAGINA[0] / 2, 22, f"Generado el {csvDate(generado)}")
    canvas.restoreState()


class NumeracionCanvas(pdfcanvas.Canvas):
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
            self.drawRightString(PAGINA[0] - MARGEN, 22, f"Página {self._pageNumber} de {total}")
            self.restoreState()
            super().showPage()
        super().save()


def _marco(id: str, sangriaSuperior: float) -> Frame:
    """Área útil de la hoja. `sangriaSuperior` reserva el alto del encabezado compacto (0 si lo ocupa el banner)."""
    return Frame(MARGEN, MARGEN_INFERIOR, ANCHO_UTIL, PAGINA[1] - MARGEN_INFERIOR - MARGEN - sangriaSuperior,
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=id)


def pdfDocument(titulo: str, asunto: str, documento: str, generado: datetime, contenido: list) -> bytes:
    """PDF con la identidad de GlucoLume. La primera hoja lleva el banner completo; las siguientes, el encabezado compacto.
    `contenido` es lo que va debajo del banner: título, resumen, tablas. `documento` es el nombre que aparece en el encabezado."""
    banner = brand.existing(brand.BANNER_PATH)
    story = bannerFlowables(banner) if banner else []
    story.append(NextPageTemplate("siguientes"))
    story += contenido
    sangria = ALTO_CABECERA_SIGUIENTE + 12
    sangriaPrimera = 0 if banner else sangria  # sin banner, la primera hoja también lleva el encabezado compacto

    def primera(canvas, doc):
        if not banner:
            cabeceraCompacta(canvas, documento)
        pie(canvas, generado)

    def siguientes(canvas, doc):
        cabeceraCompacta(canvas, documento)
        pie(canvas, generado)

    buffer = BytesIO()
    document = BaseDocTemplate(buffer, pagesize=PAGINA, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN,
                               bottomMargin=MARGEN_INFERIOR, title=titulo, author="GlucoLume", subject=asunto)
    document.addPageTemplates([
        PageTemplate(id="primera", frames=[_marco("primera", sangriaPrimera)], onPage=primera),
        PageTemplate(id="siguientes", frames=[_marco("siguientes", sangria)], onPage=siguientes),
    ])
    document.build(story, canvasmaker=NumeracionCanvas)
    return buffer.getvalue()


def seccion(titulo: str, estilos_: dict) -> Paragraph:
    return Paragraph(escape(titulo), estilos_["seccion"])


def espacio(alto: float) -> Spacer:
    return Spacer(1, alto)


# --- Excel ------------------------------------------------------------------------------------------------------------------

def textoExcel(cell, value: str) -> None:
    """Texto que nunca se interpreta como fórmula (un valor que empieza con = queda como texto)."""
    cell.value = value
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        cell.data_type = "s"


def anchoPx(ancho: float) -> int:
    """Ancho de columna de Excel en píxeles (aproximación con la fuente predeterminada)."""
    return int(ancho * 7 + 5)


def columnaEnPx(px: int, anchos: tuple[float, ...]) -> tuple[int, int]:
    """Columna (desde 0) y desplazamiento dentro de ella para una posición horizontal, en píxeles."""
    acumulado = 0
    for indice, ancho in enumerate(anchos):
        if px < acumulado + anchoPx(ancho):
            return indice, px - acumulado
        acumulado += anchoPx(ancho)
    return len(anchos) - 1, 0


def bannerExcel(hoja, anchos: tuple[float, ...], fila: int) -> int:
    """Banner completo centrado en el ancho de la hoja, con su proporción. Devuelve la primera fila libre debajo de él."""
    banner = brand.existing(brand.BANNER_PATH)
    if not banner:
        return fila
    total = sum(anchoPx(ancho) for ancho in anchos)
    anchoImagen = round(total * FRACCION_BANNER)
    altoImagen = round(anchoImagen / brand.proporcion(banner))
    filas = math.ceil(altoImagen / (ALTO_FILA_EXCEL * 96 / 72))
    for reservada in range(fila, fila + filas):
        hoja.row_dimensions[reservada].height = ALTO_FILA_EXCEL
    imagen = ExcelImage(str(banner))
    imagen.width, imagen.height = anchoImagen, altoImagen
    columna, desplazamiento = columnaEnPx((total - anchoImagen) // 2, anchos)
    imagen.anchor = OneCellAnchor(
        _from=AnchorMarker(col=columna, colOff=pixels_to_EMU(desplazamiento), row=fila - 1, rowOff=0),
        ext=XDRPositiveSize2D(pixels_to_EMU(anchoImagen), pixels_to_EMU(altoImagen)),
    )
    hoja.add_image(imagen)
    fila += filas
    hoja.row_dimensions[fila].height = 8
    for letra in "BC":
        hoja[f"{letra}{fila}"].border = Border(bottom=Side(style="medium", color=ROJO_HEX))
    return fila + 2


def anchoColumnasExcel(hoja, encabezados: tuple[str, ...], filas: list[list], maximo: int = _ANCHO_MAXIMO_EXCEL) -> None:
    """Ajusta cada columna al texto más largo (encabezado incluido), con un tope."""
    for indice, encabezado in enumerate(encabezados):
        mayor = max([len(encabezado)] + [len(str(fila[indice])) for fila in filas])
        palabra = max([len(p) for p in encabezado.split()] or [0])
        hoja.column_dimensions[get_column_letter(indice + 1)].width = min(max(mayor + 2, palabra + 2), maximo)


def encabezadoExcel(hoja, encabezados: tuple[str, ...], fila: int = 1) -> None:
    """Encabezado de tabla: texto blanco en fondo rojo institucional, centrado y con ajuste de línea."""
    for indice, titulo in enumerate(encabezados, start=1):
        celda = hoja.cell(row=fila, column=indice)
        textoExcel(celda, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = FILL_ENCABEZADO
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hoja.row_dimensions[fila].height = 34


def celdaExcel(celda, valor, formato: str | None, *, zebra: bool, centrar: bool = False) -> None:
    """Valor de una celda de tabla: texto o número con su formato nativo, borde discreto y franja alternada."""
    if isinstance(valor, str):
        textoExcel(celda, valor)
    else:
        celda.value = valor
    if formato:
        celda.number_format = formato
    numerico = not isinstance(valor, str) and valor is not None
    horizontal = "center" if centrar or numerico else "left"
    celda.alignment = Alignment(horizontal=horizontal, vertical="top", wrap_text=True)
    celda.border = BORDE_FINO
    if zebra:
        celda.fill = FILL_ZEBRA


def titulosExcel(hoja, encabezados: tuple[str, ...], filas: list[list]) -> None:
    """Filtros automáticos, encabezado congelado y repetido al imprimir."""
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(encabezados))}{max(len(filas), 0) + 1}"
    hoja.print_title_rows = "1:1"


def imprimirExcel(hoja, *, area: str | None = None) -> None:
    """Configuración de impresión común: A4 horizontal, ancho de una hoja, centrado y pie institucional con numeración."""
    hoja.sheet_properties.tabColor = ROJO_HEX
    hoja.print_options.horizontalCentered = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.oddFooter.left.text = SLOGAN_PIE
    hoja.oddFooter.left.size = 8
    hoja.oddFooter.right.text = "Página &P de &N"
    hoja.oddFooter.right.size = 8
    if area:
        hoja.print_area = area


def libroExcel(titulo: str):
    """Libro de Excel con la identidad de GlucoLume (autor y título). La hoja activa se renombra según el módulo."""
    from openpyxl import Workbook

    book = Workbook()
    book.properties.creator = "GlucoLume"
    book.properties.title = titulo
    return book


def guardarExcel(book) -> bytes:
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def bannerResumenExcel(hoja, titulo: str, subtitulo: str, anchos: tuple[float, ...]) -> int:
    """Encabezado de la hoja Resumen: banner completo, título y subtítulo. Devuelve la primera fila libre."""
    fila = bannerExcel(hoja, anchos, 2)
    textoExcel(hoja[f"B{fila}"], titulo)
    hoja[f"B{fila}"].font = Font(bold=True, size=14, color=TINTA_HEX)
    fila += 1
    textoExcel(hoja[f"B{fila}"], subtitulo)
    hoja[f"B{fila}"].font = Font(size=9, color=SUAVE_HEX)
    return fila + 2


def etiquetaValorExcel(hoja, fila: int, etiqueta: str, valor, formato: str | None = None) -> int:
    """Par etiqueta-valor en la hoja Resumen (B y C). Devuelve la fila siguiente."""
    textoExcel(hoja[f"B{fila}"], etiqueta)
    hoja[f"B{fila}"].font = Font(bold=True, color=brand.GRIS_TEXTO.lstrip("#"))
    if isinstance(valor, str):
        textoExcel(hoja[f"C{fila}"], valor)
    else:
        hoja[f"C{fila}"].value = valor
    if formato:
        hoja[f"C{fila}"].number_format = formato
    hoja[f"C{fila}"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    return fila + 1


def encabezadoIndicadoresExcel(hoja, fila: int, titulos: tuple[str, str]) -> int:
    """Título de sección «Indicadores» con su encabezado rojo. Devuelve la fila de la primera fila de datos."""
    textoExcel(hoja[f"B{fila}"], "Indicadores")
    hoja[f"B{fila}"].font = Font(bold=True, size=12, color=ROJO_HEX)
    fila += 1
    for col, texto_ in zip("BC", titulos):
        textoExcel(hoja[f"{col}{fila}"], texto_)
        hoja[f"{col}{fila}"].font = Font(bold=True, color="FFFFFF")
        hoja[f"{col}{fila}"].fill = FILL_ENCABEZADO
    return fila + 1


def indicadorExcel(hoja, fila: int, etiqueta: str, valor) -> int:
    textoExcel(hoja[f"B{fila}"], etiqueta)
    hoja[f"C{fila}"].value = valor
    hoja[f"C{fila}"].alignment = Alignment(horizontal="left", wrap_text=True)
    hoja[f"B{fila}"].border = BORDE_FINO
    hoja[f"C{fila}"].border = BORDE_FINO
    return fila + 1
