# Pruebas del módulo Medición y de la gestión de PerfilMedicion: ciclo de vida, modos, matriz y regla, historial
# individual e institucional, estadísticas, permisos de grupos familiares y aislamiento entre cuentas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurements.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py. No hay hardware: las muestras y los resultados del
# procesamiento de señal se entregan por la API del servicio, como lo hará el puente del dispositivo.

import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AuthError
from tests.ppg import ppgSamples
from app.db.base import Base
from app.models.capillaryReference import CapillaryReferenceMeasurement
from app.models.device import Device
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.sensorSample import SensorSample
from app.models.user import User
from app.schemas.measurement import (
    CapillaryReferenceRequest,
    MeasurementFinish,
    MeasurementStart,
    SamplesRequest,
)
from app.services import group as groups
from app.services import institutionPatients as patients
from app.services import measurement as measurements
from app.services import profileTransfers as transfers
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    audits,
    db,
    engine,
    mails,
    makeUser,
    reload,
)
from tests.test_groups import create as createGroup
from tests.test_groups import join, person, relationOf as groupLinkOf, share
from tests.test_institution_patients import addOperator, otherInstitution, patientData
from tests.test_institutions import (  # noqa: F401 - fixtures
    expectError,
    freshLookupLimiter,
    institutional,
    relationOf,
    team,
)


@pytest.fixture(autouse=True)
def noEstimator(monkeypatch):
    monkeypatch.setattr(measurements, "glucoseEstimator", None)


def device(db, estado="OPERATIVO", institucion=None, codigo=None, firmware="1.2.0") -> Device:
    """Dispositivo del inventario. Si el puente ya lo registró solo (alta automática al conectarse), se reutiliza ese y se le
    aplican los datos pedidos: el código es único."""
    if codigo:
        existing = db.scalar(select(Device).where(func.lower(Device.codigoDispositivo) == codigo.lower()))
        if existing is not None:
            existing.estado, existing.idInstitucionAsignada, existing.versionFirmware = estado, institucion, firmware
            db.commit()
            return existing
    row = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=codigo or uuid.uuid4().hex, nombre="Oxímetro",
                 modelo="HC-06", modeloSensor="MAX30102", versionFirmware=firmware, estado=estado,
                 idInstitucionAsignada=institucion)
    db.add(row)
    db.commit()
    return row


def addMatrix(db, ambito="GLOBAL", idInstitucion=None, estado="ACTIVA", hasta=None, rule=True, condicion="AYUNO",
              edad=(18, 80), sexo="FEMENINO", minutos=(None, None), desde=None, nombre="Matriz experimental") -> Matrix:
    matrix = Matrix(idMatriz=uuid.uuid4(), nombre=nombre, version="1", ambito=ambito,
                    idInstitucion=idInstitucion, estado=estado,
                    fechaVigenciaDesde=desde or date.today() - timedelta(days=30), fechaVigenciaHasta=hasta,
                    referenciaBase="Fuente de prueba")
    db.add(matrix)
    db.flush()
    if rule:
        db.add(MatrixRule(idReglaMatriz=uuid.uuid4(), idMatriz=matrix.idMatriz, codigoRegla="R1", sexoModelo=sexo,
                          edadDesde=edad[0], edadHasta=edad[1], condicionComida=condicion, minutosComidaMin=minutos[0],
                          minutosComidaMax=minutos[1], glucosaMinReferencia=Decimal("70"),
                          glucosaMaxReferencia=Decimal("110")))
    db.commit()
    return matrix


def samples(count=3, start=0):
    return SamplesRequest(muestras=[{"numeroMuestra": start + i, "tiempoRelativoMs": i * 10, "valorRed": 1000 + i,
                                     "valorIR": 2000 + i} for i in range(count)])


def signalSamples(hr=72, spo2=97.5, seconds=20, start=0, sensor="MAX30102"):
    """Muestras de una señal PPG sintética (solo pruebas) con la frecuencia cardíaca y la SpO₂ indicadas."""
    dc = (120000, 100000) if sensor == "MAX30102" else (30000, 25000)
    return SamplesRequest(muestras=[
        {"numeroMuestra": n, "tiempoRelativoMs": t, "valorRed": red, "valorIR": ir}
        for n, t, red, ir in ppgSamples(hr, float(spo2), seconds, dcIr=dc[0], dcRed=dc[1], seed=int(hr), startIndex=start)])


def oximetry(db, user, profileId, dev, **start):
    return measurements.startMeasurement(db, user, MeasurementStart(
        idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, **start))


def completeOximetry(db, user, profileId, dev, spo2="97.5", hr=72, quality="0.9"):
    started = oximetry(db, user, profileId, dev)
    measurements.addSamples(db, user, started.idMedicion, signalSamples(hr, spo2, sensor=dev.modeloSensor))
    return measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish())  # el servidor calcula


@pytest.fixture
def consumer(db, mails):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    profile = measurements.getOwnProfile(db, user)
    return user, profile.idPerfilMedicion


# --- Perfiles ---------------------------------------------------------------------------------------------------


def test_un_usuario_individual_consulta_su_propio_perfil(db, mails):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    profile = measurements.getOwnProfile(db, user)
    assert profile.perfilDisponible and profile.idPerfilMedicion is not None
    assert (profile.nombre, profile.sexoModelo, profile.fechaUltimaMedicion) == ("Victoria", "FEMENINO", None)
    stored = db.get(MeasurementProfile, profile.idPerfilMedicion)
    assert stored.tipoPerfil == "CONSUMIDOR_FINAL" and stored.idUsuario == user.idUsuario
    assert stored.idInstitucionUsuarioResponsable is None  # un perfil individual no pertenece a InstitucionUsuario


def test_perfil_sin_fecha_de_nacimiento_esta_disponible_y_solo_la_recomienda(db, mails):
    user = makeUser(db, email="persona@example.com", usuario="persona")
    user.fechaNacimiento = None
    db.commit()
    profile = measurements.getOwnProfile(db, user)
    assert profile.perfilDisponible and profile.datosFaltantes == [] and profile.datosRecomendados == ["fechaNacimiento"]
    assert profile.edad is None and profile.idPerfilMedicion is not None


def test_una_cuenta_institucional_no_tiene_perfil_propio(db, mails, team):
    expectError("PERFIL_NO_DISPONIBLE", measurements.getOwnProfile, db, team.operator)


def test_operador_crea_perfil_institucional_sin_usuario_ni_tabla_paciente(db, mails, team):
    users = db.scalar(select(func.count()).select_from(User))
    created = patients.createPatient(db, team.operator, team.id, patientData())
    profile = reload(db, MeasurementProfile, created.idPerfilMedicion)
    relation = relationOf(db, team, team.operator)
    assert profile.tipoPerfil == "INSTITUCIONAL" and profile.idUsuario is None
    assert profile.idInstitucionUsuarioResponsable == relation.idInstitucionUsuario
    assert relation.idInstitucion == team.id and profile.identificadorPseudonimo
    assert db.scalar(select(func.count()).select_from(User)) == users
    assert "Paciente" not in {table.name for table in Base.metadata.sorted_tables}


def test_las_modificaciones_del_paciente_persisten_y_no_se_modifica_un_perfil_ajeno(db, mails, team):
    from app.schemas.measurementProfile import PatientUpdateRequest
    created = patients.createPatient(db, team.operator, team.id, patientData())
    patients.updatePatient(db, team.operator, team.id, created.idPerfilMedicion, PatientUpdateRequest(nombre="Pedro"))
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).nombre == "Pedro"
    other = addOperator(db, team)
    from tests.test_institutions import User as _U  # noqa: F401
    otherUser = db.get(User, other.idUsuarioInvitado)
    expectError("PERMISO_INSUFICIENTE", patients.updatePatient, db, otherUser, team.id, created.idPerfilMedicion,
                PatientUpdateRequest(nombre="Hacker"))
    assert reload(db, MeasurementProfile, created.idPerfilMedicion).nombre == "Pedro"


def test_un_operador_no_consulta_perfiles_de_otra_institucion(db, mails, team):
    other, otherOperator, _ = otherInstitution(db)
    created = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db)
    expectError("PACIENTE_NO_ENCONTRADO", patients.getPatient, db, otherOperator, other.idInstitucion, created.idPerfilMedicion)
    expectError("PERFIL_NO_ENCONTRADO", measurements.startMeasurement, db, otherOperator, MeasurementStart(
        idPerfilMedicion=created.idPerfilMedicion, idDispositivo=dev.idDispositivo))
    expectError("INSTITUCION_NO_ENCONTRADA", measurements.listPatientHistory, db, otherOperator, team.id,
                created.idPerfilMedicion)


# --- Mediciones: creación y contexto --------------------------------------------------------------------------


def test_crear_una_medicion_asociada_a_un_perfil_valido_con_dispositivo_y_contexto(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    detail = oximetry(db, user, profileId, dev, condicionComida="AYUNO", observacion="Después de caminar")
    assert detail.estadoMedicion == "PENDIENTE" and detail.modoMedicion == "OXIMETRIA"
    assert detail.idPerfilMedicion == profileId and detail.dispositivo.idDispositivo == dev.idDispositivo
    assert (detail.edadAlMomento, detail.sexoModelo) == (nowForDb().year - 1990 - ((nowForDb().month, nowForDb().day) < (5, 17)), "FEMENINO")
    assert (detail.versionFirmwareAlMomento, detail.modeloSensorAlMomento) == ("1.2.0", "MAX30102")
    assert detail.matriz is None and detail.spo2 is None and detail.glucosaEstimada is None
    assert detail.condicionComida == "AYUNO" and detail.observacion == "Después de caminar"
    [audit] = audits(db, "INICIAR_MEDICION")
    assert audit.idUsuario == user.idUsuario and audit.idRegistro == detail.idMedicion


def test_el_cliente_no_puede_fijar_resultados_ni_datos_del_servidor():
    for forbidden in ({"spo2": 98}, {"glucosaEstimada": 90}, {"estadoMedicion": "COMPLETADA"}, {"duracionMs": 5},
                      {"idMatriz": str(uuid.uuid4())}, {"versionAlgoritmo": "x"}):
        with pytest.raises(ValidationError):
            MeasurementStart(idPerfilMedicion=uuid.uuid4(), idDispositivo=uuid.uuid4(), **forbidden)
    with pytest.raises(ValidationError):
        MeasurementFinish(glucosaEstimada=90)  # la glucosa nunca se recibe


def test_dispositivo_no_operativo_o_de_otra_institucion_no_se_usa(db, mails, consumer, team, deviceMode):
    deviceMode(False)  # modo restringido: el equipo de una institución no aparece para la cuenta individual
    user, profileId = consumer
    expectError("DISPOSITIVO_NO_DISPONIBLE", oximetry, db, user, profileId, device(db, estado="EN_MANTENIMIENTO"))
    expectError("DISPOSITIVO_NO_DISPONIBLE", oximetry, db, user, profileId, device(db, institucion=team.id))
    expectError("DISPOSITIVO_NO_DISPONIBLE", measurements.startMeasurement, db, user, MeasurementStart(
        idPerfilMedicion=profileId, idDispositivo=uuid.uuid4()))
    assert [d.idDispositivo for d in measurements.listDevices(db, user, profileId)] == []


def test_un_operador_mide_solo_a_sus_pacientes_con_dispositivos_de_su_institucion(db, mails, team):
    mine = patients.createPatient(db, team.operator, team.id, patientData())
    other = addOperator(db, team)
    otherUser = db.get(User, other.idUsuarioInvitado)
    dev = device(db, institucion=team.id)
    detail = oximetry(db, team.operator, mine.idPerfilMedicion, dev)
    assert detail.puedeOperar and detail.idPerfilMedicion == mine.idPerfilMedicion
    assert [d.idDispositivo for d in measurements.listDevices(db, team.operator, mine.idPerfilMedicion)] == [dev.idDispositivo]
    # Otro operador de la misma institución no consulta ni opera al paciente ajeno: rechazo explícito (y auditado).
    expectError("MEDICIONES_NO_AUTORIZADAS", oximetry, db, otherUser, mine.idPerfilMedicion, dev)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.getMeasurement, db, otherUser, detail.idMedicion)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.cancelMeasurement, db, otherUser, detail.idMedicion)
    # Propietario y moderador tampoco: su rol administrativo no autoriza información de salud individual.
    for actor in (team.moderator, team.owner):
        expectError("MEDICIONES_NO_AUTORIZADAS", oximetry, db, actor, mine.idPerfilMedicion, dev)
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.getMeasurement, db, actor, detail.idMedicion)
    [audit] = audits(db, "INICIAR_MEDICION")
    assert audit.idRelacionado == relationOf(db, team, team.operator).idInstitucionUsuario


# --- Oximetría ----------------------------------------------------------------------------------------------


def test_oximetria_completa_sin_glucosa_estimada(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    done = completeOximetry(db, user, profileId, dev)
    assert done.estadoMedicion == "COMPLETADA" and done.glucosaEstimada is None
    assert abs(done.spo2 - Decimal("97.5")) < Decimal("0.3") and done.frecuenciaCardiaca == 72  # calculados sobre la señal
    assert done.versionAlgoritmo == "oximetria-ppg-v1" and done.calidadSenal >= Decimal("0.5")
    assert done.fechaHoraFin >= done.fechaHoraInicio and done.cantidadMuestras == 400 and done.duracionMs is not None
    assert reload(db, MeasurementProfile, profileId).fechaUltimaMedicion == done.fechaHoraFin
    assert measurements.getOwnProfile(db, user).fechaUltimaMedicion == done.fechaHoraFin
    assert [a.resultado for a in audits(db, "FINALIZAR_MEDICION")] == ["EXITO"]


def test_oximetria_sin_resultados_queda_invalida_y_no_es_un_resultado_completo(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.addSamples(db, user, started.idMedicion, samples())
    result = measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish())
    assert result.estadoMedicion == "INVALIDA" and result.spo2 is None and "SpO₂" in result.observacion
    assert reload(db, MeasurementProfile, profileId).fechaUltimaMedicion is None  # no cuenta como última medición
    assert measurements.ownStatistics(db, user).cantidadMediciones == 0  # ni en las estadísticas


# --- Estados ------------------------------------------------------------------------------------------------


def test_transiciones_validas_y_samples_pasan_a_adquiriendo(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    expectError("MEDICION_ESTADO_INVALIDO", measurements.finishMeasurement, db, user, started.idMedicion, MeasurementFinish())
    assert measurements.addSamples(db, user, started.idMedicion, samples(2)).estadoMedicion == "ADQUIRIENDO"
    assert measurements.addSamples(db, user, started.idMedicion, samples(2, start=2)).cantidadMuestras == 4
    expectError("MUESTRAS_DUPLICADAS", measurements.addSamples, db, user, started.idMedicion, samples(1, start=3))
    assert db.scalar(select(func.count()).select_from(SensorSample).where(SensorSample.idMedicion == started.idMedicion)) == 4
    done = measurements.cancelMeasurement(db, user, started.idMedicion)
    assert done.estadoMedicion == "CANCELADA"
    for fn, args in ((measurements.addSamples, (samples(1, 10),)), (measurements.cancelMeasurement, ()),
                     (measurements.finishMeasurement, (MeasurementFinish(),))):
        expectError("MEDICION_ESTADO_INVALIDO", fn, db, user, started.idMedicion, *args)


def test_cancelar_desde_pendiente_y_adquiriendo_no_deja_resultados(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    first = oximetry(db, user, profileId, dev)
    assert measurements.cancelMeasurement(db, user, first.idMedicion).estadoMedicion == "CANCELADA"
    second = oximetry(db, user, profileId, dev)
    measurements.addSamples(db, user, second.idMedicion, samples())
    cancelled = measurements.cancelMeasurement(db, user, second.idMedicion)
    assert cancelled.estadoMedicion == "CANCELADA" and cancelled.spo2 is None and cancelled.fechaHoraFin is not None
    expectError("MEDICION_ESTADO_INVALIDO", measurements.addSamples, db, user, second.idMedicion, samples(1, 9))
    assert measurements.ownStatistics(db, user).cantidadMediciones == 0


def test_finalizar_sin_muestras_no_procesa(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    expectError("MEDICION_ESTADO_INVALIDO", measurements.finishMeasurement, db, user, started.idMedicion, MeasurementFinish())


def test_cancelar_y_finalizar_a_la_vez_dejan_un_unico_resultado(engine, db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    # Señal sintética válida: si «finalizar» gana la carrera el resultado es COMPLETADA. Con solo 3 muestras terminaba INVALIDA (muy pocas muestras),
    # un resultado legítimo que la aserción no admitía, y la prueba fallaba de forma intermitente (~12 % de las corridas).
    measurements.addSamples(db, user, started.idMedicion, signalSamples())
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(2)
    results, failures = [], []

    def run(action, *args):
        session = makeSession()
        try:
            actor = session.get(User, user.idUsuario)
            barrier.wait()
            action(session, actor, started.idMedicion, *args)
            results.append("OK")
        except AuthError as error:
            results.append(error.code)
        except Exception as error:  # pragma: no cover - diagnóstico
            failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(measurements.cancelMeasurement,)),
               threading.Thread(target=run, args=(measurements.finishMeasurement,
                                                  MeasurementFinish(spo2=Decimal("97"), frecuenciaCardiaca=70)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == [] and results.count("OK") == 1
    final = reload(db, Measurement, started.idMedicion)
    assert final.estadoMedicion in ("CANCELADA", "COMPLETADA")
    assert (final.spo2 is not None) == (final.estadoMedicion == "COMPLETADA")


# --- Glucosa experimental -----------------------------------------------------------------------------------


def glucose(db, user, profileId, dev, **start):
    return measurements.startMeasurement(db, user, MeasurementStart(
        idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, modoMedicion="GLUCOSA_EXPERIMENTAL", **start))


def test_glucosa_sin_matriz_o_sin_regla_aplicable_no_inicia(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, dev, condicionComida="AYUNO")  # sin matrices
    # Ninguna de estas se aplica: no están ACTIVAS o están fuera de vigencia.
    addMatrix(db, estado="BORRADOR")
    addMatrix(db, estado="INACTIVA", nombre="otra")
    addMatrix(db, estado="ARCHIVADA", nombre="archivada")
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, dev, condicionComida="AYUNO")
    # Una única global ACTIVA vencida tampoco; y una vigente sin regla para este perfil/contexto, menos.
    expired = addMatrix(db, estado="ACTIVA", nombre="vencida", hasta=date.today() - timedelta(days=1))
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, dev, condicionComida="AYUNO")
    expired.estado = "INACTIVA"
    db.commit()
    addMatrix(db, estado="ACTIVA", nombre="vigente", sexo="MASCULINO")  # regla para otro sexo
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, dev, condicionComida="AYUNO")
    assert db.scalar(select(func.count()).select_from(Measurement)) == 0  # no se creó ninguna medición


def test_la_ultima_comida_es_opcional_tambien_despues_de_comer_en_glucosa(db, mails, consumer):
    user, profileId = consumer
    addMatrix(db, condicion="POSTPRANDIAL", minutos=(30, 180))
    dev = device(db)
    # Sin la hora de la última comida la medición SÍ inicia: no hay obligatoriedad oculta, ni siquiera con «Después de comer».
    started = glucose(db, user, profileId, dev, condicionComida="POSTPRANDIAL")
    assert started.fechaHoraUltimaComida is None and started.minutosDesdeUltimaComida is None and started.matriz is not None
    measurements.addSamples(db, user, started.idMedicion, samples())
    result = measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish())
    # La estimación no está disponible por falta de información (se explica) y no se inventa ningún valor; los demás datos se guardan.
    assert result.estadoMedicion == "INVALIDA" and result.glucosaEstimada is None
    assert "falta de información" in result.observacion and "última comida" in result.observacion
    # Informada: se conserva y las demás validaciones siguen (fecha futura, ventana de la regla).
    expectError("FECHA_INVALIDA", glucose, db, user, profileId, dev, condicionComida="POSTPRANDIAL",
                fechaHoraUltimaComida=nowForDb() + timedelta(hours=1))
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, dev, condicionComida="POSTPRANDIAL",
                fechaHoraUltimaComida=nowForDb() - timedelta(minutes=5))  # informada pero fuera de la ventana de la regla
    informed = nowForDb() - timedelta(minutes=90)
    ok = glucose(db, user, profileId, dev, condicionComida="POSTPRANDIAL", fechaHoraUltimaComida=informed)
    assert ok.minutosDesdeUltimaComida in (89, 90) and ok.matriz.nombre == "Matriz experimental"
    assert ok.fechaHoraUltimaComida == informed  # conserva fecha y hora ingresadas


def test_sin_algoritmo_la_glucosa_queda_invalida_y_no_se_inventa_ningun_valor(db, mails, consumer):
    user, profileId = consumer
    matrix = addMatrix(db)
    started = glucose(db, user, profileId, device(db), condicionComida="AYUNO")
    assert started.matriz.idMatriz == matrix.idMatriz
    measurements.addSamples(db, user, started.idMedicion, samples())
    result = measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish(
        spo2=Decimal("97"), frecuenciaCardiaca=70))
    assert result.estadoMedicion == "INVALIDA" and result.glucosaEstimada is None
    assert "algoritmo" in result.observacion.lower() and result.versionAlgoritmo is None


def test_glucosa_valida_registra_matriz_regla_y_version_del_algoritmo(db, mails, consumer, monkeypatch):
    user, profileId = consumer
    matrix = addMatrix(db)
    received = {}

    def estimator(samples_, rule, matrix_, edad, sexo):
        received.update(count=len(samples_), regla=rule.codigoRegla, matriz=matrix_.idMatriz, edad=edad, sexo=sexo)
        return Decimal("92.40"), "glucosa-exp-0.1"

    monkeypatch.setattr(measurements, "glucoseEstimator", estimator)
    started = glucose(db, user, profileId, device(db), condicionComida="AYUNO")
    measurements.addSamples(db, user, started.idMedicion, samples(4))
    done = measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish(
        spo2=Decimal("97"), frecuenciaCardiaca=70, calidadSenal=Decimal("0.8")))
    assert done.estadoMedicion == "COMPLETADA" and done.glucosaEstimada == Decimal("92.40")
    assert (done.versionAlgoritmo, done.matriz.idMatriz) == ("glucosa-exp-0.1", matrix.idMatriz)
    assert received == {"count": 4, "regla": "R1", "matriz": matrix.idMatriz, "edad": done.edadAlMomento, "sexo": "FEMENINO"}
    assert done.aviso.startswith("Resultado experimental")


def test_un_estimador_sin_resultado_no_completa_la_medicion(db, mails, consumer, monkeypatch):
    user, profileId = consumer
    addMatrix(db)
    monkeypatch.setattr(measurements, "glucoseEstimator", lambda *args: None)
    started = glucose(db, user, profileId, device(db), condicionComida="AYUNO")
    measurements.addSamples(db, user, started.idMedicion, samples())
    result = measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish())
    assert result.estadoMedicion == "INVALIDA" and result.glucosaEstimada is None


def test_la_matriz_institucional_tiene_prioridad_y_la_de_otra_institucion_no_aplica(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData(sexoModelo="femenino"))
    other, _, _ = otherInstitution(db)
    addMatrix(db, ambito="INSTITUCION", idInstitucion=other.idInstitucion)
    dev = device(db, institucion=team.id)
    expectError("SIN_REGLA_APLICABLE", glucose, db, team.operator, created.idPerfilMedicion, dev, condicionComida="AYUNO")
    own = addMatrix(db, ambito="INSTITUCION", idInstitucion=team.id)
    addMatrix(db)  # global
    assert glucose(db, team.operator, created.idPerfilMedicion, dev, condicionComida="AYUNO").matriz.idMatriz == own.idMatriz


# --- Referencia capilar -------------------------------------------------------------------------------------


def test_referencia_capilar_separada_de_la_glucosa_estimada(db, mails, consumer, monkeypatch):
    user, profileId = consumer
    addMatrix(db)
    monkeypatch.setattr(measurements, "glucoseEstimator", lambda *a: (Decimal("95"), "g-1"))
    started = glucose(db, user, profileId, device(db), condicionComida="AYUNO")
    request = CapillaryReferenceRequest(glucosaReferencia=Decimal("101"), fechaHoraReferencia=nowForDb(),
                                        marcaGlucometro="OneTouch")
    expectError("MEDICION_ESTADO_INVALIDO", measurements.registerCapillaryReference, db, user, started.idMedicion, request)
    measurements.addSamples(db, user, started.idMedicion, samples())
    measurements.finishMeasurement(db, user, started.idMedicion, MeasurementFinish())
    detail = measurements.registerCapillaryReference(db, user, started.idMedicion, request)
    assert detail.referenciaCapilar.glucosaReferencia == Decimal("101") and detail.glucosaEstimada == Decimal("95")
    expectError("REFERENCIA_EXISTENTE", measurements.registerCapillaryReference, db, user, started.idMedicion, request)
    assert db.scalar(select(func.count()).select_from(CapillaryReferenceMeasurement)) == 1


def test_la_referencia_capilar_no_aplica_a_oximetria_ni_a_fechas_futuras(db, mails, consumer):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    request = CapillaryReferenceRequest(glucosaReferencia=Decimal("100"), fechaHoraReferencia=nowForDb())
    expectError("MEDICION_ESTADO_INVALIDO", measurements.registerCapillaryReference, db, user, done.idMedicion, request)


# --- Conservación de valores históricos y trazabilidad --------------------------------------------------------


def test_los_valores_historicos_no_cambian_al_modificar_el_perfil_o_el_dispositivo(db, mails, consumer):
    user, profileId = consumer
    dev = device(db, firmware="1.0.0")
    done = completeOximetry(db, user, profileId, dev)
    dev.versionFirmware = "2.0.0"
    user.fechaNacimiento = date(1960, 1, 1)
    db.commit()
    again = measurements.getMeasurement(db, user, done.idMedicion)
    assert (again.versionFirmwareAlMomento, again.edadAlMomento, again.sexoModelo) == (
        "1.0.0", done.edadAlMomento, "FEMENINO")


def test_la_transferencia_no_cambia_las_mediciones_ni_su_autoria(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    done = completeOximetry(db, team.operator, created.idPerfilMedicion, dev)
    other = addOperator(db, team)
    otherUser = db.get(User, other.idUsuarioInvitado)
    item = transfers.requestTransfer(db, team.operator, team.id, created.idPerfilMedicion, other.idInstitucionUsuario, None)
    transfers.acceptTransfer(db, otherUser, team.id, item.idTransferenciaPerfil)
    after = measurements.getMeasurement(db, otherUser, done.idMedicion)
    assert (after.spo2, after.versionFirmwareAlMomento, after.edadAlMomento, after.fechaHoraInicio) == (
        done.spo2, done.versionFirmwareAlMomento, done.edadAlMomento, done.fechaHoraInicio)
    assert after.puedeOperar is False  # terminada
    # El operador anterior ya no tiene acceso a las mediciones (ni siquiera a las que él hizo): autoría histórica no es autorización.
    expectError("MEDICIONES_NO_AUTORIZADAS", oximetry, db, team.operator, created.idPerfilMedicion, dev)
    expectError("MEDICIONES_NO_AUTORIZADAS", measurements.getMeasurement, db, team.operator, done.idMedicion)
    assert oximetry(db, otherUser, created.idPerfilMedicion, dev).puedeOperar
    # La autoría original sigue en Auditoría con el operador que la inició.
    first = [a for a in audits(db, "INICIAR_MEDICION") if a.idRegistro == done.idMedicion][0]
    assert first.idUsuario == team.operator.idUsuario
    assert first.idRelacionado == relationOf(db, team, team.operator).idInstitucionUsuario


# --- Historial individual e institucional -------------------------------------------------------------------


def test_historial_individual_con_filtros_orden_y_estadisticas(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    completeOximetry(db, user, profileId, dev, spo2="95", hr=60)
    completeOximetry(db, user, profileId, dev, spo2="99", hr=80)
    cancelled = oximetry(db, user, profileId, dev)
    measurements.cancelMeasurement(db, user, cancelled.idMedicion)
    full = measurements.listOwnHistory(db, user)
    assert full.total == 3 and [m.estadoMedicion for m in full.items][-1] in ("COMPLETADA", "CANCELADA")
    assert full.items[0].fechaHoraInicio >= full.items[-1].fechaHoraInicio  # más reciente primero
    ascending = measurements.listOwnHistory(db, user, orden="asc")
    assert ascending.items[0].fechaHoraInicio <= ascending.items[-1].fechaHoraInicio
    assert measurements.listOwnHistory(db, user, estado="COMPLETADA").total == 2
    assert measurements.listOwnHistory(db, user, estado="CANCELADA").total == 1
    assert measurements.listOwnHistory(db, user, modo="GLUCOSA_EXPERIMENTAL").total == 0
    assert measurements.listOwnHistory(db, user, desde=date.today(), hasta=date.today()).total == 3
    assert measurements.listOwnHistory(db, user, hasta=date.today() - timedelta(days=1)).total == 0
    assert measurements.listOwnHistory(db, user, tamanioPagina=1).items.__len__() == 1
    expectError("PERIODO_INVALIDO", measurements.listOwnHistory, db, user, desde=date.today(),
                hasta=date.today() - timedelta(days=1))
    stats = measurements.ownStatistics(db, user, 7)
    assert stats.cantidadMediciones == 2  # solo COMPLETADA
    assert (stats.spo2.minimo, stats.spo2.maximo, stats.spo2.promedio) == pytest.approx((95.0, 99.0, 97.0), abs=0.3)
    assert (stats.frecuenciaCardiaca.minimo, stats.frecuenciaCardiaca.maximo) == (60.0, 80.0)
    assert len(stats.serieDiaria) == 1 and stats.glucosa.cantidad == 0
    expectError("PERIODO_INVALIDO", measurements.ownStatistics, db, user, 365)
    assert measurements.ownStatistics(db, user, 30, date.today(), date.today()).cantidadMediciones == 2


def test_historial_propio_sin_perfil_esta_vacio(db, mails):
    user = makeUser(db, email="nuevo@example.com", usuario="nuevo")
    assert measurements.listOwnHistory(db, user).total == 0
    assert measurements.ownStatistics(db, user).cantidadMediciones == 0


def test_historial_institucional_autorizado_y_estadisticas_del_paciente(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    completeOximetry(db, team.operator, created.idPerfilMedicion, dev, spo2="94", hr=65)
    other = addOperator(db, team)
    otherUser = db.get(User, other.idUsuarioInvitado)
    page = measurements.listPatientHistory(db, team.operator, team.id, created.idPerfilMedicion)  # el responsable vigente
    assert page.total == 1 and page.items[0].dispositivo == dev.codigoDispositivo
    # Nadie más: ni otro operador, ni el moderador, ni el propietario (el rol administrativo no autoriza salud individual).
    for actor in (otherUser, team.moderator, team.owner):
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.listPatientHistory, db, actor, team.id, created.idPerfilMedicion)
        expectError("MEDICIONES_NO_AUTORIZADAS", measurements.patientStatistics, db, actor, team.id, created.idPerfilMedicion, 30)
    stats = measurements.patientStatistics(db, team.operator, team.id, created.idPerfilMedicion, 30)
    assert stats.cantidadMediciones == 1 and stats.spo2.promedio == 94.0
    assert measurements.listPatientHistory(db, team.operator, team.id, created.idPerfilMedicion, estado="INVALIDA").total == 0


def test_indicadores_institucionales_no_identifican_pacientes(db, mails, team):
    created = patients.createPatient(db, team.operator, team.id, patientData())
    dev = device(db, institucion=team.id)
    completeOximetry(db, team.operator, created.idPerfilMedicion, dev, spo2="96")
    # Con un solo paciente medido (menos que el mínimo) los promedios de salud no se informan: identificarían a una persona.
    small = measurements.institutionIndicators(db, team.moderator, team.id)
    assert (small.pacientesActivos, small.operadoresActivos, small.medicionesTotal) == (1, 1, 1)
    assert small.completadas["spo2"].promedio is None
    for number in range(4):  # llega al mínimo de pacientes distintos
        extra = patients.createPatient(db, team.operator, team.id, patientData(dni=f"3011122{number}", nombre=f"p{number}", apellido="x"))
        completeOximetry(db, team.operator, extra.idPerfilMedicion, dev, spo2="96")
    indicators = measurements.institutionIndicators(db, team.moderator, team.id)
    assert (indicators.pacientesActivos, indicators.operadoresActivos, indicators.medicionesTotal) == (5, 1, 5)
    assert indicators.medicionesPorEstado == {"COMPLETADA": 5} and indicators.medicionesPorModo == {"OXIMETRIA": 5}
    assert indicators.completadas["spo2"].promedio == pytest.approx(96.0, abs=0.3)
    dumped = indicators.model_dump_json()
    for secret in ("Juan", "Pérez", "20111222", str(created.idPerfilMedicion), created.identificadorPseudonimo):
        assert secret not in dumped
    expectError("PERMISO_INSUFICIENTE", measurements.institutionIndicators, db, team.operator, team.id)


# --- Aislamiento y grupos familiares ----------------------------------------------------------------------------


def test_otra_cuenta_no_accede_a_una_medicion_por_consulta_directa(db, mails, consumer, team):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    stranger = makeUser(db, email="otra@example.com", usuario="otra")
    for actor in (stranger, team.owner, team.operator):
        expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, actor, done.idMedicion)
        expectError("MEDICION_NO_ENCONTRADA", measurements.cancelMeasurement, db, actor, done.idMedicion)
        expectError("MEDICION_NO_ENCONTRADA", measurements.addSamples, db, actor, done.idMedicion, samples())
    expectError("PERFIL_NO_ENCONTRADO", oximetry, db, stranger, profileId, device(db))
    expectError("PERFIL_NO_ENCONTRADO", measurements.listDevices, db, stranger, profileId)
    expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, user, uuid.uuid4())
    # Un perfil individual tampoco se consulta por el historial institucional.
    expectError("PACIENTE_NO_ENCONTRADO", measurements.listPatientHistory, db, team.operator, team.id, profileId)


def test_grupos_el_miembro_ve_lo_compartido_pero_no_por_la_api_de_mediciones(db, mails):
    ana, beto = person(db, "ana"), person(db, "beto")
    group = createGroup(db, ana)
    join(db, ana, group.idGrupo, beto)
    betoProfile = measurements.getOwnProfile(db, beto).idPerfilMedicion
    dev = device(db)
    done = completeOximetry(db, beto, betoProfile, dev, spo2="98")
    link = groupLinkOf(db, group.idGrupo, beto).idGrupoUsuario
    # Sin permisos: ni última medición, ni historial, ni estadísticas.
    for fn in (groups.sharedLatest, groups.sharedHistory, groups.sharedStatistics):
        expectError("DATOS_NO_COMPARTIDOS", fn, db, ana, group.idGrupo, link)
    # Acceso directo a la API de mediciones: la pertenencia al grupo no da propiedad.
    expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, ana, done.idMedicion)
    # Solo última medición: devuelve únicamente la última; el historial sigue bloqueado.
    share(db, beto, group.idGrupo, comparteUltimaMedicion=True)
    assert float(groups.sharedLatest(db, ana, group.idGrupo, link).medicion.spo2) == pytest.approx(98.0, abs=0.3)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, ana, group.idGrupo, link)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedStatistics, db, ana, group.idGrupo, link)
    # Historial: registros, y las estadísticas salen del mismo permiso y del mismo cálculo.
    share(db, beto, group.idGrupo, comparteHistorial=True)
    assert groups.sharedHistory(db, ana, group.idGrupo, link).total == 1
    shared = groups.sharedStatistics(db, ana, group.idGrupo, link, 7)
    assert shared.model_dump(exclude={"puntos"}) == measurements.ownStatistics(db, beto, 7).model_dump(exclude={"puntos"})
    assert len(shared.puntos) == 1 and shared.puntos[0].fecha is not None  # la medición con su fecha y hora, para graficarla
    # Las mediciones inválidas o canceladas nunca se comparten como resultados.
    cancelled = oximetry(db, beto, betoProfile, dev)
    measurements.cancelMeasurement(db, beto, cancelled.idMedicion)
    assert groups.sharedHistory(db, ana, group.idGrupo, link).total == 1


# --- Paciente con datos opcionales (documento, fecha de nacimiento y sexo) ----------------------------------


def test_un_paciente_se_registra_sin_documento_fecha_de_nacimiento_ni_sexo(db, mails, team):
    from app.schemas.measurementProfile import PatientCreateRequest
    created = patients.createPatient(db, team.operator, team.id, PatientCreateRequest(nombre="ana", apellido="paz"))
    assert (created.dni, created.fechaNacimiento, created.edad, created.sexoModelo) == (None, None, None, None)
    stored = reload(db, MeasurementProfile, created.idPerfilMedicion)
    assert stored.tipoPerfil == "INSTITUCIONAL" and stored.sexoModelo is None and stored.identificadorPseudonimo
    # Los textos vacíos del formulario cuentan como «no informado».
    blank = PatientCreateRequest(nombre="Luz", apellido="Gil", dni="  ", fechaNacimiento="", sexoModelo="")
    assert (blank.dni, blank.fechaNacimiento, blank.sexoModelo) == (None, None, None)
    # Dos pacientes sin documento no chocan entre sí.
    patients.createPatient(db, team.operator, team.id, blank)


def test_si_se_informan_siguen_validandose(db):
    from app.schemas.measurementProfile import PatientCreateRequest
    for bad in ({"dni": "1"}, {"fechaNacimiento": "2999-01-01"}, {"sexoModelo": "otro"}):
        with pytest.raises(ValidationError):
            PatientCreateRequest(nombre="ana", apellido="paz", **bad)


def test_un_paciente_sin_edad_ni_sexo_se_mide_por_oximetria_y_la_glucosa_los_exige(db, mails, team):
    from app.schemas.measurementProfile import PatientCreateRequest, PatientUpdateRequest
    created = patients.createPatient(db, team.operator, team.id, PatientCreateRequest(nombre="ana", apellido="paz"))
    dev = device(db, institucion=team.id)
    addMatrix(db)
    # Sin fecha de nacimiento ni sexo: la oximetría se puede medir y la medición conserva esos datos como no definidos.
    started = oximetry(db, team.operator, created.idPerfilMedicion, dev)
    assert started.estadoMedicion == "PENDIENTE" and started.edadAlMomento is None and started.sexoModelo is None
    measurements.cancelMeasurement(db, team.operator, started.idMedicion)
    # La glucosa experimental depende de la regla (edad y sexo): sin ellos no se inicia, y no crea nada.
    expectError("DATOS_PACIENTE_INCOMPLETOS", glucose, db, team.operator, created.idPerfilMedicion, dev, condicionComida="AYUNO")
    patients.updatePatient(db, team.operator, team.id, created.idPerfilMedicion,
                           PatientUpdateRequest(fechaNacimiento="1985-03-04"))
    expectError("DATOS_PACIENTE_INCOMPLETOS", glucose, db, team.operator, created.idPerfilMedicion, dev, condicionComida="AYUNO")
    patients.updatePatient(db, team.operator, team.id, created.idPerfilMedicion, PatientUpdateRequest(sexoModelo="femenino"))
    full = oximetry(db, team.operator, created.idPerfilMedicion, dev)
    assert full.edadAlMomento is not None and full.sexoModelo == "FEMENINO"
    assert db.scalar(select(func.count()).select_from(Measurement)) == 2  # los intentos de glucosa no crearon nada


def test_sin_sexo_ni_nacimiento_se_puede_medir_oximetria_y_la_glucosa_por_matriz_sigue_pidiendolos(db, mails):
    user = makeUser(db, email="solo@example.com", usuario="solo")
    user.sexo = user.fechaNacimiento = None
    db.commit()
    own = measurements.getOwnProfile(db, user)
    assert own.perfilDisponible and own.datosRecomendados == ["fechaNacimiento", "sexo"]
    done = completeOximetry(db, user, own.idPerfilMedicion, device(db))
    assert done.estadoMedicion == "COMPLETADA" and (done.edadAlMomento, done.sexoModelo) == (None, None)
    # Solo la estimación de glucosa por matriz necesita la edad y el sexo (la regla se elige por ellos).
    expectError("DATOS_PACIENTE_INCOMPLETOS", glucose, db, user, own.idPerfilMedicion, device(db), condicionComida="AYUNO")

# --- Inserción de muestras por tandas (rendimiento) ------------------------------------------------------------------


def test_las_muestras_se_insertan_por_tandas_y_no_una_por_una(db, mails, consumer):
    """400 muestras = 1 INSERT de varias filas (antes 400 INSERT: el ORM no agrupa filas cuya clave genera el servidor). Siguen siendo atómicas."""
    import re

    from sqlalchemy import event, func, select
    from sqlalchemy.engine import Engine

    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    inserts = []
    pattern = re.compile(r'^\s*INSERT\s+INTO\s+\S*MuestraSensor', re.IGNORECASE)
    listener = lambda conn, cursor, statement, parameters, context, executemany: inserts.append(statement) if pattern.match(statement) else None  # noqa: E731
    event.listen(Engine, "before_cursor_execute", listener)
    try:
        batch = signalSamples(72, 97.5, seconds=50)  # 20 Hz × 50 s = 1000 muestras
        measurements.addSamples(db, user, started.idMedicion, batch)
    finally:
        event.remove(Engine, "before_cursor_execute", listener)
    stored = db.scalar(select(func.count()).select_from(SensorSample).where(SensorSample.idMedicion == started.idMedicion))
    assert stored == len(batch.muestras) == 1000
    assert len(inserts) == 3  # ceil(1000 / 400)


def test_una_muestra_repetida_revierte_toda_la_tanda(db, mails, consumer):
    from sqlalchemy import func, select

    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.addSamples(db, user, started.idMedicion, signalSamples(72, 97.5, seconds=5))
    before = db.scalar(select(func.count()).select_from(SensorSample).where(SensorSample.idMedicion == started.idMedicion))
    # La nueva tanda empieza en la muestra 50 (ya existente) y trae otras nuevas: todo o nada.
    overlapping = signalSamples(72, 97.5, seconds=5, start=50)
    expectError("MUESTRAS_DUPLICADAS", measurements.addSamples, db, user, started.idMedicion, overlapping)
    assert db.scalar(select(func.count()).select_from(SensorSample).where(SensorSample.idMedicion == started.idMedicion)) == before
