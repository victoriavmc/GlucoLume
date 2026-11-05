# Medición temporal (no versionada): consultas SQL y contadores del dashboard del operador con el escenario del panel.
import json
import os
from sqlalchemy import event

from app.services import dashboard as dashboards
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_operator_panel import panel, scene  # noqa: F401
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import device  # noqa: F401
from tests.test_dashboards import institutionData, measure  # noqa: F401


def _count(engine, action):
    statements = []

    def counter(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", counter)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    return result, len(statements)


def test_medir_dashboard_operador(db, scene, engine):
    team = scene["team"]
    op = team.operator
    panelWithoutCharts = lambda: dashboards.operatorDashboard(db, op, team.id, "me", incluirGraficos=False)  # noqa: E731
    panelWithCharts = lambda: dashboards.operatorDashboard(db, op, team.id, "me")  # noqa: E731
    panelWithoutCharts()  # calentamiento
    a, consultasSinGraficos = _count(engine, panelWithoutCharts)
    b, consultasConGraficos = _count(engine, panelWithCharts)
    out = {
        "consultasSinGraficos": consultasSinGraficos,
        "consultasConGraficos": consultasConGraficos,
        "medicionesRealizadas": a.medicionesRealizadas,
        "medicionesEnPeriodo": a.medicionesEnPeriodo,
        "medicionesPorEstado": dict(sorted(a.medicionesPorEstado.items())),
        "medicionesRealizadasDemo": a.medicionesRealizadasDemo,
        "medicionesEnPeriodoDemo": a.medicionesEnPeriodoDemo,
        "medicionesEnPeriodoSinResultado": a.medicionesEnPeriodoSinResultado,
        "medicionesSinResultado": a.medicionesSinResultado,
        "realizadas": len(a.realizadas),
        "ultimasDePacientes": len(a.ultimasDePacientes),
        "pacientes": len(a.pacientes),
        "ultimaActividadDia": a.ultimaActividad.date().isoformat() if a.ultimaActividad else None,
        "transferencias": a.transferencias.model_dump(),
    }
    with open(os.environ["METRICS_OUT"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, sort_keys=True)
