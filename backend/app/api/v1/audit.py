# Audit - Rutas de consulta de la auditoría (solo lectura)
#   /api/v1/audit                         auditoría general (ADMINISTRADOR_PLATAFORMA): plataforma, instituciones y cuentas individuales
#   /api/v1/institutions/{id}/audit       auditoría de una institución (su PROPIETARIO)
# No existen rutas para crear, modificar ni eliminar eventos: los registran los servicios de cada módulo y su depuración la hace solo la
# política de conservación (services/auditRetention.py), nunca una acción de la interfaz. La autorización real y el filtro por institución
# se resuelven en backend/app/services/auditQuery.py (y en SQL).

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentAuth, DbSession, PlatformMfaGate
from app.schemas.auditLog import (
    AuditAccountHeader,
    AuditAccountOption,
    AuditCount,
    AuditEventDetail,
    AuditPage,
    AuditSummary,
    SecuritySignals,
    TechnicalPage,
    TechnicalSummary,
)
from app.services import auditQuery, technicalAudit

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[PlatformMfaGate])
institutionRouter = APIRouter(prefix="/institutions/{idInstitucion}/audit", tags=["audit"])

Modulo = Literal["CUENTA", "GRUPOS", "INSTITUCIONES", "PERFILES", "MEDICIONES", "DISPOSITIVOS", "MATRICES", "PLATAFORMA",
                 "AUDITORIA", "SEGURIDAD", "SISTEMA"]
Resultado = Literal["EXITO", "FALLO"]
Categoria = Literal["AUTENTICACION", "ACCESOS_FALLIDOS", "CUENTAS", "INSTITUCIONES", "PERMISOS", "EXPORTACIONES", "SEGURIDAD"]
Clasificacion = Literal["INFORMATIVO", "OPERATIVO", "SOSPECHOSO", "CONFIRMADO"]
OrigenActor = Literal["PLATAFORMA", "USUARIO", "SISTEMA"]


class InstitutionFilters(BaseModel):
    """Filtros comunes. Paginación y filtros se resuelven en SQL Server; el servidor acota el tamaño de página."""

    # Un parámetro desconocido se ignora (como en cualquier otra ruta): el ámbito de una institución sale de la ruta, nunca de la consulta.
    usuario: Annotated[str | None, Field(max_length=100)] = None
    modulo: Modulo | None = None
    accion: Annotated[str | None, Field(max_length=50)] = None
    categoria: Categoria | None = None
    clasificacion: Clasificacion | None = None
    origenActor: OrigenActor | None = None
    motivo: Annotated[str | None, Field(max_length=40)] = None
    resultado: Resultado | None = None
    desde: date | None = None
    hasta: date | None = None
    critica: bool | None = None


class GlobalFilters(InstitutionFilters):
    """Además, los que solo tiene la administración: institución, cuenta involucrada, identificador probado y datos de red."""

    idInstitucion: uuid.UUID | None = None
    idCuenta: uuid.UUID | None = None
    identificador: Annotated[str | None, Field(max_length=254)] = None
    idCorrelacion: Annotated[str | None, Field(max_length=64)] = None
    ip: Annotated[str | None, Field(max_length=45)] = None
    refIdentificador: Annotated[str | None, Field(max_length=32)] = None


class Paging(BaseModel):
    pagina: Annotated[int, Field(ge=1)] = 1
    tamanioPagina: Annotated[int, Field(ge=1, le=auditQuery.MAX_PAGE_SIZE)] = 25


class GlobalListQuery(GlobalFilters, Paging):
    pass


class InstitutionListQuery(InstitutionFilters, Paging):
    pass


class SignalsQuery(BaseModel):
    desde: date | None = None
    hasta: date | None = None
    idInstitucion: uuid.UUID | None = None
    ventanaMinutos: Annotated[int | None, Field(ge=1, le=1440)] = None
    fallosPorCuenta: Annotated[int | None, Field(ge=2, le=1000)] = None
    cuentasPorOrigen: Annotated[int | None, Field(ge=2, le=1000)] = None
    historialOrigenInusual: Annotated[int | None, Field(ge=1, le=1000)] = None


PAGING = {"pagina", "tamanioPagina"}


@router.get("", response_model=AuditPage, summary="Auditoría general",
            description="Solo ADMINISTRADOR_PLATAFORMA (403 para cualquier otra cuenta, que además queda registrado). "
            "Cubre los tres ámbitos: plataforma (sin `idInstitucion` ni `idCuenta`), institución (`idInstitucion`) y cuenta individual (`idCuenta`: "
            "la cuenta como autora o como afectada). Filtros, orden (más reciente primero) y paginación se resuelven en SQL Server. "
            "Devuelve IP, cliente y correlación, que la auditoría de una institución nunca incluye.")
def listGlobal(auth: CurrentAuth, db: DbSession, query: Annotated[GlobalListQuery, Query()]):
    return auditQuery.listGlobal(db, auth.user, pagina=query.pagina, tamanioPagina=query.tamanioPagina,
                                 **query.model_dump(exclude=PAGING))


@router.get("/summary", response_model=AuditSummary, summary="Resumen de la auditoría general",
            description="Total, exitosos, fallidos, operaciones críticas, accesos fallidos, eventos sospechosos y controles activados, y actividad por "
            "módulo y por institución, con los mismos filtros que el listado.")
def summaryGlobal(auth: CurrentAuth, db: DbSession, query: Annotated[GlobalFilters, Query()]):
    return auditQuery.summaryGlobal(db, auth.user, **query.model_dump())


@router.get("/security/signals", response_model=SecuritySignals, summary="Señales de actividad sospechosa",
            description="Solo ADMINISTRADOR_PLATAFORMA. Patrones detectados sobre los accesos fallidos auditados (cuenta atacada repetidamente, un "
            "origen que prueba muchas cuentas, origen inusual) y controles que ya actuaron (bloqueos, límites, ráfagas de rechazos). Los umbrales "
            "salen de la configuración y se pueden ajustar para una consulta. Las señales se calculan en el momento: no son registros de auditoría.")
def securitySignals(auth: CurrentAuth, db: DbSession, query: Annotated[SignalsQuery, Query()]):
    return auditQuery.securitySignals(db, auth.user, **query.model_dump())


@router.get("/institutions", response_model=list[AuditCount], summary="Instituciones para el selector de la auditoría")
def listInstitutions(auth: CurrentAuth, db: DbSession, q: Annotated[str | None, Query(max_length=100)] = None):
    return auditQuery.searchInstitutions(db, auth.user, q)


@router.get("/accounts", response_model=list[AuditAccountOption], summary="Buscar cuentas para auditar",
            description="Solo ADMINISTRADOR_PLATAFORMA. Mínimo 3 caracteres; el correo se devuelve enmascarado.")
def searchAccounts(auth: CurrentAuth, db: DbSession, q: Annotated[str, Query(min_length=3, max_length=100)]):
    return auditQuery.searchAccounts(db, auth.user, q)


@router.get("/accounts/{idUsuario}", response_model=AuditAccountHeader, summary="Ficha de una cuenta para su auditoría",
            description="Solo ADMINISTRADOR_PLATAFORMA. Abrirla queda registrado (CONSULTAR_AUDITORIA_CUENTA). Los eventos de la cuenta se listan con "
            "`GET /audit?idCuenta=`. No incluye mediciones ni datos clínicos.")
def accountHeader(idUsuario: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return auditQuery.accountHeader(db, auth.user, idUsuario)


@router.get("/technical-measurements", response_model=TechnicalPage, summary="Auditoría técnica anonimizada de mediciones",
            description="Solo ADMINISTRADOR_PLATAFORMA. Intentos de medición cancelados, inválidos, abandonados o vencidos, SIN ningún "
            "identificador de usuario, perfil o medición (hora redondeada a la hora en punto). Sirve para analizar la estabilidad del prototipo.")
def listTechnical(auth: CurrentAuth, db: DbSession, desde: date | None = None, hasta: date | None = None,
                  estado: Literal["CANCELADA", "INVALIDA"] | None = None, motivo: str | None = None,
                  pagina: Annotated[int, Query(ge=1)] = 1, tamanioPagina: Annotated[int, Query(ge=1, le=auditQuery.MAX_PAGE_SIZE)] = 25):
    return technicalAudit.listTechnical(db, auth.user, desde=desde, hasta=hasta, estado=estado, motivo=motivo, pagina=pagina,
                                        tamanioPagina=tamanioPagina)


@router.get("/technical-measurements/summary", response_model=TechnicalSummary, summary="Resumen de la auditoría técnica anonimizada")
def summaryTechnical(auth: CurrentAuth, db: DbSession, desde: date | None = None, hasta: date | None = None):
    return technicalAudit.summaryTechnical(db, auth.user, desde=desde, hasta=hasta)


@router.get("/events/{idAuditoria}", response_model=AuditEventDetail, summary="Detalle de un evento")
def detailGlobal(idAuditoria: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return auditQuery.detailGlobal(db, auth.user, idAuditoria)


@institutionRouter.get("", response_model=AuditPage, summary="Auditoría de la institución",
                       description="Solo el PROPIETARIO de la institución (404 si no pertenece; 403 para moderador y "
                       "operador). Devuelve únicamente eventos ocurridos en esa institución, sin los registros internos de la administración y sin IP, "
                       "cliente ni correlación. `origenActor` distingue al personal de la institución de la administración de GlucoLume.")
def listInstitution(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, query: Annotated[InstitutionListQuery, Query()]):
    return auditQuery.listInstitution(db, auth.user, idInstitucion, pagina=query.pagina, tamanioPagina=query.tamanioPagina,
                                      **query.model_dump(exclude=PAGING))


@institutionRouter.get("/summary", response_model=AuditSummary, summary="Resumen de la auditoría de la institución")
def summaryInstitution(idInstitucion: uuid.UUID, auth: CurrentAuth, db: DbSession, query: Annotated[InstitutionFilters, Query()]):
    return auditQuery.summaryInstitution(db, auth.user, idInstitucion, **query.model_dump())


@institutionRouter.get("/events/{idAuditoria}", response_model=AuditEventDetail, summary="Detalle de un evento de la institución",
                       description="404 si el evento no pertenece a esta institución.")
def detailInstitution(idInstitucion: uuid.UUID, idAuditoria: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return auditQuery.detailInstitution(db, auth.user, idInstitucion, idAuditoria)
