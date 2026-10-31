# Reglas de matriz con condiciones EXPLÍCITAS «sexo no informado» y «comida sin informar»: se crean, persisten, se consultan, se editan
# y se aplican igual que las demás, sin reemplazar nunca lo no informado por un valor inventado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrix_unreported_conditions.py -v
#
# Cuatro combinaciones: sexo informado/no informado x comida informada/sin informar. «No informado» elegido en una regla NO es lo mismo que un
# campo obligatorio sin completar: lo segundo se rechaza (la edad, a medias; los límites de glucosa, vacíos).

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models.matrixRule import MatrixRule
from app.schemas.matrix import MatrixRuleUpdateRequest
from app.services import matrix as matrices
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_matrices import newMatrix, platform, rule  # noqa: F401 - fixtures
from tests.test_measurement_optional_data import person
from tests.test_measurements import device, expectError, glucose
from tests.test_telemetry import bridge, clock  # noqa: F401 - fixtures

COMBINATIONS = {
    "1_sexo_informado_comida_informada": ("FEMENINO", "AYUNO"),
    "2_sexo_no_informado_comida_informada": ("NO_INFORMADO", "AYUNO"),
    "3_sexo_informado_comida_sin_informar": ("FEMENINO", "NO_INFORMADA"),
    "4_sexo_no_informado_comida_sin_informar": ("NO_INFORMADO", "NO_INFORMADA"),
}
combos = pytest.mark.parametrize("sexo,comida", list(COMBINATIONS.values()), ids=list(COMBINATIONS))


def stored(db, idMatriz):
    db.expire_all()
    return list(db.scalars(select(MatrixRule).where(MatrixRule.idMatriz == idMatriz)))


# --- Creación, persistencia, consulta y edición ---------------------------------------------------------------------------------------


@combos
def test_se_crea_persiste_consulta_y_edita_la_regla(db, mails, platform, sexo, comida):
    created = newMatrix(db, platform, rules=())
    detail = matrices.addRule(db, platform, created.idMatriz, rule(sexoModelo=sexo, condicionComida=comida))
    # Persistencia: el valor guardado es exactamente el elegido (nada de reemplazos automáticos).
    saved = stored(db, created.idMatriz)
    assert [(r.sexoModelo, r.condicionComida) for r in saved] == [(sexo, comida)]
    # Consulta.
    shown = matrices.getMatrix(db, platform, created.idMatriz).reglas
    assert [(r.sexoModelo, r.condicionComida) for r in shown] == [(sexo, comida)] and detail.cantidadReglas == 1
    # Edición: otro dato de la regla; sexo y comida se conservan, y se pueden volver a editar entre sí.
    edited = matrices.updateRule(db, platform, created.idMatriz, shown[0].idReglaMatriz,
                                 MatrixRuleUpdateRequest(glucosaMaxReferencia="120"))
    assert [(r.sexoModelo, r.condicionComida, float(r.glucosaMaxReferencia)) for r in edited.reglas] == [(sexo, comida, 120.0)]
    other_sex = "FEMENINO" if sexo == "NO_INFORMADO" else "NO_INFORMADO"
    swapped = matrices.updateRule(db, platform, created.idMatriz, shown[0].idReglaMatriz, MatrixRuleUpdateRequest(sexoModelo=other_sex))
    assert swapped.reglas[0].sexoModelo == other_sex and swapped.reglas[0].condicionComida == comida
    assert matrices.validateMatrix(db, platform, created.idMatriz).valida


def test_las_cuatro_combinaciones_conviven_en_una_matriz_sin_duplicarse_ni_solaparse(db, mails, platform):
    created = newMatrix(db, platform, rules=tuple(rule(sexoModelo=s, condicionComida=c) for s, c in COMBINATIONS.values()))
    assert created.cantidadReglas == 4 and matrices.validateMatrix(db, platform, created.idMatriz).valida
    # Las validaciones de siempre siguen valiendo con las condiciones no informadas.
    expectError("REGLA_DUPLICADA", matrices.addRule, db, platform, created.idMatriz, rule(sexoModelo="NO_INFORMADO", condicionComida="NO_INFORMADA"))
    expectError("REGLA_SOLAPADA", matrices.addRule, db, platform, created.idMatriz,
                rule(sexoModelo="NO_INFORMADO", condicionComida="NO_INFORMADA", edadDesde=30, edadHasta=70))


def test_no_informado_elegido_no_equivale_a_un_dato_obligatorio_sin_completar():
    for bad in ({"sexoModelo": None}, {"sexoModelo": ""}, {"condicionComida": None}, {"condicionComida": ""},
                {"edadDesde": 18, "edadHasta": None}, {"edadDesde": None, "edadHasta": 60},
                {"glucosaMaxReferencia": ""}):
        with pytest.raises(ValidationError):
            rule(**bad)
    for value in ("no_informado", "NO_INFORMADO", " No_Informado "):
        assert rule(sexoModelo=value.strip()).sexoModelo == "NO_INFORMADO"
    assert rule(sexoModelo="NO_INFORMADO", condicionComida="NO_INFORMADA").condicionComida == "NO_INFORMADA"


def test_el_minimo_de_glucosa_puede_quedar_vacio_pero_el_maximo_es_obligatorio():
    # Un objetivo solo con tope (posprandial «menor de 180 mg/dL», ADA) no inventa un límite inferior.
    assert rule(glucosaMinReferencia=None, glucosaMaxReferencia="179.99").glucosaMinReferencia is None
    with pytest.raises(ValidationError):
        rule(glucosaMinReferencia="80", glucosaMaxReferencia="70")


def test_una_regla_para_edad_no_especificada_se_crea_y_edita_como_las_de_la_matriz_global(db, mails, platform):
    created = newMatrix(db, platform, rules=(rule(sexoModelo="NO_INFORMADO", condicionComida="NO_INFORMADA", edadDesde="", edadHasta=None),))
    only = created.reglas[0]
    assert (only.edadDesde, only.edadHasta) == (None, None)
    edited = matrices.updateRule(db, platform, created.idMatriz, only.idReglaMatriz, MatrixRuleUpdateRequest(glucosaMinReferencia="75"))
    assert (edited.reglas[0].edadDesde, edited.reglas[0].edadHasta, float(edited.reglas[0].glucosaMinReferencia)) == (None, None, 75.0)


# --- Aplicación durante una medición ---------------------------------------------------------------------------------------------------


@combos
def test_la_medicion_aplica_la_regla_prevista_para_su_combinacion(db, mails, platform, sexo, comida):
    # Matriz con las cuatro combinaciones, cada una con un rango distinto para saber cuál se aplicó.
    created = newMatrix(db, platform, rules=tuple(rule(sexoModelo=s, condicionComida=c, glucosaMinReferencia=str(70 + i),
                                                       glucosaMaxReferencia=str(100 + i))
                                                  for i, (s, c) in enumerate(COMBINATIONS.values())))
    matrices.activate(db, platform, created.idMatriz)
    informed = sexo != "NO_INFORMADO"
    user, profileId = person(db, sex="FEMENINO" if informed else None, email=f"{sexo}{comida}@example.com".lower(), usuario="p" + comida.lower())
    started = glucose(db, user, profileId, device(db), condicionComida=comida, edadAlMomento=40)
    # La medición conserva lo que se informó: sexo no informado queda sin dato (no se lo reemplaza por masculino ni femenino).
    assert started.sexoModelo == ("FEMENINO" if informed else None) and started.condicionComida == comida
    applied = matrices.resolveRule(db, created.idMatriz, started.sexoModelo, 40, started.condicionComida, None)
    assert (applied.sexoModelo, applied.condicionComida) == (sexo, comida)
    assert started.matriz is not None and started.matriz.idMatriz == created.idMatriz


def test_sin_regla_para_sexo_no_informado_no_se_aplica_otra_ni_se_inventa(db, mails, platform):
    created = newMatrix(db, platform, rules=(rule(sexoModelo="FEMENINO"), rule(sexoModelo="MASCULINO")))
    matrices.activate(db, platform, created.idMatriz)
    user, profileId = person(db, email="sinsexo@example.com", usuario="sinsexo")
    assert matrices.resolveRule(db, created.idMatriz, None, 40, "AYUNO", None) is None
    error = expectError("DATOS_PACIENTE_INCOMPLETOS", glucose, db, user, profileId, device(db), condicionComida="AYUNO", edadAlMomento=40)
    assert "no se inventan valores" in error.message


def test_una_regla_para_sexo_no_informado_no_se_aplica_a_quien_si_lo_informo(db, mails, platform):
    created = newMatrix(db, platform, rules=(rule(sexoModelo="NO_INFORMADO"),))
    matrices.activate(db, platform, created.idMatriz)
    user, profileId = person(db, sex="MASCULINO", email="masc@example.com", usuario="masc")
    expectError("SIN_REGLA_APLICABLE", glucose, db, user, profileId, device(db), condicionComida="AYUNO", edadAlMomento=40)
    assert matrices.resolveRule(db, created.idMatriz, "MASCULINO", 40, "AYUNO", None) is None


def test_comida_sin_informar_solo_coincide_con_reglas_para_comida_sin_informar(db, mails, platform):
    created = newMatrix(db, platform, rules=(rule(condicionComida="AYUNO"),))
    assert matrices.resolveRule(db, created.idMatriz, "FEMENINO", 40, "NO_INFORMADA", None) is None
    matrices.addRule(db, platform, created.idMatriz, rule(condicionComida="NO_INFORMADA", glucosaMinReferencia="65"))
    chosen = matrices.resolveRule(db, created.idMatriz, "FEMENINO", 40, "NO_INFORMADA", None)
    assert chosen.condicionComida == "NO_INFORMADA" and float(chosen.glucosaMinReferencia) == 65.0


# --- API --------------------------------------------------------------------------------------------------------------------------------


def test_la_api_acepta_y_devuelve_las_reglas_no_informadas(db, mails, platform, api):
    created = newMatrix(db, platform, rules=())
    client = api(platform)
    body = {"sexoModelo": "NO_INFORMADO", "edadDesde": None, "edadHasta": None, "condicionComida": "NO_INFORMADA",
            "minutosComidaMin": None, "minutosComidaMax": None, "glucosaMinReferencia": "70", "glucosaMaxReferencia": "180"}
    response = client.post(f"/api/v1/matrices/{created.idMatriz}/rules", json=body)
    assert response.status_code in (200, 201), response.text
    rules = response.json()["reglas"]
    assert [(r["sexoModelo"], r["condicionComida"], r["edadDesde"]) for r in rules] == [("NO_INFORMADO", "NO_INFORMADA", None)]
    edited = client.patch(f"/api/v1/matrices/{created.idMatriz}/rules/{rules[0]['idReglaMatriz']}", json={"glucosaMaxReferencia": "190"})
    assert edited.status_code == 200, edited.text
    # Un campo obligatorio sin completar sigue rechazándose (no es lo mismo que «no informado»).
    assert client.post(f"/api/v1/matrices/{created.idMatriz}/rules", json={**body, "sexoModelo": "", "condicionComida": "AYUNO"}).status_code == 422
