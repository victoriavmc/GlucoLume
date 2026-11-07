# Health - Readiness de la API (B-6, auditoría 07/11/2026). El liveness es /healthz (app/main.py) y no cambia.
#
# La ruta es síncrona a propósito: la comprobación puede esperar hasta PROBE_TIMEOUT_SECONDS a la base, y en el event loop eso
# congelaría todas las peticiones. Como `def`, FastAPI la corre en el threadpool.
#
# Respuestas: 200 {"estado":"listo"} si todas las dependencias están bien; 503 {"estado":"no_listo"} con Retry-After si no. El cuerpo
# lista solo valores enumerados por dependencia (ok, no_disponible, no_verificado, tiempo_agotado).

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import readiness

router = APIRouter(include_in_schema=False)


@router.get("/readyz")
def readyz() -> JSONResponse:
    estado = readiness.snapshot()
    cuerpo = {"estado": "listo" if estado["listo"] else "no_listo", "dependencias": estado["dependencias"]}
    headers = {"Cache-Control": "no-store"}
    if estado["listo"]:
        return JSONResponse(cuerpo, status_code=200, headers=headers)
    headers["Retry-After"] = str(readiness.RETRY_AFTER_SECONDS)
    return JSONResponse(cuerpo, status_code=503, headers=headers)
