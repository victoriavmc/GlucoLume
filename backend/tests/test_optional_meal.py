# «Última comida» es opcional en TODOS los modos y para todos los perfiles (usuario individual e institucional): vacía no bloquea, informada se conserva.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_optional_meal.py -v

from datetime import timedelta

from app.schemas.measurement import MeasurementFinish, MeasurementStart
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, reload  # noqa: F401
from tests.test_institution_patients import patientData
from tests.test_institutions import expectError, freshLookupLimiter, team  # noqa: F401
from tests.test_measurements import addMatrix, device, samples  # noqa: F401


def start(db, actor, profile, dev, mode, deviceSession=False, **extra):
    return measurements.startMeasurement(db, actor, MeasurementStart(
        idPerfilMedicion=profile, idDispositivo=dev.idDispositivo, modoMedicion=mode, **extra), deviceSession=deviceSession)


def test_paciente_institucional_inicia_y_finaliza_sin_ultima_comida_en_todos_los_modos(db, team):
    dev = device(db, institucion=team.id)
    patient = patients.createPatient(db, team.operator, team.id, patientData(nombre="rosa", apellido="díaz", sexoModelo="masculino"))
    addMatrix(db, ambito="INSTITUCION", idInstitucion=team.id, sexo="MASCULINO", condicion="POSTPRANDIAL", minutos=(30, 180))
    # Oximetría sin comida, con «Después de comer» y sin hora: nunca bloquea.
    for food in ("NO_INFORMADA", "AYUNO", "POSTPRANDIAL"):
        oxi = start(db, team.operator, patient.idPerfilMedicion, dev, "OXIMETRIA", condicionComida=food)
        assert oxi.fechaHoraUltimaComida is None and oxi.condicionComida == food
    # Glucosa experimental «Después de comer» sin hora: inicia, guarda NULL y la estimación queda no disponible, explicada.
    glucose = start(db, team.operator, patient.idPerfilMedicion, dev, "GLUCOSA_EXPERIMENTAL", condicionComida="POSTPRANDIAL")
    assert glucose.fechaHoraUltimaComida is None
    measurements.addSamples(db, team.operator, glucose.idMedicion, samples())
    done = measurements.finishMeasurement(db, team.operator, glucose.idMedicion, MeasurementFinish())
    assert done.estadoMedicion == "INVALIDA" and done.glucosaEstimada is None and "falta de información" in done.observacion
    # Con sesión de dispositivo (la glucosa la informa el firmware) tampoco se pide nada.
    session = start(db, team.operator, patient.idPerfilMedicion, dev, "GLUCOSA_EXPERIMENTAL", deviceSession=True, condicionComida="POSTPRANDIAL")
    assert session.fechaHoraUltimaComida is None
    # Informada: se conserva fecha y hora.
    informed = nowForDb() - timedelta(minutes=95)
    kept = start(db, team.operator, patient.idPerfilMedicion, dev, "GLUCOSA_EXPERIMENTAL", condicionComida="POSTPRANDIAL", fechaHoraUltimaComida=informed)
    assert kept.fechaHoraUltimaComida == informed and kept.minutosDesdeUltimaComida in (94, 95)


def test_la_fecha_vacia_o_en_blanco_llega_como_null_y_una_mal_formada_se_rechaza(team):
    from pydantic import ValidationError

    from app.schemas.acquisition import TelemetrySessionStart
    base = {"idPerfilMedicion": team.id, "idDispositivo": team.id}
    for schema in (MeasurementStart, TelemetrySessionStart):
        for empty in (None, "", "   "):
            assert schema(**base, fechaHoraUltimaComida=empty).fechaHoraUltimaComida is None  # vacío ≠ error
        assert schema(**base, fechaHoraUltimaComida="2026-10-17 12:30:00").fechaHoraUltimaComida.hour == 12  # informada: se conserva
        try:
            schema(**base, fechaHoraUltimaComida="ayer")
        except ValidationError:
            pass
        else:
            raise AssertionError("una fecha mal formada debe rechazarse")
