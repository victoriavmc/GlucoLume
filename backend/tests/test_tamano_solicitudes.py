# Límites de tamaño por cantidad de elementos y longitud en los esquemas que reciben listas grandes (B-1, auditoría 07/11/2026).
#
# El tamaño en bytes del cuerpo lo acota Nginx por tipo de operación (docker/nginx/default.conf.template, probado en
# docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/sondas_tamano_cuerpo.sh). Acá se prueba lo que valida la API:
# - cerca del límite pasa;
# - por encima se rechaza con ValidationError (que la API responde 422);
# - un JSON inválido o fuera de esquema responde 422 (nunca 413, que es solo de Nginx).

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sqlalchemy.orm import sessionmaker

from app.db.session import getDb
from app.main import app
from app.schemas.acquisition import BridgeIngest, BridgeLine
from app.schemas.auth import MfaRecoveryVerifyRequest
from app.schemas.matrix import MatrixRulesCheckRequest
from app.schemas.measurement import SampleItem, SamplesRequest
from app.schemas.offboarding import OffboardAssignment, OffboardRequest
from app.schemas.matrix import MatrixRuleInput
from tests.test_account_deletion import engine  # noqa: F401 - fixture (SQLite de prueba)

PUENTE = dict(idPuente=uuid.uuid4(), codigoDispositivo="DEV-001", medio="BLUETOOTH", estadoEnlace="CONECTADO")


def linea(seq, texto="x" * 40):
    return {"seq": seq, "edadMs": 1000, "texto": texto}


def regla(**cambios):
    datos = {"sexoModelo": "FEMENINO", "edadDesde": 18, "edadHasta": 60, "condicionComida": "AYUNO",
             "glucosaMinReferencia": "70", "glucosaMaxReferencia": "110"}
    return MatrixRuleInput(**{**datos, **cambios})


# --- Lotes del puente: 200 líneas y 512 caracteres por línea (MAX_BATCH del puente y su validación) --------------------------------


def test_lote_del_puente_de_200_lineas_pasa_y_201_se_rechaza():
    BridgeIngest(**PUENTE, lineas=[linea(i) for i in range(200)])
    with pytest.raises(ValidationError) as rechazo:
        BridgeIngest(**PUENTE, lineas=[linea(i) for i in range(201)])
    assert "lineas" in str(rechazo.value)


def test_linea_del_puente_de_512_caracteres_pasa_y_513_se_rechaza():
    BridgeLine(seq=1, edadMs=1, texto="x" * 512)
    with pytest.raises(ValidationError):
        BridgeLine(seq=1, edadMs=1, texto="x" * 513)


def test_lote_del_puente_con_512_caracteres_no_ascii_en_cada_linea_pasa():
    """El peor caso legítimo: 200 líneas de 512 caracteres escapados (JSON). Lo valida la API; el tamaño en bytes lo acota Nginx (768k)."""
    lote = [linea(i, texto="é" * 512) for i in range(200)]
    BridgeIngest(**PUENTE, lineas=lote)


# --- Muestras: hasta 2000 por medición, al menos una ----------------------------------------------------------------------------


def muestra(i):
    return {"numeroMuestra": i, "valorRed": 100000 + i, "valorIR": 200000 + i}


def test_muestras_hasta_2000_pasan_y_2001_se_rechazan():
    SamplesRequest(muestras=[muestra(i) for i in range(2000)])
    with pytest.raises(ValidationError):
        SamplesRequest(muestras=[muestra(i) for i in range(2001)])


def test_una_medicion_sin_muestras_se_rechaza():
    with pytest.raises(ValidationError):
        SamplesRequest(muestras=[])


def test_muestra_con_valor_negativo_se_rechaza_aunque_el_lote_sea_chico():
    with pytest.raises(ValidationError):
        SampleItem(numeroMuestra=1, valorRed=-1, valorIR=5)


# --- Reglas de matriz: hasta 300 ------------------------------------------------------------------------------------------------


def test_reglas_de_matriz_hasta_300_pasan_y_301_se_rechazan():
    MatrixRulesCheckRequest(reglas=[regla() for _ in range(300)])
    with pytest.raises(ValidationError):
        MatrixRulesCheckRequest(reglas=[regla() for _ in range(301)])


# --- Offboarding: hasta 2000 asignaciones --------------------------------------------------------------------------------------


def asignacion():
    return OffboardAssignment(idPerfilMedicion=uuid.uuid4(), idOperadorNuevo=uuid.uuid4())


def test_offboarding_hasta_2000_asignaciones_pasa_y_2001_se_rechaza():
    OffboardRequest(asignaciones=[asignacion() for _ in range(2000)])
    with pytest.raises(ValidationError):
        OffboardRequest(asignaciones=[asignacion() for _ in range(2001)])


# --- Códigos de MFA: 6 dígitos con espacios, con tope de largo ----------------------------------------------------------------


def test_codigo_mfa_con_espacios_razonables_pasa():
    MfaRecoveryVerifyRequest(recoveryToken="token", codigo=" 123456 ")
    MfaRecoveryVerifyRequest(recoveryToken="token", codigo=" " * 5 + "123456" + " " * 5)  # 16 caracteres: justo en el tope


def test_codigo_mfa_con_espacios_excesivos_se_rechaza_aunque_coincida_el_patron():
    with pytest.raises(ValidationError):
        MfaRecoveryVerifyRequest(recoveryToken="token", codigo=" " * 20 + "123456")  # el patrón lo admitiría; el tope no


def test_codigo_mfa_con_letras_se_rechaza():
    with pytest.raises(ValidationError):
        MfaRecoveryVerifyRequest(recoveryToken="token", codigo="12345a")


# --- Respuestas de la API: 422 para cuerpos inválidos (el 413 es solo de Nginx) --------------------------------------------------


@pytest.fixture
def http(engine):  # noqa: F811 - la base de prueba (SQLite) evita que las dependencias intenten abrir SQL Server
    makeSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def getTestDb():
        session = makeSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[getDb] = getTestDb
    yield TestClient(app, raise_server_exceptions=False, client=("203.0.113.55", 50000))
    app.dependency_overrides.clear()


def test_json_invalido_responde_422_con_formato_de_la_api(http):
    r = http.post("/api/v1/auth/login", content=b"{", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_cuerpo_fuera_de_esquema_responde_422_no_413(http):
    r = http.post("/api/v1/auth/login", json={"identificador": "x" * 300, "password": "x"})
    assert r.status_code == 422
    assert r.status_code != 413


def test_identificador_de_login_justo_en_254_pasa_la_validacion_de_tamano(http):
    r = http.post("/api/v1/auth/login", json={"identificador": "a" * 254, "password": "x"})
    assert r.status_code != 422  # llega a la lógica de autenticación (credenciales inválidas), no a la validación de tamaño
