# POST /devices/resolve: el firmware identificado solo lo registra quien administra el inventario, sobre dispositivos de su ámbito.
#
#     python -m pytest tests/test_device_resolve_authority.py -v
#
# Hallazgo de la auditoría Cloudflare (run-1): cualquier cuenta autenticada reescribía versionFirmware de un dispositivo del pool compartido (o un
# operador, el de un dispositivo que no podía editar) y el valor falso se copiaba a versionFirmwareAlMomento de las mediciones de otras cuentas.

from app.models.device import Device
from tests.test_account_deletion import db, engine, mails, makeUser, reload  # noqa: F401 - fixtures
from tests.test_devices import platformModerator, resolve  # noqa: F401
from tests.test_institutions import team  # noqa: F401
from tests.test_matrices import north  # noqa: F401
from tests.test_measurements import device  # noqa: F401


def firmware(db, dev):
    return reload(db, Device, dev.idDispositivo).versionFirmware


def test_una_cuenta_individual_no_reescribe_el_firmware_del_pool_compartido(db, mails):
    pool = device(db, institucion=None, codigo="GL-POOL", firmware="1.2.0")
    person = makeUser(db, email="persona@example.com", usuario="persona")
    result = resolve(db, person, "GL-POOL", versionFirmware="EVIL-9.9.9")
    assert not result.firmwareActualizado and firmware(db, pool) == "1.2.0"


def test_un_operador_no_reescribe_el_firmware_ni_siquiera_de_su_institucion(db, mails, team):
    own = device(db, institucion=team.id, codigo="GL-OWN", firmware="1.2.0")
    result = resolve(db, team.operator, "GL-OWN", versionFirmware="OP-2.0", idInstitucion=team.id)
    assert not result.firmwareActualizado and firmware(db, own) == "1.2.0"


def test_una_institucion_no_reescribe_el_firmware_de_un_dispositivo_del_pool(db, mails, team):
    pool = device(db, institucion=None, codigo="GL-POOL2", firmware="1.2.0")
    result = resolve(db, team.owner, "GL-POOL2", versionFirmware="OWN-3.0", idInstitucion=team.id)
    assert not result.firmwareActualizado and firmware(db, pool) == "1.2.0"


def test_quien_administra_el_inventario_si_registra_el_firmware_de_su_ambito(db, mails, team, platformModerator):
    own = device(db, institucion=team.id, codigo="GL-OWN2", firmware="1.2.0")
    assert resolve(db, team.owner, "GL-OWN2", versionFirmware="1.3.0", idInstitucion=team.id).firmwareActualizado
    assert firmware(db, own) == "1.3.0"
    pool = device(db, institucion=None, codigo="GL-POOL3", firmware="1.2.0")
    assert resolve(db, platformModerator, "GL-POOL3", versionFirmware="1.4.0").firmwareActualizado  # la plataforma administra el pool
    assert firmware(db, pool) == "1.4.0"
