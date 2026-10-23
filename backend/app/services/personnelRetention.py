# PersonnelRetention - Minimización de los datos personales históricos de InstitucionUsuario
#
# InstitucionUsuario conserva, aunque la cuenta se elimine, nombre y apellido profesionales históricos, legajo y matrícula: es información
# personal identificable. Conservarla sirve a una finalidad concreta —que la institución pueda saber quién estuvo vinculado, con qué rol y
# quién realizó cada operación—, pero no por tiempo indefinido. Vencido el plazo de conservación contado desde la BAJA de la relación
# (PERSONNEL_RETENTION_MONTHS; 0 por defecto = desactivado, porque el plazo legal NO está aprobado: 120 meses, alineado con el plazo de las historias
# clínicas del Decreto 1089/2012, es solo una referencia a validar con asesoría legal) se SUPRIMEN esos cuatro datos y se registra
# fechaMinimizacionDatos. Corrida por el servicio «lifecycle» o la línea de comandos (guarded=True) exige además RETENTION_APPROVAL_REFERENCE
# y respeta el tope de volumen (services/retentionGuard.py, H-04).
# La relación no se borra: rol, función, fechas de invitación, incorporación y baja, origen e invitador siguen. La autoría de las
# mediciones sigue resolviéndose por el vínculo, que desde ese momento ya no tiene nombre asociado.
#
# Idempotente: una relación ya minimizada no se vuelve a tocar. Auditoría: un evento por pasada con la cantidad, sin datos personales.

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models.institutionUser import InstitutionUser
from app.services import retentionGuard
from app.services.audit import registerEvent
from app.services.institution import addMonths
from app.utils.timeZone import nowForDb

BATCH = 500
ACCION = "MINIMIZAR_DATOS_PERSONAL_HISTORICO"
ACCION_INICIO = "MINIMIZAR_DATOS_PERSONAL_INICIADA"
ACCION_FALLA = "MINIMIZAR_DATOS_PERSONAL_FALLIDA"
ACCION_OMITIDA = "MINIMIZAR_DATOS_PERSONAL_OMITIDA"


def _expiredConditions(cutoff: datetime) -> tuple:
    return (InstitutionUser.estadoRelacion == "BAJA", InstitutionUser.fechaBaja <= cutoff, InstitutionUser.fechaMinimizacionDatos.is_(None),
            or_(InstitutionUser.nombreProfesionalHistorico.is_not(None), InstitutionUser.apellidoProfesionalHistorico.is_not(None),
                InstitutionUser.legajoInstitucional.is_not(None), InstitutionUser.matriculaProfesional.is_not(None)))


def plan(db: Session, months: int, now: datetime | None = None) -> dict:
    """Qué haría una pasada ahora, SIN modificar nada (simulación): plazo efectivo (0 si falta la aprobación), relaciones a minimizar y si el
    tope de volumen la frenaría. `months` es el plazo configurado."""
    now = now or nowForDb()
    effective = retentionGuard.approvedMonths("PERSONNEL_RETENTION_MONTHS", months)
    withData = db.scalar(select(func.count()).select_from(InstitutionUser).where(
        InstitutionUser.fechaMinimizacionDatos.is_(None),
        or_(InstitutionUser.nombreProfesionalHistorico.is_not(None), InstitutionUser.apellidoProfesionalHistorico.is_not(None),
            InstitutionUser.legajoInstitucional.is_not(None), InstitutionUser.matriculaProfesional.is_not(None)))) or 0
    candidates = (db.scalar(select(func.count()).select_from(InstitutionUser).where(*_expiredConditions(addMonths(now, -effective)))) or 0
                  if effective > 0 else 0)
    return {"relacionesAMinimizar": candidates, "relacionesConDatosPersonales": withData, "plazoMesesEfectivo": effective,
            "plazoMesesConfigurado": months, "aprobacion": retentionGuard.approvalReference(),
            "bloqueadaPorVolumen": retentionGuard.blockedByVolume(candidates, withData)}


def minimizeExpired(db: Session, months: int, now: datetime | None = None, batchSize: int = BATCH, *, guarded: bool = False,
                    confirmed: int | None = None) -> int:
    """Suprime los datos personales históricos de las relaciones dadas de baja hace más de `months` meses. Devuelve la cantidad.

    `guarded` (lo usan el servicio «lifecycle» y la línea de comandos; H-04): exige RETENTION_APPROVAL_REFERENCE y respeta el tope de volumen. Una pasada
    frenada por el tope no suprime nada y deja un evento de omisión; `confirmed` la autoriza si coincide con la cantidad exacta que informó `plan()`."""
    if months <= 0:
        return 0
    now = now or nowForDb()
    if guarded:
        planned = plan(db, months, now)
        if planned["plazoMesesEfectivo"] <= 0 or planned["relacionesAMinimizar"] == 0:
            return 0
        if planned["bloqueadaPorVolumen"]:
            if confirmed is None:
                if retentionGuard.shouldRecordSkip("personal"):
                    registerEvent(db, "CRUD", ACCION_OMITIDA, False, None, "InstitucionUsuario", None, motivo="LIMITE_DE_VOLUMEN",
                                  observacion="La minimización se omitió: alcanzaría más del tope; requiere ejecución manual confirmada.",
                                  datosNuevos={"previstas": planned["relacionesAMinimizar"], "conDatos": planned["relacionesConDatosPersonales"]})
                    db.commit()
                return 0
            if confirmed != planned["relacionesAMinimizar"]:
                raise ValueError(f"La cantidad confirmada ({confirmed}) no coincide con la actual ({planned['relacionesAMinimizar']}): "
                                 "no se suprimió nada. Volvé a previsualizar.")
        registerEvent(db, "CRUD", ACCION_INICIO, True, None, "InstitucionUsuario", None,
                      datosNuevos={"previstas": planned["relacionesAMinimizar"], "plazoMeses": months, "aprobacion": planned["aprobacion"],
                                   "confirmadaALaMano": confirmed is not None})
        db.commit()
    cutoff = addMonths(now, -months)
    total = 0
    try:
        while True:
            ids = db.scalars(select(InstitutionUser.idInstitucionUsuario).where(*_expiredConditions(cutoff)).limit(batchSize)).all()
            if not ids:
                break
            db.execute(
                update(InstitutionUser)
                .where(InstitutionUser.idInstitucionUsuario.in_(ids), InstitutionUser.fechaMinimizacionDatos.is_(None))
                .values(nombreProfesionalHistorico=None, apellidoProfesionalHistorico=None, legajoInstitucional=None,
                        matriculaProfesional=None, fechaMinimizacionDatos=now)
                .execution_options(synchronize_session=False)
            )
            db.commit()
            total += len(ids)
    except Exception as error:
        db.rollback()
        if guarded:
            registerEvent(db, "CRUD", ACCION_FALLA, False, None, "InstitucionUsuario", None, motivo="ERROR_INTERNO",
                          observacion=f"La minimización se interrumpió ({type(error).__name__}); lo ya suprimido no se revierte.",
                          datosNuevos={"relacionesMinimizadas": total, "plazoMeses": months})
            db.commit()
        raise
    if total:
        data = {"relacionesMinimizadas": total, "plazoMeses": months}
        if guarded:
            data["aprobacion"] = retentionGuard.approvalReference()
        registerEvent(db, "CRUD", ACCION, True, None, "InstitucionUsuario", None, datosNuevos=data)
        db.commit()
    return total
