# El modo elegido (OXIMETRIA / GLUCOSA_EXPERIMENTAL) se conserva en todo el ciclo de una sesión con el dispositivo, y el detalle de una
# medición de glucosa muestra su matriz de referencia con las reglas REALES (sin elegir un sexo ni una edad por la persona).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_glucose_mode.py -v

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.acquisition.telemetry import hub
from app.core.exceptions import AuthError
from app.models.matrix import Matrix
from app.models.matrixRule import MatrixRule
from app.models.measurement import Measurement
from app.schemas.acquisition import TelemetrySessionStart
from app.services import measurement as measurements
from app.services import schemaCompat
from app.services import telemetry as telemetryService
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import addMatrix, consumer, device, expectError  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, freshHub, line, startFor  # noqa: F401

GLUCOSE = "GLUCOSA_EXPERIMENTAL"


def addRule(db, matrix, sexo, code, edad=(18, 80), condicion="AYUNO", low="70", high="110", minutos=(None, None)):
    db.add(MatrixRule(idReglaMatriz=uuid.uuid4(), idMatriz=matrix.idMatriz, codigoRegla=code, sexoModelo=sexo, edadDesde=edad[0],
                      edadHasta=edad[1], condicionComida=condicion, minutosComidaMin=minutos[0], minutosComidaMax=minutos[1],
                      glucosaMinReferencia=Decimal(low), glucosaMaxReferencia=Decimal(high)))
    db.commit()


def twoSexMatrix(db):
    matrix = addMatrix(db, rule=False)
    addRule(db, matrix, "FEMENINO", "F1", low="70", high="105")
    addRule(db, matrix, "MASCULINO", "M1", low="75", high="115")
    return matrix


def measureAndSave(db, user, profileId, bridge, mode, seconds=9, **fields):
    dev = device(db, codigo=CODE)
    bridge.seconds(1, **fields)
    started = startFor(db, user, profileId, dev, modoMedicion=mode)
    bridge.seconds(seconds, **fields)
    return started, telemetryService.saveSession(db, user)


def stored(db, idMedicion):
    db.expire_all()
    return db.get(Measurement, idMedicion)


# --- 1 a 5: el modo se conserva -------------------------------------------------------------------------------------------------


def test_1_oximetria_se_guarda_como_oximetria(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    started, saved = measureAndSave(db, user, profileId, bridge, "OXIMETRIA")
    assert started.modoMedicion == saved.modoMedicion == "OXIMETRIA"
    assert stored(db, saved.idMedicion).modoMedicion == "OXIMETRIA" and saved.referenciaGlucosa is None


def test_2_glucosa_experimental_conserva_su_modo_de_principio_a_fin(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    started, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE)
    assert started.modoMedicion == GLUCOSE and started.estadoMedicion == "ADQUIRIENDO"
    assert saved.modoMedicion == GLUCOSE and saved.estadoMedicion == "COMPLETADA"
    row = stored(db, saved.idMedicion)
    assert row.modoMedicion == GLUCOSE and row.estadoMedicion == "COMPLETADA"
    # Se recupera y aparece en el historial con el mismo modo, y el filtro por modo lo encuentra.
    assert measurements.getMeasurement(db, user, saved.idMedicion).modoMedicion == GLUCOSE
    assert [i.modoMedicion for i in measurements.listOwnHistory(db, user).items] == [GLUCOSE]
    assert [i.idMedicion for i in measurements.listOwnHistory(db, user, modo=GLUCOSE).items] == [saved.idMedicion]
    assert measurements.listOwnHistory(db, user, modo="OXIMETRIA").total == 0


def test_el_modo_viaja_en_el_estado_en_vivo_y_en_el_contrato(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    startFor(db, user, profileId, dev, modoMedicion="glucosa_experimental")  # se normaliza
    assert telemetryService.status(db, user)["sesion"]["modo"] == GLUCOSE
    with pytest.raises(ValidationError):
        TelemetrySessionStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo, modoMedicion="OTRO")
    assert TelemetrySessionStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo).modoMedicion == "OXIMETRIA"


def test_4_la_glucosa_demo_no_se_convierte_en_una_estimacion(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="117.0", origen="DEMO")
    row = stored(db, saved.idMedicion)
    # Resultado del firmware con su origen; la estimación del servidor queda vacía (no se copia el valor DEMO).
    assert (row.origenGlucosa, float(row.glucosaDispositivo)) == ("DEMO", 117.0)
    assert row.glucosaEstimada is None and schemaCompat.ruleIdOf(db, saved.idMedicion) is None
    assert saved.esDemo and saved.referenciaGlucosa.esDemo and saved.referenciaGlucosa.origen == "DEMO"
    # Y sigue fuera de las estadísticas experimentales.
    assert measurements.ownEvolution(db, user, 7).puntos == []
    assert [p.idMedicion for p in measurements.ownEvolution(db, user, 7, origen="DEMO").puntos] == [saved.idMedicion]


def test_5_los_resultados_se_persisten_con_su_origen(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="121.5", origen="EXPERIMENTAL")
    row = stored(db, saved.idMedicion)
    assert (row.origenGlucosa, float(row.glucosaDispositivo), row.unidadGlucosa) == ("EXPERIMENTAL", 121.5, "mg/dL")
    assert row.spo2 is not None and row.frecuenciaCardiaca is not None and row.indiceOptico is not None  # métricas complementarias
    assert row.modoMedicion == GLUCOSE and row.glucosaEstimada is None


def test_glucosa_sin_calibrar_no_se_puede_guardar_ni_cambia_de_modo(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    fields = {"glu": "NA", "origen": "SIN_CALIBRAR"}
    bridge.seconds(1, **fields)
    started = startFor(db, user, profileId, dev, modoMedicion=GLUCOSE)
    bridge.seconds(9, **fields)
    stability = telemetryService.status(db, user)["sesion"]["estabilidad"]
    assert stability["estable"] is False and stability["motivo"] == "GLUCOSA_NO_DISPONIBLE"
    assert "Estimación de glucosa no disponible" in stability["mensaje"]
    error = expectError("LECTURA_NO_ESTABLE", telemetryService.saveSession, db, user)
    assert "Oximetría" in error.message
    assert stored(db, started.idMedicion).modoMedicion == GLUCOSE and stored(db, started.idMedicion).estadoMedicion == "ADQUIRIENDO"
    # Cancelar conserva el modo elegido (no se reemplaza en silencio por oximetría).
    telemetryService.cancelSession(db, user)
    assert stored(db, started.idMedicion).modoMedicion == GLUCOSE and hub.session is None


def test_la_glucosa_con_el_dispositivo_no_exige_edad_ni_sexo(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    other = makeUser(db, email="sin@example.com", usuario="sinDatos")
    from app.models.user import User

    db.execute(update(User).where(User.idUsuario == other.idUsuario).values(fechaNacimiento=None, sexo=None))
    db.commit()
    profile = measurements.getOwnProfile(db, other).idPerfilMedicion
    started = startFor(db, other, profile, (bridge.seconds(1), device(db, codigo=CODE))[1], modoMedicion=GLUCOSE)
    assert started.edadAlMomento is None and started.sexoModelo is None and started.modoMedicion == GLUCOSE


# --- Restricciones del esquema (reflejadas en el modelo) -------------------------------------------------------------------------


def insertMeasurement(db, profileId, deviceId, **values):
    base = dict(idMedicion=uuid.uuid4(), idPerfilMedicion=profileId, idDispositivo=deviceId, modoMedicion=GLUCOSE, estadoMedicion="ADQUIRIENDO",
                fechaHoraInicio=nowForDb(), condicionComida="NO_INFORMADA")
    db.add(Measurement(**{**base, **values}))
    db.commit()


def test_11_las_restricciones_admiten_las_combinaciones_validas_y_rechazan_las_falsas(db, mails, consumer):
    user, profileId = consumer
    deviceId = device(db).idDispositivo
    done = dict(estadoMedicion="COMPLETADA", fechaHoraFin=nowForDb() + timedelta(seconds=5))
    # Glucosa completada con el resultado del firmware (origen DEMO o EXPERIMENTAL): válida.
    insertMeasurement(db, profileId, deviceId, **done, origenGlucosa="DEMO", glucosaDispositivo=Decimal("114"), unidadGlucosa="mg/dL")
    insertMeasurement(db, profileId, deviceId, **done, origenGlucosa="EXPERIMENTAL", glucosaDispositivo=Decimal("101"), unidadGlucosa="mg/dL")
    # Glucosa completada SIN ningún resultado: no puede completarse.
    with pytest.raises(IntegrityError):
        insertMeasurement(db, profileId, deviceId, **done)
    db.rollback()
    # Un valor DEMO jamás se copia a la estimación del servidor.
    matrix = addMatrix(db)
    with pytest.raises(IntegrityError):
        insertMeasurement(db, profileId, deviceId, **done, origenGlucosa="DEMO", glucosaDispositivo=Decimal("114"), unidadGlucosa="mg/dL",
                          glucosaEstimada=Decimal("114"), idMatriz=matrix.idMatriz, versionAlgoritmo="x")
    db.rollback()
    # Toda estimación del servidor exige su matriz y su algoritmo (trazabilidad).
    with pytest.raises(IntegrityError):
        insertMeasurement(db, profileId, deviceId, **done, glucosaEstimada=Decimal("100"))
    db.rollback()
    insertMeasurement(db, profileId, deviceId, **done, glucosaEstimada=Decimal("100"), idMatriz=matrix.idMatriz, versionAlgoritmo="algo-1")
    # La oximetría nunca tiene estimación del servidor.
    with pytest.raises(IntegrityError):
        insertMeasurement(db, profileId, deviceId, **done, modoMedicion="OXIMETRIA", glucosaEstimada=Decimal("100"),
                          idMatriz=matrix.idMatriz, versionAlgoritmo="algo-1")
    db.rollback()


# --- 6 a 10: matriz de referencia ------------------------------------------------------------------------------------------------


def setSex(db, idMedicion, sexo=None, edad=None, condicion=None):
    values = {"sexoModelo": sexo, "edadAlMomento": edad}
    if condicion:
        values["condicionComida"] = condicion
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(**values))
    db.commit()


def measureWithMatrix(db, consumer, bridge, **fields):
    user, profileId = consumer
    matrix = twoSexMatrix(db)
    started, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, **fields)
    return user, matrix, started, saved


def test_6_la_matriz_asociada_es_de_referencia_y_no_aplicada_si_el_servidor_no_estimo(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="90.0", origen="EXPERIMENTAL")
    reference = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    assert reference.estado == "REFERENCIA"  # participó como comparación, no en un cálculo
    assert reference.matriz.idMatriz == matrix.idMatriz and reference.matriz.ambito == "GLOBAL" and reference.matriz.version == "1"
    assert reference.valor == 90.0 and reference.unidad == "mg/dL" and reference.origen == "EXPERIMENTAL"
    assert all(group.aplicada is False for group in reference.grupos)


def test_7_con_el_sexo_nulo_se_muestran_ambas_referencias_sin_elegir_ninguna(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="90.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo=None, edad=None)
    reference = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    assert reference.sexoInformado is False and "El sexo no fue informado" in reference.avisoSexo
    assert [g.sexoModelo for g in reference.grupos] == ["FEMENINO", "MASCULINO"]
    # Sin edad no se asigna un intervalo ficticio ni una posición: se listan las reglas reales con sus rangos.
    for group in reference.grupos:
        assert group.reglaSeleccionada is None and group.posicion is None and "no puede seleccionarse" in group.motivoSinSeleccion
        assert [(r.edadDesde, r.edadHasta) for r in group.reglas] == [(18, 80)]
    assert (reference.grupos[0].reglas[0].glucosaMinReferencia, reference.grupos[0].reglas[0].glucosaMaxReferencia) == (70.0, 105.0)
    assert (reference.grupos[1].reglas[0].glucosaMinReferencia, reference.grupos[1].reglas[0].glucosaMaxReferencia) == (75.0, 115.0)
    # Nada se asignó al perfil ni a la medición.
    row = stored(db, saved.idMedicion)
    assert row.sexoModelo is None and schemaCompat.ruleIdOf(db, saved.idMedicion) is None


def test_sexo_nulo_con_edad_y_ayuno_compara_contra_cada_referencia_de_forma_ilustrativa(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="108.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo=None, edad=40, condicion="AYUNO")
    female, male = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos
    assert female.reglaSeleccionada.codigo == "F1" and female.posicion == "POR_ENCIMA"  # 108 > 105
    assert male.reglaSeleccionada.codigo == "M1" and male.posicion == "DENTRO"  # 75 <= 108 <= 115
    assert female.aplicada is False and male.aplicada is False


def test_8_con_el_sexo_definido_se_muestra_solo_su_regla_y_no_se_modifica_nada(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="60.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo="MASCULINO", edad=30, condicion="AYUNO")
    reference = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    assert reference.avisoSexo is None and [g.sexoModelo for g in reference.grupos] == ["MASCULINO"]
    group = reference.grupos[0]
    assert group.reglaSeleccionada.codigo == "M1" and group.posicion == "POR_DEBAJO" and group.aplicada is False
    assert reference.edad == 30 and reference.condicionComida == "AYUNO"


def test_9_sin_regla_aplicable_no_se_elige_una_arbitraria(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="90.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo="FEMENINO", edad=10, condicion="AYUNO")  # fuera del rango 18–80
    group = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos[0]
    assert group.reglas == [] and group.reglaSeleccionada is None and group.posicion is None
    assert group.motivoSinSeleccion == "Referencia no disponible."
    # Sin dato de alimentación tampoco se elige: hay que ver todas las condiciones.
    setSex(db, saved.idMedicion, sexo="FEMENINO", edad=40, condicion="NO_INFORMADA")
    group = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos[0]
    assert group.reglaSeleccionada is None and "alimentación" in group.motivoSinSeleccion


def test_una_medicion_sin_matriz_vigente_muestra_sin_matriz(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE)  # no hay ninguna matriz activa
    reference = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    assert reference.estado == "SIN_MATRIZ" and reference.matriz is None and reference.grupos == []


def test_10_una_version_posterior_de_la_matriz_no_cambia_la_referencia_guardada(db, mails, consumer, bridge, clock):
    user, matrix, started, saved = measureWithMatrix(db, consumer, bridge, glu="90.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo="FEMENINO", edad=40, condicion="AYUNO")
    before = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    # Se publica otra versión (activa) y se archiva la anterior: la medición sigue mostrando la matriz con la que se hizo.
    db.execute(update(Matrix).where(Matrix.idMatriz == matrix.idMatriz).values(estado="ARCHIVADA", fechaVigenciaHasta=date.today() - timedelta(days=1)))
    db.commit()
    newer = addMatrix(db, rule=False)
    addRule(db, newer, "FEMENINO", "F2", low="10", high="20")
    after = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    assert after.matriz.idMatriz == matrix.idMatriz == before.matriz.idMatriz
    assert after.grupos[0].reglaSeleccionada.codigo == "F1" and after.grupos[0].posicion == before.grupos[0].posicion


def test_la_medicion_manual_con_matriz_conserva_la_regla_realmente_aplicada(db, mails, consumer):
    user, profileId = consumer
    matrix = addMatrix(db, rule=True)  # regla FEMENINO 18–80 en ayunas
    started = measurements.startMeasurement(db, user, measurements.MeasurementStart(
        idPerfilMedicion=profileId, idDispositivo=device(db).idDispositivo, modoMedicion=GLUCOSE, condicionComida="AYUNO",
        edadAlMomento=40, sexoModelo="FEMENINO"))
    row = stored(db, started.idMedicion)
    assert row.idMatriz == matrix.idMatriz and schemaCompat.ruleIdOf(db, started.idMedicion) == db.scalar(select(MatrixRule.idReglaMatriz).where(MatrixRule.idMatriz == matrix.idMatriz))
    assert row.modoMedicion == GLUCOSE


def test_http_el_detalle_expone_la_matriz_solo_en_modo_glucosa(api, db, mails, consumer, bridge, clock):
    user, profileId = consumer
    twoSexMatrix(db)
    _, glucose = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="95.0", origen="EXPERIMENTAL")
    _, oximetry = measureAndSave(db, user, profileId, bridge, "OXIMETRIA")
    client = api(user)
    body = client.get(f"/api/v1/measurements/{glucose.idMedicion}").json()
    assert body["modoMedicion"] == GLUCOSE and body["referenciaGlucosa"]["estado"] == "REFERENCIA"
    assert {g["sexoModelo"] for g in body["referenciaGlucosa"]["grupos"]} <= {"FEMENINO", "MASCULINO"}
    assert client.get(f"/api/v1/measurements/{oximetry.idMedicion}").json()["referenciaGlucosa"] is None
    listing = client.get("/api/v1/measurements").json()["items"]
    assert sorted(item["modoMedicion"] for item in listing) == [GLUCOSE, "OXIMETRIA"]
    assert client.get(f"/api/v1/measurements?modo={GLUCOSE}").json()["total"] == 1


# --- Regresión: la matriz REAL trae reglas sin rango de edad (NULL) y reglas para «sexo no informado» ---------------------------------


def realLikeMatrix(db):
    matrix = addMatrix(db, rule=False)
    addRule(db, matrix, "MASCULINO", "M_N_U", edad=(None, None), condicion="NO_INFORMADA", low="70", high="180")
    addRule(db, matrix, "FEMENINO", "F_N65", edad=(65, 130), condicion="NO_INFORMADA", low="70", high="180")
    addRule(db, matrix, "NO_INFORMADO", "NI_N_U", edad=(None, None), condicion="NO_INFORMADA", low="70", high="180")
    addRule(db, matrix, "NO_INFORMADO", "NI_A18", edad=(18, 64), condicion="AYUNO", low="80", high="130")
    return matrix


def test_las_reglas_con_edad_vacia_no_rompen_el_detalle_y_se_leen_como_sin_limite(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    realLikeMatrix(db)
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="115.0", origen="DEMO")
    setSex(db, saved.idMedicion, sexo="MASCULINO", edad=40, condicion="NO_INFORMADA")  # antes: TypeError al comparar None <= int
    group = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos[0]
    assert group.reglaSeleccionada.codigo == "M_N_U" and (group.reglaSeleccionada.edadDesde, group.reglaSeleccionada.edadHasta) == (None, None)
    assert group.posicion == "DENTRO"


def test_sin_sexo_ni_edad_se_listan_las_referencias_y_la_prevista_para_sexo_no_informado(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    realLikeMatrix(db)
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="115.0", origen="DEMO")
    setSex(db, saved.idMedicion, sexo=None, edad=None, condicion="NO_INFORMADA")
    reference = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa
    groups = {g.sexoModelo: g for g in reference.grupos}
    assert list(groups) == ["FEMENINO", "MASCULINO", "NO_INFORMADO"] and "El sexo no fue informado" in reference.avisoSexo
    # La regla de la matriz prevista para edad y sexo no especificados es la única sin rango: se muestra, sin inventar nada.
    assert groups["NO_INFORMADO"].reglaSeleccionada.codigo == "NI_N_U" and groups["NO_INFORMADO"].posicion == "DENTRO"
    # Femenina solo tiene una regla con rango de edad: sin edad no se elige.
    assert groups["FEMENINO"].reglaSeleccionada is None and [r.codigo for r in groups["FEMENINO"].reglas] == ["F_N65"]
    # Masculina: la regla sin rango de edad es la prevista para edad no especificada.
    assert groups["MASCULINO"].reglaSeleccionada.codigo == "M_N_U"


def test_con_la_edad_conocida_se_prefiere_la_franja_a_la_regla_de_edad_no_especificada(db, mails, consumer, bridge, clock):
    """Como en la matriz real: por sexo y alimentación hay una regla sin rango (_U) y reglas por franja (18–64, 65+)."""
    user, profileId = consumer
    matrix = addMatrix(db, rule=False)
    addRule(db, matrix, "MASCULINO", "M_A_U", edad=(None, None), condicion="AYUNO", low="70", high="180")
    addRule(db, matrix, "MASCULINO", "M_A18", edad=(18, 64), condicion="AYUNO", low="80", high="130")
    addRule(db, matrix, "MASCULINO", "M_A65", edad=(65, 130), condicion="AYUNO", low="80", high="130")
    _, saved = measureAndSave(db, user, profileId, bridge, GLUCOSE, glu="150.0", origen="EXPERIMENTAL")
    setSex(db, saved.idMedicion, sexo="MASCULINO", edad=40, condicion="AYUNO")
    group = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos[0]
    assert group.reglaSeleccionada.codigo == "M_A18" and group.posicion == "POR_ENCIMA"  # 150 > 130
    setSex(db, saved.idMedicion, sexo="MASCULINO", edad=None, condicion="AYUNO")  # sin edad: la prevista para edad no especificada
    group = measurements.getMeasurement(db, user, saved.idMedicion).referenciaGlucosa.grupos[0]
    assert group.reglaSeleccionada.codigo == "M_A_U" and group.posicion == "DENTRO"
