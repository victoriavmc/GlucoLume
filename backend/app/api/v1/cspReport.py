# CspReport - Recepción de reportes de incumplimiento de CSP (B-7, auditoría 07/11/2026).
#
# Ruta pública (sin sesión, sin cookies): el navegador la llama cuando la CSP de la app bloquea algo (report-uri). Responde siempre 204,
# con o sin reporte válido, para no servir de oráculo. Límite de tamaño en Nginx (8 KB) y aquí; límite por IP (rateLimit "cspReport").
# La sanitización y el formato del log están en services/cspReports.py.

from fastapi import APIRouter, Request, Response

from app.api.rateLimit import rateLimit
from app.services import cspReports

router = APIRouter(prefix="/security", tags=["security"], include_in_schema=False)


@router.post("/csp-report", status_code=204, dependencies=[rateLimit("cspReport")])
async def receiveCspReport(request: Request) -> Response:
    if int(request.headers.get("content-length", "0") or 0) > cspReports.MAX_BODY_BYTES:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})  # ni se lee el cuerpo
    cuerpo = await request.body()
    tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
    cspReports.registrar(cspReports.parsear(cuerpo, tipo))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
