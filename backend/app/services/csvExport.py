# CsvExport - Formato común de las exportaciones CSV (personal y pacientes)
#
# Separador punto y coma, UTF-8 con BOM (Excel en español muestra bien las tildes) y escape de fórmulas: un valor que empieza con
# = + - @ se prefija con una comilla simple para que no se ejecute como fórmula al abrir el archivo.

import csv
import io
from datetime import date, datetime

from app.utils.timeZone import withArgentinaZone

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csvText(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def csvDate(value: date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return withArgentinaZone(value).strftime("%d/%m/%Y %H:%M")
    return value.strftime("%d/%m/%Y")


def csvBytes(columns: tuple[str, ...], rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")
