# Pruebas de PerfilMedicion base (app/services/measurementProfile.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_profile.py -v
#
# Usan el esquema SQLite temporal de test_account_deletion.py (CHECK, FK e índices activos).

import json
from datetime import date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AuthError
from app.models.audit import Audit
from app.models.measurementProfile import MeasurementProfile
from app.schemas.measurementProfile import InstitutionalProfileCreate
from app.schemas.user import UserProfileUpdate
from app.services import measurementProfile as profiles
from app.services import user as userService
from tests.test_account_deletion import (  # noqa: F401 - fixtures
    addInstitution,
    db,
    engine,
    mails,
    makeUser,
    reload,
)


def countProfiles(db) -> int:
    return db.scalar(select(func.count()).select_from(MeasurementProfile))


def patient(**overrides) -> InstitutionalProfileCreate:
    data = {"nombre": "laura", "apellido": "díaz", "dni": " 30111222 ", "fechaNacimiento": "1985-03-10",
            "sexoModelo": "femenino"}
    return InstitutionalProfileCreate(**{**data, **overrides})


# --- Consumidor final --------------------------------------------------------------------


def test_consumidor_crea_su_perfil_la_primera_vez(db):
    user = makeUser(db)

    profile = profiles.ensureConsumerProfile(db, user)

    stored = reload(db, MeasurementProfile, profile.idPerfilMedicion)
    assert stored.tipoPerfil == "CONSUMIDOR_FINAL" and stored.idUsuario == user.idUsuario
    assert stored.idInstitucionUsuarioResponsable is None and stored.identificadorPseudonimo is None
    assert (stored.nombre, stored.apellido, stored.fechaNacimiento, stored.sexoModelo) == (
        "Victoria", "Cortés", date(1990, 5, 17), "FEMENINO")
    assert stored.dni is None and stored.edadDeclarada is None and stored.fechaCreacion is not None

    [audit] = db.scalars(select(Audit).where(Audit.accion == "CREAR_PERFIL_MEDICION")).all()
    assert audit.idRegistro == profile.idPerfilMedicion and audit.tablaAfectada == "PerfilMedicion"
    assert json.loads(audit.datosNuevos) == {"tipoPerfil": "CONSUMIDOR_FINAL"}
    assert "Victoria" not in str(audit.datosNuevos) + str(audit.observacion)


def test_consumidor_reutiliza_el_mismo_perfil(db):
    user = makeUser(db)
    first = profiles.ensureConsumerProfile(db, user)
    second = profiles.ensureConsumerProfile(db, user)

    assert first.idPerfilMedicion == second.idPerfilMedicion
    assert countProfiles(db) == 1
    assert db.scalar(select(func.count()).select_from(Audit).where(Audit.accion == "CREAR_PERFIL_MEDICION")) == 1


def test_perfil_se_actualiza_desde_usuario(db):
    user = makeUser(db)
    profile = profiles.ensureConsumerProfile(db, user)

    userService.updateProfile(db, user, UserProfileUpdate(apellido="gómez", fechaNacimiento="1991-01-02",
                                                         sexo="masculino"))
    profiles.ensureConsumerProfile(db, user)

    stored = reload(db, MeasurementProfile, profile.idPerfilMedicion)
    assert (stored.apellido, stored.fechaNacimiento, stored.sexoModelo) == ("Gómez", date(1991, 1, 2), "MASCULINO")
    assert countProfiles(db) == 1


@pytest.mark.parametrize("missing", [("fechaNacimiento",), ("sexo",), ("fechaNacimiento", "sexo")])
def test_el_perfil_se_crea_sin_fecha_de_nacimiento_ni_sexo(db, missing):
    """La fecha de nacimiento y el sexo son opcionales: se recomiendan, pero no impiden crear el perfil ni medir."""
    user = makeUser(db)
    for field in missing:
        setattr(user, field, None)
    db.commit()

    profile = profiles.ensureConsumerProfile(db, user)
    assert countProfiles(db) == 1
    assert profile.fechaNacimiento is None or "fechaNacimiento" not in missing
    assert profile.sexoModelo is None or "sexo" not in missing
    assert profiles.missingRecommendedFields(user) == list(missing)
    snapshot = profiles.measurementSnapshot(profile)
    assert (snapshot.edadAlMomento is None) == ("fechaNacimiento" in missing)
    assert (snapshot.sexoModelo is None) == ("sexo" in missing)


def test_cuenta_google_sin_datos_opcionales_tiene_perfil(db):
    user = makeUser(db, local=False, google=True, usuario=None)
    user.fechaNacimiento = user.sexo = None
    db.commit()
    profile = profiles.ensureConsumerProfile(db, user)
    assert profile.fechaNacimiento is None and profile.sexoModelo is None
    assert profiles.missingRecommendedFields(user) == ["fechaNacimiento", "sexo"]


def test_completar_los_datos_despues_actualiza_el_perfil(db):
    user = makeUser(db)
    user.fechaNacimiento = user.sexo = None
    db.commit()
    profile = profiles.ensureConsumerProfile(db, user)
    userService.updateProfile(db, user, UserProfileUpdate(fechaNacimiento="1991-01-02", sexo="masculino"))
    profiles.ensureConsumerProfile(db, user)
    stored = reload(db, MeasurementProfile, profile.idPerfilMedicion)
    assert (stored.fechaNacimiento, stored.sexoModelo) == (date(1991, 1, 2), "MASCULINO")
    assert profiles.missingRecommendedFields(user) == []


@pytest.mark.parametrize("tipoCuenta", ["USUARIO_INSTITUCIONAL", "ADMINISTRADOR_PLATAFORMA"])
def test_solo_consumidor_final_tiene_perfil_propio(db, tipoCuenta):
    user = makeUser(db, tipoCuenta=tipoCuenta)
    with pytest.raises(AuthError) as error:
        profiles.ensureConsumerProfile(db, user)
    assert error.value.code == "PERFIL_NO_DISPONIBLE"
    assert countProfiles(db) == 0


def test_indice_unico_un_perfil_por_consumidor(db):
    user = makeUser(db)
    profiles.ensureConsumerProfile(db, user)
    db.add(MeasurementProfile(tipoPerfil="CONSUMIDOR_FINAL", idUsuario=user.idUsuario, fechaNacimiento=date(1990, 1, 1),
                              sexoModelo="FEMENINO"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_creacion_simultanea_reutiliza_el_perfil_existente(db, monkeypatch):
    """Si otra solicitud lo creó entre la consulta y el INSERT, se usa ese perfil (sin duplicar)."""
    user = makeUser(db)
    existing = profiles.ensureConsumerProfile(db, user)

    original = profiles.getConsumerProfile
    calls = []

    def staleFirstRead(db_, user_):
        calls.append(1)
        return None if len(calls) == 1 else original(db_, user_)

    monkeypatch.setattr(profiles, "getConsumerProfile", staleFirstRead)
    profile = profiles.ensureConsumerProfile(db, user)

    assert profile.idPerfilMedicion == existing.idPerfilMedicion
    assert len(calls) == 2, "Debe chocar con el índice único y releer el perfil existente."
    assert countProfiles(db) == 1


def test_perfil_no_guarda_contexto_de_medicion():
    columns = set(MeasurementProfile.__table__.columns.keys())
    for field in ("condicionComida", "fechaHoraUltimaComida", "minutosDesdeUltimaComida", "comio", "contexto"):
        assert field not in columns
    with pytest.raises(ValidationError):
        patient(condicionComida="AYUNO")


# --- Edad --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nacimiento", "dia", "edad"),
    [
        (date(1990, 5, 17), date(2026, 5, 16), 35),
        (date(1990, 5, 17), date(2026, 5, 17), 36),
        (date(2000, 2, 29), date(2026, 2, 28), 25),
        (date(2000, 2, 29), date(2026, 3, 1), 26),
        (date(2026, 10, 1), date(2026, 10, 7), 0),
    ],
)
def test_calcula_edad_a_la_fecha(nacimiento, dia, edad):
    assert profiles.calculateAge(nacimiento, dia) == edad


def test_snapshot_calcula_edad_al_iniciar_y_no_cambia_despues(db):
    user = makeUser(db)
    profile = profiles.ensureConsumerProfile(db, user)

    before = profiles.measurementSnapshot(profile, datetime(2026, 5, 16, 23, 0))
    after = profiles.measurementSnapshot(profile, datetime(2026, 5, 17, 9, 0))
    assert (before.edadAlMomento, before.sexoModelo) == (35, "FEMENINO")
    assert after.edadAlMomento == 36

    # El snapshot es un valor: cambiar el perfil después no lo modifica.
    profile.fechaNacimiento = date(1980, 1, 1)
    assert before.edadAlMomento == 35
    with pytest.raises(AttributeError):
        before.edadAlMomento = 1


def test_snapshot_sin_fecha_usa_edad_declarada_y_sin_datos_queda_sin_informar():
    declared = MeasurementProfile(tipoPerfil="INSTITUCIONAL", edadDeclarada=40, sexoModelo="MASCULINO")
    assert profiles.measurementSnapshot(declared).edadAlMomento == 40

    # Un perfil individual sin fecha, edad ni sexo (depurado o nunca informado) mide igual: la edad y el sexo quedan sin informar.
    empty = MeasurementProfile(tipoPerfil="CONSUMIDOR_FINAL")
    snapshot = profiles.measurementSnapshot(empty)
    assert (snapshot.edadAlMomento, snapshot.sexoModelo) == (None, None)


def test_snapshot_respeta_rango_de_medicion():
    tooOld = MeasurementProfile(tipoPerfil="CONSUMIDOR_FINAL", fechaNacimiento=date(1880, 1, 1), sexoModelo="FEMENINO")
    with pytest.raises(AuthError) as error:
        profiles.measurementSnapshot(tooOld)
    assert error.value.code == "EDAD_FUERA_DE_RANGO"


# --- Institucional (preparado) -----------------------------------------------------------


def test_perfil_institucional_representa_al_paciente(db):
    operator = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    relation = addInstitution(db, operator, "OPERADOR")

    profile = profiles.buildInstitutionalProfile(relation, patient())
    db.add(profile)
    db.commit()  # cumple CK_PerfilMedicion_coherenciaTipo / datoEdad / sexo

    stored = reload(db, MeasurementProfile, profile.idPerfilMedicion)
    assert stored.tipoPerfil == "INSTITUCIONAL" and stored.idUsuario is None
    assert stored.idInstitucionUsuarioResponsable == relation.idInstitucionUsuario
    assert stored.identificadorPseudonimo.startswith("PAC-")
    assert (stored.nombre, stored.apellido, stored.dni, stored.fechaNacimiento, stored.sexoModelo) == (
        "Laura", "Díaz", "30111222", date(1985, 3, 10), "FEMENINO")
    assert stored.fechaCreacion is not None
    # Ningún dato del operador.
    assert "Victoria" not in (stored.nombre, stored.apellido)


def test_pseudonimos_distintos_por_paciente(db):
    operator = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    relation = addInstitution(db, operator, "OPERADOR")
    first = profiles.buildInstitutionalProfile(relation, patient())
    second = profiles.buildInstitutionalProfile(relation, patient(dni="40111222"))
    assert first.identificadorPseudonimo != second.identificadorPseudonimo


@pytest.mark.parametrize(("rol", "estado"), [("OPERADOR", "BAJA"), ("OPERADOR", "PENDIENTE"), ("MODERADOR", "ACTIVO"),
                                             ("PROPIETARIO", "ACTIVO")])
def test_solo_operador_activo_es_responsable(db, rol, estado):
    operator = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    relation = addInstitution(db, operator, rol, estadoRelacion=estado)
    with pytest.raises(AuthError) as error:
        profiles.buildInstitutionalProfile(relation, patient())
    assert error.value.code == "RESPONSABLE_INVALIDO"


@pytest.mark.parametrize("missing", ["nombre", "apellido"])
def test_paciente_requiere_nombre_y_apellido(missing):
    data = {"nombre": "Laura", "apellido": "Díaz", "dni": "30111222", "fechaNacimiento": "1985-03-10",
            "sexoModelo": "FEMENINO"}
    data.pop(missing)
    with pytest.raises(ValidationError):
        InstitutionalProfileCreate(**data)


@pytest.mark.parametrize("missing", ["dni", "fechaNacimiento", "sexoModelo"])
def test_documento_fecha_de_nacimiento_y_sexo_son_opcionales(missing):
    data = {"nombre": "Laura", "apellido": "Díaz", "dni": "30111222", "fechaNacimiento": "1985-03-10",
            "sexoModelo": "FEMENINO"}
    data.pop(missing)
    assert getattr(InstitutionalProfileCreate(**data), missing) is None


def test_paciente_rechaza_fecha_futura_y_sexo_invalido():
    with pytest.raises(ValidationError):
        patient(fechaNacimiento="2999-01-01")
    with pytest.raises(ValidationError):
        patient(sexoModelo="OTRO")
