# Contact - Ruta pública del formulario de contacto (/api/v1/contact)

from fastapi import APIRouter, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.rateLimit import normalizeIp
from app.schemas.contact import ContactRequest, ContactResponse
from app.services import contact as contactService

router = APIRouter(prefix="/contact", tags=["contact"])


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar una consulta desde el formulario de contacto de la landing",
    description=(
        "Público (sin sesión). Envía la consulta por correo a `CONTACT_EMAIL` (From la cuenta SMTP de GlucoLume, "
        "Reply-To el `email` de la persona) y después una confirmación automática a ese `email`. Si la consulta llega "
        "pero falla la confirmación, la respuesta sigue siendo exitosa con `confirmacionEnviada: false`. "
        "422 si los datos no son válidos; 503 si la consulta no pudo enviarse (la causa queda en el log del backend); "
        "429 tras 5 consultas en 15 minutos por IP. `sitioWeb` es un campo trampa que debe quedar vacío."
    ),
)
async def sendContact(data: ContactRequest, request: Request):
    clientIp = normalizeIp(request.client.host if request.client else None)  # IPv6 agrupada por /64
    # SMTP es bloqueante: se ejecuta fuera del event loop.
    confirmed = await run_in_threadpool(contactService.sendContactMessage, data, clientIp)
    return ContactResponse(mensaje="Consulta enviada correctamente.", confirmacionEnviada=confirmed)
