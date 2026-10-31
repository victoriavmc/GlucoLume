# Autoridad sobre las órdenes al puente serie (POST /acquisition/bridge/command).
#
#     python -m pytest tests/test_bridge_command_authority.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): cualquier cuenta que puede medir (una cuenta individual autorregistrada) podía detener,
# pausar o reconfigurar el puente que atiende un dispositivo de OTRA institución. Datos sintéticos, SQLite temporal.

import pytest
from sqlalchemy import select

from app.acquisition.telemetry import hub
from app.models.audit import Audit
from app.schemas.acquisition import BridgeIngest, BridgePort
from app.services import telemetry as telemetryService
from tests.test_account_deletion import audits, db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401
from tests.test_institutions import team  # noqa: F401
from tests.test_matrices import north  # noqa: F401
from tests.test_measurements import consumer, device  # noqa: F401
from tests.test_telemetry import CODE, FakeBridge, bridge, clock, freshHub, line  # noqa: F401

COMMAND = "/api/v1/acquisition/bridge/command"
CONTROL = "/api/v1/acquisition/telemetry/control"  # «Usar dispositivo»: control temporal, obligatorio para dar órdenes


def beat(db, bridgeId):
    return telemetryService.ingest(db, BridgeIngest(
        idPuente=bridgeId, codigoDispositivo=CODE, puerto="COM4", medio="BLUETOOTH", baudios=9600, estadoEnlace="CONECTADO",
        puertos=[BridgePort(puerto="COM3", descripcion="USB-SERIAL CH340 (COM3)", esArduino=True),
                 BridgePort(puerto="COM4", descripcion="Bluetooth link (COM4)", esBluetooth=True)], versionPuente="1.2.0"))


def refused(db):
    return db.scalars(select(Audit).where(Audit.accion == "ORDEN_PUENTE_SERIE", Audit.resultado == "FALLO")).all()


def test_una_cuenta_ajena_no_puede_ordenar_al_puente_de_una_institucion(db, mails, team, bridge, api, deviceMode):
    deviceMode(False)  # modo restringido por asignación (DEC-01); el modo compartido se prueba en test_device_context_authority
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    outsider = makeUser(db, email="ajena@example.com", usuario="ajena")  # cuenta individual sin relación con la institución
    for payload in ({"accion": "DETENER"}, {"accion": "CONFIGURAR", "puerto": "COM3", "medio": "usb"}, {"accion": "REINICIAR"}):
        response = api(outsider).post(COMMAND, json=payload)
        assert response.status_code == 403 and response.json()["codigo"] == "PERMISO_INSUFICIENTE"
    assert beat(db, bridge.id).comando is None, "el puente no recibe ninguna orden de la cuenta ajena"
    assert len(refused(db)) == 3 and all(a.idUsuario == outsider.idUsuario for a in refused(db))  # intentos auditados


def test_un_operador_de_otra_institucion_tampoco(db, mails, team, north, bridge, api):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    for foreign in (north.operator,):  # operador ACTIVO de la Clínica Norte (puede medir en la suya), sin vínculo con `team`
        response = api(foreign).post(COMMAND, json={"accion": "DETENER"})
        assert response.status_code == 403 and response.json()["codigo"] == "PERMISO_INSUFICIENTE"
    assert beat(db, bridge.id).comando is None


def test_el_operador_de_la_institucion_duena_si_puede(db, mails, team, bridge, api):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    assert api(team.operator).post(CONTROL).status_code == 200
    response = api(team.operator).post(COMMAND, json={"accion": "DETENER"})
    assert response.status_code == 200 and response.json()["puente"]["comandoPendiente"] == "DETENER"
    assert beat(db, bridge.id).comando.accion == "DETENER"
    assert not refused(db)


def test_moderador_y_propietario_no_miden_y_siguen_sin_poder_ordenar(db, mails, team, bridge, api):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    for viewer in (team.moderator, team.owner):
        assert api(viewer).post(COMMAND, json={"accion": "DETENER"}).status_code == 403


def test_el_dispositivo_sin_institucion_conserva_la_regla_general(db, mails, bridge, api):
    """Pool compartido de cuentas individuales: quien puede medir sigue pudiendo configurar su puente."""
    device(db, institucion=None, codigo=CODE)
    bridge.seconds(2)
    person = makeUser(db, email="persona@example.com", usuario="persona")
    assert api(person).post(CONTROL).status_code == 200
    response = api(person).post(COMMAND, json={"accion": "DETENER"})
    assert response.status_code == 200 and response.json()["puente"]["comandoPendiente"] == "DETENER"


def test_el_modo_automatico_se_ordena_sin_puerto_y_el_puente_lo_informa_sin_dispositivo(db, mails, team, bridge, api):
    device(db, institucion=team.id, codigo=CODE)
    bridge.seconds(2)
    assert api(team.operator).post(CONTROL).status_code == 200
    rejected = api(team.operator).post(COMMAND, json={"accion": "CONFIGURAR", "medio": "AUTO", "puerto": "COM3"})
    assert rejected.status_code != 200  # con AUTO no se admite un puerto fijo
    response = api(team.operator).post(COMMAND, json={"accion": "CONFIGURAR", "medio": "AUTO"})
    assert response.status_code == 200
    pending = response.json()["puente"]["comandoPendiente"]
    assert pending == "CONFIGURAR"
    # El puente, sin dispositivo a la vista, informa DISPOSITIVO_DESCONECTADO con medio AUTO y sin puerto: se acepta sin error.
    result = telemetryService.ingest(db, BridgeIngest(
        idPuente=bridge.id, codigoDispositivo=CODE, puerto=None, medio="AUTO", baudios=None,
        estadoEnlace="DISPOSITIVO_DESCONECTADO", puertos=[], versionPuente="1.4.0"))
    assert result.comando.accion == "CONFIGURAR" and result.comando.medio == "AUTO"
