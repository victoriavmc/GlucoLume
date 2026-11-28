# MatrixExport - Exportación de la matriz de referencia en Excel y PDF, con la identidad visual de GlucoLume.
#
# El CSV de la matriz lo arma el servicio de matrices (sin cambios). Este módulo solo presenta los datos ya preparados. Banner,
# colores, encabezados, pies y numeración vienen de exportTemplate (plantilla común a todas las exportaciones):
#   · Excel: hoja «Resumen» (banner completo, datos de la matriz e indicadores) y hoja «Matriz» (una fila por regla, con tipos
#     nativos, encabezado rojo, paneles congelados, filtros e impresión A4 horizontal con el encabezado repetido).
#   · PDF: A4 horizontal. La primera hoja lleva el banner completo centrado; las siguientes, un encabezado compacto.
# Un límite que no existe se muestra como «Sin límite»; una glucosa o un dato ausente nunca se muestra como cero.

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.services import exportTemplate as tpl
from app.services.csvExport import csvDate

SIN_LIMITE = "Sin límite"
_EXTENSIONES = {"xlsx": ".xlsx", "pdf": ".pdf"}
_ANCHOS_RESUMEN = (2, 30, 80, 2)  # columnas de la hoja Resumen (caracteres de Excel)
_ANCHOS_MATRIZ = (34, 12, 24, 12, 13, 13, 34, 44, 13, 14, 12, 12, 20, 16, 16, 16, 16)  # una por columna de MATRIX_EXPORT_COLUMNS
_FORMATO_GLUCOSA = "0.00"
_FORMATO_NUMERO = "0"
_ANCHOS_REGLAS = (84, 84, 66, 66, 118, 86, 86, 86, 86)  # se escalan al ancho útil
_ANCHOS_DATOS = (110, 290, 110, 252)
_DOCUMENTO = "Matriz de referencia de glucosa"


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


# --- Excel ------------------------------------------------------------------------------------------------------------------

def _xlsx(titulo: str, columns: tuple[str, ...], header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> bytes:
    book = tpl.libroExcel(titulo)
    resumen = book.active
    resumen.title = "Resumen"
    resumen.sheet_view.showGridLines = False
    _hojaResumen(resumen, titulo, header, rules, generado)
    hoja = book.create_sheet("Matriz")
    _hojaMatriz(hoja, columns, header, rules)
    return tpl.guardarExcel(book)


def _hojaResumen(hoja, titulo: str, header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> None:
    for letra, ancho in zip("ABCD", _ANCHOS_RESUMEN):
        hoja.column_dimensions[letra].width = ancho
    fila = tpl.bannerResumenExcel(hoja, titulo, _subtitulo(header, rules, generado), _ANCHOS_RESUMEN)
    datos = [
        ("Origen / alcance", header.origen), ("Versión", header.version), ("Estado", header.estado),
        ("Vigencia desde", _fecha(header.vigenciaDesde)), ("Vigencia hasta", _fecha(header.vigenciaHasta)),
        ("Referencia base", header.referenciaBase), ("URL de referencia", header.urlReferencia or "Sin URL"),
    ]
    for etiqueta, valor in datos:
        fila = tpl.etiquetaValorExcel(hoja, fila, etiqueta, valor)
    fila += 1
    fila = tpl.encabezadoIndicadoresExcel(hoja, fila, ("Indicador", "Valor"))
    indicadores = [("Registros exportados", len(rules)), ("Condiciones de comida contempladas", _condiciones(rules))]
    for etiqueta, valor in indicadores:
        fila = tpl.indicadorExcel(hoja, fila, etiqueta, valor)
        hoja[f"C{fila - 1}"].alignment = Alignment(horizontal="left", wrap_text=True)
    tpl.imprimirExcel(hoja, area=f"A1:D{fila + 1}")
    hoja.print_options.horizontalCentered = True


def _valorFecha(value: date | None) -> tuple:
    return (value, tpl.FORMATO_FECHA) if value is not None else (SIN_LIMITE, None)


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
    for indice, ancho in enumerate(_ANCHOS_MATRIZ, start=1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    tpl.encabezadoExcel(hoja, columns)
    filas = _filasMatriz(header, rules)
    for numero, valores in enumerate(filas, start=2):
        for indice, (valor, formato) in enumerate(valores, start=1):
            if valor is None:
                continue
            celda = hoja.cell(row=numero, column=indice)
            tpl.celdaExcel(celda, valor, formato, zebra=numero % 2 == 1)
    tpl.titulosExcel(hoja, columns, filas)
    hoja.freeze_panes = "B2"  # encabezado y nombre de la matriz quedan visibles al desplazarse
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(filas) + 1}"
    tpl.imprimirExcel(hoja)


# --- PDF --------------------------------------------------------------------------------------------------------------------

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
    tabla = Table(cabecera + cuerpo, colWidths=tpl.escalar(_ANCHOS_REGLAS), repeatRows=2)
    tabla.setStyle(TableStyle([
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (3, 0)), ("SPAN", (4, 0), (4, 1)),
        ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor(tpl.brand.ROJO)),
        ("LINEBELOW", (2, 0), (3, 0), 0.5, colors.white), ("LINEBELOW", (5, 0), (6, 0), 0.5, colors.white),
        ("LINEBELOW", (7, 0), (8, 0), 0.5, colors.white),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#" + tpl.ZEBRA_HEX)]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(tpl.brand.GRIS_LINEA)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def _datos(header: MatrixHeader, estilos) -> Table:
    """Datos de la matriz que no son tarjetas: referencia, versión, vigencia y URL de la fuente."""
    etiqueta = lambda texto: Paragraph(escape(texto), estilos["etiqueta"])  # noqa: E731
    filas = [
        [etiqueta("Referencia base"), tpl.texto(header.referenciaBase, estilos["celda"]), etiqueta("Versión"),
         tpl.texto(header.version, estilos["celda"])],
        [etiqueta("Vigencia desde"), tpl.texto(_fecha(header.vigenciaDesde), estilos["celda"]), etiqueta("Vigencia hasta"),
         tpl.texto(_fecha(header.vigenciaHasta), estilos["celda"])],
        [etiqueta("URL de referencia"), tpl.texto(header.urlReferencia or "Sin URL", estilos["celda"]), "", ""],
    ]
    tabla = Table(filas, colWidths=tpl.escalar(_ANCHOS_DATOS))
    tabla.setStyle(TableStyle([
        ("SPAN", (1, 2), (3, 2)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(tpl.brand.GRIS_LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def _pdf(titulo: str, header: MatrixHeader, rules: list[MatrixRuleRow], generado: datetime) -> bytes:
    estilos = tpl.estilos()
    contenido = [
        Paragraph(escape(titulo), estilos["titulo"]),
        Paragraph(escape(_subtitulo(header, rules, generado)), estilos["subtitulo"]),
        Spacer(1, 10),
        tpl.tarjetas([
            ("Registros exportados", str(len(rules)), True),
            ("Reglas de la matriz", str(len(rules)), True),
            ("Vigencia desde", _fecha(header.vigenciaDesde), False),
            ("Origen / alcance", header.origen, False),
            ("Condiciones de comida contempladas", _condiciones(rules), False),
        ], estilos),
        Spacer(1, 10),
        _datos(header, estilos),
        tpl.seccion(f"Reglas ({len(rules)})", estilos),
    ]
    if rules:
        contenido.append(_tablaReglas(rules, estilos))
    else:
        contenido.append(Paragraph("La matriz no tiene reglas cargadas.", estilos["aviso"]))
    return tpl.pdfDocument(titulo, "Matriz de referencia de glucosa", _DOCUMENTO, generado, contenido)
