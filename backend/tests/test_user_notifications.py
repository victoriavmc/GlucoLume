# Pruebas de «Notificaciones»: canales por aviso, horario de recordatorio, bandeja de la página y los avisos que disparan el
# inicio de sesión, el alta y la salida de un grupo, y las mediciones del grupo. También el proceso de recordatorios y las rutas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_user_notifications.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py.

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import AuthContext, getAuthContext
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.jobs import reminders
from app.main import app
from app.models.notificationPreference import NotificationPreference
from app.models.reminderSchedule import ReminderSchedule
from app.schemas.group import FamilyGroupCreateRequest
from app.schemas.userNotification import ReminderScheduleUpdate
from app.services import auth as authService
from app.services import group as groups
from app.services import schemaCompat
from app.services import userNotifications as service
from app.utils.timeZone import nowForDb
from tests.test_account_deletion import audits, db, engine, mails, makeUser  # noqa: F401 - fixtures


def expectError(code, fn, *args, **kwargs) -> AuthError:
    with pytest.raises(AuthError) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.message
    return error.value


def preferencia(settings, evento):
    return next(p for p in settings.preferencias if p.evento == evento)


def scheduleOf(db, user) -> ReminderSchedule | None:
    db.expire_all()
    return db.get(ReminderSchedule, user.idUsuario)


def join(db, admin, idGrupo, user):
    invitation = groups.invite(db, admin, idGrupo, user.correoElectronico)
    return groups.respondInvitation(db, user, invitation.idGrupoUsuario, accept=True)


# --- Canales y horario ---------------------------------------------------------------------------


def test_los_valores_por_omision_y_el_correo_de_inicio_de_sesion_vienen_de_la_cuenta(db):
    user = makeUser(db)
    user.notificarNuevoInicioSesion = False
    db.commit()

    settings = service.settings(db, user)

    assert [p.evento for p in settings.preferencias] == list(service.EVENTOS)
    assert (preferencia(settings, "INICIO_SESION").enPagina, preferencia(settings, "INICIO_SESION").porCorreo) == (True, False)
    assert (preferencia(settings, "RECORDATORIO_MEDICION").enPagina, preferencia(settings, "RECORDATORIO_MEDICION").porCorreo) == (True, False)
    assert settings.recordatorio.modo == "NINGUNO"


def test_cambiar_un_canal_queda_guardado_y_se_audita(db):
    user = makeUser(db)

    service.updatePreference(db, user, "AGREGADO_GRUPO", porCorreo=False)

    settings = service.settings(db, user)
    assert (preferencia(settings, "AGREGADO_GRUPO").enPagina, preferencia(settings, "AGREGADO_GRUPO").porCorreo) == (True, False)
    [event] = audits(db, "PREFERENCIA_NOTIFICACION")
    assert event.datosPrevios is not None and event.datosNuevos is not None


def test_pedir_el_estado_que_ya_existe_no_escribe_ni_audita(db):
    user = makeUser(db)

    service.updatePreference(db, user, "AGREGADO_GRUPO", enPagina=True)

    assert audits(db, "PREFERENCIA_NOTIFICACION") == []
    assert db.scalar(select(NotificationPreference.idPreferenciaNotificacion)) is None


def test_un_aviso_desconocido_se_rechaza(db):
    user = makeUser(db)

    with pytest.raises(AuthError) as error:
        service.updatePreference(db, user, "EVENTO_INVENTADO", enPagina=False)
    assert error.value.code == "EVENTO_NO_VALIDO"


@pytest.mark.parametrize("payload", [
    {"modo": "HORARIOS", "horarios": ["25:00"]},
    {"modo": "HORARIOS", "horarios": ["8:00"]},
    {"modo": "HORARIOS", "horarios": []},
    {"modo": "HORARIOS", "horarios": [f"0{hora}:00" for hora in range(7)]},
    {"modo": "INTERVALO", "intervaloHoras": 5},
    {"modo": "INTERVALO"},
    {"modo": "CADA_RATO"},
])
def test_horario_invalido_se_rechaza(payload):
    with pytest.raises(ValidationError):
        ReminderScheduleUpdate(**payload)


def test_los_horarios_se_ordenan_y_no_se_repiten():
    data = ReminderScheduleUpdate(modo="HORARIOS", horarios=["21:00", "08:30", "08:30"])

    assert data.horarios == ["08:30", "21:00"]


def test_horario_por_intervalo_no_avisa_antes_de_cumplirse(db):
    user = makeUser(db)

    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=4))

    settings = service.settings(db, user)
    assert (settings.recordatorio.modo, settings.recordatorio.intervaloHoras) == ("INTERVALO", 4)
    row = scheduleOf(db, user)
    assert service.dueReminderAt(row, row.ultimoAviso + timedelta(hours=3)) is None
    assert service.dueReminderAt(row, row.ultimoAviso + timedelta(hours=4, minutes=1)) == row.ultimoAviso + timedelta(hours=4)


def test_horarios_avisan_el_ultimo_cumplido_una_sola_vez():
    schedule = ReminderSchedule(modo="HORARIOS", horarios="08:00,21:00", ultimoAviso=datetime(2026, 10, 27, 21, 0))

    assert service.dueReminderAt(schedule, datetime(2026, 10, 29, 22, 0)) == datetime(2026, 10, 29, 21, 0)

    schedule.ultimoAviso = datetime(2026, 10, 29, 21, 0)
    assert service.dueReminderAt(schedule, datetime(2026, 10, 29, 23, 0)) is None
    assert service.dueReminderAt(schedule, datetime(2026, 10, 30, 8, 30)) == datetime(2026, 10, 30, 8, 0)

    schedule.ultimoAviso = datetime(2026, 10, 25, 9, 0)
    assert service.dueReminderAt(schedule, datetime(2026, 10, 29, 10, 0)) == datetime(2026, 10, 29, 8, 0)


def test_el_horario_de_una_cuenta_institucional_se_rechaza(db):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")

    expectError("RECORDATORIO_NO_DISPONIBLE", service.updateSchedule, db, user, ReminderScheduleUpdate(modo="NINGUNO"))


def test_recordatorio_vencido_avisa_en_la_pagina_y_por_correo(db, mails):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=True, porCorreo=True)
    row = scheduleOf(db, user)

    assert service.processReminders(db, user, row, row.ultimoAviso + timedelta(hours=1)) is True

    assert [n.titulo for n in service.inbox(db, user).notificaciones] == ["Es hora de medirte"]
    assert [m["subject"] for m in mails] == ["Es hora de medirte en GlucoLume"]
    assert mails[0]["to"] == user.correoElectronico


def test_recordatorio_sin_canales_no_envia_nada(db, mails):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=False, porCorreo=False)
    row = scheduleOf(db, user)

    service.processReminders(db, user, row, row.ultimoAviso + timedelta(hours=1))

    assert service.inbox(db, user).notificaciones == []
    assert mails == []


def test_el_proceso_de_recordatorios_avisa_una_sola_vez(db, mails):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="HORARIOS", horarios=["08:00"]))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=True, porCorreo=True)
    row = scheduleOf(db, user)
    row.ultimoAviso = datetime(2026, 10, 29, 9, 0)
    db.commit()

    assert reminders.run(db, datetime(2026, 10, 30, 9, 0)) == {"revisadas": 1, "avisadas": 1}
    assert reminders.run(db, datetime(2026, 10, 30, 9, 0)) == {"revisadas": 1, "avisadas": 0}
    assert len(mails) == 1


# --- Bandeja de la página -------------------------------------------------------------------------


def test_la_bandeja_cuenta_los_no_leidos_y_los_marca(db):
    user = makeUser(db)
    service.notify(db, user, "INICIO_SESION", "Primero", "uno")
    service.notify(db, user, "INICIO_SESION", "Segundo", "dos")

    inbox = service.inbox(db, user)
    assert inbox.noLeidas == 2

    service.markRead(db, user, inbox.notificaciones[0].idNotificacion)
    assert service.inbox(db, user).noLeidas == 1

    service.markRead(db, user)
    assert service.inbox(db, user).noLeidas == 0


def test_no_se_puede_marcar_un_aviso_de_otra_cuenta(db):
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")
    service.notify(db, ana, "INICIO_SESION", "Solo de Ana", "texto")
    idAna = service.inbox(db, ana).notificaciones[0].idNotificacion

    service.markRead(db, beto, idAna)

    assert service.inbox(db, ana).noLeidas == 1
    assert service.inbox(db, beto).notificaciones == []


def test_iniciar_sesion_avisa_en_la_pagina_solo_si_lo_eligio(db, mails):
    user = makeUser(db)

    authService.issueSession(db, user)
    assert [n.evento for n in service.inbox(db, user).notificaciones] == ["INICIO_SESION"]

    service.updatePreference(db, user, "INICIO_SESION", enPagina=False)
    authService.issueSession(db, user)
    assert len(service.inbox(db, user).notificaciones) == 1


def test_sin_el_esquema_nuevo_los_avisos_se_omiten_y_la_seccion_no_escribe(db, monkeypatch):
    monkeypatch.setattr(schemaCompat, "hasTable", lambda db, table: False)
    user = makeUser(db)

    assert service.notify(db, user, "INICIO_SESION", "x", "y") is False
    assert service.settings(db, user).recordatorio.modo == "NINGUNO"
    assert service.inbox(db, user).notificaciones == []
    expectError("NOTIFICACIONES_NO_DISPONIBLES", service.updatePreference, db, user, "INICIO_SESION", enPagina=False)


# --- Grupo ----------------------------------------------------------------------------------------


def _group(db):
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")
    carla = makeUser(db, usuario="carla", email="carla@example.com")
    group = groups.createGroup(db, ana, FamilyGroupCreateRequest(nombre="Familia Pérez", descripcion="Nuestro grupo"))
    return ana, beto, carla, group


def test_unirse_al_grupo_avisa_al_nuevo_integrante_y_a_los_demas(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    mails.clear()

    join(db, ana, group.idGrupo, beto)

    assert [n.titulo for n in service.inbox(db, beto).notificaciones] == ["Ahora formás parte de un grupo"]
    novedades = [n.mensaje for n in service.inbox(db, carla).notificaciones if n.evento == "NUEVA_ACCION_GRUPO"]
    assert any("se sumó al grupo" in texto for texto in novedades)
    subjects_carla = [m["subject"] for m in mails if m["to"] == carla.correoElectronico]
    assert "Hubo novedades en tu grupo" in subjects_carla
    subjects_ana = [m["subject"] for m in mails if m["to"] == ana.correoElectronico]
    assert "Hubo novedades en tu grupo" not in subjects_ana


def test_salir_del_grupo_avisa_a_los_demas_integrantes_en_la_pagina(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    join(db, ana, group.idGrupo, beto)

    groups.leaveGroup(db, beto, group.idGrupo)

    textos = [n.mensaje for n in service.inbox(db, carla).notificaciones if n.evento == "NUEVA_ACCION_GRUPO"]
    assert any("abandonó el grupo" in texto for texto in textos)


def test_el_correo_de_novedades_respeta_la_preferencia_apagada(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    service.updatePreference(db, carla, "NUEVA_ACCION_GRUPO", porCorreo=False)
    mails.clear()

    join(db, ana, group.idGrupo, beto)

    assert "Hubo novedades en tu grupo" not in [m["subject"] for m in mails if m["to"] == carla.correoElectronico]
    assert any(n.evento == "NUEVA_ACCION_GRUPO" for n in service.inbox(db, carla).notificaciones)


# --- Rutas ----------------------------------------------------------------------------------------


@pytest.fixture
def http(db, monkeypatch):
    user_holder = {}

    def fakeAuth():
        return AuthContext(user=user_holder["user"], session=None)

    app.dependency_overrides[getDb] = lambda: db
    app.dependency_overrides[getAuthContext] = fakeAuth
    yield TestClient(app, raise_server_exceptions=False), user_holder
    app.dependency_overrides.clear()


def test_las_rutas_leen_y_guardan_las_preferencias_de_la_sesion(db, http):
    client, holder = http
    holder["user"] = makeUser(db)

    settings = client.get("/api/v1/notificaciones/preferencias").json()
    assert [p["evento"] for p in settings["preferencias"]] == list(service.EVENTOS)

    response = client.put("/api/v1/notificaciones/preferencias/INICIO_SESION", json={"porCorreo": False})
    assert response.status_code == 200
    db.expire_all()
    assert holder["user"].notificarNuevoInicioSesion is False

    response = client.put("/api/v1/notificaciones/recordatorio",
                          json={"modo": "HORARIOS", "horarios": ["21:00", "07:30"]})
    assert response.status_code == 200
    assert response.json()["recordatorio"] == {"modo": "HORARIOS", "intervaloHoras": None, "horarios": ["07:30", "21:00"]}


def test_las_rutas_rechazan_avisos_y_horarios_invalidos(db, http):
    client, holder = http
    holder["user"] = makeUser(db)

    assert client.put("/api/v1/notificaciones/preferencias/OTRO_AVISO", json={"enPagina": False}).status_code == 422
    assert client.put("/api/v1/notificaciones/recordatorio", json={"modo": "HORARIOS", "horarios": ["99:00"]}).status_code == 422
    assert client.put("/api/v1/notificaciones/preferencias/AGREGADO_GRUPO", json={"otro": 1}).status_code == 422


def test_la_bandeja_por_ruta_marca_como_leidos(db, http):
    client, holder = http
    holder["user"] = makeUser(db)
    service.notify(db, holder["user"], "INICIO_SESION", "Hola", "texto")
    idNotificacion = client.get("/api/v1/notificaciones").json()["notificaciones"][0]["idNotificacion"]

    assert client.post(f"/api/v1/notificaciones/{idNotificacion}/leer").json()["noLeidas"] == 0
    service.notify(db, holder["user"], "INICIO_SESION", "Otro", "texto")
    assert client.post("/api/v1/notificaciones/leer-todas").json()["noLeidas"] == 0
    assert client.post(f"/api/v1/notificaciones/{uuid.uuid4()}/leer").status_code == 200
