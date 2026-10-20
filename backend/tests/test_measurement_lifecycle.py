# Conservación, visibilidad y auditoría técnica anonimizada de las mediciones según su estado.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_measurement_lifecycle.py -v
#
# COMPLETADA se conserva; CANCELADA / INVALIDA se ocultan del historial personal a los 30 minutos; las incompletas sin actividad vencen
# a INVALIDA (TIEMPO_AGOTADO). Nunca se borra el registro y la auditoría técnica no identifica a nadie.

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.acquisition.telemetry import ABANDON_SECONDS, hub
from app.models.audit import Audit
from app.models.measurement import Measurement
from app.models.technicalAudit import TechnicalAudit
from app.services import maintenance, measurementLifecycle, technicalAudit
from app.services import measurement as measurements
from app.services import telemetry as telemetryService
from app.services.measurementVisibility import VISIBLE_MINUTES
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_dashboards import dashboards  # noqa: F401
from tests.test_measurements import completeOximetry, consumer, device, expectError, oximetry  # noqa: F401
from tests.test_telemetry import CODE, bridge, clock, freshHub, startFor  # noqa: F401


def shift(db, idMedicion, *, minutes, end=True):
    """Envejece una medición `minutes` minutos (inicio y, si ya cerró, fin)."""
    row = db.get(Measurement, idMedicion)
    values = {"fechaHoraInicio": row.fechaHoraInicio - timedelta(minutes=minutes)}
    if end and row.fechaHoraFin is not None:
        values["fechaHoraFin"] = row.fechaHoraFin - timedelta(minutes=minutes)
    db.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(**values))
    db.commit()
    db.expire_all()


def history(db, user, **filters):
    return [item.idMedicion for item in measurements.listOwnHistory(db, user, **filters).items]


def technical(db):
    db.expire_all()
    return list(db.scalars(select(TechnicalAudit)))


# 1 y 2 -------------------------------------------------------------------------------------------------------------------------


def test_1_una_medicion_completada_se_conserva_pasados_los_30_minutos(db, mails, consumer):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    shift(db, done.idMedicion, minutes=5 * 60)
    measurementLifecycle.sweep(db)
    assert history(db, user) == [done.idMedicion]
    assert measurements.getMeasurement(db, user, done.idMedicion).estadoMedicion == "COMPLETADA"
    assert db.get(Measurement, done.idMedicion).estadoMedicion == "COMPLETADA"  # el mantenimiento no la toca


def test_2_una_prueba_demo_completada_sigue_en_el_historial_de_pruebas(db, mails, consumer):
    user, profileId = consumer
    done = completeOximetry(db, user, profileId, device(db))
    db.execute(update(Measurement).where(Measurement.idMedicion == done.idMedicion).values(
        origenGlucosa="DEMO", glucosaDispositivo=114, unidadGlucosa="mg/dL"))
    db.commit()
    shift(db, done.idMedicion, minutes=24 * 60)
    measurementLifecycle.sweep(db)
    assert history(db, user, origen="DEMO") == [done.idMedicion]
    # Pero sigue fuera de los indicadores experimentales.
    assert dashboards.personalDashboard(db, user, 30).resumen.completadas == 0


# 3 y 4 -------------------------------------------------------------------------------------------------------------------------


def test_3_una_cancelada_se_ve_30_minutos_y_despues_desaparece_de_la_vista_personal(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, started.idMedicion)
    # Recién cancelada: visible, con hasta cuándo.
    item = measurements.listOwnHistory(db, user).items[0]
    assert item.estadoMedicion == "CANCELADA" and item.visibleHasta is not None
    assert measurements.getMeasurement(db, user, started.idMedicion).visibleHasta is not None
    shift(db, started.idMedicion, minutes=VISIBLE_MINUTES - 1)
    assert history(db, user) == [started.idMedicion]  # a los 29 minutos todavía se ve
    shift(db, started.idMedicion, minutes=2)
    assert history(db, user) == []  # a los 31 ya no
    # No se borró: el registro y su auditoría siguen en la base.
    assert db.get(Measurement, started.idMedicion).estadoMedicion == "CANCELADA"
    assert db.scalar(select(Audit).where(Audit.accion == "CANCELAR_MEDICION", Audit.idRegistro == started.idMedicion)) is not None


def test_4_una_invalida_se_oculta_a_los_30_minutos_con_su_motivo_registrado(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    now = nowForDb()
    db.execute(update(Measurement).where(Measurement.idMedicion == started.idMedicion).values(
        estadoMedicion="INVALIDA", fechaHoraFin=now))
    db.commit()
    assert history(db, user) == [started.idMedicion]
    shift(db, started.idMedicion, minutes=VISIBLE_MINUTES + 1)
    assert history(db, user) == []
    assert db.get(Measurement, started.idMedicion) is not None


# 5 y 6 -------------------------------------------------------------------------------------------------------------------------


def test_5_una_medicion_pendiente_sin_actividad_vence_a_invalida_y_queda_oculta(db, mails, consumer):
    user, profileId = consumer
    pending = oximetry(db, user, profileId, device(db))
    assert pending.estadoMedicion == "PENDIENTE"
    shift(db, pending.idMedicion, minutes=VISIBLE_MINUTES + 1, end=False)
    assert measurementLifecycle.sweep(db)["invalidadas"] == 1
    row = db.get(Measurement, pending.idMedicion)
    assert row.estadoMedicion == "INVALIDA" and row.fechaHoraFin == row.fechaHoraInicio
    assert history(db, user) == []  # oculta al cumplirse el plazo de inactividad
    event = db.scalar(select(Audit).where(Audit.accion == "INVALIDAR_MEDICION_TIEMPO_AGOTADO"))
    assert event is not None and "TIEMPO_AGOTADO" in event.datosNuevos and event.idRegistro == pending.idMedicion
    [row] = technical(db)
    assert (row.estadoFinal, row.motivo, row.tipoOperacion) == ("INVALIDA", "TIEMPO_AGOTADO", "MANTENIMIENTO")
    # Idempotente: otra pasada no la vuelve a procesar ni duplica la auditoría.
    assert measurementLifecycle.sweep(db)["invalidadas"] == 0 and len(technical(db)) == 1


def test_una_medicion_reciente_sin_actividad_todavia_no_vence(db, mails, consumer):
    user, profileId = consumer
    pending = oximetry(db, user, profileId, device(db))
    shift(db, pending.idMedicion, minutes=VISIBLE_MINUTES - 5, end=False)
    assert measurementLifecycle.sweep(db)["invalidadas"] == 0
    assert db.get(Measurement, pending.idMedicion).estadoMedicion == "PENDIENTE"


def test_6_una_adquisicion_activa_no_se_cancela_por_error(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    started = startFor(db, user, profileId, dev)
    shift(db, started.idMedicion, minutes=VISIBLE_MINUTES + 20, end=False)  # lleva más de 30 min en la base...
    telemetryService.status(db, user)  # ...pero su dueño sigue consultando: hay una sesión viva
    assert measurementLifecycle.sweep(db)["invalidadas"] == 0
    assert db.get(Measurement, started.idMedicion).estadoMedicion == "ADQUIRIENDO" and hub.session is not None


def test_una_medicion_que_se_completa_justo_antes_del_vencimiento_no_se_pisa(db, mails, consumer, monkeypatch):
    user, profileId = consumer
    pending = oximetry(db, user, profileId, device(db))
    shift(db, pending.idMedicion, minutes=VISIBLE_MINUTES + 1, end=False)
    real = measurements._transition

    def completedFirst(database, idMedicion, expected, new, **values):  # otro proceso gana la carrera
        database.execute(update(Measurement).where(Measurement.idMedicion == idMedicion).values(
            estadoMedicion="COMPLETADA", fechaHoraFin=nowForDb()))
        database.commit()  # confirmado por el otro proceso antes de que el mantenimiento escriba
        return real(database, idMedicion, expected, new, **values)

    monkeypatch.setattr(measurements, "_transition", completedFirst)
    assert measurementLifecycle.sweep(db)["invalidadas"] == 0
    assert db.get(Measurement, pending.idMedicion).estadoMedicion == "COMPLETADA"
    assert technical(db) == []


# 7 -----------------------------------------------------------------------------------------------------------------------------


def test_7_una_sesion_abandonada_libera_el_arduino_aunque_nadie_consulte(db, mails, consumer, bridge, clock):
    user, profileId = consumer
    dev = device(db, codigo=CODE)
    bridge.seconds(1)
    started = startFor(db, user, profileId, dev)
    clock.advance(ABANDON_SECONDS + 5)
    bridge.seconds(1)
    measurementLifecycle.sweep(db)  # lo hace el mantenimiento, sin ninguna petición de usuarios
    assert hub.session is None
    assert db.get(Measurement, started.idMedicion).estadoMedicion == "CANCELADA"
    [row] = technical(db)
    assert (row.estadoFinal, row.motivo, row.tipoOperacion) == ("CANCELADA", "SESION_ABANDONADA", "SESION_DISPOSITIVO")


# 8 -----------------------------------------------------------------------------------------------------------------------------


def test_8_una_medicion_oculta_no_se_consulta_por_su_id_ni_por_url(api, db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, started.idMedicion)
    client = api(user)
    assert client.get(f"/api/v1/measurements/{started.idMedicion}").status_code == 200
    shift(db, started.idMedicion, minutes=VISIBLE_MINUTES + 1)
    assert client.get(f"/api/v1/measurements/{started.idMedicion}").status_code == 404
    assert client.get("/api/v1/measurements").json()["total"] == 0
    expectError("MEDICION_NO_ENCONTRADA", measurements.getMeasurement, db, user, started.idMedicion)


# 9 -----------------------------------------------------------------------------------------------------------------------------


def test_9_el_auditor_ve_la_informacion_tecnica_sin_identificar_a_nadie(api, db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, started.idMedicion)
    admin = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA", email="admin@example.com", usuario="admin")
    body = api(admin).get("/api/v1/audit/technical-measurements").json()
    [event] = body["items"]
    assert set(event) == {"idEvento", "fechaHora", "tipoOperacion", "estadoFinal", "motivo", "modeloSensor", "duracionSegundos", "codigoError"}
    assert (event["estadoFinal"], event["motivo"]) == ("CANCELADA", "CANCELADA_POR_USUARIO")
    assert event["idEvento"] != str(started.idMedicion)
    assert event["fechaHora"].endswith("00:00")  # hora en punto: no se cruza con la auditoría general por el instante
    flat = str(body)
    assert str(user.idUsuario) not in flat and str(profileId) not in flat and str(started.idMedicion) not in flat
    summary = api(admin).get("/api/v1/audit/technical-measurements/summary").json()
    assert summary["total"] == 1 and summary["porMotivo"] == {"CANCELADA_POR_USUARIO": 1}
    # Cualquier otra cuenta, incluida la dueña, recibe 403.
    assert api(user).get("/api/v1/audit/technical-measurements").status_code == 403


def test_la_tabla_tecnica_no_tiene_ninguna_columna_que_identifique_a_la_persona():
    names = {column.name for column in TechnicalAudit.__table__.columns}
    assert names.isdisjoint({"idUsuario", "idPerfilMedicion", "idMedicion", "idDispositivo", "idInstitucion", "correoElectronico", "usuario"})
    assert not TechnicalAudit.__table__.foreign_keys  # sin ninguna relación con usuarios, perfiles ni mediciones


def test_la_auditoria_tecnica_se_purga_por_antiguedad(db, mails, consumer):
    user, profileId = consumer
    started = oximetry(db, user, profileId, device(db))
    measurements.cancelMeasurement(db, user, started.idMedicion)
    db.execute(update(TechnicalAudit).values(fechaHora=nowForDb() - timedelta(days=technicalAudit.RETENTION_DAYS + 1)))
    db.commit()
    assert measurementLifecycle.sweep(db)["purgadas"] == 1 and technical(db) == []


# 10 ----------------------------------------------------------------------------------------------------------------------------


def test_10_dashboard_y_estadisticas_no_incluyen_canceladas_invalidas_ni_incompletas(db, mails, consumer):
    user, profileId = consumer
    dev = device(db)
    good = completeOximetry(db, user, profileId, dev, spo2="98", hr=70)
    cancelled = oximetry(db, user, profileId, dev)
    measurements.cancelMeasurement(db, user, cancelled.idMedicion)
    oximetry(db, user, profileId, dev)  # pendiente
    data = dashboards.personalDashboard(db, user, 30)
    assert [m.idMedicion for m in data.recientes] == [good.idMedicion]
    assert data.resumen.completadas == 1 and data.estadisticas.cantidadMediciones == 1
    evolution = measurements.ownEvolution(db, user, 7, origen="TODOS")
    assert [p.idMedicion for p in evolution.puntos] == [good.idMedicion]
    # Vencidas: el total del resumen personal tampoco las cuenta.
    shift(db, cancelled.idMedicion, minutes=VISIBLE_MINUTES + 1)
    assert dashboards.personalDashboard(db, user, 30).resumen.total == 2  # la completada y la pendiente


# 11 ----------------------------------------------------------------------------------------------------------------------------


def test_11_el_mantenimiento_arranca_con_la_aplicacion_y_vuelve_a_hacerlo_tras_reiniciar(monkeypatch):
    runs = []
    monkeypatch.setattr(maintenance, "runOnce", lambda: runs.append(1))
    monkeypatch.setattr(maintenance, "FIRST_RUN_DELAY_SECONDS", 0.01)

    class Settings:
        MAINTENANCE_INTERVAL_SECONDS = 0.05

    monkeypatch.setattr(maintenance, "getSettings", lambda: Settings())

    async def boot():
        async with maintenance.lifespan(None):
            await asyncio.sleep(0.3)

    asyncio.run(boot())
    first = len(runs)
    assert first >= 2  # corre periódicamente
    asyncio.run(boot())  # «reinicio de contenedores»: vuelve a arrancar solo
    assert len(runs) >= first + 2


def test_una_medicion_pendiente_de_antes_del_reinicio_se_cierra_aunque_la_memoria_este_vacia(db, mails, consumer):
    user, profileId = consumer
    orphan = oximetry(db, user, profileId, device(db))
    shift(db, orphan.idMedicion, minutes=VISIBLE_MINUTES + 10, end=False)
    hub.reset()  # se perdió el estado en memoria (reinicio del contenedor)
    assert maintenance_pass(db) == 1
    assert db.get(Measurement, orphan.idMedicion).estadoMedicion == "INVALIDA"


def maintenance_pass(db):
    return measurementLifecycle.sweep(db)["invalidadas"]


def test_runOnce_no_propaga_errores(monkeypatch):
    monkeypatch.setattr(maintenance, "getSessionFactory", lambda: (_ for _ in ()).throw(RuntimeError("sin base")))
    assert maintenance.runOnce() is None
