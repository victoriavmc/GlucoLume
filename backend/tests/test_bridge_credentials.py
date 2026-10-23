# Credenciales individuales de los puentes serie (H-16): alta, autenticación, alcance por dispositivo, vencimiento, revocación, rotación,
# auditoría sin el token, compatibilidad con el BRIDGE_TOKEN compartido y línea de comandos. Datos sintéticos; SQLite temporal.

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.api import rateLimit
from app.cli import bridgeTokens
from app.core.config import getSettings
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.bridgeCredential import BridgeCredential
from app.services import bridgeCredentials
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, TOKEN, bridge, clock, freshHub, line, payload  # noqa: F401 - fixtures

INGEST = "/api/v1/acquisition/bridge/ingest"
CHECK = "/api/v1/acquisition/bridge/check"


@pytest.fixture(autouse=True)
def cleanControls():
    bridgeCredentials.reset()
    yield
    bridgeCredentials.reset()


def post(client, token, body, url=INGEST):
    return client.post(url, json=body, headers={"X-Bridge-Token": token})


def actions(db, action):
    db.expire_all()
    return list(db.scalars(select(Audit).where(Audit.accion == action).order_by(Audit.fechaHora)))


def test_el_token_individual_se_guarda_solo_como_hash_y_se_muestra_una_vez(db):
    credential, token = bridgeCredentials.create(db, "Puente de laboratorio", CODE)
    stored = db.get(BridgeCredential, credential.idPuenteCredencial)
    assert len(token) >= 60 and token not in repr(stored.__dict__) and stored.tokenHash != token
    assert db.execute(text("SELECT COUNT(*) FROM dbo.PuenteCredencial WHERE tokenHash = :t"), {"t": token}).scalar() == 0
    assert stored.fechaExpiracion - stored.fechaCreacion == timedelta(days=bridgeCredentials.DEFAULT_VALID_DAYS)
    assert [row["huella"] for row in bridgeCredentials.listAll(db)] == [stored.tokenHash[:8]]
    assert token not in repr(bridgeCredentials.listAll(db))
    [event] = actions(db, "CREAR_CREDENCIAL_PUENTE")
    assert token not in f"{event.observacion} {event.datosNuevos} {event.detalle}" and event.modulo == "SEGURIDAD"


def test_validaciones_de_alta(db):
    for name, code, days in (("", CODE, 10), ("x", "  ", 10), ("x", CODE, 0), ("x", CODE, bridgeCredentials.MAX_VALID_DAYS + 1)):
        with pytest.raises(ValueError):
            bridgeCredentials.create(db, name, code, days)
    assert db.scalars(select(BridgeCredential)).all() == []


def test_un_puente_se_autentica_con_su_credencial_y_solo_para_su_dispositivo(api, consumer, bridge, db):
    user, _ = consumer
    client = api(user)
    _, token = bridgeCredentials.create(db, "Puente A", CODE)
    ok = post(client, token, payload(bridge, [line()]))
    assert ok.status_code == 200 and ok.json()["aceptadas"] == 1
    assert post(client, token, {"codigoDispositivo": CODE}, CHECK).status_code == 200
    other = {**payload(bridge, [line()]), "codigoDispositivo": "OTRO-999"}
    refused = post(client, token, other)
    assert refused.status_code == 403 and refused.json()["codigo"] == "PUENTE_FUERA_DE_ALCANCE"
    assert post(client, token, {"codigoDispositivo": "otro-999"}, CHECK).status_code == 403  # tampoco para consultar otro dispositivo
    assert post(client, token, {"codigoDispositivo": CODE.lower()}, CHECK).status_code == 200  # el código no distingue mayúsculas
    [rejection] = actions(db, "CREDENCIAL_PUENTE_RECHAZADA")  # una sola vez por credencial y motivo dentro del intervalo
    assert rejection.resultado == "FALLO" and token not in f"{rejection.observacion}"


def test_una_credencial_revocada_o_vencida_deja_de_valer_y_queda_auditada(api, consumer, bridge, db):
    user, _ = consumer
    client = api(user)
    revoked, revokedToken = bridgeCredentials.create(db, "Revocable", CODE)
    expired, expiredToken = bridgeCredentials.create(db, "Vencible", CODE)
    other, otherToken = bridgeCredentials.create(db, "Otro puente", CODE)
    assert post(client, revokedToken, payload(bridge, [line()])).status_code == 200
    bridgeCredentials.revoke(db, revoked.tokenHash[:8])
    expired.fechaExpiracion = nowForDb() - timedelta(minutes=1)
    expired.fechaCreacion = nowForDb() - timedelta(days=2)
    db.commit()
    for token in (revokedToken, expiredToken):
        denied = post(client, token, payload(bridge, [line()]))
        assert denied.status_code == 403 and denied.json()["codigo"] == "PUENTE_NO_AUTORIZADO"
    assert post(client, otherToken, payload(bridge, [line()])).status_code == 200  # revocar uno no afecta a los demás
    rejections = actions(db, "CREDENCIAL_PUENTE_RECHAZADA")
    assert {db.get(AuditContext, row.idAuditoria).motivo for row in rejections} == {"REVOCADA", "VENCIDA"}
    assert sorted("Revocable" if "Revocable" in row.observacion else "Vencible" for row in rejections) == ["Revocable", "Vencible"]
    assert all(row.resultado == "FALLO" for row in rejections)
    assert len(actions(db, "REVOCAR_CREDENCIAL_PUENTE")) == 1


def test_un_token_desconocido_se_rechaza_y_cuenta_para_el_bloqueo_por_ip(api, consumer, bridge, db):
    user, _ = consumer
    client = api(user)
    bridgeCredentials.create(db, "Puente A", CODE)
    for _ in range(rateLimit.BRIDGE_FAILURES[0]):
        assert post(client, "z" * 64, payload(bridge, [line()])).status_code == 403
    assert post(client, "z" * 64, payload(bridge, [line()])).status_code == 429


def test_el_token_compartido_sigue_valiendo_y_se_puede_desactivar(api, consumer, bridge, db, monkeypatch):
    user, _ = consumer
    client = api(user)
    bridgeCredentials.create(db, "Puente A", CODE)
    assert post(client, TOKEN, payload(bridge, [line()])).status_code == 200  # compatibilidad: sin alcance por dispositivo
    assert post(client, TOKEN, {**payload(bridge, [line()]), "codigoDispositivo": "OTRO-999"}).status_code == 200
    monkeypatch.setenv("BRIDGE_ALLOW_SHARED_TOKEN", "false")
    getSettings.cache_clear()
    rateLimit.resetLimits()
    refused = post(client, TOKEN, payload(bridge, [line()]))
    assert refused.status_code == 403 and refused.json()["codigo"] == "PUENTE_NO_AUTORIZADO"
    assert "compartido" not in " ".join(getSettings().securityWarnings())


def test_sin_token_compartido_ni_credenciales_la_recepcion_esta_deshabilitada(api, consumer, bridge, db, monkeypatch):
    user, _ = consumer
    client = api(user)
    monkeypatch.setenv("BRIDGE_ALLOW_SHARED_TOKEN", "false")
    getSettings.cache_clear()
    disabled = post(client, TOKEN, payload(bridge, [line()]))
    assert disabled.status_code == 503 and disabled.json()["codigo"] == "PUENTE_NO_CONFIGURADO"
    bridgeCredentials.create(db, "Puente A", CODE)
    assert post(client, TOKEN, payload(bridge, [line()])).status_code == 403  # ahora hay credenciales: el compartido ya no vale


def test_la_rotacion_acorta_la_credencial_anterior_y_no_se_extiende(db):
    first, firstToken = bridgeCredentials.create(db, "Puente A", CODE, validDays=90)
    second, secondToken = bridgeCredentials.rotate(db, first.tokenHash[:8], overlapHours=12)
    assert firstToken != secondToken and second.codigoDispositivo == first.codigoDispositivo and second.nombre == first.nombre
    db.refresh(first)
    assert first.fechaExpiracion <= nowForDb() + timedelta(hours=12, seconds=5) and first.fechaExpiracion > nowForDb()
    assert bridgeCredentials.authenticate(db, firstToken) is not None and bridgeCredentials.authenticate(db, secondToken) is not None
    with pytest.raises(ValueError, match="superposición"):
        bridgeCredentials.rotate(db, second.tokenHash[:8], overlapHours=bridgeCredentials.MAX_OVERLAP_HOURS + 1)
    short, _ = bridgeCredentials.create(db, "Corta", "ARD-002", validDays=1)
    rotated, _ = bridgeCredentials.rotate(db, short.tokenHash[:8], overlapHours=72)
    db.refresh(short)
    assert short.fechaExpiracion <= short.fechaCreacion + timedelta(days=1)  # nunca más allá de su propio vencimiento
    bridgeCredentials.revoke(db, second.tokenHash[:8])
    with pytest.raises(ValueError, match="revocada"):
        bridgeCredentials.rotate(db, second.tokenHash[:8])
    assert len(actions(db, "ROTAR_CREDENCIAL_PUENTE")) == 2


def test_referencias_inexistentes_o_ambiguas(db):
    a, _ = bridgeCredentials.create(db, "A", CODE)
    with pytest.raises(ValueError):
        bridgeCredentials.find(db, "ffffffff")
    with pytest.raises(ValueError):
        bridgeCredentials.find(db, "ab")  # una huella demasiado corta no identifica
    assert bridgeCredentials.find(db, str(a.idPuenteCredencial)).idPuenteCredencial == a.idPuenteCredencial


def test_ultimo_uso_se_registra_con_frecuencia_limitada(db):
    credential, token = bridgeCredentials.create(db, "A", CODE)
    assert credential.fechaUltimoUso is None
    bridgeCredentials.authenticate(db, token)
    db.refresh(credential)
    first = credential.fechaUltimoUso
    assert first is not None
    credential.fechaUltimoUso = None
    db.commit()
    bridgeCredentials.authenticate(db, token)  # dentro del intervalo: no vuelve a escribir
    db.refresh(credential)
    assert credential.fechaUltimoUso is None


def test_la_linea_de_comandos_exige_confirmar_la_base_y_no_muestra_secretos_al_listar(db, engine, monkeypatch, capsys):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(bridgeTokens, "getJobsSessionFactory", lambda: sessions)
    base = getSettings().DB_NAME
    assert bridgeTokens.main(["crear", "--nombre", "P", "--dispositivo", CODE]) == 2
    assert bridgeTokens.main(["crear", "--nombre", "P", "--dispositivo", CODE, "--confirmo-base", "OtraBase"]) == 2
    assert db.scalars(select(BridgeCredential)).all() == []
    capsys.readouterr()
    assert bridgeTokens.main(["crear", "--nombre", "P", "--dispositivo", CODE, "--confirmo-base", base]) == 0
    token = capsys.readouterr().out.strip().splitlines()[-1]
    assert len(token) >= 60
    assert bridgeTokens.main(["listar"]) == 0
    listing = capsys.readouterr().out
    assert token not in listing and CODE in listing and "ACTIVA" in listing
    huella = listing.splitlines()[1].split()[0]
    assert bridgeTokens.main(["revocar", "--huella", huella, "--confirmo-base", base]) == 0
    assert bridgeTokens.main(["rotar", "--huella", huella, "--confirmo-base", base]) == 1  # revocada: no se rota
    capsys.readouterr()
    assert bridgeTokens.main(["revocar", "--huella", "00000000", "--confirmo-base", base]) == 1
