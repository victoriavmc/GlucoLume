# PersonnelRetention - Minimización de los datos personales históricos de InstitucionUsuario
#
# InstitucionUsuario conserva, aunque la cuenta se elimine, nombre y apellido profesionales históricos, legajo y matrícula: es información
# personal identificable. Conservarla sirve a una finalidad concreta —que la institución pueda saber quién estuvo vinculado, con qué rol y
# quién realizó cada operación—, pero no por tiempo indefinido. Vencido el plazo de conservación contado desde la BAJA de la relación
# (PERSONNEL_RETENTION_MONTHS; 120 meses por defecto, alineado con el plazo de conservación de historias clínicas del Decreto 1089/2012,
# a confirmar con asesoría legal; 0 desactiva el procedimiento) se SUPRIMEN esos cuatro datos y se registra fechaMinimizacionDatos.
# La relación no se borra: rol, función, fechas de invitación, incorporación y baja, origen e invitador siguen. La autoría de las
# mediciones sigue resolviéndose por el vínculo, que desde ese momento ya no tiene nombre asociado.
#
# Idempotente: una relación ya minimizada no se vuelve a tocar. Auditoría: un evento por pasada con la cantidad, sin datos personales.

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.institutionUser import InstitutionUser
from app.services.audit import registerEvent
from app.services.institution import addMonths
from app.utils.timeZone import nowForDb

BATCH = 500
ACCION = "MINIMIZAR_DATOS_PERSONAL_HISTORICO"


def minimizeExpired(db: Session, months: int, now: datetime | None = None, batchSize: int = BATCH) -> int:
    """Suprime los datos personales históricos de las relaciones dadas de baja hace más de `months` meses. Devuelve la cantidad."""
    if months <= 0:
        return 0
    now = now or nowForDb()
    cutoff = addMonths(now, -months)
    total = 0
    while True:
        ids = db.scalars(
            select(InstitutionUser.idInstitucionUsuario).where(
                InstitutionUser.estadoRelacion == "BAJA", InstitutionUser.fechaBaja <= cutoff,
                InstitutionUser.fechaMinimizacionDatos.is_(None),
                or_(InstitutionUser.nombreProfesionalHistorico.is_not(None), InstitutionUser.apellidoProfesionalHistorico.is_not(None),
                    InstitutionUser.legajoInstitucional.is_not(None), InstitutionUser.matriculaProfesional.is_not(None)),
            ).limit(batchSize)).all()
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
    if total:
        registerEvent(db, "CRUD", ACCION, True, None, "InstitucionUsuario", None,
                      datosNuevos={"relacionesMinimizadas": total, "plazoMeses": months})
        db.commit()
    return total
