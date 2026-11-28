"""Inventario de dispositivos en Excel y PDF: reglas de presentación según el tipo de uso (sin base de datos).

Ejecutar desde backend/:  python -m pytest tests/test_device_report.py -v
"""
import io
from datetime import datetime

import openpyxl
import pytest

from app.services.deviceReport import (
    ENCABEZADOS_INDIVIDUAL, ENCABEZADOS_INSTITUCIONAL, HOJA_INDIVIDUAL, HOJA_INSTITUCIONAL, SIN_DATO, DeviceRecord, inventoryFile,
)

AHORA = datetime(2026, 11, 28, 10, 30)
FILTROS = [("Estado", "Operativo")]


def individual(i: int, operativo: bool = True) -> DeviceRecord:
    return DeviceRecord(codigo=f"IND-{i:03d}", nombre=f"Glucómetro {i}", modelo="GL-200", estado="Operativo" if operativo else "Fuera de servicio",
                        operativo=operativo, uso="Individual", responsable="paciente@correo.com.ar", sensor="LUM-S2", firmware="1.4.0",
                        registrado=datetime(2026, 1, 10, 9, 0), institucional=False, institucion=None, incorporado=None)


def institucional(i: int, institucion: str | None = "Hospital Central", incorporado: datetime | None = datetime(2026, 2, 3, 8, 0)) -> DeviceRecord:
    return DeviceRecord(codigo=f"INS-{i:03d}", nombre=f"Equipo {i}", modelo="GL-300", estado="Operativo", operativo=True,
                        uso=institucion or "Institución", responsable="Enfermería", sensor="LUM-S3", firmware="2.0.1",
                        registrado=datetime(2025, 6, 1, 8, 0), institucional=True, institucion=institucion, incorporado=incorporado)


def libro(records):
    content, _ = inventoryFile("xlsx", "dispositivos", "Inventario de dispositivos", FILTROS, records, AHORA)
    return openpyxl.load_workbook(io.BytesIO(content))


def encabezados(hoja) -> list[str]:
    return [celda.value for celda in hoja[1] if celda.value]


def test_solo_individuales_no_tiene_hoja_institucional_ni_columnas_institucionales():
    book = libro([individual(1), individual(2)])
    assert book.sheetnames == ["Resumen", HOJA_INDIVIDUAL]
    assert encabezados(book[HOJA_INDIVIDUAL]) == list(ENCABEZADOS_INDIVIDUAL)
    assert "Institución" not in encabezados(book[HOJA_INDIVIDUAL])


def test_solo_institucionales_no_tiene_hoja_individual():
    book = libro([institucional(1), institucional(2)])
    assert book.sheetnames == ["Resumen", HOJA_INSTITUCIONAL]
    assert encabezados(book[HOJA_INSTITUCIONAL]) == list(ENCABEZADOS_INSTITUCIONAL)


def test_mixta_tiene_una_hoja_por_tipo_y_cada_una_con_sus_campos():
    book = libro([individual(1), institucional(1)])
    assert book.sheetnames == ["Resumen", HOJA_INDIVIDUAL, HOJA_INSTITUCIONAL]
    assert "Fecha de incorporación a la institución" in encabezados(book[HOJA_INSTITUCIONAL])
    assert "Fecha de incorporación a la institución" not in encabezados(book[HOJA_INDIVIDUAL])


def test_fecha_de_incorporacion_es_la_vinculacion_y_no_la_de_registro():
    book = libro([institucional(1)])
    hoja = book[HOJA_INSTITUCIONAL]
    columnas = {titulo: indice for indice, titulo in enumerate(encabezados(hoja), start=1)}
    registro = hoja.cell(row=2, column=columnas["Fecha de registro"]).value
    incorporacion = hoja.cell(row=2, column=columnas["Fecha de incorporación a la institución"]).value
    assert registro.date() == datetime(2025, 6, 1).date()
    assert incorporacion.date() == datetime(2026, 2, 3).date()
    assert hoja.cell(row=2, column=columnas["Fecha de registro"]).number_format == "dd/mm/yyyy"


def test_institucional_con_vinculacion_incompleta_dice_no_registrado():
    book = libro([institucional(1, institucion=None, incorporado=None)])
    hoja = book[HOJA_INSTITUCIONAL]
    columnas = {titulo: indice for indice, titulo in enumerate(encabezados(hoja), start=1)}
    assert hoja.cell(row=2, column=columnas["Institución"]).value == SIN_DATO
    assert hoja.cell(row=2, column=columnas["Fecha de incorporación a la institución"]).value == SIN_DATO


def test_resumen_cuenta_los_registros_exportados():
    records = [individual(1), individual(2, operativo=False), institucional(1), institucional(2)]
    resumen = libro(records)["Resumen"]
    valores = {resumen.cell(row=fila, column=2).value: resumen.cell(row=fila, column=3).value for fila in range(1, resumen.max_row + 1)}
    assert valores["Total de dispositivos"] == 4
    assert valores["Dispositivos operativos"] == 3
    assert valores["Dispositivos de uso individual"] == 2
    assert valores["Dispositivos de uso institucional"] == 2


def test_excel_tiene_filtros_encabezado_congelado_y_formato_condicional_de_estado():
    hoja = libro([individual(1), individual(2, operativo=False)])[HOJA_INDIVIDUAL]
    assert hoja.freeze_panes == "A2"
    assert hoja.auto_filter.ref and hoja.auto_filter.ref.startswith("A1:")
    assert any("D2" in str(rango.sqref) for rango in hoja.conditional_formatting)


@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_los_formatos_salen_con_su_firma_y_nombre(formato):
    content, nombre = inventoryFile(formato, "dispositivos", "Inventario de dispositivos", FILTROS, [individual(1)], AHORA)
    assert nombre == f"dispositivos.{formato}"
    assert content.startswith(b"%PDF") if formato == "pdf" else content.startswith(b"PK")


def test_exportacion_vacia_sigue_siendo_un_archivo_valido():
    content, _ = inventoryFile("pdf", "dispositivos", "Inventario de dispositivos", FILTROS, [], AHORA)
    assert content.startswith(b"%PDF")
    assert libro([]).sheetnames == ["Resumen"]


def test_muchos_dispositivos_ocupan_varias_paginas():
    records = [individual(i) for i in range(1, 120)]
    content, _ = inventoryFile("pdf", "dispositivos", "Inventario de dispositivos", FILTROS, records, AHORA)
    assert content.count(b"/Type /Page\n") + content.count(b"/Type /Page ") >= 2
