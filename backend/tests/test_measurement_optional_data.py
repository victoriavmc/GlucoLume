# Edad y sexo OPCIONALES en el módulo de Mediciones: ni la cuenta, ni el perfil, ni la medición los exigen, y se pueden informar
# solo para UNA medición sin tocar los datos personales.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_optional_data.py -v
#
# Prioridad: informado en la medición > perfil de medición (que toma los datos de la cuenta) > NULL. Nunca se inventan valores.

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models.measurementProfile import MeasurementProfile
from app.models.user import User
from app.schemas.measurement import MeasurementStart
from app.schemas.user import UserProfileUpdate
from app.services import measurement as measurements
from app.services import user as userService
from app.services.measurementProfile import calculateAge
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import addMatrix, completeOximetry, device, expectError, glucose, noEstimator, oximetry  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, freshHub, startFor  # noqa: F401

BIRTH = date(1990, 5, 17)


def person(db, *, birth=None, sex=None, email="persona@example.com", usuario="persona"):
    user = makeUser(db, email=email, usuario=usuario)
    user.fechaNacimiento, user.sexo = birth, sex
    db.commit()
    return user, measurements.getOwnProfile(db, user).idPerfilMedicion


def started(db, user, profileId, **extra):
    return oximetry(db, user, profileId, device(db), **extra)


def context(measurement):
    return measurement.edadAlMomento, measurement.sexoModelo


# --- Escenarios obligatorios ---------------------------------------------------------------------------------------------------


def test_1_sin_fecha_de_nacimiento_ni_sexo_puede_iniciar_una_medicion(db, mails):
    user, profileId = person(db)
    assert context(started(db, user, profileId)) == (None, None)  # NULL: ni edad 0 ni un sexo por defecto


def test_2_con_fecha_de_nacimiento_pero_sin_sexo_puede_medir(db, mails):
    user, profileId = person(db, birth=BIRTH)
    assert context(started(db, user, profileId)) == (calculateAge(BIRTH, nowForDb().date()), None)


def test_3_con_sexo_pero_sin_fecha_de_nacimiento_puede_medir(db, mails):
    user, profileId = person(db, sex="FEMENINO")
    assert context(started(db, user, profileId)) == (None, "FEMENINO")


def test_4_con_ambos_datos_los_recupera_automaticamente(db, mails):
    user, profileId = person(db, birth=BIRTH, sex="MASCULINO")
    assert context(started(db, user, profileId)) == (calculateAge(BIRTH, nowForDb().date()), "MASCULINO")


def test_5_sin_datos_pero_informando_solo_la_edad_puede_medir(db, mails):
    user, profileId = person(db)
    assert context(started(db, user, profileId, edadAlMomento=5)) == (5, None)
    other, otherProfile = person(db, email="otra@example.com", usuario="otra")
    assert context(started(db, other, otherProfile, edadAlMomento=60)) == (60, None)


def test_6_sin_datos_pero_informando_solo_el_sexo_puede_medir(db, mails):
    user, profileId = person(db)
    assert context(started(db, user, profileId, sexoModelo="masculino")) == (None, "MASCULINO")


def test_7_dejando_ambos_campos_vacios_no_hay_bloqueos(db, mails):
    user, profileId = person(db)
    # Lo que envía el formulario con los campos vacíos: cadenas vacías o nulos explícitos.
    for blank in ({"edadAlMomento": "", "sexoModelo": ""}, {"edadAlMomento": None, "sexoModelo": None}, {}):
        done = completeOximetry(db, user, profileId, device(db)) if not blank else started(db, user, profileId, **blank)
        assert context(done) == (None, None)
        if done.estadoMedicion not in ("COMPLETADA", "CANCELADA"):
            measurements.cancelMeasurement(db, user, done.idMedicion)


def test_8_una_edad_distinta_de_la_calculada_afecta_solo_a_esa_medicion(db, mails):
    user, profileId = person(db, birth=BIRTH, sex="FEMENINO")
    computed = calculateAge(BIRTH, nowForDb().date())
    first = started(db, user, profileId, edadAlMomento=computed + 7, sexoModelo="MASCULINO")
    assert context(first) == (computed + 7, "MASCULINO")  # el valor explícito gana, solo para esta medición
    # Los datos personales y el perfil NO cambian por haberlo informado.
    stored = reload(db, User, user.idUsuario)
    profile = reload(db, MeasurementProfile, profileId)
    assert (stored.fechaNacimiento, stored.sexo) == (BIRTH, "FEMENINO")
    assert (profile.fechaNacimiento, profile.sexoModelo) == (BIRTH, "FEMENINO")
    measurements.cancelMeasurement(db, user, first.idMedicion)
    # La medición siguiente, sin informar nada, vuelve a usar el perfil.
    assert context(started(db, user, profileId)) == (computed, "FEMENINO")


def test_9_una_medicion_anterior_conserva_su_edad_y_sexo_aunque_cambie_el_perfil(db, mails):
    user, profileId = person(db, birth=BIRTH, sex="FEMENINO")
    before = completeOximetry(db, user, profileId, device(db))
    userService.updateProfile(db, user, UserProfileUpdate(fechaNacimiento="1970-01-01", sexo="masculino"))
    measurements.getOwnProfile(db, user)  # sincroniza el perfil con los datos nuevos
    after = completeOximetry(db, user, profileId, device(db))
    assert context(measurements.getMeasurement(db, user, before.idMedicion)) == (calculateAge(BIRTH, nowForDb().date()), "FEMENINO")
    assert context(after) == (calculateAge(date(1970, 1, 1), nowForDb().date()), "MASCULINO")


# --- Reglas de borde -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("data", [{"edadAlMomento": 131}, {"edadAlMomento": -1}, {"sexoModelo": "OTRO"}, {"edadAlMomento": "veinte"}])
def test_los_valores_informados_se_validan_pero_nunca_se_exigen(db, mails, data):
    base = {"idPerfilMedicion": "00000000-0000-4000-8000-000000000001", "idDispositivo": "00000000-0000-4000-8000-000000000002"}
    with pytest.raises(ValidationError):
        MeasurementStart(**base, **data)
    assert MeasurementStart(**base).edadAlMomento is None and MeasurementStart(**base).sexoModelo is None


def test_no_se_inventan_valores_aunque_el_perfil_este_vacio(db, mails):
    user, profileId = person(db)
    measurement = started(db, user, profileId)
    assert measurement.edadAlMomento is None and measurement.sexoModelo is None
    profile = measurements.getOwnProfile(db, user)
    assert (profile.edad, profile.fechaNacimiento, profile.sexoModelo) == (None, None, None)
    assert profile.datosFaltantes == [] and profile.datosRecomendados == ["fechaNacimiento", "sexo"]


def test_la_edad_cero_es_un_valor_valido_distinto_de_no_informado(db, mails):
    user, profileId = person(db)
    assert context(started(db, user, profileId, edadAlMomento=0)) == (0, None)


def test_la_auditoria_indica_que_se_informaron_pero_no_guarda_los_valores(db, mails):
    from app.models.audit import Audit

    user, profileId = person(db)
    started(db, user, profileId, edadAlMomento=33, sexoModelo="FEMENINO")
    row = db.scalar(select(Audit).where(Audit.accion == "INICIAR_MEDICION"))
    import json

    logged = json.loads(row.datosNuevos)
    assert logged["edadInformadaEnLaMedicion"] is True and logged["sexoInformadoEnLaMedicion"] is True
    assert "edadAlMomento" not in logged and "sexoModelo" not in logged and "FEMENINO" not in row.datosNuevos


# --- Estimación de glucosa por matriz: la única dependencia real ---------------------------------------------------------------


def test_la_glucosa_por_matriz_no_se_estima_sin_edad_y_sexo_pero_se_pueden_informar_en_la_medicion(db, mails):
    user, profileId = person(db)
    addMatrix(db)  # regla FEMENINO, 18 a 80 años, en ayunas
    # Sin datos: no se puede elegir la regla ni se inventa una; el mensaje lo explica y propone alternativas que no los necesitan.
    error = expectError("DATOS_PACIENTE_INCOMPLETOS", glucose, db, user, profileId, device(db), condicionComida="AYUNO")
    assert "no se inventan valores" in error.message and "oximetría" in error.message
    # Informados SOLO para esta medición alcanzan, sin tocar la cuenta.
    done = glucose(db, user, profileId, device(db), condicionComida="AYUNO", edadAlMomento=40, sexoModelo="FEMENINO")
    assert done.estadoMedicion == "PENDIENTE" and context(done) == (40, "FEMENINO") and done.matriz is not None
    assert reload(db, User, user.idUsuario).sexo is None


# --- Medición con el dispositivo (telemetría) ---------------------------------------------------------------------------------------


def test_la_sesion_con_el_dispositivo_acepta_edad_y_sexo_opcionales(db, mails, bridge, clock):
    user, profileId = person(db)
    registered = device(db, codigo=CODE)
    bridge.seconds(1)
    assert startFor(db, user, profileId, registered).edadAlMomento is None  # sin nada: arranca igual
    from app.services import telemetry as telemetryService

    telemetryService.cancelSession(db, user)
    session = startFor(db, user, profileId, registered, edadAlMomento=25, sexoModelo="masculino")
    assert (session.edadAlMomento, session.sexoModelo) == (25, "MASCULINO")
    assert reload(db, User, user.idUsuario).fechaNacimiento is None


def test_http_acepta_la_solicitud_sin_edad_ni_sexo_y_con_ellos(api, db, mails):
    user, profileId = person(db)
    registered = device(db)
    client = api(user)
    body = {"idPerfilMedicion": str(profileId), "idDispositivo": str(registered.idDispositivo)}
    ok = client.post("/api/v1/measurements", json=body)
    assert ok.status_code == 201 and ok.json()["edadAlMomento"] is None and ok.json()["sexoModelo"] is None
    client.post(f"/api/v1/measurements/{ok.json()['idMedicion']}/cancel")
    informed = client.post("/api/v1/measurements", json={**body, "edadAlMomento": 61, "sexoModelo": "FEMENINO"})
    assert informed.status_code == 201 and (informed.json()["edadAlMomento"], informed.json()["sexoModelo"]) == (61, "FEMENINO")


def test_la_edad_se_calcula_a_la_fecha_de_la_medicion_y_no_solo_por_el_anio():
    assert calculateAge(date(2002, 2, 16), date(2026, 10, 13)) == 24  # ya cumplió años en febrero
    assert calculateAge(date(2002, 12, 1), date(2026, 10, 13)) == 23  # todavía no cumplió años este año
    assert calculateAge(date(2002, 10, 13), date(2026, 10, 13)) == 24  # el día del cumpleaños


def test_http_acepta_edadInformada_y_sexoInformado_como_nombres_de_los_datos_de_la_medicion(api, db, mails):
    user, profileId = person(db)
    registered = device(db)
    client = api(user)
    body = {"idPerfilMedicion": str(profileId), "idDispositivo": str(registered.idDispositivo), "edadInformada": 47, "sexoInformado": "masculino"}
    response = client.post("/api/v1/measurements", json=body)
    assert response.status_code == 201
    assert (response.json()["edadAlMomento"], response.json()["sexoModelo"]) == (47, "MASCULINO")
    assert reload(db, User, user.idUsuario).sexo is None  # los datos personales no cambian


def test_el_consumidor_sin_fecha_ni_sexo_ve_perfil_dashboard_dispositivos_e_historial_sin_bloqueos(api, db, mails):
    user, profileId = person(db)
    registered = device(db)
    client = api(user)
    profile = client.get("/api/v1/measurements/profile")
    assert profile.status_code == 200
    assert profile.json()["perfilDisponible"] is True and profile.json()["idPerfilMedicion"] == str(profileId)
    assert profile.json()["edad"] is None and profile.json()["sexoModelo"] is None
    dashboard = client.get("/api/v1/measurements/dashboard?dias=30")
    assert dashboard.status_code == 200 and dashboard.json()["perfilDisponible"] is True
    devices = client.get(f"/api/v1/measurements/devices?idPerfilMedicion={profileId}")
    assert devices.status_code == 200 and [d["idDispositivo"] for d in devices.json()] == [str(registered.idDispositivo)]
    assert client.get("/api/v1/measurements").status_code == 200
    started = client.post("/api/v1/measurements", json={"idPerfilMedicion": str(profileId), "idDispositivo": str(registered.idDispositivo)})
    assert started.status_code == 201 and started.json()["edadAlMomento"] is None and started.json()["sexoModelo"] is None
