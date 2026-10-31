# TableExport - Formatos de descarga de una tabla: CSV (por defecto), Excel (.xlsx) y PDF
#
# Los tres formatos reciben las mismas columnas y las mismas celdas ya preparadas por csvExport (csvText / csvDate): cambia la
# presentación, no lo que sale. Lo llama el servicio que ya validó el permiso y abrió la auditoría de la exportación; este módulo no
# decide quién puede exportar.

import re
from datetime import datetime
from io import BytesIO
from typing import Literal
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.csvExport import csvBytes, csvDate

FormatoExportacion = Literal["csv", "xlsx", "pdf"]

_EXTENSIONES = {"csv": ".csv", "xlsx": ".xlsx", "pdf": ".pdf"}
_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
_CARACTERES_NO_PERMITIDOS_EN_HOJA = re.compile(r"[\\/*?:\[\]]")  # Excel no admite estos caracteres en el nombre de una hoja
_ANCHO_MAXIMO_EXCEL = 60  # caracteres
_TAMANO_CELDA_PDF = 7  # puntos
_PADDING_CELDA_PDF = 8  # puntos que se suman al ancho de texto de cada columna (márgenes de la celda y un poco de aire)
_ANCHO_DESEADO_MAXIMO_PDF = 220  # puntos: una columna de texto largo no reclama más que esto
_TEXTO_SIN_ESPACIOS_LARGO = 20  # desde acá, un texto sin espacios (un enlace, por ejemplo) se corta dentro de la celda


def mediaTypeOf(formato: str) -> str:
    return _MEDIA_TYPES[formato]


def tableFile(formato: str, nombreBase: str, titulo: str, columns: tuple[str, ...], rows, generado: datetime) -> tuple[bytes, str]:
    """(contenido, nombre del archivo) de la tabla en el formato pedido. `nombreBase` lleva la fecha y la extensión se agrega acá."""
    if formato == "csv":
        content = csvBytes(columns, rows)
    elif formato == "xlsx":
        content = _xlsxBytes(titulo, columns, rows)
    elif formato == "pdf":
        content = _pdfBytes(titulo, columns, rows, generado)
    else:
        raise ValueError(f"Formato de exportación desconocido: {formato}")
    return content, nombreBase + _EXTENSIONES[formato]


def _xlsxBytes(titulo: str, columns: tuple[str, ...], rows) -> bytes:
    book = Workbook()
    book.properties.creator = "GlucoLume"
    sheet = book.active
    sheet.title = _CARACTERES_NO_PERMITIDOS_EN_HOJA.sub(" ", titulo)[:31] or "Datos"
    sheet.append(list(columns))
    for row in rows:
        sheet.append(list(row))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DCE6F1")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, column in enumerate(columns):
        longest = max([len(column)] + [len(str(row[index])) for row in rows])
        sheet.column_dimensions[get_column_letter(index + 1)].width = min(longest + 2, _ANCHO_MAXIMO_EXCEL)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _anchos(columns: tuple[str, ...], rows, width: float) -> list[float]:
    """Ancho de cada columna en puntos: nunca menos que su palabra más larga (para que no se corte una palabra), y lo que sobra se
    reparte según cuánto texto tiene cada columna."""
    minimos, deseados = [], []
    for index, column in enumerate(columns):
        values = [str(row[index]) for row in rows]
        palabrasEncabezado = [stringWidth(word, "Helvetica-Bold", _TAMANO_CELDA_PDF) for word in column.split()] or [0]
        palabras = [stringWidth(word, "Helvetica", _TAMANO_CELDA_PDF) for value in values for word in value.split()] or [0]
        minimo = min(max(palabrasEncabezado + palabras) + _PADDING_CELDA_PDF, _ANCHO_DESEADO_MAXIMO_PDF)
        mayorTexto = max([stringWidth(column, "Helvetica-Bold", _TAMANO_CELDA_PDF)]
                         + [stringWidth(value, "Helvetica", _TAMANO_CELDA_PDF) for value in values])
        minimos.append(minimo)
        deseados.append(min(max(mayorTexto + _PADDING_CELDA_PDF, minimo), _ANCHO_DESEADO_MAXIMO_PDF))
    if sum(minimos) >= width:
        return [width * minimo / sum(minimos) for minimo in minimos]
    sobra = width - sum(minimos)
    holguras = [deseado - minimo for deseado, minimo in zip(deseados, minimos)]
    total = sum(holguras)
    if total == 0:
        return [minimo + sobra / len(minimos) for minimo in minimos]
    return [minimo + sobra * holgura / total for minimo, holgura in zip(minimos, holguras)]


def _numerarPagina(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.bottomMargin / 2, f"GlucoLume · Página {doc.page}")
    canvas.restoreState()


def _pdfBytes(titulo: str, columns: tuple[str, ...], rows, generado: datetime) -> bytes:
    pagina = landscape(A4)
    margen = 14 * mm
    estilos = getSampleStyleSheet()
    celda = ParagraphStyle("celda", parent=estilos["Normal"], fontName="Helvetica", fontSize=_TAMANO_CELDA_PDF, leading=8.5)
    celdaSinEspacios = ParagraphStyle("celdaSinEspacios", parent=celda, wordWrap="CJK")
    encabezado = ParagraphStyle("encabezado", parent=celda, fontName="Helvetica-Bold", textColor=colors.white)
    tituloEstilo = ParagraphStyle("titulo", parent=estilos["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, spaceAfter=2)
    subtitulo = ParagraphStyle("subtitulo", parent=celda, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))

    def paragraph(value: str, style: ParagraphStyle) -> Paragraph:
        if " " not in value and len(value) > _TEXTO_SIN_ESPACIOS_LARGO:
            style = celdaSinEspacios
        return Paragraph(escape(value), style)

    data = [[paragraph(column, encabezado) for column in columns]]
    data += [[paragraph(str(value), celda) for value in row] for row in rows]
    tabla = Table(data, colWidths=_anchos(columns, rows, pagina[0] - 2 * margen), repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D3E0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story = [
        Paragraph(escape(titulo), tituloEstilo),
        Paragraph(escape(f"Generado el {csvDate(generado)} · {len(rows)} registros"), subtitulo),
        Spacer(1, 5 * mm),
        tabla,
    ]
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=pagina, leftMargin=margen, rightMargin=margen, topMargin=margen, bottomMargin=margen,
                                 title=titulo, author="GlucoLume")
    document.build(story, onFirstPage=_numerarPagina, onLaterPages=_numerarPagina)
    return buffer.getvalue()
