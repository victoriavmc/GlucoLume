# Matrices - Rutas del módulo de matrices de estimación (/api/v1/matrices)
#
# Solo traduce HTTP <-> servicios. La autorización por ámbito (cuentas de plataforma para las globales; propietario
# y moderador de la institución para las suyas), el estado de la versión y la validación de las reglas viven en
# backend/app/services/matrix.py. El resumen por institución está en /institutions/{id}/matrices.

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentAuth, DbSession, PlatformMfaGate
from app.schemas.matrix import (
    MatrixAuditEntry,
    MatrixCreateRequest,
    MatrixDetail,
    MatrixDraftUpdateRequest,
    MatrixItem,
    MatrixRuleInput,
    MatrixRulesCheckRequest,
    MatrixRuleUpdateRequest,
    MatrixValidation,
)
from app.services import matrix as matrixService

router = APIRouter(prefix="/matrices", tags=["matrices"], dependencies=[PlatformMfaGate])


@router.get("/global", response_model=list[MatrixItem], summary="Matrices globales",
            description="Solo MODERADOR_PLATAFORMA y ADMINISTRADOR_PLATAFORMA. Todas las versiones, la más reciente primero.")
def listGlobal(auth: CurrentAuth, db: DbSession):
    return matrixService.listGlobal(db, auth.user)


@router.post("/check-rules", response_model=MatrixValidation, summary="Revisar reglas antes de guardar una matriz",
             description="Devuelve los problemas (sin reglas, duplicadas, solapadas) y las advertencias de cobertura de un conjunto "
             "de reglas todavía sin guardar. No persiste nada. Propietario o moderador de alguna institución, o la plataforma.")
def checkRules(data: MatrixRulesCheckRequest, auth: CurrentAuth, db: DbSession):
    return matrixService.checkRules(db, auth.user, data.reglas)


@router.post("", response_model=MatrixDetail, status_code=status.HTTP_201_CREATED, summary="Crear una matriz",
             description="Global: cuentas de plataforma. Institucional: propietario o moderador de esa institución. "
             "Se crea en BORRADOR con la versión que asigna el servidor, con las `reglas` enviadas (todo o nada: una regla "
             "inválida, duplicada o solapada impide crear la matriz). Crear no activa: la activación es otra operación.")
def createMatrix(data: MatrixCreateRequest, auth: CurrentAuth, db: DbSession):
    return matrixService.createMatrix(db, auth.user, data)


@router.get("/{idMatriz}", response_model=MatrixDetail, summary="Detalle de una matriz con sus reglas",
            description="404 si la cuenta no puede ver esa matriz (incluida la privada de otra institución).")
def getMatrix(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.getMatrix(db, auth.user, idMatriz)


@router.patch("/{idMatriz}", response_model=MatrixDetail, summary="Modificar los datos de un borrador",
              description="Solo BORRADOR (409 `MATRIZ_NO_EDITABLE` si ya se usó o se activó).")
def updateDraft(idMatriz: uuid.UUID, data: MatrixDraftUpdateRequest, auth: CurrentAuth, db: DbSession):
    return matrixService.updateDraft(db, auth.user, idMatriz, data)


@router.post("/{idMatriz}/new-version", response_model=MatrixDetail, status_code=status.HTTP_201_CREATED,
             summary="Crear una versión nueva a partir de otra",
             description="Copia las reglas en un BORRADOR nuevo; la versión original no cambia.")
def newVersion(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.newVersion(db, auth.user, idMatriz)


@router.post("/{idMatriz}/validate", response_model=MatrixValidation, summary="Validar las reglas de la matriz",
             description="Devuelve los problemas (sin reglas, duplicadas, solapadas, incoherentes) sin modificar nada.")
def validateMatrix(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.validateMatrix(db, auth.user, idMatriz)


@router.post("/{idMatriz}/activate", response_model=MatrixDetail, summary="Activar una versión",
             description="Transaccional: la activa del mismo ámbito pasa a INACTIVA. Exige una matriz válida y vigente.")
def activate(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.activate(db, auth.user, idMatriz)


@router.post("/{idMatriz}/deactivate", response_model=MatrixDetail, summary="Desactivar la versión activa")
def deactivate(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.deactivate(db, auth.user, idMatriz)


@router.post("/{idMatriz}/archive", response_model=MatrixDetail, summary="Archivar una versión",
             description="Solo un borrador o una versión inactiva. Se conserva para la trazabilidad; no se borra.")
def archive(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.archive(db, auth.user, idMatriz)


@router.post("/{idMatriz}/export", response_class=Response, summary="Exportar la matriz con sus reglas (CSV)",
             description="Quien puede ver la matriz: la plataforma (globales); el propietario y el moderador de la institución (las suyas y "
             "la global activa). Un operador u otra institución recibe 404 y el intento queda en la auditoría de exportaciones. Una fila "
             "por regla. Cada exportación queda registrada.")
def exportMatrix(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    content, filename = matrixService.exportMatrix(db, auth.user, idMatriz)
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/{idMatriz}/audit", response_model=list[MatrixAuditEntry], summary="Auditoría de la matriz",
            description="Global: solo cuentas de plataforma. Institucional: solo el PROPIETARIO (el moderador puede "
            "modificar pero no auditar).")
def audit(idMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.auditTrail(db, auth.user, idMatriz)


@router.post("/{idMatriz}/rules", response_model=MatrixDetail, status_code=status.HTTP_201_CREATED,
             summary="Agregar una regla a un borrador",
             description="Valida los rangos y rechaza duplicadas (`REGLA_DUPLICADA`) y solapadas (`REGLA_SOLAPADA`).")
def addRule(idMatriz: uuid.UUID, data: MatrixRuleInput, auth: CurrentAuth, db: DbSession):
    return matrixService.addRule(db, auth.user, idMatriz, data)


@router.patch("/{idMatriz}/rules/{idReglaMatriz}", response_model=MatrixDetail, summary="Modificar una regla de un borrador")
def updateRule(idMatriz: uuid.UUID, idReglaMatriz: uuid.UUID, data: MatrixRuleUpdateRequest, auth: CurrentAuth,
               db: DbSession):
    return matrixService.updateRule(db, auth.user, idMatriz, idReglaMatriz, data)


@router.delete("/{idMatriz}/rules/{idReglaMatriz}", response_model=MatrixDetail, summary="Eliminar una regla de un borrador")
def deleteRule(idMatriz: uuid.UUID, idReglaMatriz: uuid.UUID, auth: CurrentAuth, db: DbSession):
    return matrixService.deleteRule(db, auth.user, idMatriz, idReglaMatriz)
