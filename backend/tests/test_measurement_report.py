# Informe de mediciones (CSV, Excel y PDF): presentación de GlucoLume sobre los mismos datos.
#
# Estas pruebas no usan base de datos: arman filas tipadas y revisan cada formato.
# El texto del PDF se verifica con pypdf (solo para pruebas; si no está instalado, esas comprobaciones se omiten).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_report.py -v

import csv
import io
from datetime import date, datetime

import openpyxl
import pytest
from openpyxl.worksheet.properties import PageSetupProperties
from PIL import Image

from app.services import brandAssets
from app.services import measurementReport as report

GENERADO = datetime(2026, 11, 27, 10, 30)
OBSERVACION_LARGA = "Observación extensa de la medición. " * 14  # ~490 caracteres: el máximo que guarda la base (500)


def linea(**cambios) -> report.ReportLine:
    base = dict(
        fecha=datetime(2026, 11, 26, 15, 35), modo="Glucosa (experimental)", estado="Completada", condicion="En ayunas",
        ultimaComida=datetime(2026, 11, 26, 8, 0), spo2=98.7, frecuenciaCardiaca=75, glucosa=131.2,
        origenGlucosa="DEMO (prueba)", semaforo="VERDE", esDemo=True, dispositivo="ARD-001", observacion="Sin novedades",
    )
    base.update(cambios)
    return report.ReportLine(**base)


def muestra(cantidad: int) -> list[report.ReportLine]:
    return [linea(fecha=datetime(2026, 11, 1, 8, 0).replace(day=1 + i % 27), observacion=f"Registro {i}") for i in range(cantidad)]


def generar(formato: str, lineas, **extra):
    datos = dict(alcance="Historial de mediciones", periodo="todas las fechas", filtros="sin filtros adicionales")
    datos.update(extra)
    return report.measurementFile(formato, "mis-mediciones-prueba", lineas, GENERADO, **datos)


def csvFilas(content: bytes) -> list[list[str]]:
    texto = content.decode("utf-8")
    assert texto.startswith("﻿")  # BOM UTF-8: Excel en español lee bien las tildes
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


# --- CSV --------------------------------------------------------------------------------------------------------------


def test_el_csv_tiene_bom_separador_punto_y_coma_y_encabezados_descriptivos():
    content, nombre = generar("csv", [linea()])
    assert nombre == "mis-mediciones-prueba.csv"
    encabezado, fila = csvFilas(content)
    assert tuple(encabezado) == report.CSV_COLUMNS
    assert fila[0] == "26/11/2026 15:35" and fila[5] == "98,70" and fila[6] == "75" and fila[7] == "131,2"
    assert fila[9] == "Verde" and fila[10] == "Prueba (DEMO)"


def test_un_valor_faltante_queda_vacio_y_no_se_confunde_con_cero():
    content, _ = generar("csv", [linea(spo2=None, frecuenciaCardiaca=None, glucosa=None, origenGlucosa=None, semaforo=None),
                                 linea(glucosa=0.0)])
    faltante, cero = csvFilas(content)[1:]
    assert faltante[5] == "" and faltante[6] == "" and faltante[7] == "" and faltante[9] == ""  # sin dato: vacío, sin color
    assert cero[7] == "0,0"  # un cero medido es 0, no vacío


def test_sin_clasificacion_el_semaforo_queda_vacio_y_ultima_comida_dice_sin_informar():
    content, _ = generar("csv", [linea(semaforo=None, ultimaComida=None)])
    fila = csvFilas(content)[1]
    assert fila[9] == "" and fila[4] == "Sin informar"


def test_el_csv_protege_contra_formulas_en_observaciones_y_dispositivos():
    content, _ = generar("csv", [linea(observacion='=HYPERLINK("http://x")', dispositivo="+SUMA(1)")])
    fila = csvFilas(content)[1]
    assert fila[11] == "'+SUMA(1)"
    assert fila[12] == "'=HYPERLINK(\"http://x\")"


def test_el_csv_no_tiene_imagenes_ni_adornos():
    content, _ = generar("csv", [linea()])
    assert b"\x89PNG" not in content and b"%PDF" not in content and b"<" not in content


# --- Excel ------------------------------------------------------------------------------------------------------------


def libro(content: bytes):
    return openpyxl.load_workbook(io.BytesIO(content))


def test_el_excel_tiene_resumen_y_mediciones_con_el_logo_oficial():
    content, nombre = generar("xlsx", muestra(3))
    assert nombre == "mis-mediciones-prueba.xlsx"
    book = libro(content)
    assert book.sheetnames == ["Resumen", "Mediciones"]
    assert len(book["Resumen"]._images) >= 1  # el logo oficial (o la gota, si el archivo no está)
    assert book["Resumen"]["C3"].value == "Informe de mediciones"
    assert book["Resumen"]["C2"].value is None  # el logo oficial ya trae el nombre: no se repite como texto


def test_sin_logo_oficial_el_excel_dibuja_la_gota_con_el_nombre_y_el_eslogan(monkeypatch, tmp_path):
    monkeypatch.setattr(brandAssets, "LOGO_PATH", tmp_path / "no-existe.png")
    book = libro(generar("xlsx", muestra(1))[0])
    assert book["Resumen"]["C2"].value == "GlucoLume"
    assert book["Resumen"]["C4"].value == brandAssets.SLOGAN


def test_los_indicadores_del_resumen_son_numeros_nativos():
    lineas = [linea(), linea(semaforo="ROJO"), linea(semaforo=None, glucosa=None, esDemo=False, origenGlucosa=None)]
    resumen = libro(generar("xlsx", lineas)[0])["Resumen"]
    valores = {resumen[f"B{fila}"].value: resumen[f"C{fila}"].value for fila in range(14, 22)}
    assert valores["Registros exportados"] == 3 and isinstance(valores["Registros exportados"], int)
    assert valores["Con glucosa del dispositivo"] == 2
    assert valores["Pruebas DEMO (simuladas)"] == 2
    assert valores["Sin clasificación de semáforo"] == 1


def test_la_hoja_mediciones_tiene_encabezado_rojo_filtros_y_paneles_congelados():
    hoja = libro(generar("xlsx", muestra(2))[0])["Mediciones"]
    encabezado = hoja["A1"]
    assert encabezado.fill.fgColor.rgb.endswith("D90820") and encabezado.font.color.rgb.endswith("FFFFFF")
    assert [c.value for c in hoja[1]] == list(report.CSV_COLUMNS)
    assert hoja.freeze_panes == "A2"
    assert hoja.auto_filter.ref == "A1:M3"
    assert hoja.print_title_rows == "$1:$1"  # encabezado repetido al imprimir
    assert hoja.page_setup.orientation == "landscape"


def test_los_datos_van_como_tipos_nativos_y_los_faltantes_quedan_vacios():
    hoja = libro(generar("xlsx", [linea(), linea(spo2=None, glucosa=None, frecuenciaCardiaca=None, ultimaComida=None,
                                              semaforo=None)])[0])["Mediciones"]
    fila = [c for c in hoja[2]]
    assert fila[0].value == datetime(2026, 11, 26, 15, 35) and fila[0].is_date
    assert fila[5].value == pytest.approx(98.7) and fila[5].data_type == "n"
    assert fila[6].value == 75 and fila[6].data_type == "n"
    assert fila[7].value == pytest.approx(131.2)
    assert fila[4].value == datetime(2026, 11, 26, 8, 0)
    segunda = [c for c in hoja[3]]
    assert segunda[5].value is None and segunda[6].value is None and segunda[7].value is None  # vacío, no cero
    assert segunda[4].value == "Sin informar" and segunda[9].value is None


def test_el_semaforo_tiene_formato_condicional_solo_para_las_tres_clasificaciones():
    hoja = libro(generar("xlsx", muestra(2))[0])["Mediciones"]
    reglas = [regla.formula for rangos in hoja.conditional_formatting for regla in rangos.rules]
    assert sorted(f[0] for f in reglas) == ['"Amarillo"', '"Rojo"', '"Verde"']
    assert all(str(rango.sqref) == "J2:J3" for rango in hoja.conditional_formatting)  # columna Semáforo


def test_una_observacion_con_formula_queda_como_texto_y_la_extensa_no_se_corta():
    hoja = libro(generar("xlsx", [linea(observacion='=HYPERLINK("x")'), linea(observacion=OBSERVACION_LARGA)])[0])["Mediciones"]
    assert hoja["M2"].value == '=HYPERLINK("x")' and hoja["M2"].data_type == "s"
    assert hoja["M3"].value == OBSERVACION_LARGA
    assert hoja.row_dimensions[3].height > 16  # la fila crece para mostrar la observación completa


def test_la_impresion_del_excel_sale_en_a4_horizontal_con_pie_institucional():
    book = libro(generar("xlsx", muestra(1))[0])
    for hoja in book.worksheets:
        assert str(hoja.page_setup.paperSize) == hoja.PAPERSIZE_A4  # A4
        assert hoja.page_setup.orientation == "landscape"
        assert "GlucoLume" in hoja.oddFooter.right.text
        assert brandAssets.AVISO_EXPERIMENTAL in hoja.oddFooter.left.text
    assert book["Mediciones"].sheet_properties.pageSetUpPr == PageSetupProperties(fitToPage=True)


# --- PDF --------------------------------------------------------------------------------------------------------------


def paginas(content: bytes) -> list[str]:
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(content))
    return [pagina.extract_text() or "" for pagina in reader.pages]


def test_el_pdf_es_un_informe_con_titulo_slogan_y_aviso_experimental():
    content, nombre = generar("pdf", [linea()])
    assert nombre == "mis-mediciones-prueba.pdf" and content.startswith(b"%PDF-")
    [texto] = paginas(content)
    assert "Informe de mediciones" in texto and brandAssets.SLOGAN in texto
    assert brandAssets.AVISO_EXPERIMENTAL in texto
    assert "Página 1 de 1" in texto


@pytest.mark.parametrize("cantidad", [1, 3, 60, 400])
def test_el_pdf_funciona_con_uno_varios_y_muchos_registros(cantidad):
    content, _ = generar("pdf", muestra(cantidad))
    textos = paginas(content)
    assert f"Mediciones ({cantidad})" in textos[0]
    if cantidad > 60:
        assert len(textos) > 1
        assert all("Fecha y hora" in t for t in textos[1:])  # el encabezado de la tabla se repite en cada hoja
        assert f"Página 2 de {len(textos)}" in textos[1]  # numeración automática con el total
    assert all(brandAssets.AVISO_EXPERIMENTAL in t for t in textos)


def test_una_observacion_de_500_caracteres_no_rompe_el_pdf():
    content, _ = generar("pdf", [linea(observacion=OBSERVACION_LARGA), linea(observacion=OBSERVACION_LARGA)])
    texto = paginas(content)[0]
    assert "Observación extensa de la medición" in texto


def test_sin_mediciones_el_pdf_avisa_y_no_falla():
    content, _ = generar("pdf", [])
    assert "No hay mediciones que coincidan con los filtros elegidos." in paginas(content)[0]


def test_el_pdf_muestra_sin_dato_y_no_inventa_colores_sin_clasificacion():
    content, _ = generar("pdf", [linea(semaforo=None, glucosa=None, spo2=None), linea(glucosa=0.0)])
    texto = paginas(content)[0]
    assert "Sin dato" in texto and "0,0" in texto and "Sin clasificación" in texto


def test_con_el_logo_oficial_cargado_se_incrusta_sin_depender_de_recursos_externos(tmp_path, monkeypatch):
    pypdf = pytest.importorskip("pypdf")
    archivo = tmp_path / "lumi.png"
    Image.new("RGB", (64, 64), (217, 8, 32)).save(archivo)  # marcador de prueba: no es la mascota
    monkeypatch.setattr(brandAssets, "LUMI_PATH", archivo)
    content, _ = generar("pdf", [linea()])
    lector = pypdf.PdfReader(io.BytesIO(content))
    assert len(lector.pages[0].images) >= 1
    assert "Informe de mediciones" in lector.pages[0].extract_text()  # el texto sigue siendo seleccionable


def test_sin_el_archivo_de_lumi_el_pdf_sale_igual_de_bien(monkeypatch, tmp_path):
    monkeypatch.setattr(brandAssets, "LUMI_PATH", tmp_path / "no-existe.png")
    content, _ = generar("pdf", [linea()])
    assert content.startswith(b"%PDF-")


# --- Varios ----------------------------------------------------------------------------------------------------------


def test_un_formato_desconocido_no_exporta():
    with pytest.raises(ValueError):
        generar("docx", [linea()])


@pytest.mark.parametrize("desde, hasta, esperado", [
    (None, None, "todas las fechas"),
    (date(2026, 11, 1), date(2026, 11, 27), "del 01/11/2026 al 27/11/2026"),
    (date(2026, 11, 1), None, "desde el 01/11/2026"),
    (None, date(2026, 11, 27), "hasta el 27/11/2026"),
])
def test_el_periodo_se_describe_segun_lo_elegido(desde, hasta, esperado):
    assert report.periodoTexto(desde, hasta) == esperado
