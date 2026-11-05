# Aviso de «medición realizada» para cuentas individuales: cartel en la página con la hora, el modo y los valores; por correo solo si la
# cuenta lo eligió (con el detalle y un enlace a esa medición). Cubre los dos caminos que completan una medición: el dispositivo en vivo
# y las muestras procesadas por el servidor. Una medición DEMO o de una institución no avisa, y una cuenta institucional no ve el aviso.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_notifications.py -v

import pytest
from sqlalchemy import select, update

from app.core.exceptions import AuthError
from app.models.measurement import Measurement
from app.models.userNotification import UserNotification
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from app.services import userNotifications as service
from tests.test_account_deletion import audits, db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_dashboards import measure
from tests.test_institutions import freshLookupLimiter, team  # noqa: F401 - fixtures
from tests.test_measurements import consumer, device  # noqa: F401 - fixtures
from tests.test_telemetry import CODE, bridge, clock, freshHub, line, startFor  # noqa: F401 - fixtures

TITULO = "Ya está disponible tu última medición"


def avisos(db, user):
    db.expire_all()
    return list(db.scalars(select(UserNotification).where(
        UserNotification.idUsuario == user.idUsuario, UserNotification.evento == "MEDICION_REALIZADA")))


def individual(db, email="persona@example.com", usuario="persona"):
    user = makeUser(db, email=email, usuario=usuario)
    return user, measurements.getOwnProfile(db, user).idPerfilMedicion


def test_una_medicion_individual_avisa_en_la_pagina_con_hora_modo_y_valores(db, mails):
    user, profileId = individual(db)
    done = measure(db, user, profileId, device(db), "97", 72)
    stored = db.get(Measurement, done.idMedicion)

    [aviso] = avisos(db, user)
    assert aviso.titulo == TITULO
    assert aviso.mensaje.startswith(f"Te mediste el {stored.fechaHoraInicio:%d/%m/%Y} a las {stored.fechaHoraInicio:%H:%M} (Oximetría)")
    # El valor que se muestra es el guardado (promedio de las muestras), no el de la primera lectura.
    assert f"SpO₂ {float(stored.spo2):g} %" in aviso.mensaje and "frecuencia cardíaca 72 lpm" in aviso.mensaje
    assert aviso.url == f"/app/mediciones/{done.idMedicion}"
    # Por omisión solo aparece en la página: sin correo elegido no sale ninguno.
    assert aviso.estadoCorreo is None and not mails


def test_con_correo_elegido_sale_el_detalle_y_un_enlace_a_esa_medicion(db, mails):
    user, profileId = individual(db)
    service.updatePreference(db, user, "MEDICION_REALIZADA", porCorreo=True)
    done = measure(db, user, profileId, device(db), "96", 80)

    [correo] = [m for m in mails if m["to"] == user.correoElectronico]
    assert correo["subject"] == "Nueva medición registrada"
    stored = db.get(Measurement, done.idMedicion)
    assert "Oximetría" in correo["html"] and f"{float(stored.spo2):g}" in correo["html"] and "80" in correo["html"]
    assert f"/app/mediciones/{done.idMedicion}" in correo["html"]
    assert [a.estadoCorreo for a in avisos(db, user)] == ["ENVIADO"]


def test_la_medicion_en_vivo_desde_el_dispositivo_tambien_avisa(db, consumer, bridge, mails):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    started = startFor(db, user, profileId, dev)
    for _ in range(9):  # lecturas estables de una medición real (no DEMO)
        bridge.send([line(bpm="72.00", spo2="97.00", glu="117.0", origen="EXPERIMENTAL", index="2.41492")])
        bridge.clock.advance(1)

    saved = telemetryService.saveSession(db, user)
    assert saved.estadoMedicion == "COMPLETADA" and saved.idMedicion == started.idMedicion
    [aviso] = avisos(db, user)
    assert aviso.url == f"/app/mediciones/{saved.idMedicion}" and f"SpO₂ {float(saved.spo2):g} %" in aviso.mensaje
    assert not mails  # el correo es opcional y esta cuenta no lo eligió


def test_una_medicion_demo_o_de_una_institucion_no_avisa(db, mails):
    user, profileId = individual(db)
    done = measure(db, user, profileId, device(db), "97", 72)
    before = len(avisos(db, user))
    stored = db.get(Measurement, done.idMedicion)

    assert service.notifyMeasurementCompleted(db, user, stored, institutional=True) is False  # de una institución

    # Una medición DEMO lleva también su glucosa (CK_Medicion_origenConGlucosa): se marca como tal con sus dos campos.
    db.execute(update(Measurement).where(Measurement.idMedicion == done.idMedicion).values(
        origenGlucosa="DEMO", glucosaDispositivo="117.00", unidadGlucosa="mg/dL"))
    db.commit()
    stored = db.get(Measurement, done.idMedicion)
    assert service.notifyMeasurementCompleted(db, user, stored, institutional=False) is False  # DEMO: una prueba, no una medición
    assert len(avisos(db, user)) == before


def test_el_mismo_hecho_no_duplica_el_aviso_ni_el_correo(db, mails):
    user, profileId = individual(db)
    service.updatePreference(db, user, "MEDICION_REALIZADA", porCorreo=True)
    done = measure(db, user, profileId, device(db), "97", 72)
    stored = db.get(Measurement, done.idMedicion)

    assert service.notifyMeasurementCompleted(db, user, stored, institutional=False) is False
    assert len(avisos(db, user)) == 1
    assert len([m for m in mails if m["to"] == user.correoElectronico]) == 1


def test_una_cuenta_institucional_no_ve_ni_puede_cambiar_este_aviso(db, team, mails):
    operador = team.operator
    assert "MEDICION_REALIZADA" not in [p.evento for p in service.settings(db, operador).preferencias]
    with pytest.raises(AuthError) as raised:
        service.updatePreference(db, operador, "MEDICION_REALIZADA", enPagina=False)
    assert raised.value.code == "EVENTO_NO_VALIDO"


def test_la_cuenta_individual_si_ve_el_aviso_con_su_preferencia_por_omision(db, mails):
    user, _ = individual(db)
    [preference] = [p for p in service.settings(db, user).preferencias if p.evento == "MEDICION_REALIZADA"]
    assert (preference.categoria, preference.enPagina, preference.porCorreo, preference.correoDisponible) == ("MEDICION", True, False, True)
