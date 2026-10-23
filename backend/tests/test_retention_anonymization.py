# Pruebas con DATOS SINTÉTICOS de la migración 031: DNI único por institución, anonimización real de pacientes y retención de 12 meses
# desde la última medición. Todo corre sobre el esquema SQLite temporal de las pruebas; no toca ninguna base real.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_retention_anonymization.py -v
#
# Reglas que se prueban (docs/RETENCION_Y_ANONIMIZACION.md):
#   · DNI normalizado antes de comparar; único entre pacientes ACTIVOS de una misma institución; repetible en otra institución; sin DNI,
#     dado de baja o anonimizado no bloquea; el índice único frena también las altas simultáneas; no se fusiona nada.
#   · Anonimización real: ninguna medición queda unida a la persona, los datos estadísticos y el origen DEMO se conservan, el seudónimo se
#     reemplaza y el perfil queda vacío. Se diferencia de la seudonimización anterior.
#   · Retención: 12 meses desde la última medición de esa persona, también después de anonimizar; alcanza a los datos derivados; no alcanza
#     a pacientes activos.
#   · Estadísticas institucionales coherentes con pacientes anonimizados y operadores eliminados.

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models.audit import Audit
from app.models.capillaryReference import CapillaryReferenceMeasurement
from app.models.device import Device
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.resultDelivery import ResultDelivery
from app.models.sensorSample import SensorSample
from app.schemas.measurementProfile import PatientUpdateRequest
from app.services import dashboard
from app.services import institution as institutions
from app.services import institutionPatients as patients
from app.services import measurementRetention
from app.services.institutionalRetention import purgeExpiredPatientData
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    audits,
    db,
    enableMfa,
    engine,
    mails,
    makeUser,
    reload,
    totpCode,
)
from tests.test_institution_patients import deletion, otherInstitution, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    newInstitution,
    relationOf,
    team,
)

COHORTE = measurementRetention.TIPO_COHORTE


def device(db) -> Device:
    found = db.scalar(select(Device))
    if found is None:
        found = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
        db.add(found)
        db.flush()
    return found


def measure(db, idPerfil, daysAgo: float, **overrides) -> Measurement:
    start = nowForDb() - timedelta(days=daysAgo)
    values = dict(
        idMedicion=uuid.uuid4(), idPerfilMedicion=idPerfil, idDispositivo=device(db).idDispositivo, modoMedicion="OXIMETRIA",
        estadoMedicion="COMPLETADA", edadAlMomento=46, sexoModelo="MASCULINO", condicionComida="AYUNO", fechaHoraInicio=start,
        calidadSenal=0.9, spo2=97, frecuenciaCardiaca=72, modeloSensorAlMomento="MAX30102", observacion="nota con datos del paciente")
    values.update(overrides)
    row = Measurement(**values)
    db.add(row)
    db.commit()
    return row


def newPatient(db, team, **data):
    return patients.createPatient(db, team.operator, team.id, patientData(**data))


def cohortOf(db):
    return db.scalar(select(MeasurementProfile).where(MeasurementProfile.tipoPerfil == COHORTE))


# --- DNI único por institución --------------------------------------------------------------------


def test_dni_se_normaliza_y_es_unico_entre_pacientes_activos_de_la_institucion(db, mails, team):
    first = newPatient(db, team, dni="20.111.222")
    assert first.dni == "20111222"
    for variant in ("20111222", "20-111-222", "20 111 222"):
        expectError("PACIENTE_REGISTRADO", patients.createPatient, db, team.operator, team.id, patientData(dni=variant))
    # Modificar otro paciente para repetir ese documento también se rechaza; conservar el propio no es un duplicado.
    other = newPatient(db, team, dni="30111222")
    expectError("PACIENTE_REGISTRADO", patients.updatePatient, db, team.operator, team.id, other.idPerfilMedicion,
                PatientUpdateRequest(dni="20.111.222"))
    patients.updatePatient(db, team.operator, team.id, first.idPerfilMedicion, PatientUpdateRequest(dni="20-111-222"))
    assert db.scalar(select(func.count()).select_from(MeasurementProfile).where(MeasurementProfile.dni == "20111222")) == 1


def test_mismo_dni_en_otra_institucion_y_pacientes_sin_dni_no_chocan(db, mails, team):
    newPatient(db, team, dni="20111222")
    institution, operator, _ = otherInstitution(db)
    other = patients.createPatient(db, operator, institution.idInstitucion, patientData(dni="20.111.222"))
    assert other.dni == "20111222"
    # Sin documento: cualquier cantidad (no hay nada que comparar), en la misma institución.
    for index in range(3):
        patients.createPatient(db, team.operator, team.id, patientData(dni=None, nombre=f"Sin{index}", apellido="Documento"))
    assert db.scalar(select(func.count()).select_from(MeasurementProfile).where(MeasurementProfile.dni.is_(None))) == 3


def test_el_indice_unico_frena_altas_simultaneas(db, mails, team, monkeypatch):
    """Dos pedidos que pasan la comprobación previa a la vez (carrera): la garantía es el índice de SQL Server/SQLite, no el código."""
    newPatient(db, team, dni="20111222")
    monkeypatch.setattr(patients, "_requireUniqueDocument", lambda *args, **kwargs: None)  # simula la ventana de la carrera
    expectError("PACIENTE_REGISTRADO", patients.createPatient, db, team.operator, team.id, patientData(dni="20.111.222"))
    other = newPatient(db, team, dni="30111222")
    expectError("PACIENTE_REGISTRADO", patients.updatePatient, db, team.operator, team.id, other.idPerfilMedicion,
                PatientUpdateRequest(dni="20111222"))
    assert db.scalar(select(func.count()).select_from(MeasurementProfile).where(MeasurementProfile.dni == "20111222")) == 1
    assert reload(db, MeasurementProfile, other.idPerfilMedicion).dni == "30111222"  # no se fusionó ni se pisó nada


def test_el_documento_se_libera_con_la_baja_y_con_la_anonimizacion(db, mails, team):
    first = newPatient(db, team, dni="20111222")
    patients.dischargePatient(db, team.owner, team.id, first.idPerfilMedicion)
    again = newPatient(db, team, dni="20111222")  # el anterior ya no es un paciente activo
    assert again.idPerfilMedicion != first.idPerfilMedicion
    assert reload(db, MeasurementProfile, first.idPerfilMedicion).dni is None  # la baja anonimiza: el documento se borra en el acto


# --- Anonimización real ---------------------------------------------------------------------------


def test_anonimizar_separa_las_mediciones_de_la_persona_y_conserva_lo_estadistico(db, mails, team):
    created = newPatient(db, team, dni="20111222")
    old = reload(db, MeasurementProfile, created.idPerfilMedicion)
    recent = measure(db, old.idPerfilMedicion, 2, spo2=96, observacion="dato libre")
    demo = measure(db, old.idPerfilMedicion, 5, modoMedicion="OXIMETRIA", origenGlucosa="DEMO", glucosaDispositivo=117, unidadGlucosa="mg/dL")
    now = nowForDb()

    assert measurementRetention.anonymizeProfile(db, old.idPerfilMedicion, now) is True
    db.commit()

    # 1. Ninguna medición sigue unida al perfil original: no hay relación persona-medición.
    shell = reload(db, MeasurementProfile, old.idPerfilMedicion)
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == shell.idPerfilMedicion)) == 0
    # 2. Pasaron a la cohorte anónima de la institución: sin usuario, responsable, seudónimo ni datos personales.
    cohort = cohortOf(db)
    assert (cohort.idUsuario, cohort.idInstitucionUsuarioResponsable, cohort.identificadorPseudonimo) == (None, None, None)
    assert (cohort.nombre, cohort.apellido, cohort.dni, cohort.fechaNacimiento, cohort.edadDeclarada) == (None,) * 5
    moved = {m.idMedicion: m for m in db.scalars(select(Measurement).where(Measurement.idPerfilMedicion == cohort.idPerfilMedicion))}
    assert set(moved) == {recent.idMedicion, demo.idMedicion}
    # 3. Se conservan los datos estadísticos, el modo, el origen DEMO y el estado; se pierde solo la observación libre.
    row = moved[recent.idMedicion]
    assert (row.edadAlMomento, row.sexoModelo, row.condicionComida, float(row.calidadSenal), float(row.spo2), row.frecuenciaCardiaca) \
        == (46, "MASCULINO", "AYUNO", 0.9, 96, 72)
    assert (row.modoMedicion, row.estadoMedicion, row.observacion) == ("OXIMETRIA", "COMPLETADA", None)
    assert moved[demo.idMedicion].origenGlucosa == "DEMO" and float(moved[demo.idMedicion].glucosaDispositivo) == 117
    # 4. La cáscara del paciente queda vacía y con un seudónimo nuevo (el anterior pudo comunicarse): no es seudonimización.
    assert (shell.nombre, shell.apellido, shell.dni, shell.fechaNacimiento, shell.edadDeclarada, shell.sexoModelo) == (None,) * 6
    assert shell.fechaDepuracionDatosPersonales == now and shell.fechaUltimaMedicion is None
    assert shell.identificadorPseudonimo != created.identificadorPseudonimo and shell.identificadorPseudonimo.startswith("ANON-")
    # 5. Cada medición lleva su fin de conservación: última medición de ESA persona + 12 meses (la identidad ya no hace falta).
    stamps = dict(db.execute(select(Measurement.__table__.c.idMedicion, Measurement.__table__.c.fechaVencimientoRetencion)).all())
    expected = institutions.addMonths(recent.fechaHoraInicio, 12)
    assert stamps[recent.idMedicion] == stamps[demo.idMedicion] == expected
    # Idempotente: un perfil ya anonimizado no se vuelve a tocar.
    assert measurementRetention.anonymizeProfile(db, old.idPerfilMedicion, now) is False


def test_una_sola_cohorte_por_institucion_y_las_de_otra_no_se_mezclan(db, mails, team):
    first, second = newPatient(db, team, dni="20111222"), newPatient(db, team, dni="30111222")
    measure(db, first.idPerfilMedicion, 3)
    measure(db, second.idPerfilMedicion, 4)
    institution, operator, _ = otherInstitution(db)
    third = patients.createPatient(db, operator, institution.idInstitucion, patientData(dni="40111222"))
    measure(db, third.idPerfilMedicion, 1)
    for created in (first, second, third):
        measurementRetention.anonymizeProfile(db, created.idPerfilMedicion, nowForDb())
    db.commit()
    cohorts = db.scalars(select(MeasurementProfile).where(MeasurementProfile.tipoPerfil == COHORTE)).all()
    assert len(cohorts) == 2
    perInstitution = {c.idPerfilMedicion: db.scalar(select(func.count()).select_from(Measurement)
                                                    .where(Measurement.idPerfilMedicion == c.idPerfilMedicion)) for c in cohorts}
    assert sorted(perInstitution.values()) == [1, 2]


def test_la_cohorte_no_es_un_paciente_ni_se_puede_consultar(db, mails, team):
    created = newPatient(db, team, dni="20111222")
    measure(db, created.idPerfilMedicion, 3)
    measurementRetention.anonymizeProfile(db, created.idPerfilMedicion, nowForDb())
    db.commit()
    cohort = cohortOf(db)
    for user in (team.owner, team.moderator, team.operator):
        for state in ("ACTIVO", "BAJA"):
            page = patients.listPatients(db, user, team.id, estado=state)
            assert cohort.idPerfilMedicion not in {item.idPerfilMedicion for item in page.items}
        expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, user, team.id, cohort.idPerfilMedicion)
    # Tampoco el paciente anonimizado: deja de listarse.
    assert patients.listPatients(db, team.operator, team.id).total == 0


# --- Retención de 12 meses desde la última medición ---------------------------------------------------


def test_el_vencimiento_se_controla_despues_de_anonimizar_y_cada_persona_tiene_su_plazo(db, mails, team):
    """Dos personas con última medición distinta: tras anonimizarlas ya no se sabe quién es quién, pero cada medición vence a los 12 meses
    de la última de SU persona. Se borran también los datos derivados."""
    early, late = newPatient(db, team, dni="20111222"), newPatient(db, team, dni="30111222")
    a1 = measure(db, early.idPerfilMedicion, 380)
    a2 = measure(db, early.idPerfilMedicion, 366)  # última de la primera persona: hace 366 días
    b1 = measure(db, late.idPerfilMedicion, 100)
    b2 = measure(db, late.idPerfilMedicion, 2)  # última de la segunda: hace 2 días
    db.add_all([SensorSample(idMedicion=a2.idMedicion, numeroMuestra=0, valorRed=100, valorIR=200),
                CapillaryReferenceMeasurement(idMedicion=a2.idMedicion, glucosaReferencia=100, fechaHoraReferencia=a2.fechaHoraInicio),
                ResultDelivery(idMedicion=a2.idMedicion, estadoEnvio="FALLIDO")])
    db.commit()
    for created in (early, late):
        measurementRetention.anonymizeProfile(db, created.idPerfilMedicion, nowForDb())
    db.commit()

    deleted = measurementRetention.purgeExpiredMeasurements(db)
    assert deleted == 2  # a1 y a2 (última + 12 meses ya pasó); las de la segunda persona, no
    remaining = {m.idMedicion for m in db.scalars(select(Measurement))}
    assert a1.idMedicion not in remaining and a2.idMedicion not in remaining and b1.idMedicion in remaining and len(remaining) == 2
    for model in (SensorSample, CapillaryReferenceMeasurement, ResultDelivery):  # datos derivados
        assert db.scalar(select(func.count()).select_from(model)) == 0
    # La auditoría registra la cantidad, sin identificadores ni datos.
    event = db.scalar(select(Audit).where(Audit.accion == measurementRetention.ACCION_DEPURAR))
    assert event is not None and '"medicionesEliminadas": 2' in event.datosNuevos and str(b1.idMedicion) not in (event.datosNuevos or "")
    # Idempotente, y vence cuando llega su fecha (no antes).
    assert measurementRetention.purgeExpiredMeasurements(db) == 0
    due = institutions.addMonths(b2.fechaHoraInicio, 12)  # las dos de la segunda persona comparten el vencimiento de SU última medición
    assert measurementRetention.purgeExpiredMeasurements(db, now=due - timedelta(days=1)) == 0
    assert measurementRetention.purgeExpiredMeasurements(db, now=due + timedelta(days=1)) == 2
    assert db.scalar(select(func.count()).select_from(Measurement)) == 0


def test_paciente_con_identidad_conservada_vence_desde_su_ultima_medicion_y_el_activo_no(db, mails, team):
    """El cierre de una institución sí conserva la identidad 12 meses (la baja individual ya anonimiza): esos pacientes vencen a los 12
    meses de SU última medición, que siempre cae antes del final de esa conservación."""
    old, recent = newPatient(db, team, dni="20111222"), newPatient(db, team, dni="30111222")
    measure(db, old.idPerfilMedicion, 400)
    measure(db, recent.idPerfilMedicion, 30)
    institution, operator, _ = otherInstitution(db)
    active = patients.createPatient(db, operator, institution.idInstitucion, patientData(dni="40111222"))
    measure(db, active.idPerfilMedicion, 400)
    institutions.deleteInstitution(db, team.owner, team.id, deletion())

    assert measurementRetention.purgeExpiredMeasurements(db) == 1
    counts = [db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == c.idPerfilMedicion))
              for c in (old, recent, active)]
    assert counts == [0, 1, 1]  # el alcance es solo lo conservado: el paciente ACTIVO no vence por no medir
    assert reload(db, MeasurementProfile, old.idPerfilMedicion).nombre == "Juan"  # la identidad sigue hasta su propio plazo


def test_el_job_completo_despues_del_cierre_de_la_institucion(db, mails, team):
    """Misma secuencia que app/jobs/purgeInstitutionalRetention.py: borra lo vencido, anonimiza y borra lo que nació vencido."""
    created = newPatient(db, team, dni="20111222")
    measure(db, created.idPerfilMedicion, 10)
    institutions.deleteInstitution(db, team.owner, team.id, deletion())
    retentionEnd = reload(db, MeasurementProfile, created.idPerfilMedicion).fechaExpiracionDatosPersonales
    now = retentionEnd + timedelta(minutes=1)
    deleted = measurementRetention.purgeExpiredMeasurements(db, now=now)
    anonymized = purgeExpiredPatientData(db, now=now)
    deleted += measurementRetention.purgeExpiredMeasurements(db, now=now)
    assert (deleted, anonymized) == (1, 1)
    assert db.scalar(select(func.count()).select_from(Measurement)) == 0
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).nombre is None
    assert db.scalar(select(Audit).where(Audit.accion == "ANONIMIZAR_PACIENTES")) is not None


# --- Anonimización al dar de baja -------------------------------------------------------------------


def test_la_baja_anonimiza_en_el_acto_y_las_mediciones_quedan_hasta_12_meses_de_la_ultima(db, mails, team):
    created = newPatient(db, team, dni="20111222")
    first = measure(db, created.idPerfilMedicion, 200)
    last = measure(db, created.idPerfilMedicion, 40)
    result = patients.dischargePatient(db, team.owner, team.id, created.idPerfilMedicion)

    assert result.estado == "BAJA" and (result.nombre, result.apellido, result.dni, result.fechaNacimiento) == (None,) * 4
    shell = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert shell.fechaDepuracionDatosPersonales is not None and shell.identificadorPseudonimo != created.identificadorPseudonimo
    cohort = cohortOf(db)
    moved = {m.idMedicion for m in db.scalars(select(Measurement).where(Measurement.idPerfilMedicion == cohort.idPerfilMedicion))}
    assert moved == {first.idMedicion, last.idMedicion}
    # Vencen a los 12 meses de la ÚLTIMA medición de esa persona, no de la baja ni de cada una.
    due = institutions.addMonths(last.fechaHoraInicio, 12)
    assert measurementRetention.purgeExpiredMeasurements(db) == 0
    assert measurementRetention.purgeExpiredMeasurements(db, now=due - timedelta(minutes=1)) == 0
    assert measurementRetention.purgeExpiredMeasurements(db, now=due + timedelta(minutes=1)) == 2
    # Auditoría sin datos personales: quién dio de baja y la cantidad.
    [event] = audits(db, "ANONIMIZAR_PACIENTES")
    assert event.idUsuario == team.owner.idUsuario and "Juan" not in (event.datosNuevos or "")
    # Nadie puede consultarlo ni listarlo, y el job ya no tiene nada que anonimizar.
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, team.owner, team.id, created.idPerfilMedicion)
    assert purgeExpiredPatientData(db, now=nowForDb() + timedelta(days=800)) == 0


def test_el_aviso_de_baja_al_operador_no_enlaza_a_un_paciente_que_ya_no_existe(db, mails, team):
    created = newPatient(db, team, dni="20111222")
    del mails[:]
    patients.dischargePatient(db, team.owner, team.id, created.idPerfilMedicion)
    [notice] = [mail for mail in mails if mail["to"] == "operadora@example.com"]
    assert created.identificadorPseudonimo in notice["html"] and str(created.idPerfilMedicion) not in notice["html"]


def test_no_se_da_de_baja_con_una_medicion_en_curso(db, mails, team):
    created = newPatient(db, team, dni="20111222")
    measure(db, created.idPerfilMedicion, 0.001, estadoMedicion="ADQUIRIENDO", spo2=None, frecuenciaCardiaca=None, calidadSenal=None)
    expectError("MEDICION_EN_CURSO", patients.dischargePatient, db, team.owner, team.id, created.idPerfilMedicion)
    assert patients.getPatient(db, team.owner, team.id, created.idPerfilMedicion).estado == "ACTIVO"  # nada cambió
    assert db.scalar(select(func.count()).select_from(MeasurementProfile).where(MeasurementProfile.tipoPerfil == COHORTE)) == 0


# --- Dashboard ------------------------------------------------------------------------------------


def test_los_totales_institucionales_no_cambian_al_anonimizar_y_no_hay_datos_individuales(db, mails, team):
    first, second = newPatient(db, team, dni="20111222"), newPatient(db, team, dni="30111222")
    measure(db, first.idPerfilMedicion, 3)
    measure(db, first.idPerfilMedicion, 4)
    measure(db, second.idPerfilMedicion, 1)
    before = dashboard.institutionDashboard(db, team.owner, team.id)
    assert before.medicionesTotal == 3

    measurementRetention.anonymizeProfile(db, first.idPerfilMedicion, nowForDb())
    db.commit()
    after = dashboard.institutionDashboard(db, team.owner, team.id)
    assert after.medicionesTotal == 3  # coherente: las mediciones conservadas siguen contando, ya sin persona
    assert after.pacientesActivos == 1  # la persona anonimizada ya no es un paciente
    assert after.agregadosProtegidos is True  # menos de 5 pacientes distintos: sin estadísticas de salud que identifiquen a alguien
    assert after.estadisticas is not None


def test_operador_eliminado_o_minimizado_no_expone_datos_personales_en_estadisticas(db, mails, team):
    relation = relationOf(db, team, team.operator)
    visible = dashboard._staffName(relation, team.operator)  # cuenta vigente: su nombre
    assert visible[0] and visible[0] != "Operador desvinculado"
    relation.fechaMinimizacionDatos = nowForDb()  # datos históricos ya minimizados
    db.commit()
    assert dashboard._staffName(relation, team.operator) == ("Operador desvinculado", None)
    relation.fechaMinimizacionDatos = None
    team.operator.estado, team.operator.fechaEliminacion = "ELIMINADO", nowForDb()  # cuenta eliminada
    team.operator.nombre = team.operator.apellido = None  # anonimizada: ya no tiene nombre propio
    db.commit()
    assert dashboard._staffName(relation, team.operator) == ("Victoria", "Cortés")  # eliminada la cuenta, el nombre histórico del vínculo sigue siendo el permitido
    relation.nombreProfesionalHistorico = relation.apellidoProfesionalHistorico = None
    db.commit()
    assert dashboard._staffName(relation, team.operator) == ("Operador desvinculado", None)  # sin ninguna identificación registrada: neutro
    relation.nombreProfesionalHistorico, relation.apellidoProfesionalHistorico = "Victoria", "Cortés"
    db.commit()
    relation.fechaMinimizacionDatos = nowForDb()
    db.commit()
    assert dashboard._staffName(relation, team.operator) == ("Operador desvinculado", None)  # vencida la conservación: neutro


@pytest.mark.parametrize("dni", ["20111222", None])
def test_sin_la_031_nada_cambia(db, mails, team, monkeypatch, dni):
    """Mientras la migración no esté aplicada el backend se comporta como antes: no anonimiza ni borra mediciones."""
    created = newPatient(db, team, dni=dni)
    measure(db, created.idPerfilMedicion, 400)
    monkeypatch.setattr(measurementRetention, "ready", lambda _db: False)
    patients.dischargePatient(db, team.owner, team.id, created.idPerfilMedicion)  # sin 031: baja de siempre (conserva 12 meses)
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).nombre == "Juan"
    assert measurementRetention.purgeExpiredMeasurements(db) == 0
    retentionEnd = reload(db, MeasurementProfile, created.idPerfilMedicion).fechaExpiracionDatosPersonales
    assert purgeExpiredPatientData(db, now=retentionEnd + timedelta(minutes=1)) == 1  # seudonimización de siempre
    kept = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert kept.identificadorPseudonimo == created.identificadorPseudonimo and kept.nombre is None
    assert db.scalar(select(func.count()).select_from(Measurement).where(Measurement.idPerfilMedicion == kept.idPerfilMedicion)) == 1


def test_el_job_manual_de_retencion_exige_nombrar_la_base_y_confirmar_las_cantidades(monkeypatch):
    # Sin --confirmo-base exacto no abre ninguna sesión ni modifica nada; con la base, además exige las cantidades que informó --simular (H-04).
    from contextlib import nullcontext

    from app.jobs import purgeInstitutionalRetention as job

    monkeypatch.setattr(job, "run", lambda: (_ for _ in ()).throw(AssertionError("no debía correr")))
    monkeypatch.setattr(job, "getJobsSessionFactory", lambda: (_ for _ in ()).throw(AssertionError("no debía abrir una sesión")))
    assert job.main([]) == 2
    assert job.main(["--confirmo-base", "otra"]) == 2
    monkeypatch.setattr(job, "getJobsSessionFactory", lambda: lambda: nullcontext())
    monkeypatch.setattr(job, "plan", lambda db: {"perfilesAAnonimizar": 0, "medicionesAEliminar": 0})
    assert job.main(["--confirmo-base", job.getSettings().DB_NAME]) == 2  # sin confirmar las cantidades
    monkeypatch.setattr(job, "run", lambda: 0)
    assert job.main(["--confirmo-base", job.getSettings().DB_NAME, "--confirmo-perfiles", "0", "--confirmo-mediciones", "0"]) == 0


def test_un_perfil_que_falla_no_frena_a_los_demas_y_se_reintenta(db, mails, team, monkeypatch):
    # Recuperación ante errores: el que falla (a mitad de lote y después de haber cambiado algo) se deshace solo él; los demás se
    # anonimizan, se cuentan una vez y se auditan con la cantidad exacta. La próxima pasada lo completa.
    patients = [newPatient(db, team, dni=f"2011{n}555") for n in range(3)]
    institutions.deleteInstitution(db, team.owner, team.id, deletion())
    now = reload(db, MeasurementProfile, patients[0].idPerfilMedicion).fechaExpiracionDatosPersonales + timedelta(minutes=1)
    original = measurementRetention.anonymizeProfile
    calls, failedId = [], []

    def flaky(session, idPerfil, moment):
        calls.append(idPerfil)
        result = original(session, idPerfil, moment)
        if len(calls) == 2:  # el segundo del lote falla después de haber anonimizado
            failedId.append(idPerfil)
            raise RuntimeError("falla simulada")
        return result

    monkeypatch.setattr(measurementRetention, "anonymizeProfile", flaky)
    assert purgeExpiredPatientData(db, now=now) == 2
    failed = reload(db, MeasurementProfile, failedId[0])
    assert failed.fechaDepuracionDatosPersonales is None and failed.nombre is not None  # sin cambios a medias
    assert sum(reload(db, MeasurementProfile, p.idPerfilMedicion).nombre is None for p in patients) == 2
    [event] = db.scalars(select(Audit).where(Audit.accion == "ANONIMIZAR_PACIENTES")).all()
    assert json.loads(event.datosNuevos)["perfilesAnonimizados"] == 2
    monkeypatch.setattr(measurementRetention, "anonymizeProfile", original)
    assert purgeExpiredPatientData(db, now=now) == 1  # la próxima pasada lo completa
    assert purgeExpiredPatientData(db, now=now) == 0
