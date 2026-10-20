# ExportAudit - Auditoría obligatoria de las exportaciones de datos
#
# HOY GlucoLume no tiene ninguna función que exporte datos (ni CSV, ni PDF, ni descarga masiva): no hay nada que auditar y por eso la
# auditoría no muestra exportaciones inventadas. Este módulo es el punto único por el que DEBE pasar cualquier exportación futura, para que
# no pueda existir una sin evento:
#
#     with auditedExport(db, actor, "MEDICIONES_PACIENTE", ambito="INSTITUCION", idInstitucion=idInstitucion, formato="CSV") as export:
#         rows = buildRows(...)
#         export.registros = len(rows)
#         return render(rows)
#
# Deja tres tipos de evento, ligados por el mismo `idExportacion` (y por el identificador de correlación de la solicitud):
#   EXPORTACION_SOLICITADA   la exportación se aceptó y empieza.
#   EXPORTACION_COMPLETADA   terminó; guarda cuántos registros salieron.
#   EXPORTACION_FALLIDA      se rechazó (permiso) o falló; guarda un motivo normalizado.
# El evento guarda quién la pidió, el ámbito, el tipo de información y el resultado. NUNCA el contenido exportado ni los filtros con datos
# personales: solo el tipo de datos, el formato y la cantidad de registros.
#
# La autorización de la exportación es del llamador (este módulo no decide quién puede exportar), pero un rechazo se registra con
# `rejectExport` para que el intento quede en la auditoría.

import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.models.user import User
from app.services import auditClassification as classification
from app.services import institution as institutions
from app.services.audit import registerEvent, registerFailure

AMBITOS = ("PLATAFORMA", "INSTITUCION", "CUENTA")
_MODULO_POR_AMBITO = {"PLATAFORMA": "PLATAFORMA", "INSTITUCION": "INSTITUCIONES", "CUENTA": "CUENTA"}


@dataclass
class ExportHandle:
    idExportacion: uuid.UUID
    tipoDatos: str
    ambito: str
    formato: str | None
    registros: int | None = None


def _data(handle: ExportHandle, **extra) -> dict:
    return {"idExportacion": str(handle.idExportacion), "tipoDatos": handle.tipoDatos, "ambito": handle.ambito, "formato": handle.formato, **extra}


def _check(tipoDatos: str, ambito: str) -> None:
    if ambito not in AMBITOS:
        raise ValueError(f"Ámbito de exportación desconocido: {ambito}")
    if not tipoDatos or len(tipoDatos) > 60:
        raise ValueError("Hay que indicar el tipo de datos exportado (hasta 60 caracteres).")


def failureReason(error: BaseException) -> str:
    """Motivo normalizado de una exportación fallida: el código de un AuthError o ERROR_INTERNO. Nunca el mensaje de la excepción (puede traer
    fragmentos de consultas, rutas o datos)."""
    return error.code if isinstance(error, AuthError) else "ERROR_INTERNO"


@contextmanager
def auditedExport(db: Session, actor: User, tipoDatos: str, *, ambito: str, idInstitucion: uuid.UUID | None = None, formato: str | None = None):
    _check(tipoDatos, ambito)
    # Una institución pausada o cerrada no exporta nada, ni siquiera con un permiso válido: el estado vigente manda (institution.isOperating).
    if ambito == "INSTITUCION" and idInstitucion is not None and not institutions.isOperating(db, idInstitucion):
        rejectExport(db, actor, tipoDatos, ambito=ambito, idInstitucion=idInstitucion, formato=formato, motivo="INSTITUCION_PAUSADA")
        db.commit()
        raise AuthError("INSTITUCION_PAUSADA", institutions.PAUSED_MESSAGE)
    handle = ExportHandle(uuid.uuid4(), tipoDatos, ambito, formato)
    modulo = _MODULO_POR_AMBITO[ambito]
    registerEvent(db, "ACCESO", classification.ACCION_EXPORT_SOLICITADA, True, actor.idUsuario, idInstitucion=idInstitucion, modulo=modulo,
                  datosNuevos=_data(handle))
    db.commit()
    try:
        yield handle
    except BaseException as error:  # incluye cortes de la solicitud: una exportación que no terminó no puede figurar como completada
        reason = failureReason(error)
        registerFailure(db, "ACCESO", classification.ACCION_EXPORT_FALLIDA, actor.idUsuario, idInstitucion=idInstitucion, modulo=modulo,
                        motivo=reason, observacion=f"Motivo: {reason}", datosNuevos=_data(handle))
        raise
    registerEvent(db, "ACCESO", classification.ACCION_EXPORT_COMPLETADA, True, actor.idUsuario, idInstitucion=idInstitucion, modulo=modulo,
                  datosNuevos=_data(handle, cantidadRegistros=handle.registros))
    db.commit()


def rejectExport(db: Session, actor: User, tipoDatos: str, *, ambito: str, idInstitucion: uuid.UUID | None = None, formato: str | None = None,
                 motivo: str = "PERMISO_INSUFICIENTE") -> None:
    """Registra una exportación rechazada antes de empezar (p. ej. sin permiso): el intento queda como EXPORTACION_FALLIDA."""
    _check(tipoDatos, ambito)
    handle = ExportHandle(uuid.uuid4(), tipoDatos, ambito, formato)
    registerFailure(db, "ACCESO", classification.ACCION_EXPORT_FALLIDA, actor.idUsuario, idInstitucion=idInstitucion,
                    modulo=_MODULO_POR_AMBITO[ambito], motivo=motivo, observacion=f"Motivo: {motivo}", datosNuevos=_data(handle))
