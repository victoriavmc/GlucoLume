# InstitutionalRetention - Fin del período de conservación de datos de pacientes institucionales
#
# Al cerrar una institución (o dar de baja un paciente) los datos personales del paciente se conservan 12 meses
# (PerfilMedicion.fechaExpiracionDatosPersonales) sin acceso operativo. Vencido ese plazo se desidentifican de forma
# irreversible: se borran nombre, apellido, documento, fecha de nacimiento y edad declarada, y se registra
# fechaDepuracionDatosPersonales (que satisface CK_PerfilMedicion_datoEdad). Se conservan el seudónimo, sexoModelo
# y las mediciones, que guardan su propia edad al momento: sirven para fines estadísticos sin identificar a nadie.
#
# Con la migración 031 aplicada el paso es más profundo: ANONIMIZACIÓN real (services/measurementRetention.py). Las mediciones se separan de
# la persona (cohorte anónima de la institución, con su fin de conservación sellado), el seudónimo se reemplaza y el perfil queda vacío.
# Sin la 031 se hace lo descrito arriba, que es seudonimización.
#
# Lo ejecuta app/jobs/purgeInstitutionalRetention.py. Auditoría: un evento por ejecución con la cantidad, sin datos.
# Idempotente: un perfil ya depurado no se vuelve a tocar.

import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.measurementProfile import MeasurementProfile
from app.services import measurementRetention
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.jobs")

DEFAULT_BATCH_SIZE = 500


def purgeExpiredPatientData(db: Session, now: datetime | None = None, batchSize: int = DEFAULT_BATCH_SIZE) -> int:
    """Desidentifica los perfiles institucionales cuyo período de conservación venció. Devuelve la cantidad."""
    now = now or nowForDb()
    total = 0
    # Con la migración 031 es anonimización real (measurementRetention); sin ella, la desidentificación de siempre (seudonimización).
    anonymize = measurementRetention.ready(db)
    failed: set = set()  # un perfil que falla se registra y se omite en esta pasada: no frena a los demás; la próxima lo reintenta
    while True:
        conditions = [
            MeasurementProfile.tipoPerfil == "INSTITUCIONAL",
            MeasurementProfile.fechaExpiracionDatosPersonales <= now,
            MeasurementProfile.fechaDepuracionDatosPersonales.is_(None),
        ]
        if failed:
            conditions.append(MeasurementProfile.idPerfilMedicion.not_in(failed))
        ids = db.scalars(select(MeasurementProfile.idPerfilMedicion).where(*conditions).limit(batchSize)).all()
        if not ids:
            break
        if anonymize:
            for idPerfil in list(ids):
                try:
                    measurementRetention.anonymizeProfile(db, idPerfil, now)
                except Exception:  # noqa: BLE001 - se informa y se sigue con el resto
                    db.rollback()
                    failed.add(idPerfil)
                    ids.remove(idPerfil)
                    logger.exception("No se pudo anonimizar el perfil %s; se reintenta en la próxima pasada.", idPerfil)
        else:
            db.execute(
                update(MeasurementProfile)
                .where(MeasurementProfile.idPerfilMedicion.in_(ids), MeasurementProfile.fechaDepuracionDatosPersonales.is_(None))
                .values(nombre=None, apellido=None, dni=None, fechaNacimiento=None, edadDeclarada=None,
                        fechaDepuracionDatosPersonales=now)
                .execution_options(synchronize_session=False)
            )
        db.commit()
        total += len(ids)
    if total:
        if anonymize:
            registerEvent(db, "CRUD", measurementRetention.ACCION_ANONIMIZAR, True, None, "PerfilMedicion", None,
                          datosNuevos={"perfilesAnonimizados": total})
        else:
            registerEvent(db, "CRUD", "DEPURAR_DATOS_PACIENTES", True, None, "PerfilMedicion", None,
                          datosNuevos={"perfilesDesidentificados": total})
        db.commit()
    return total
