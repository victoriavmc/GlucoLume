# Retention - Simulación y ejecución manual de la conservación de la auditoría y del personal histórico (H-04)
#
# El servicio «lifecycle» aplica estas políticas solo si están aprobadas (RETENTION_APPROVAL_REFERENCE) y respetando el tope de volumen
# (services/retentionGuard.py). Esta herramienta sirve para REVISARLAS antes de habilitarlas y para ejecutar a mano una pasada que el tope frenó:
#
#     python -m app.jobs.retention previsualizar
#         Solo lectura: plazos configurados y efectivos, aprobación, cantidades que se eliminarían/suprimirían y si el tope las frenaría.
#     python -m app.jobs.retention ejecutar --confirmo-base <DB_NAME> --confirmo-eventos <N> --confirmo-personal <M>
#         Ejecuta UNA pasada de ambas políticas. Exige nombrar la base y confirmar EXACTAMENTE las cantidades de «previsualizar»: si cambiaron,
#         no se toca nada. Sin aprobación (RETENTION_APPROVAL_REFERENCE) los plazos destructivos no se aplican ni aquí.
#
# No inventa plazos: usa AUDIT_RETENTION_MONTHS y PERSONNEL_RETENTION_MONTHS tal como están configurados (0 = desactivado). Usa la cuenta de base
# de los procesos de conservación (DB_JOBS_USER) si está configurada. No programa nada.

import argparse
import json
import logging
import sys

from app.core.config import getSettings
from app.db.session import getJobsSessionFactory
from app.services import auditRetention, personnelRetention
from app.utils.timeZone import nowForDb


def report(db) -> dict:
    settings = getSettings()
    audit = auditRetention.plan(db)
    personnel = personnelRetention.plan(db, settings.PERSONNEL_RETENTION_MONTHS)
    return {"simulacion": True, "aprobacion": settings.RETENTION_APPROVAL_REFERENCE, "auditoria": audit, "personal": personnel}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Conservación de la auditoría y del personal histórico: simulación y ejecución manual.")
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("previsualizar", help="Solo lectura: qué haría una pasada ahora.")
    run = sub.add_parser("ejecutar", help="Ejecuta una pasada confirmando las cantidades.")
    run.add_argument("--confirmo-base", default=None, help="Nombre exacto de la base configurada (DB_NAME).")
    run.add_argument("--confirmo-eventos", type=int, default=None, help="Eventos de auditoría a eliminar, como los informó previsualizar.")
    run.add_argument("--confirmo-personal", type=int, default=None, help="Relaciones a minimizar, como las informó previsualizar.")
    args = parser.parse_args(argv)

    settings = getSettings()
    with getJobsSessionFactory()() as db:
        current = report(db)
        if args.orden == "previsualizar":
            print(json.dumps(current, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.confirmo_base != settings.DB_NAME:
            print("No se modificó nada: --confirmo-base debe ser el nombre exacto de la base configurada.", file=sys.stderr)
            return 2
        events, people = current["auditoria"]["eventosAEliminar"], current["personal"]["relacionesAMinimizar"]
        if (args.confirmo_eventos, args.confirmo_personal) != (events, people):
            print(f"No se modificó nada: las cantidades confirmadas deben coincidir con las actuales ({events} eventos, {people} relaciones). "
                  "Corré previsualizar y revisá.", file=sys.stderr)
            return 2
        if not settings.RETENTION_APPROVAL_REFERENCE and (settings.AUDIT_RETENTION_MONTHS or settings.PERSONNEL_RETENTION_MONTHS):
            print("Aviso: sin RETENTION_APPROVAL_REFERENCE los plazos AUDIT_RETENTION_MONTHS y PERSONNEL_RETENTION_MONTHS no se aplican.", file=sys.stderr)
        logging.basicConfig(level=logging.INFO)
        try:
            audit = auditRetention.run(db, nowForDb(), confirmedDeletions=events if events else None)
            minimized = personnelRetention.minimizeExpired(db, settings.PERSONNEL_RETENTION_MONTHS, guarded=True,
                                                           confirmed=people if people else None)
        except ValueError as error:
            print(f"No se modificó nada más: {error}", file=sys.stderr)
            return 2
        print(json.dumps({"auditoria": audit, "relacionesMinimizadas": minimized}, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
