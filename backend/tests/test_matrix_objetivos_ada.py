# Matriz de objetivos de glucosa de la guía ADA (Diabetes Tests, adultos no gestantes), v1 del catálogo global:
#   · AYUNO (preprandial): 80–130 mg/dL, para cualquier sexo, adultos 18–130 años.
#   · POSTPRANDIAL: menor de 180 mg/dL (solo tope), medido 60–120 min desde el INICIO de la comida, para cualquier sexo.
#   · Comida no informada: sin regla ni objetivo. La vista de referencia muestra los dos objetivos sin elegir ninguno.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_matrix_objetivos_ada.py -v

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.measurement import ReferenceRule
from app.services import glucoseReference as reference
from app.services import matrix as matrices
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_matrices import activeMatrix, newMatrix, platform, rule  # noqa: F401 - fixtures
from tests.test_measurements import expectError
from tests.test_telemetry import bridge, clock  # noqa: F401 - fixtures

INSTALADOR = Path(__file__).resolve().parents[2] / "database" / "reference" / "MATRIZ.SQL"


def objetivosAda():
    """Las dos reglas que el instalador SQL carga (MATRIZ.SQL): deben coincidir valor por valor."""
    return (
        rule(sexoModelo="CUALQUIER_SEXO", edadDesde=18, edadHasta=130, condicionComida="AYUNO",
             glucosaMinReferencia="80", glucosaMaxReferencia="130"),
        rule(sexoModelo="CUALQUIER_SEXO", edadDesde=18, edadHasta=130, condicionComida="POSTPRANDIAL",
             minutosComidaMin=60, minutosComidaMax=120, glucosaMinReferencia=None, glucosaMaxReferencia="179.99"),
    )


def medicion(matriz, *, glucosa="117", condicion="NO_INFORMADA", minutosDesdeComida=None, sexo=None, edad=40):
    inicio = datetime(2026, 10, 30, 10, 0)
    return SimpleNamespace(
        idMedicion=uuid.uuid4(), idMatriz=matriz.idMatriz, glucosaEstimada=None, glucosaDispositivo=Decimal(glucosa),
        origenGlucosa="DEMO", sexoModelo=sexo, edadAlMomento=edad, condicionComida=condicion, fechaHoraInicio=inicio,
        fechaHoraUltimaComida=None if minutosDesdeComida is None else inicio - timedelta(minutes=minutosDesdeComida))


# --- Selección de la regla -----------------------------------------------------------------------------------------------------------


def test_la_regla_vale_para_cualquier_sexo_informado_o_no(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    for sexo in ("FEMENINO", "MASCULINO", "NO_INFORMADO"):
        found = matrices.resolveRule(db, matriz.idMatriz, sexo, 40, "AYUNO", None)
        assert found is not None and found.glucosaMinReferencia == Decimal("80.00") and found.glucosaMaxReferencia == Decimal("130.00")


def test_comida_no_informada_no_elige_ningun_objetivo(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    assert matrices.resolveRule(db, matriz.idMatriz, "FEMENINO", 40, "NO_INFORMADA", None) is None
    assert matrices.resolveRule(db, matriz.idMatriz, "FEMENINO", 40, "NO_INFORMADA", 90) is None


def test_posprandial_depende_de_los_minutos_desde_el_inicio_de_la_comida(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    esperado = {59: False, 60: True, 90: True, 120: True, 121: False, None: False}
    for minutos, aplica in esperado.items():
        found = matrices.resolveRule(db, matriz.idMatriz, "MASCULINO", 40, "POSTPRANDIAL", minutos)
        assert (found is not None) == aplica, minutos
    # Solo tope: no se inventa un límite inferior para el posprandial.
    found = matrices.resolveRule(db, matriz.idMatriz, "MASCULINO", 40, "POSTPRANDIAL", 90)
    assert found.glucosaMinReferencia is None and found.glucosaMaxReferencia == Decimal("179.99")


def test_sin_edad_dentro_del_alcance_no_hay_regla(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    assert matrices.resolveRule(db, matriz.idMatriz, "FEMENINO", 17, "AYUNO", None) is None


# --- Validación y solapamientos --------------------------------------------------------------------------------------------------


def test_una_regla_por_sexo_se_pisa_con_la_que_vale_para_cualquier_sexo(db, mails, platform):
    created = newMatrix(db, platform, rules=(objetivosAda()[0],))
    expectError("REGLA_SOLAPADA", matrices.addRule, db, platform, created.idMatriz,
                rule(sexoModelo="FEMENINO", edadDesde=18, edadHasta=60, condicionComida="AYUNO"))


def test_la_matriz_ada_se_valida_sin_huecos_de_sexo(db, mails, platform):
    created = newMatrix(db, platform, rules=objetivosAda())
    validation = matrices.validateMatrix(db, platform, created.idMatriz)
    assert validation.valida and not any(a.codigo == "SIN_COBERTURA" and "sexo" in a.mensaje for a in validation.advertencias)


# --- Vista de referencia (la misma lógica que el cálculo) ---------------------------------------------------------------------


def test_comida_no_informada_muestra_los_dos_objetivos_sin_elegir_uno(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    ref = reference.build(db, medicion(matriz, condicion="NO_INFORMADA"))
    assert ref.avisoSexo is None and len(ref.grupos) == 1
    grupo = ref.grupos[0]
    assert grupo.sexoModelo == "CUALQUIER_SEXO" and grupo.reglaSeleccionada is None and len(grupo.reglas) == 2
    assert grupo.motivoSinSeleccion is not None and grupo.posicion is None


def test_posprandial_a_90_minutos_compara_con_el_tope_de_180(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    ref = reference.build(db, medicion(matriz, glucosa="200", condicion="POSTPRANDIAL", minutosDesdeComida=90))
    grupo = ref.grupos[0]
    assert grupo.reglaSeleccionada.codigo == "R-002" and grupo.reglaSeleccionada.glucosaMinReferencia is None
    assert grupo.posicion == "POR_ENCIMA"
    dentro = reference.build(db, medicion(matriz, glucosa="20", condicion="POSTPRANDIAL", minutosDesdeComida=90))
    assert dentro.grupos[0].posicion == "DENTRO"  # sin piso: un valor bajo no se marca como «por debajo del objetivo»


def test_posprandial_a_150_minutos_queda_fuera_de_la_ventana(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    ref = reference.build(db, medicion(matriz, glucosa="200", condicion="POSTPRANDIAL", minutosDesdeComida=150))
    assert ref.grupos[0].reglaSeleccionada is None and ref.grupos[0].posicion is None


def test_sin_edad_no_se_elige_objetivo(db, mails, platform):
    matriz = activeMatrix(db, platform, rules=objetivosAda())
    ref = reference.build(db, medicion(matriz, condicion="AYUNO", edad=None))
    assert all(grupo.reglaSeleccionada is None for grupo in ref.grupos)


def test_posicion_sin_limite_inferior_solo_compara_el_tope():
    tope = ReferenceRule(idRegla=uuid.uuid4(), codigo="R-002", sexoModelo="CUALQUIER_SEXO", edadDesde=18, edadHasta=130,
                         condicionComida="POSTPRANDIAL", minutosComidaMin=60, minutosComidaMax=120,
                         glucosaMinReferencia=None, glucosaMaxReferencia=179.99)
    assert reference.position(tope, 20.0) == "DENTRO"
    assert reference.position(tope, 179.99) == "DENTRO"
    assert reference.position(tope, 180.0) == "POR_ENCIMA"


# --- Coherencia con el instalador SQL ------------------------------------------------------------------------------------------


def test_el_instalador_sql_carga_los_mismos_objetivos_que_el_backend():
    sql = INSTALADOR.read_text(encoding="utf-8")
    # Valores: AYUNO 80–130; POSTPRANDIAL sin piso y tope 179,99 (menor de 180), ventana 60–120 min, para cualquier sexo, 18–130 años.
    assert "VALUES (N'R-001', N'CUALQUIER_SEXO', 18, 130, N'AYUNO', NULL, NULL, CAST(80.00 AS DECIMAL(8,2)), CAST(130.00 AS DECIMAL(8,2)))" in sql
    assert "(N'R-002', N'CUALQUIER_SEXO', 18, 130, N'POSTPRANDIAL', 60, 120, NULL, CAST(179.99 AS DECIMAL(8,2)))" in sql
    # El procedimiento usa la misma ventana y el mismo sexo comodín que el backend.
    assert "@MinutosComida BETWEEN COALESCE(r.minutosComidaMin, 0)" in sql
    assert "r.sexoModelo = N''CUALQUIER_SEXO''" in sql  # dentro de sp_executesql las comillas van duplicadas
    # Fuente única, sin la matriz DEMO anterior ni cifras de Sección 13 o 6 que no se verificaron.
    assert "ADA, Diabetes Tests" in sql
    assert "https://diabetes.org/living-with-diabetes/treatment-care/checking-your-blood-sugar" in sql
    assert "N'ADA 2026 - Seguimiento adulto no gestante'" not in sql
    assert "matriz de prueba DEMO" not in sql
