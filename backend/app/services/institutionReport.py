# InstitutionReport - Informe de UNA institución para la administración de la plataforma (CSV, Excel o PDF), en secciones:
#   1. Institución: nombre, tipo, identificador (CUIT), estado, propietario (nombre, apellido, correo), inicio, fin, cuentas y cupos.
#   2. Moderadores (y su número), con nombre, apellido, correo, inicio y fin de cada uno.
#   3. Operadores (y su número), igual que los moderadores.
#   4. Pacientes: activos, registrados, total de mediciones y cantidad de dispositivos (solo cantidades, sin datos clínicos).
#   5. Dispositivos: nombre, estado, identificador, código y quién lo registró en esa institución.
# Si una sección no tiene datos, sale con sus encabezados y una fila vacía. Lo usa solo la administración de la plataforma
# (SUPERVISAR_INSTITUCIONES, con MFA) y cada exportación queda en la auditoría.

import csv
import io
import re
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.device import Device
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.measurement import Measurement
from app.models.user import User
from app.services import dashboard as dashboards
from app.services import device as deviceService
from app.services import institution as institutions
from app.services import quota
from app.services.csvExport import csvDate, csvText
from app.services.exportAudit import auditedExport, rejectExport
from app.services.platformDashboard import _requireSupervision, _rows
from app.utils.timeZone import nowForDb

EXPORT_TIPO_DATOS = "INSTITUCION_INFORME_PLATAFORMA"
_ESTADO_INSTITUCION = {"ACTIVA": "Activa", "INACTIVA": "Pausada", "CERRADA": "Cerrada"}
_ESTADO_DISPOSITIVO = {"OPERATIVO": "Operativo", "EN_MANTENIMIENTO": "En mantenimiento", "FUERA_DE_SERVICIO": "Fuera de servicio",
                       "BAJA": "Descomisionado"}
_ESTADO_RELACION = {"ACTIVO": "Activo", "PENDIENTE": "Pendiente", "BAJA": "Dado de baja"}
MEMBER_COLUMNS = ("Nombre", "Apellido", "Correo electrónico", "Inicio", "Fin", "Estado")
DEVICE_COLUMNS = ("Nombre", "Estado", "Identificador", "Código", "Registrado por")


def _text(value) -> str:
    return csvText(value or "")


def _memberRows(db: Session, idInstitucion, rol: str) -> tuple[list, int]:
    """Filas de moderadores u operadores (todos los vínculos) y cuántos están activos."""
    rows = db.execute(
        select(User.nombre, User.apellido, User.correoElectronico, InstitutionUser.fechaIncorporacion, InstitutionUser.fechaBaja,
               InstitutionUser.estadoRelacion)
        .select_from(InstitutionUser).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == rol, User.estado != "ELIMINADO")
        .order_by(InstitutionUser.fechaInvitacion)).all()
    active = sum(1 for r in rows if r.estadoRelacion == "ACTIVO")
    out = [[_text(r.nombre), _text(r.apellido), _text(r.correoElectronico), csvDate(r.fechaIncorporacion), csvDate(r.fechaBaja),
            _ESTADO_RELACION.get(r.estadoRelacion, _text(r.estadoRelacion))] for r in rows]
    return out, active


def _owner(db: Session, idInstitucion) -> tuple[str, str, str]:
    row = db.execute(
        select(User.nombre, User.apellido, User.correoElectronico)
        .select_from(InstitutionUser).join(User, User.idUsuario == InstitutionUser.idUsuarioInvitado)
        .where(InstitutionUser.idInstitucion == idInstitucion, InstitutionUser.rolInstitucion == "PROPIETARIO",
               InstitutionUser.estadoRelacion == "ACTIVO", User.estado != "ELIMINADO")
        .order_by(InstitutionUser.fechaInvitacion)).first()
    if row is None:
        return "", "", ""
    return _text(row.nombre), _text(row.apellido), _text(row.correoElectronico)


def _sections(db: Session, institution: Institution) -> list:
    idInstitucion = institution.idInstitucion
    row = _rows(db, [institution])[0]
    usage = quota.usage(db, idInstitucion)
    ownerName, ownerLast, ownerMail = _owner(db, idInstitucion)
    owner = " ".join(part for part in (ownerName, ownerLast) if part)

    summary = [
        ["Institución", _text(row.nombre)],
        ["Tipo", _text(row.tipoInstitucion)],
        ["Tipo de identificador", _text(institution.tipoIdentificadorLegal)],
        ["Identificador (CUIT)", _text(institution.identificadorLegal)],
        ["Estado", _ESTADO_INSTITUCION.get(row.estado, _text(row.estado))],
        ["Propietario (nombre y apellido)", owner],
        ["Correo del propietario", ownerMail],
        ["Inicio", csvDate(row.fechaInicio)],
        ["Finalización", csvDate(row.fechaFin)],
        ["Cuentas internas", str(row.cuentasInternas)],
        ["Cuentas en uso (cupos utilizados)", str(usage.usuariosActivos)],
        ["Cupos disponibles", str(usage.cuposDisponibles)],
        ["Límite de cuentas", str(usage.capacidadMaximaUsuarios)],
    ]
    moderators, moderatorsActive = _memberRows(db, idInstitucion, "MODERADOR")
    operators, operatorsActive = _memberRows(db, idInstitucion, "OPERADOR")

    devices = db.scalars(select(Device).where(Device.idInstitucionAsignada == idInstitucion)
                         .order_by(Device.codigoDispositivo)).all()
    profiles = dashboards._institutionProfileIds(idInstitucion)
    patients = [[str(institutions._activePatientCount(db, idInstitucion)),
                 str(db.scalar(select(func.count()).select_from(profiles.subquery())) or 0),
                 str(db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion.in_(profiles))) or 0),
                 str(len(devices))]]

    deviceRows = []
    for device in devices:
        registered = deviceService.registration(db, device, idInstitucion)
        by = " ".join(part for part in (registered.nombre, registered.apellido) if part) if registered else ""
        deviceRows.append([_text(device.nombre), _ESTADO_DISPOSITIVO.get(device.estado, _text(device.estado)), str(device.idDispositivo),
                           _text(device.codigoDispositivo), _text(by)])

    return [
        ("Institución", ("Campo", "Valor"), summary),
        (f"Moderadores ({moderatorsActive} activos)", MEMBER_COLUMNS, moderators),
        (f"Operadores ({operatorsActive} activos)", MEMBER_COLUMNS, operators),
        ("Pacientes", ("Pacientes activos", "Pacientes registrados", "Mediciones totales", "Dispositivos"), patients),
        (f"Dispositivos ({len(devices)})", DEVICE_COLUMNS, deviceRows),
    ]


def _filled(columns, rows) -> list:
    return rows if rows else [[""] * len(columns)]


def _csvFile(sections) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    for title, columns, rows in sections:
        writer.writerow([title])
        writer.writerow(columns)
        writer.writerows(_filled(columns, rows))
        writer.writerow([])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _xlsxFile(titulo: str, sections) -> bytes:
    book = Workbook()
    book.properties.creator = "GlucoLume"
    sheet = book.active
    sheet.title = "Informe"
    widths: dict = {}
    row = 1
    sheet.cell(row=row, column=1, value=titulo).font = Font(bold=True, size=13)
    row += 2
    for title, columns, rows in sections:
        sheet.cell(row=row, column=1, value=title).font = Font(bold=True, size=11)
        row += 1
        for index, value in enumerate(columns, start=1):
            cell = sheet.cell(row=row, column=index, value=value)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="B91C1C")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            widths[index] = max(widths.get(index, 0), len(str(value)))
        row += 1
        for values in _filled(columns, rows):
            for index, value in enumerate(values, start=1):
                sheet.cell(row=row, column=index, value=value).alignment = Alignment(vertical="top", wrap_text=True)
                widths[index] = max(widths.get(index, 0), min(len(str(value)), 60))
            row += 1
        row += 1
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = min(max(width + 2, 12), 62)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def _pdfFile(titulo: str, sections, generado) -> bytes:
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=titulo, author="GlucoLume")
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=8, spaceAfter=4)
    story = [Paragraph(escape(titulo), ParagraphStyle("title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14)),
             Paragraph(escape(f"Generado {generado:%d/%m/%Y %H:%M}"), cell), Spacer(1, 4)]
    usable = landscape(A4)[0] - 28 * mm
    for title, columns, rows in sections:
        story.append(Paragraph(escape(title), heading))
        data = [[Paragraph(escape(str(c)), head) for c in columns]]
        data += [[Paragraph(escape(str(v)), cell) for v in values] for values in _filled(columns, rows)]
        table = Table(data, colWidths=[usable / len(columns)] * len(columns), repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8FB")]),
        ]))
        story.append(table)
    doc.build(story)
    return stream.getvalue()


def reportFile(formato: str, nombreBase: str, titulo: str, sections, generado) -> tuple:
    if formato == "csv":
        return _csvFile(sections), nombreBase + ".csv"
    if formato == "xlsx":
        return _xlsxFile(titulo, sections), nombreBase + ".xlsx"
    if formato == "pdf":
        return _pdfFile(titulo, sections, generado), nombreBase + ".pdf"
    raise ValueError(f"Formato de exportación desconocido: {formato}")


def exportInstitutionReport(db: Session, actor, idInstitucion, formato: str = "csv") -> tuple:
    """Informe de una institución (CSV, Excel o PDF) para la administración de la plataforma. Devuelve (contenido, nombre del archivo)."""
    try:
        _requireSupervision(db, actor)
    except AuthError as error:
        rejectExport(db, actor, EXPORT_TIPO_DATOS, ambito="PLATAFORMA", idInstitucion=idInstitucion, formato=formato.upper(), motivo=error.code)
        db.commit()
        raise
    institution = db.get(Institution, idInstitucion)
    if institution is None:
        raise AuthError("INSTITUCION_NO_ENCONTRADA", "No encontramos esa institución.")
    with auditedExport(db, actor, EXPORT_TIPO_DATOS, ambito="PLATAFORMA", idInstitucion=idInstitucion, formato=formato.upper()) as export:
        sections = _sections(db, institution)
        export.registros = sum(len(rows) for _, _, rows in sections)
        now = nowForDb()
        safe = re.sub(r"[^A-Za-z0-9]+", "-", institution.nombre or "institucion").strip("-")[:40] or "institucion"
        return reportFile(formato, f"informe-{safe}-{now:%Y%m%d-%H%M}", f"Informe de {institution.nombre}", sections, now)
