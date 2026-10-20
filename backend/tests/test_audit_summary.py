# Pruebas del resumen de la auditoría: los contadores salen de los mismos filtros, ámbito y período que el listado, y la consulta
# del resumen es válida en SQL Server (los tests corren en SQLite, que acepta lo que SQL Server rechaza).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_audit_summary.py -v

from sqlalchemy import select
from sqlalchemy.dialects.mssql import dialect as mssqlDialect

from app.models.audit import Audit
from app.services import auditQuery
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import admin  # noqa: F401 - fixture
from tests.test_institutions import freshLookupLimiter, institutional, relationOf, team  # noqa: F401


def test_el_resumen_por_modulo_no_agrupa_por_una_expresion_con_parametros():
    """Causa del «0 eventos» en la pantalla: `GROUP BY COALESCE(modulo, ?)` falla en SQL Server (error 8120) porque no la
    reconoce igual a la de la lista de selección. La consulta debe agrupar por la columna sola."""
    base = select(Audit.modulo, Audit.accion).subquery()
    compiled = str(auditQuery._moduleCountsQuery(base).compile(dialect=mssqlDialect()))
    groupBy = compiled.split("GROUP BY", 1)[1]
    assert "?" not in groupBy and "%(" not in groupBy and "coalesce" not in groupBy.lower()


def test_los_contadores_y_el_listado_coinciden_con_los_mismos_filtros(db, mails, team):
    page = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100)
    summary = auditQuery.summaryInstitution(db, team.owner, team.id)
    assert page.total > 0 and summary.total == page.total  # lo que cuenta el resumen es lo que lista la tabla
    assert summary.exitosos + summary.fallidos == summary.total
    assert sum(item.total for item in summary.porModulo) == summary.total
    for filters in ({"modulo": "INSTITUCIONES"}, {"resultado": "EXITO"}, {"resultado": "FALLO"}, {"critica": True},
                    {"accion": "CREAR"}, {"modulo": "INSTITUCIONES", "resultado": "EXITO"}):
        listed = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=1, **filters)
        counted = auditQuery.summaryInstitution(db, team.owner, team.id, **filters)
        assert counted.total == listed.total, filters
    # La paginación no cambia el total: el contador no sale de la página visible.
    small = auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=1)
    assert small.total == summary.total and len(small.items) == 1


def test_un_evento_sin_modulo_se_cuenta_como_sistema_y_la_suma_cierra(db, mails, team):
    first = db.scalar(select(Audit).where(Audit.idInstitucion == team.id))
    first.modulo = None
    db.commit()
    summary = auditQuery.summaryInstitution(db, team.owner, team.id)
    assert "SISTEMA" in {item.clave for item in summary.porModulo}
    assert sum(item.total for item in summary.porModulo) == summary.total


def test_los_nombres_y_valores_del_detalle_son_legibles(db, mails, team):
    invitation = next(a for a in auditQuery.listInstitution(db, team.owner, team.id, accion="INVIT", tamanioPagina=100).items)
    assert invitation.accionEtiqueta  # nombre funcional, no el código
    for item in auditQuery.listInstitution(db, team.owner, team.id, tamanioPagina=100).items:
        if item.accion in auditQuery.ACTION_LABELS:
            assert item.accionEtiqueta == auditQuery.ACTION_LABELS[item.accion]
    assert auditQuery._plainValue("estadoRelacion", "PENDIENTE").texto == "Pendiente"
    assert auditQuery._plainValue("rolInstitucion", "MODERADOR").texto == "Moderador/a"
    assert auditQuery._plainValue("campoNuevo", "VALOR_RARO").texto == "VALOR_RARO"  # desconocido: tal cual, sin inventar
    assert auditQuery._plainValue("registroAutomatico", True).texto == "Sí"
    assert auditQuery._humanize("fechaUltimaReapertura") == "Fecha ultima reapertura"


def test_un_valor_ausente_se_distingue_de_uno_vacio_y_de_un_valor_real():
    nothing = auditQuery._plainValue("rolInstitucion", None)
    assert (nothing.texto, nothing.ausente) == ("Sin rol", True)
    assert auditQuery._plainValue("estadoRelacion", None).texto == "Sin estado"
    assert auditQuery._plainValue("campoCualquiera", None).texto == "Sin valor"
    empty = auditQuery._plainValue("nombre", "   ")
    assert (empty.texto, empty.ausente) == ("Vacío", True)
    real = auditQuery._plainValue("estadoRelacion", "ACTIVO")
    assert (real.texto, real.ausente) == ("Activo", False)  # nunca el código interno si hay etiqueta


def test_el_detalle_de_aceptar_una_invitacion_muestra_sin_rol_sin_estado_y_las_etiquetas(db, mails, team):
    """Caso real: el evento guarda solo los valores nuevos {rolInstitucion: MODERADOR, estadoRelacion: ACTIVO}."""
    page = auditQuery.listInstitution(db, team.owner, team.id, accion="ACEPTAR_INVITACION", tamanioPagina=50)
    assert page.items
    detail = auditQuery.detailInstitution(db, team.owner, team.id, page.items[0].idAuditoria)
    byField = {c.campo: c for c in detail.cambios}
    assert byField["rolInstitucion"].anterior.texto == "Sin rol"
    assert byField["rolInstitucion"].nuevo.texto in ("Moderador/a", "Operador/a")  # etiqueta, no MODERADOR/OPERADOR
    assert byField["estadoRelacion"].anterior.texto == "Sin estado" and byField["estadoRelacion"].nuevo.texto == "Activo"
    assert byField["rolInstitucion"].anterior.ausente and byField["estadoRelacion"].anterior.ausente
    # El registro original no se toca: los valores crudos siguen siendo los códigos.
    assert detail.valoresNuevos["estadoRelacion"] == "ACTIVO" and detail.valoresPrevios is None
