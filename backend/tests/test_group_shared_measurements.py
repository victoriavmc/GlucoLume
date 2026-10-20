# Mediciones compartidas en el grupo familiar: pertenecen al PERFIL de su dueño (no al grupo), se comparten con autorización expresa sin
# importar cuándo se hicieron, incluyen las pruebas DEMO (identificadas) y NUNCA entran en estadísticas experimentales.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_group_shared_measurements.py -v

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.device import Device
from app.models.measurement import Measurement
from app.services import dashboard as dashboards
from app.services import group as groups
from app.services import measurement as measurements
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import db, engine, mails, makeUser  # noqa: F401 - fixtures
from tests.test_audit import api  # noqa: F401 - fixture
from tests.test_groups import create, expectError, freshLimiter, join, person, relationOf, share  # noqa: F401


def add(db, profile, *, days=1, modo="OXIMETRIA", estado="COMPLETADA", demo=False, device=None, **values):
    """Una medición del perfil de `profile`. `demo=True`: valor sintético del firmware (origen DEMO) en glucosaDispositivo."""
    if device is None:
        device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30100")
        db.add(device)
        db.flush()
    extra = dict(origenGlucosa="DEMO", glucosaDispositivo=Decimal("114"), unidadGlucosa="mg/dL") if demo else {}
    row = Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo, modoMedicion=modo,
        estadoMedicion=estado, condicionComida="AYUNO", fechaHoraInicio=nowForDb() - timedelta(days=days),
        fechaHoraFin=nowForDb() - timedelta(days=days) + timedelta(seconds=30) if estado in ("COMPLETADA", "CANCELADA", "INVALIDA") else None,
        **{**dict(spo2=Decimal("97"), frecuenciaCardiaca=70), **extra, **values})
    db.add(row)
    db.commit()
    return row


def profileOf(db, user):
    measurements.getOwnProfile(db, user)  # crea el perfil propio si falta
    return groups._ownProfile(db, user.idUsuario)


@pytest.fixture
def home(db, mails):
    """Beto ya tenía mediciones ANTES de que existiera el grupo; Ana administra y se suma después."""
    beto = person(db, "beto")
    profile = profileOf(db, beto)
    before = [add(db, profile, days=40, spo2=Decimal("95")), add(db, profile, days=20, modo="GLUCOSA_EXPERIMENTAL", demo=True),
              add(db, profile, days=10, spo2=Decimal("96"))]
    ana = person(db, "ana")
    group = create(db, ana)
    join(db, ana, group.idGrupo, beto)
    mails.clear()

    class Home:
        pass

    home = Home()
    home.ana, home.beto, home.profile, home.before, home.id = ana, beto, profile, before, group.idGrupo
    home.betoLink = relationOf(db, group.idGrupo, beto).idGrupoUsuario
    home.anaLink = relationOf(db, group.idGrupo, ana).idGrupoUsuario
    return home


def rows(db):
    return db.scalar(select(func.count()).select_from(Measurement))


# --- 1 a 4 -------------------------------------------------------------------------------------------------------------------------


def test_1_el_historial_incluye_mediciones_anteriores_a_la_creacion_del_grupo(db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    history = groups.sharedHistory(db, home.ana, home.id, home.betoLink)
    assert history.total == 3 and {m.idMedicion for m in history.items} == {m.idMedicion for m in home.before}
    assert [m.idMedicion for m in history.items] == [home.before[2].idMedicion, home.before[1].idMedicion, home.before[0].idMedicion]  # recientes primero


def test_2_las_pruebas_demo_aparecen_identificadas_y_no_como_estimacion(db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    demo = next(m for m in groups.sharedHistory(db, home.ana, home.id, home.betoLink).items if m.esDemo)
    assert demo.modoMedicion == "GLUCOSA_EXPERIMENTAL" and demo.estadoMedicion == "COMPLETADA"
    assert (demo.origenGlucosa, float(demo.glucosaDispositivo), demo.unidadGlucosa) == ("DEMO", 114.0, "mg/dL")
    assert demo.glucosaEstimada is None  # el valor DEMO nunca se presenta como una estimación


def test_3_una_ultima_medicion_demo_se_muestra_como_ultima_compartida(db, home):
    add(db, home.profile, days=0.01, modo="GLUCOSA_EXPERIMENTAL", demo=True)
    share(db, home.beto, home.id, comparteUltimaMedicion=True)
    latest = groups.sharedLatest(db, home.ana, home.id, home.betoLink).medicion
    assert latest.esDemo and latest.origenGlucosa == "DEMO" and latest.modoMedicion == "GLUCOSA_EXPERIMENTAL"
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, home.ana, home.id, home.betoLink)  # el permiso de última no abre el historial


def test_4_una_medicion_nueva_aparece_sola_y_no_se_duplica_nada(db, home):
    share(db, home.beto, home.id, comparteUltimaMedicion=True, comparteHistorial=True)
    before = rows(db)
    new = add(db, home.profile, days=0)
    assert groups.sharedLatest(db, home.ana, home.id, home.betoLink).medicion.idMedicion == new.idMedicion
    assert groups.sharedHistory(db, home.ana, home.id, home.betoLink).total == 4
    assert rows(db) == before + 1  # solo la medición real: compartir y consultar no crea copias
    assert db.get(Measurement, new.idMedicion).idPerfilMedicion == home.profile.idPerfilMedicion


# --- 5 a 8 -------------------------------------------------------------------------------------------------------------------------


def test_5_y_6_el_detalle_respeta_el_permiso_de_cada_nivel(db, home):
    share(db, home.beto, home.id, comparteUltimaMedicion=True)
    latest = groups.sharedLatest(db, home.ana, home.id, home.betoLink).medicion
    detail = groups.sharedMeasurement(db, home.ana, home.id, home.betoLink, latest.idMedicion)
    assert detail.esUltima and detail.idMedicion == latest.idMedicion
    old = home.before[0].idMedicion
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedMeasurement, db, home.ana, home.id, home.betoLink, old)  # solo la última
    share(db, home.beto, home.id, comparteUltimaMedicion=True, comparteHistorial=True)
    assert groups.sharedMeasurement(db, home.ana, home.id, home.betoLink, old).esUltima is False  # con historial, cualquiera completada


def test_el_detalle_compartido_no_expone_datos_privados_y_no_sirve_para_medir_de_otro(db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    detail = groups.sharedMeasurement(db, home.ana, home.id, home.betoLink, home.before[1].idMedicion)
    assert set(detail.model_dump()).isdisjoint({"observacion", "dispositivo", "edadAlMomento", "sexoModelo", "idPerfilMedicion", "idDispositivo"})
    mine = add(db, profileOf(db, home.ana), days=2)
    expectError("MEDICION_NO_ENCONTRADA", groups.sharedMeasurement, db, home.ana, home.id, home.betoLink, mine.idMedicion)  # no es de Beto


def test_7_revocar_corta_el_acceso_de_inmediato_pero_conserva_las_mediciones(db, home):
    share(db, home.beto, home.id, comparteUltimaMedicion=True, comparteHistorial=True)
    assert groups.sharedHistory(db, home.ana, home.id, home.betoLink).total == 3
    count = rows(db)
    share(db, home.beto, home.id)  # revoca todo
    for call in (groups.sharedHistory, groups.sharedLatest, groups.sharedStatistics):
        expectError("DATOS_NO_COMPARTIDOS", call, db, home.ana, home.id, home.betoLink)
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedMeasurement, db, home.ana, home.id, home.betoLink, home.before[0].idMedicion)
    assert rows(db) == count and db.get(Measurement, home.before[0].idMedicion) is not None


def test_8_quien_abandona_el_grupo_conserva_sus_mediciones_y_los_demas_pierden_el_acceso(db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    count = rows(db)
    groups.leaveGroup(db, home.beto, home.id)
    expectError("MIEMBRO_NO_ENCONTRADO", groups.sharedHistory, db, home.ana, home.id, home.betoLink)
    assert rows(db) == count
    assert measurements.listOwnHistory(db, home.beto, estado="COMPLETADA").total == 3  # su historial personal intacto


# --- 9 y 10 ------------------------------------------------------------------------------------------------------------------------


def test_9_las_estadisticas_experimentales_excluyen_demo_y_las_pruebas_van_aparte(db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    stats = groups.sharedStatistics(db, home.ana, home.id, home.betoLink, dias=90)
    assert stats.cantidadMediciones == 2  # solo las dos de oximetría experimental (95 y 96): la DEMO no cuenta
    assert stats.spo2.promedio == pytest.approx(95.5, abs=0.2) and stats.glucosa.cantidad == 0
    assert stats.pruebasDemo == 1 and len(stats.puntosDemo) == 1 and stats.puntosDemo[0].glucosa == 114.0
    # Cada medición experimental llega con fecha y hora completas (para el gráfico de evolución); la DEMO no se mezcla.
    assert len(stats.puntos) == 2 and all(point.fecha is not None for point in stats.puntos)
    assert [point.fecha for point in stats.puntos] == sorted(point.fecha for point in stats.puntos)
    # Con solo pruebas DEMO: no hay estadísticas experimentales, pero sí pruebas para consultar.
    solo = person(db, "solo")
    add(db, profileOf(db, solo), days=2, modo="GLUCOSA_EXPERIMENTAL", demo=True)
    join(db, home.ana, home.id, solo)
    link = relationOf(db, home.id, solo).idGrupoUsuario
    share(db, solo, home.id, comparteHistorial=True)
    only = groups.sharedStatistics(db, home.ana, home.id, link, dias=30)
    assert only.cantidadMediciones == 0 and only.pruebasDemo == 1 and only.glucosa.promedio is None
    assert groups.sharedHistory(db, home.ana, home.id, link).total == 1  # existen registros compartidos


def test_el_dashboard_del_grupo_muestra_la_ultima_demo_pero_no_la_promedia(db, home):
    add(db, home.profile, days=0.01, modo="GLUCOSA_EXPERIMENTAL", demo=True)
    share(db, home.beto, home.id, comparteUltimaMedicion=True, comparteHistorial=True)
    share(db, home.ana, home.id, comparteHistorial=True)
    add(db, profileOf(db, home.ana), days=1, spo2=Decimal("99"))
    data = dashboards.groupDashboard(db, home.ana, home.id, 90)
    betos = [a for a in data.actividadReciente if a.idGrupoUsuario == home.betoLink]
    assert betos and betos[0].medicion.esDemo  # visible, identificada
    assert data.agregado is not None and data.agregado.estadisticas.glucosa.cantidad == 0  # sin DEMO en el agregado
    assert data.agregado.estadisticas.pruebasDemo == 0 and data.agregado.estadisticas.puntosDemo == [] and data.agregado.estadisticas.puntos == []  # el agregado no expone registros


def test_10_canceladas_invalidas_y_pendientes_no_son_resultados_completados(db, home):
    for estado in ("CANCELADA", "INVALIDA", "PENDIENTE", "ADQUIRIENDO"):
        add(db, home.profile, days=0, estado=estado)
    share(db, home.beto, home.id, comparteUltimaMedicion=True, comparteHistorial=True)
    history = groups.sharedHistory(db, home.ana, home.id, home.betoLink)
    assert history.total == 3 and {m.estadoMedicion for m in history.items} == {"COMPLETADA"}
    assert groups.sharedLatest(db, home.ana, home.id, home.betoLink).medicion.idMedicion == home.before[2].idMedicion
    pending = db.scalar(select(Measurement).where(Measurement.estadoMedicion == "PENDIENTE"))
    expectError("MEDICION_NO_ENCONTRADA", groups.sharedMeasurement, db, home.ana, home.id, home.betoLink, pending.idMedicion)


# --- 12 ----------------------------------------------------------------------------------------------------------------------------


def test_12_el_administrador_no_ve_nada_sin_permiso_y_nadie_se_consulta_a_si_mismo_por_esta_via(db, home):
    expectError("DATOS_NO_COMPARTIDOS", groups.sharedHistory, db, home.ana, home.id, home.betoLink)  # administrar no da acceso
    share(db, home.beto, home.id, comparteHistorial=True)
    expectError("MIEMBRO_NO_ENCONTRADO", groups.sharedHistory, db, home.beto, home.id, home.betoLink)  # lo propio se ve en «Mis mediciones»


def test_http_las_rutas_compartidas_devuelven_el_contrato_ampliado(api, db, home):
    share(db, home.beto, home.id, comparteHistorial=True)
    client = api(home.ana)
    base = f"/api/v1/groups/{home.id}/shared/{home.betoLink}"
    items = client.get(f"{base}/history").json()["items"]
    assert {"estadoMedicion", "origenGlucosa", "glucosaDispositivo", "unidadGlucosa", "esDemo", "glucosaEstimada"} <= set(items[0])
    assert any(item["esDemo"] and item["glucosaEstimada"] is None for item in items)
    detail = client.get(f"{base}/measurements/{items[0]['idMedicion']}")
    assert detail.status_code == 200 and detail.json()["idMedicion"] == items[0]["idMedicion"]
    assert api(home.beto).get(f"{base}/measurements/{items[0]['idMedicion']}").status_code == 404
