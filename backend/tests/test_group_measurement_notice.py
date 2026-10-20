# Aviso de medición al grupo familiar: cuando una persona completa una medición y autorizó el aviso
# (GrupoUsuario.notificaMedicion), los demás integrantes reciben un correo que dice QUIÉN se midió y CUÁNDO, nunca el valor.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_group_measurement_notice.py -v

import re

import pytest

from app.services import group as groups
from app.services import measurement as measurements
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_groups import create, freshLimiter, join, person, share  # noqa: F401
from tests.test_measurements import completeOximetry, device, noEstimator  # noqa: F401

SUBJECT = "Un integrante de tu grupo se midió"


@pytest.fixture
def pair(db, mails):
    """Juan (se mide) y Pepe, en el mismo grupo; ninguno comparte nada todavía."""
    juan, pepe = person(db, "juan", ), person(db, "pepe")
    group = create(db, juan)
    join(db, juan, group.idGrupo, pepe)
    profile = measurements.getOwnProfile(db, juan)
    mails.clear()
    return juan, pepe, group.idGrupo, profile.idPerfilMedicion


def notices(mails):
    return [m for m in mails if m["subject"] == SUBJECT]


def test_el_aviso_esta_apagado_por_defecto(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    assert groups.getMySharing(db, juan, idGrupo).notificaMedicion is False
    completeOximetry(db, juan, profileId, device(db))
    assert notices(mails) == []


def test_avisa_quien_y_cuando_pero_nunca_el_valor(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    assert share(db, juan, idGrupo, notificaMedicion=True).notificaMedicion is True
    done = completeOximetry(db, juan, profileId, device(db), spo2="97.5", hr=72)

    [mail] = notices(mails)
    assert mail["to"] == "pepe@example.com"
    for part in (mail["html"], mail["text"]):
        assert juan.nombre in part and juan.apellido in part
        # Ninguna magnitud de la medición (SpO₂, frecuencia cardíaca, glucosa) ni sus unidades.
        for word in ("SpO", "glucosa", "lpm", "mg/dL"):
            assert word not in part, word
    assert "%" not in mail["text"]
    # Los números sueltos solo se buscan en el texto plano: en el HTML podrían coincidir con colores o estilos.
    for number in (str(done.spo2), str(done.frecuenciaCardiaca), "97", "72"):
        assert not re.search(rf"(?<![\w.]){re.escape(number)}(?![\w.])", mail["text"]), number
    assert f"/app/grupo/{idGrupo}" in mail["text"]


def test_no_se_avisa_a_quien_se_midio_y_solo_a_integrantes_activos(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    ana = person(db, "ana")
    join(db, juan, idGrupo, ana)
    groups.leaveGroup(db, ana, idGrupo)
    mails.clear()
    share(db, juan, idGrupo, notificaMedicion=True)
    completeOximetry(db, juan, profileId, device(db))
    assert [m["to"] for m in notices(mails)] == ["pepe@example.com"]


def test_el_aviso_no_habilita_ver_datos(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    share(db, juan, idGrupo, notificaMedicion=True)
    completeOximetry(db, juan, profileId, device(db))
    link = next(m for m in groups.sharedMembers(db, pepe, idGrupo)).idGrupoUsuario
    for fn in (groups.sharedProfile, groups.sharedLatest, groups.sharedHistory, groups.sharedStatistics):
        with pytest.raises(Exception) as error:
            fn(db, pepe, idGrupo, link)
        assert getattr(error.value, "code", None) == "DATOS_NO_COMPARTIDOS"


def test_revocar_o_abandonar_apaga_el_aviso(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    share(db, juan, idGrupo, notificaMedicion=True)
    share(db, juan, idGrupo)  # revoca todo
    completeOximetry(db, juan, profileId, device(db))
    assert notices(mails) == []


def test_un_fallo_del_correo_no_afecta_la_medicion(db, mails, pair, monkeypatch):
    from app.services import email as emailService

    juan, pepe, idGrupo, profileId = pair
    share(db, juan, idGrupo, notificaMedicion=True)
    monkeypatch.setattr(emailService, "sendEmailEvent", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp")))
    assert completeOximetry(db, juan, profileId, device(db)).estadoMedicion == "COMPLETADA"


def test_una_medicion_invalida_no_avisa(db, mails, pair):
    juan, pepe, idGrupo, profileId = pair
    share(db, juan, idGrupo, notificaMedicion=True)
    started = measurements.startMeasurement(db, juan, measurements_start(juan, profileId, device(db)))
    measurements.addSamples(db, juan, started.idMedicion, tinySamples())
    result = measurements.finishMeasurement(db, juan, started.idMedicion, measurements_finish())
    assert result.estadoMedicion == "INVALIDA" and notices(mails) == []


def measurements_start(user, profileId, dev):
    from app.schemas.measurement import MeasurementStart

    return MeasurementStart(idPerfilMedicion=profileId, idDispositivo=dev.idDispositivo)


def measurements_finish():
    from app.schemas.measurement import MeasurementFinish

    return MeasurementFinish()


def tinySamples():
    from tests.test_measurements import samples

    return samples()
