# Pruebas de «Notificaciones»: canales por aviso, horario de recordatorio, bandeja de la página (filtros, paginación, lectura), unicidad de
# los avisos (también en paralelo), reintentos del correo, avisos de seguridad y de grupo, equipos nuevos, retención y las rutas.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_user_notifications.py -v
#
# Usan el esquema SQLite temporal y el SMTP simulado de test_account_deletion.py. Las pruebas de concurrencia usan varias sesiones sobre
# el mismo archivo SQLite: demuestran que el índice único y la reserva de la ocurrencia se comportan bien, pero NO reemplazan una prueba
# con SQL Server real (aislamiento y bloqueos distintos).

import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, getAuthContext
from app.core.exceptions import AuthError
from app.db.session import getDb
from app.integrations.email import sender
from app.jobs import reminders
from app.main import app
from app.models import notificationEvents
from app.models.audit import Audit
from app.models.groupUser import GroupUser
from app.models.knownAccess import KnownAccess
from app.models.notificationPreference import NotificationPreference
from app.models.reminderSchedule import ReminderSchedule
from app.models.user import User
from app.models.userNotification import UserNotification
from app.schemas.group import FamilyGroupCreateRequest
from app.schemas.userNotification import EventoAviso, ReminderScheduleUpdate
from app.services import auth as authService
from app.services import group as groups
from app.services import email as emailService
from app.services import knownAccess, notificationRetention, notifications, schemaCompat
from app.services import userNotifications as service
from app.utils.timeZone import nowForDb
from app.utils.userAgent import ClientInfo
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


def rows(db, user=None, evento=None) -> list[UserNotification]:
    db.expire_all()
    query = select(UserNotification).order_by(UserNotification.fechaCreacion, UserNotification.idNotificacion)
    if user is not None:
        query = query.where(UserNotification.idUsuario == user.idUsuario)
    if evento is not None:
        query = query.where(UserNotification.evento == evento)
    return list(db.scalars(query))


def reminderEmail():
    return service.EmailEventType.RECORDATORIO_MEDICION, {"urlMediciones": emailService.frontendUrl("/app/mediciones")}


def failSmtp(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("SMTP caído")

    monkeypatch.setattr(sender, "sendHtmlEmail", broken)


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

    assert reminders.run(db, datetime(2026, 10, 30, 9, 0)) == {"revisadas": 1, "avisadas": 1, "reintentos": 0}
    assert reminders.run(db, datetime(2026, 10, 30, 9, 0)) == {"revisadas": 1, "avisadas": 0, "reintentos": 0}
    assert len(mails) == 1
    assert len(rows(db, user, "RECORDATORIO_MEDICION")) == 1


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

    expectError("NOTIFICACION_NO_ENCONTRADA", service.markRead, db, beto, idAna)

    assert service.inbox(db, ana).noLeidas == 1
    assert service.inbox(db, beto).notificaciones == []


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

    assert {n.titulo for n in service.inbox(db, beto).notificaciones} == {"Te invitaron a un grupo", "Ahora formás parte de un grupo"}
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


# --- Unicidad de los avisos (RN-NOT-01) -------------------------------------------------------------


def test_un_aviso_valido_queda_con_categoria_hora_argentina_y_destino_conocido(db):
    user = makeUser(db)
    before = nowForDb()

    service.notify(db, user, "AGREGADO_GRUPO", "Titulo", "Mensaje", url="/app/grupo", clave="AGREGADO_GRUPO:1")

    [aviso] = service.inbox(db, user).notificaciones
    assert (aviso.titulo, aviso.mensaje, aviso.url, aviso.categoria, aviso.leida) == ("Titulo", "Mensaje", "/app/grupo", "GRUPO", False)
    [row] = rows(db, user)
    # Hora de Argentina (política temporal del backend), no la UTC que ponía el DEFAULT de la base.
    assert before - timedelta(seconds=2) <= row.fechaCreacion <= nowForDb() + timedelta(seconds=2)


@pytest.mark.parametrize("url", ["https://malo.example", "//malo.example", "/app/ruta-inventada", "/app/grupo?x=1", "javascript:alert(1)", "/app/grupofalso"])
def test_un_destino_externo_o_inventado_no_se_guarda(db, url):
    user = makeUser(db)

    service.notify(db, user, "AGREGADO_GRUPO", "Titulo", "Mensaje", url=url, clave="k")

    assert service.inbox(db, user).notificaciones[0].url is None


def test_el_mismo_hecho_procesado_dos_veces_deja_un_solo_aviso_y_un_solo_correo(db, mails):
    user = makeUser(db)
    email = reminderEmail()
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)

    first = service.notify(db, user, "RECORDATORIO_MEDICION", "Es hora", "texto", email=email, clave="RECORDATORIO_MEDICION:2026-10-29T08:00:00")
    second = service.notify(db, user, "RECORDATORIO_MEDICION", "Es hora", "texto", email=email, clave="RECORDATORIO_MEDICION:2026-10-29T08:00:00")

    assert (first, second) == (True, False)
    assert len(rows(db, user)) == 1
    assert len(mails) == 1


def test_hechos_distintos_o_cuentas_distintas_si_generan_avisos_distintos(db):
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")

    service.notify(db, ana, "AGREGADO_GRUPO", "t", "m", clave="AGREGADO_GRUPO:1")
    service.notify(db, ana, "AGREGADO_GRUPO", "t", "m", clave="AGREGADO_GRUPO:2")
    service.notify(db, beto, "AGREGADO_GRUPO", "t", "m", clave="AGREGADO_GRUPO:1")

    assert (len(rows(db, ana)), len(rows(db, beto))) == (2, 1)


def test_la_base_rechaza_dos_filas_con_la_misma_clave_para_la_misma_cuenta(db):
    user = makeUser(db)
    db.add_all([UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="k",
                                 fechaCreacion=nowForDb()),
                UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="k",
                                 fechaCreacion=nowForDb())])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # Sin clave (avisos anteriores a la migración) se pueden repetir: el índice es filtrado.
    db.add_all([UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", fechaCreacion=nowForDb())
                for _ in range(2)])
    db.commit()


def test_varias_sesiones_que_procesan_el_mismo_hecho_a_la_vez_dejan_un_solo_aviso(engine, db, mails):
    user = makeUser(db)
    barrier = threading.Barrier(6)

    def worker():
        with Session(engine) as session:
            current = session.get(User, user.idUsuario)
            barrier.wait()
            service.notify(session, current, "CAMBIO_MFA", "t", "m", clave="CAMBIO_MFA:mismo-hecho")

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(rows(db, user)) == 1


def test_varias_ejecuciones_simultaneas_reservan_la_misma_ocurrencia_una_sola_vez(engine, db, mails):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)
    now = scheduleOf(db, user).ultimoAviso + timedelta(hours=1, minutes=5)
    barrier = threading.Barrier(6)
    outcomes: list[bool] = []

    def worker():
        with Session(engine) as session:
            current = session.get(User, user.idUsuario)
            schedule = session.get(ReminderSchedule, user.idUsuario)
            barrier.wait()
            outcomes.append(service.processReminders(session, current, schedule, now))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count(True) == 1
    assert len(rows(db, user, "RECORDATORIO_MEDICION")) == 1
    assert len(mails) == 1


# --- Recordatorios (RN-NOT-02) ----------------------------------------------------------------------


def test_los_horarios_configurados_avisan_exactamente_a_esa_hora(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="HORARIOS", horarios=["08:00", "21:00"]))
    row = scheduleOf(db, user)
    row.ultimoAviso = datetime(2026, 10, 29, 0, 0)
    db.commit()

    assert service.processReminders(db, user, row, datetime(2026, 10, 29, 7, 59)) is False
    assert service.processReminders(db, user, row, datetime(2026, 10, 29, 8, 0)) is True
    assert service.processReminders(db, user, row, datetime(2026, 10, 29, 20, 59)) is False
    assert service.processReminders(db, user, row, datetime(2026, 10, 29, 21, 0)) is True

    keys = sorted(r.claveEvento for r in rows(db, user, "RECORDATORIO_MEDICION"))
    assert keys == ["RECORDATORIO_MEDICION:2026-10-29T08:00:00", "RECORDATORIO_MEDICION:2026-10-29T21:00:00"]


def test_mirar_la_misma_ocurrencia_otra_vez_no_repite_el_recordatorio(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    row = scheduleOf(db, user)
    later = row.ultimoAviso + timedelta(hours=1, minutes=1)

    assert [service.processReminders(db, user, row, later + timedelta(minutes=n)) for n in range(4)] == [True, False, False, False]
    assert len(rows(db, user, "RECORDATORIO_MEDICION")) == 1


def test_abrir_la_bandeja_varias_veces_no_repite_el_recordatorio_que_ya_envio_el_proceso(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="HORARIOS", horarios=["08:00"]))
    row = scheduleOf(db, user)
    row.ultimoAviso = datetime(2026, 10, 28, 9, 0)
    db.commit()
    reminders.run(db, datetime(2026, 10, 29, 9, 0))

    for _ in range(3):
        assert service.processReminders(db, user, scheduleOf(db, user), datetime(2026, 10, 29, 9, 30)) is False

    assert len(rows(db, user, "RECORDATORIO_MEDICION")) == 1


def test_modificar_el_horario_no_dispara_horarios_anteriores_a_guardarlo(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="HORARIOS", horarios=["00:01"]))
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="HORARIOS", horarios=["00:01", "07:30"]))
    row = scheduleOf(db, user)

    assert service.dueReminderAt(row, row.ultimoAviso) is None
    assert service.settings(db, user).recordatorio.horarios == ["00:01", "07:30"]


def test_eliminar_la_programacion_apaga_los_recordatorios(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="NINGUNO"))
    row = scheduleOf(db, user)

    assert service.settings(db, user).recordatorio.modo == "NINGUNO"
    assert service.dueReminderAt(row, row.ultimoAviso + timedelta(days=3)) is None
    assert reminders.run(db, row.ultimoAviso + timedelta(days=3)) == {"revisadas": 0, "avisadas": 0, "reintentos": 0}


def test_el_proceso_ignora_cuentas_que_no_estan_activas(db):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    user.estado = "BLOQUEADO"
    db.commit()

    result = reminders.run(db, nowForDb() + timedelta(hours=3))

    assert result["avisadas"] == 0 and rows(db, user) == []


# --- Canales independientes y fallas de correo (RN-NOT-07) --------------------------------------------


def test_apagar_la_pagina_no_apaga_el_correo_y_viceversa(db, mails):
    user = makeUser(db)
    email = reminderEmail()

    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=False, porCorreo=True)
    service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="a")
    assert service.inbox(db, user).notificaciones == [] and service.unreadCount(db, user) == 0
    assert len(mails) == 1

    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=True, porCorreo=False)
    service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="b")
    assert [n.titulo for n in service.inbox(db, user).notificaciones] == ["t"]
    assert len(mails) == 1


def test_una_falla_smtp_no_quita_el_aviso_de_la_pagina_y_queda_registrada(db, mails, monkeypatch):
    user = makeUser(db)
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)
    failSmtp(monkeypatch)
    email = reminderEmail()

    service.notify(db, user, "RECORDATORIO_MEDICION", "Es hora", "texto", email=email, clave="k")

    assert [n.titulo for n in service.inbox(db, user).notificaciones] == ["Es hora"]
    [row] = rows(db, user)
    assert (row.estadoCorreo, row.intentosCorreo) == ("FALLIDO", 1)


def test_reintentar_el_mismo_hecho_reenvia_solo_el_correo_y_respeta_el_tope(db, mails, monkeypatch):
    user = makeUser(db)
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)
    email = reminderEmail()
    realSend = sender.sendHtmlEmail
    failSmtp(monkeypatch)
    service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="k")
    service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="k")  # segundo intento, sigue fallando
    assert [(r.estadoCorreo, r.intentosCorreo) for r in rows(db, user)] == [("FALLIDO", 2)]

    monkeypatch.setattr(sender, "sendHtmlEmail", realSend)  # vuelve el SMTP
    assert service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="k") is True

    assert [(r.estadoCorreo, r.intentosCorreo) for r in rows(db, user)] == [("ENVIADO", 3)]
    assert len(service.inbox(db, user).notificaciones) == 1  # nunca un segundo aviso
    assert len(mails) == 1
    assert service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", email=email, clave="k") is False  # ya enviado


def test_el_proceso_reintenta_el_correo_de_un_recordatorio_fallido_sin_crear_otro_aviso(db, mails, monkeypatch):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)
    now = scheduleOf(db, user).ultimoAviso + timedelta(hours=1, minutes=1)
    realSend = sender.sendHtmlEmail
    failSmtp(monkeypatch)
    assert reminders.run(db, now) == {"revisadas": 1, "avisadas": 1, "reintentos": 0}

    monkeypatch.setattr(sender, "sendHtmlEmail", realSend)
    assert reminders.run(db, now + timedelta(minutes=5)) == {"revisadas": 1, "avisadas": 0, "reintentos": 1}

    [row] = rows(db, user, "RECORDATORIO_MEDICION")
    assert (row.estadoCorreo, row.intentosCorreo) == ("ENVIADO", 2)
    assert len(mails) == 1
    assert reminders.run(db, now + timedelta(minutes=10))["reintentos"] == 0


def test_no_se_reintenta_si_la_cuenta_apago_el_correo_despues(db, mails, monkeypatch):
    user = makeUser(db)
    service.updateSchedule(db, user, ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=True)
    now = scheduleOf(db, user).ultimoAviso + timedelta(hours=1, minutes=1)
    failSmtp(monkeypatch)
    reminders.run(db, now)
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", porCorreo=False)

    assert service.retryFailedReminderEmails(db, now + timedelta(minutes=5)) == 0


# --- Bandeja: filtros, paginación y lectura (RN-NOT-04 / RN-NOT-06) --------------------------------


def _fill(db, user, count=25):
    """Avisos del más viejo al más nuevo: los n pares son de GRUPO, los impares múltiplos de 5 de SEGURIDAD y el resto, RECORDATORIO."""
    base = nowForDb() - timedelta(hours=count)
    for n in range(count):
        evento = "NUEVA_ACCION_GRUPO" if n % 2 == 0 else "CAMBIO_MFA" if n % 5 == 0 else "RECORDATORIO_MEDICION"
        db.add(UserNotification(idUsuario=user.idUsuario, evento=evento, titulo=f"Aviso {n}", mensaje="m", claveEvento=f"k{n}",
                                fechaCreacion=base + timedelta(hours=n)))
    db.commit()


def test_la_bandeja_pagina_del_mas_nuevo_al_mas_viejo(db):
    user = makeUser(db)
    _fill(db, user, 25)

    first = service.inbox(db, user, limite=10)
    second = service.inbox(db, user, limite=10, desplazamiento=10)
    third = service.inbox(db, user, limite=10, desplazamiento=20)

    assert (first.total, first.hayMas, len(first.notificaciones)) == (25, True, 10)
    assert (second.hayMas, len(second.notificaciones)) == (True, 10)
    assert (third.hayMas, len(third.notificaciones)) == (False, 5)
    titles = [n.titulo for page in (first, second, third) for n in page.notificaciones]
    assert titles == [f"Aviso {n}" for n in range(24, -1, -1)]


def test_el_limite_se_acota_y_el_contador_de_no_leidas_ignora_el_filtro(db):
    user = makeUser(db)
    _fill(db, user, 12)

    assert len(service.inbox(db, user, limite=10_000).notificaciones) == 12
    grupo = service.inbox(db, user, categoria="GRUPO")
    assert grupo.total == 6 and grupo.noLeidas == 12


def test_filtra_por_categoria_y_por_no_leidas(db):
    user = makeUser(db)
    _fill(db, user, 25)
    first = service.inbox(db, user, limite=50).notificaciones[0]
    service.markRead(db, user, first.idNotificacion)

    for categoria in ("SEGURIDAD", "GRUPO", "RECORDATORIO"):
        result = service.inbox(db, user, categoria=categoria, limite=50)
        assert result.notificaciones and {n.categoria for n in result.notificaciones} == {categoria}
    assert service.inbox(db, user, categoria="GRUPO").total == 13
    assert service.inbox(db, user, categoria="SEGURIDAD").total == 2
    unread = service.inbox(db, user, soloNoLeidas=True, limite=50)
    assert unread.total == 24 and all(not n.leida for n in unread.notificaciones)


def test_una_categoria_inexistente_se_rechaza(db):
    user = makeUser(db)

    expectError("CATEGORIA_NO_VALIDA", service.inbox, db, user, categoria="OTRA")


def test_marcar_todas_solo_afecta_a_la_cuenta_autenticada(db):
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")
    for n in range(3):
        service.notify(db, ana, "CAMBIO_MFA", "t", "m", clave=f"a{n}")
        service.notify(db, beto, "CAMBIO_MFA", "t", "m", clave=f"b{n}")

    assert service.markRead(db, ana) == 3

    assert (service.unreadCount(db, ana), service.unreadCount(db, beto)) == (0, 3)
    assert service.markRead(db, ana) == 0  # idempotente


def test_la_lectura_individual_se_conserva_y_no_cambia_la_fecha_de_lectura(db):
    user = makeUser(db)
    service.notify(db, user, "CAMBIO_MFA", "t", "m", clave="uno")
    service.notify(db, user, "CAMBIO_MFA", "t", "m", clave="dos")
    [uno, dos] = [n.idNotificacion for n in service.inbox(db, user).notificaciones]

    assert service.markRead(db, user, uno) == 1
    firstRead = next(r.fechaLectura for r in rows(db, user) if r.idNotificacion == uno)
    assert service.markRead(db, user, uno) == 0

    assert next(r.fechaLectura for r in rows(db, user) if r.idNotificacion == uno) == firstRead
    assert [n.leida for n in service.inbox(db, user).notificaciones if n.idNotificacion == dos] == [False]


def test_un_aviso_oculto_por_la_preferencia_de_pagina_no_aparece_ni_se_puede_marcar(db, mails):
    user = makeUser(db)
    service.updatePreference(db, user, "RECORDATORIO_MEDICION", enPagina=False, porCorreo=True)
    service.notify(db, user, "RECORDATORIO_MEDICION", "t", "m", clave="k",
                   email=reminderEmail())
    [hidden] = rows(db, user)

    assert service.inbox(db, user).notificaciones == []
    expectError("NOTIFICACION_NO_ENCONTRADA", service.markRead, db, user, hidden.idNotificacion)


# --- Alertas de seguridad obligatorias ----------------------------------------------------------------------


@pytest.mark.parametrize("evento", ["CAMBIO_CONTRASENA", "CAMBIO_MFA", "ACTIVIDAD_SOSPECHOSA"])
def test_las_alertas_criticas_no_se_pueden_apagar_y_se_entregan_siempre(db, evento):
    user = makeUser(db)

    expectError("AVISO_OBLIGATORIO", service.updatePreference, db, user, evento, enPagina=False)
    settings = service.settings(db, user)
    assert (preferencia(settings, evento).enPagina, preferencia(settings, evento).obligatoria) == (True, True)
    # Aun con una fila de preferencia apagada (datos viejos o manipulados), se entrega.
    db.add(NotificationPreference(idUsuario=user.idUsuario, evento=evento, enPagina=False, porCorreo=False))
    db.commit()
    service.notifySecurity(db, user, evento, "t", "m", "hecho")
    assert len(service.inbox(db, user).notificaciones) == 1


def test_agregar_la_contrasena_avisa_en_la_pagina_y_el_correo_existente_sigue_saliendo(db, mails):
    user = makeUser(db, local=False, google=True)

    authService.setLocalPassword(db, user, "Glucolume#Nueva2026")

    [aviso] = service.inbox(db, user).notificaciones
    assert (aviso.evento, aviso.categoria, aviso.url) == ("CAMBIO_CONTRASENA", "SEGURIDAD", "/app/seguridad")
    assert len(mails) == 1


def test_el_mismo_bloqueo_por_intentos_fallidos_avisa_una_sola_vez(db):
    user = makeUser(db)
    until = nowForDb() + timedelta(minutes=15)

    service.notifySecurity(db, user, "ACTIVIDAD_SOSPECHOSA", "t", "m", f"BLOQUEO:{until:%Y-%m-%dT%H:%M:%S}")
    service.notifySecurity(db, user, "ACTIVIDAD_SOSPECHOSA", "t", "m", f"BLOQUEO:{until:%Y-%m-%dT%H:%M:%S}")

    assert len(rows(db, user, "ACTIVIDAD_SOSPECHOSA")) == 1


def test_el_bloqueo_real_de_la_cuenta_por_intentos_fallidos_avisa_una_sola_vez(db, mails):
    from tests.test_account_deletion import EMAIL

    user = makeUser(db)
    limit = authService.MAX_FAILED_LOGIN_ATTEMPTS

    for _ in range(limit):
        with pytest.raises(AuthError):
            authService.loginLocal(db, EMAIL, "OtraClave#2026")
    with pytest.raises(AuthError):  # ya bloqueada: sigue rechazando sin generar otra alerta
        authService.loginLocal(db, EMAIL, "OtraClave#2026")

    [aviso] = service.inbox(db, user).notificaciones
    assert (aviso.evento, aviso.categoria) == ("ACTIVIDAD_SOSPECHOSA", "SEGURIDAD")
    assert len(mails) == 1  # el correo de actividad de seguridad existente sigue saliendo, una vez


# --- Inicio de sesión: auditoría completa, aviso solo de equipos nuevos (RN-NOT-03) -----------------------

CHROME = ClientInfo(navegador="Chrome", sistemaOperativo="Windows", dispositivo="Computadora", ip="203.0.113.5")
FIREFOX = ClientInfo(navegador="Firefox", sistemaOperativo="Linux", dispositivo="Computadora", ip="203.0.113.9")


def login(db, user, client):
    return authService._completePrimaryAuthentication(db, user, authService.METHOD_PASSWORD, client)


def test_el_primer_inicio_de_sesion_y_los_repetidos_desde_el_mismo_equipo_no_generan_aviso(db, mails):
    user = makeUser(db)

    login(db, user, CHROME)
    login(db, user, CHROME)
    login(db, user, ClientInfo(navegador="Chrome", sistemaOperativo="Windows", dispositivo="Computadora", ip="198.51.100.7"))  # otra IP, mismo equipo

    assert rows(db, user, "INICIO_SESION") == []
    assert db.scalar(select(func.count(KnownAccess.idAccesoConocido))) == 1


def test_un_equipo_nuevo_avisa_una_sola_vez_sin_incluir_la_ip(db, mails):
    user = makeUser(db)
    login(db, user, CHROME)

    login(db, user, FIREFOX)
    login(db, user, FIREFOX)

    [aviso] = service.inbox(db, user).notificaciones
    assert aviso.evento == "INICIO_SESION" and aviso.categoria == "SEGURIDAD"
    assert "Firefox en Linux (Computadora)" in aviso.mensaje
    assert "203.0.113" not in aviso.mensaje and aviso.url == "/app/seguridad"


def test_el_aviso_de_equipo_nuevo_respeta_la_preferencia_de_la_pagina(db, mails):
    user = makeUser(db)
    service.updatePreference(db, user, "INICIO_SESION", enPagina=False)
    login(db, user, CHROME)

    login(db, user, FIREFOX)

    assert service.inbox(db, user).notificaciones == []


def test_todos_los_inicios_de_sesion_siguen_auditados_aunque_no_generen_aviso(db, mails):
    user = makeUser(db)

    for client in (CHROME, CHROME, FIREFOX, CHROME):
        login(db, user, client)

    assert len(audits(db, "LOGIN_PWD")) == 4
    assert len(rows(db, user, "INICIO_SESION")) == 1


def test_el_correo_de_inicio_de_sesion_sigue_su_propio_interruptor(db, mails):
    user = makeUser(db)

    login(db, user, CHROME)
    login(db, user, CHROME)
    assert len(mails) == 2  # un correo por acceso mientras la cuenta lo tenga activado (comportamiento anterior)

    user.notificarNuevoInicioSesion = False
    db.commit()
    login(db, user, CHROME)
    assert len(mails) == 2


def test_sin_datos_del_cliente_no_se_registra_ni_se_avisa(db):
    user = makeUser(db)

    assert knownAccess.registerAccess(db, user, None) is None
    assert knownAccess.registerAccess(db, user, ClientInfo(ip="203.0.113.5")) is None
    assert db.scalar(select(func.count(KnownAccess.idAccesoConocido))) == 0


def test_dos_cuentas_no_comparten_equipos_conocidos(db):
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")
    knownAccess.registerAccess(db, ana, CHROME)

    assert knownAccess.registerAccess(db, beto, CHROME) is None  # primer acceso de Beto: solo se registra
    assert knownAccess.registerAccess(db, ana, FIREFOX) is not None


# --- Grupo ---------------------------------------------------------------------------------------------------


def test_invitar_a_una_cuenta_avisa_en_la_pagina_y_por_correo_segun_sus_preferencias(db, mails):
    ana, beto, carla, group = _group(db)
    mails.clear()

    groups.invite(db, ana, group.idGrupo, beto.correoElectronico)

    [aviso] = [n for n in service.inbox(db, beto).notificaciones if n.evento == "INVITACION_GRUPO"]
    assert (aviso.categoria, aviso.url) == ("GRUPO", "/app/grupo")
    assert len([m for m in mails if m["to"] == beto.correoElectronico]) == 1

    service.updatePreference(db, carla, "INVITACION_GRUPO", porCorreo=False)
    mails.clear()
    groups.invite(db, ana, group.idGrupo, carla.correoElectronico)
    assert [m for m in mails if m["to"] == carla.correoElectronico] == []
    assert any(n.evento == "INVITACION_GRUPO" for n in service.inbox(db, carla).notificaciones)


def test_la_misma_incorporacion_procesada_dos_veces_no_duplica_los_avisos(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    join(db, ana, group.idGrupo, beto)
    antes = len(rows(db, carla)) + len(rows(db, beto))

    relation = db.scalar(select(GroupUser).where(GroupUser.idUsuario == beto.idUsuario))
    service.notify(db, beto, "AGREGADO_GRUPO", "t", "m", clave=f"AGREGADO_GRUPO:{relation.idGrupoUsuario}")
    service.notifyGroupNews(db, group.idGrupo, beto.idUsuario, "texto", {}, f"{relation.idGrupoUsuario}:SUMA")

    assert len(rows(db, carla)) + len(rows(db, beto)) == antes


def test_el_aviso_de_medicion_del_grupo_respeta_el_permiso_individual_y_no_se_duplica(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    join(db, ana, group.idGrupo, beto)
    when = nowForDb()

    assert notifications.notifyGroupMeasurement(db, beto, when) == 0  # beto no autorizó el aviso
    assert rows(db, carla, "MEDICION_GRUPO") == []

    relation = db.scalar(select(GroupUser).where(GroupUser.idUsuario == beto.idUsuario))
    relation.notificaMedicion = True
    db.commit()
    first = notifications.notifyGroupMeasurement(db, beto, when)
    second = notifications.notifyGroupMeasurement(db, beto, when)

    assert first >= 1 and second == 0
    assert len(rows(db, carla, "MEDICION_GRUPO")) == 1
    assert "se midió" in rows(db, carla, "MEDICION_GRUPO")[0].mensaje


def test_las_preferencias_de_novedades_y_de_mediciones_del_grupo_son_independientes(db, mails):
    ana, beto, carla, group = _group(db)
    join(db, ana, group.idGrupo, carla)
    join(db, ana, group.idGrupo, beto)
    service.updatePreference(db, carla, "MEDICION_GRUPO", enPagina=False)
    relation = db.scalar(select(GroupUser).where(GroupUser.idUsuario == beto.idUsuario))
    relation.notificaMedicion = True
    db.commit()

    notifications.notifyGroupMeasurement(db, beto, nowForDb())

    assert [n for n in service.inbox(db, carla).notificaciones if n.evento == "MEDICION_GRUPO"] == []
    assert any(n.evento == "NUEVA_ACCION_GRUPO" for n in service.inbox(db, carla).notificaciones)


# --- Retención (RN-NOT-05) -----------------------------------------------------------------------------------


def _retention(monkeypatch, read, unread):
    from app.core.config import getSettings

    monkeypatch.setenv("NOTIFICATION_READ_RETENTION_DAYS", str(read))
    monkeypatch.setenv("NOTIFICATION_UNREAD_RETENTION_DAYS", str(unread))
    getSettings.cache_clear()


def test_la_depuracion_elimina_solo_avisos_vencidos_y_nunca_toca_la_auditoria(db, monkeypatch):
    user = makeUser(db)
    now = nowForDb()

    def add(clave, days, read=False, visible=True):
        db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo=clave, mensaje="m", claveEvento=clave,
                                fechaCreacion=now - timedelta(days=days), fechaLectura=now if read else None, visible=visible))

    add("leido-viejo", 200, read=True)
    add("leido-reciente", 10, read=True)
    add("sin-leer-viejo", 400)
    add("sin-leer-medio", 200)
    add("oculto-viejo", 200, visible=False)
    db.commit()
    audits_before = db.scalar(select(func.count(Audit.idAuditoria)))
    _retention(monkeypatch, read=180, unread=365)

    assert notificationRetention.plan(db, now)["avisosVencidos"] == 3
    assert notificationRetention.purge(db, now) == 3

    assert sorted(r.claveEvento for r in rows(db)) == ["leido-reciente", "sin-leer-medio"]
    assert db.scalar(select(func.count(Audit.idAuditoria))) == audits_before


def test_la_depuracion_trabaja_por_tandas_hasta_vaciar_lo_vencido(db, monkeypatch):
    user = makeUser(db)
    now = nowForDb()
    monkeypatch.setattr(notificationRetention, "BATCH", 3)
    for n in range(10):
        db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento=f"v{n}",
                                fechaCreacion=now - timedelta(days=100), fechaLectura=now - timedelta(days=99)))
    db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="reciente",
                            fechaCreacion=now, fechaLectura=now))
    db.commit()
    _retention(monkeypatch, read=30, unread=365)

    assert notificationRetention.purge(db, now) == 10
    assert [r.claveEvento for r in rows(db)] == ["reciente"]


def test_el_ciclo_automatico_de_lifecycle_depura_los_avisos_vencidos(db, engine, monkeypatch):
    from app.jobs import accountLifecycle

    user = makeUser(db)
    now = nowForDb()
    db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="viejo",
                            fechaCreacion=now - timedelta(days=60), fechaLectura=now - timedelta(days=59)))
    db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="sin-leer",
                            fechaCreacion=now - timedelta(days=60)))
    db.commit()
    _retention(monkeypatch, read=30, unread=365)
    monkeypatch.setattr(accountLifecycle, "getJobsSessionFactory", lambda: (lambda: Session(engine)))
    for part in ("accountLifecycle", "pendingAccounts", "personnelRetention", "auditRetention"):
        monkeypatch.setattr(getattr(accountLifecycle, part), {"accountLifecycle": "sweep", "pendingAccounts": "purgeDead",
                                                              "personnelRetention": "minimizeExpired", "auditRetention": "run"}[part],
                            lambda *args, **kwargs: 0)

    result = accountLifecycle.run()

    assert result["avisosEliminados"] == 1
    assert [r.claveEvento for r in rows(db)] == ["sin-leer"]


def test_los_plazos_en_cero_desactivan_la_depuracion(db, monkeypatch):
    user = makeUser(db)
    db.add(UserNotification(idUsuario=user.idUsuario, evento="CAMBIO_MFA", titulo="t", mensaje="m", claveEvento="k",
                            fechaCreacion=nowForDb() - timedelta(days=5000), fechaLectura=nowForDb()))
    db.commit()
    _retention(monkeypatch, read=0, unread=0)

    assert notificationRetention.purge(db) == 0
    assert len(rows(db)) == 1


# --- Contratos y esquema -----------------------------------------------------------------------------------


def test_los_contratos_conocen_exactamente_los_avisos_del_catalogo():
    from typing import get_args

    assert set(get_args(EventoAviso)) == set(notificationEvents.EVENTOS) == set(service.EVENTOS)
    assert {spec.categoria for spec in notificationEvents.CATALOGO.values()} == set(notificationEvents.CATEGORIAS)
    assert {e for e, spec in notificationEvents.CATALOGO.items() if spec.obligatorio} == {"CAMBIO_CONTRASENA", "CAMBIO_MFA", "ACTIVIDAD_SOSPECHOSA"}


def test_la_migracion_v2_cubre_los_avisos_las_columnas_y_es_idempotente():
    import re

    script = (Path(__file__).resolve().parents[2] / "database" / "reference" / "GlucoLume_notificaciones_v2.sql").read_text(encoding="utf-8")
    code = re.sub(r"--[^\n]*", "", script)

    assert ":on error exit" in script and "N'$(CONFIRMAR)' <> N'ACTUALIZAR_NOTIFICACIONES_V2'" in script
    assert script.rstrip().endswith("SET NOEXEC OFF;\nGO")
    for evento in notificationEvents.EVENTOS:
        assert f"[evento]=N'{evento}'" in script, evento
    for column in ("claveEvento", "visible", "estadoCorreo", "intentosCorreo"):
        assert f"COL_LENGTH(N'dbo.NotificacionUsuario', N'{column}') IS NULL" in script
    assert "UX_NotificacionUsuario_clave" in script and "WHERE [claveEvento] IS NOT NULL" in script
    # Los datos anteriores se corrigen una sola vez: solo filas sin clave.
    assert "DATEADD(HOUR, -3, [fechaCreacion])" in script and "WHERE [claveEvento] IS NULL" in script
    assert "OBJECT_ID(N'dbo.AccesoConocido', N'U') IS NULL" in script
    for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE"):
        assert forbidden not in code.upper(), forbidden  # no borra datos: solo agrega y reemplaza restricciones


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
    assert {p["evento"] for p in settings["preferencias"] if p["obligatoria"]} == {"CAMBIO_CONTRASENA", "CAMBIO_MFA", "ACTIVIDAD_SOSPECHOSA"}

    response = client.put("/api/v1/notificaciones/preferencias/INICIO_SESION", json={"porCorreo": False})
    assert response.status_code == 200
    db.expire_all()
    assert holder["user"].notificarNuevoInicioSesion is False

    response = client.put("/api/v1/notificaciones/recordatorio",
                          json={"modo": "HORARIOS", "horarios": ["21:00", "07:30"]})
    assert response.status_code == 200
    assert response.json()["recordatorio"] == {"modo": "HORARIOS", "intervaloHoras": None, "horarios": ["07:30", "21:00"]}


def test_la_ruta_no_deja_apagar_una_alerta_obligatoria(db, http):
    client, holder = http
    holder["user"] = makeUser(db)

    response = client.put("/api/v1/notificaciones/preferencias/CAMBIO_CONTRASENA", json={"enPagina": False})

    assert response.status_code == 409 and response.json()["codigo"] == "AVISO_OBLIGATORIO"


def test_las_rutas_rechazan_avisos_y_horarios_invalidos(db, http):
    client, holder = http
    holder["user"] = makeUser(db)

    assert client.put("/api/v1/notificaciones/preferencias/OTRO_AVISO", json={"enPagina": False}).status_code == 422
    assert client.put("/api/v1/notificaciones/recordatorio", json={"modo": "HORARIOS", "horarios": ["99:00"]}).status_code == 422
    assert client.put("/api/v1/notificaciones/preferencias/AGREGADO_GRUPO", json={"otro": 1}).status_code == 422


def test_la_bandeja_por_ruta_filtra_pagina_y_valida_los_parametros(db, http):
    client, holder = http
    holder["user"] = makeUser(db)
    _fill(db, holder["user"], 25)

    page = client.get("/api/v1/notificaciones", params={"limite": 10, "desplazamiento": 20}).json()
    assert (page["total"], page["hayMas"], len(page["notificaciones"]), page["noLeidas"]) == (25, False, 5, 25)
    grupo = client.get("/api/v1/notificaciones", params={"categoria": "GRUPO", "limite": 50}).json()
    assert {n["categoria"] for n in grupo["notificaciones"]} == {"GRUPO"}
    assert client.get("/api/v1/notificaciones", params={"limite": 0}).status_code == 422
    assert client.get("/api/v1/notificaciones", params={"limite": 51}).status_code == 422
    assert client.get("/api/v1/notificaciones", params={"desplazamiento": -1}).status_code == 422
    assert client.get("/api/v1/notificaciones", params={"categoria": "OTRA"}).status_code == 422


def test_la_bandeja_por_ruta_marca_como_leidos(db, http):
    client, holder = http
    holder["user"] = makeUser(db)
    service.notify(db, holder["user"], "CAMBIO_MFA", "Hola", "texto", clave="a")
    idNotificacion = client.get("/api/v1/notificaciones").json()["notificaciones"][0]["idNotificacion"]

    assert client.post(f"/api/v1/notificaciones/{idNotificacion}/leer").json() == {"noLeidas": 0, "marcadas": 1}
    service.notify(db, holder["user"], "CAMBIO_MFA", "Otro", "texto", clave="b")
    assert client.post("/api/v1/notificaciones/leer-todas").json() == {"noLeidas": 0, "marcadas": 1}


def test_un_usuario_no_puede_leer_ni_marcar_los_avisos_de_otro_por_su_identificador(db, http):
    client, holder = http
    ana = makeUser(db, usuario="ana", email="ana@example.com")
    beto = makeUser(db, usuario="beto", email="beto@example.com")
    service.notify(db, ana, "CAMBIO_MFA", "Solo de Ana", "texto", clave="a")
    idAna = rows(db, ana)[0].idNotificacion
    holder["user"] = beto

    response = client.post(f"/api/v1/notificaciones/{idAna}/leer")
    unknown = client.post(f"/api/v1/notificaciones/{uuid.uuid4()}/leer")

    assert response.status_code == 404 and response.json()["codigo"] == "NOTIFICACION_NO_ENCONTRADA"
    assert (unknown.status_code, unknown.json()) == (404, response.json())  # no distingue "ajeno" de "inexistente"
    assert client.get("/api/v1/notificaciones").json()["notificaciones"] == []
    assert client.post("/api/v1/notificaciones/leer-todas").json()["marcadas"] == 0
    assert rows(db, ana)[0].fechaLectura is None


def test_abrir_la_bandeja_varias_veces_envia_el_recordatorio_una_sola_vez(db, http, mails):
    client, holder = http
    holder["user"] = makeUser(db)
    service.updateSchedule(db, holder["user"], ReminderScheduleUpdate(modo="INTERVALO", intervaloHoras=1))
    db.execute(update(ReminderSchedule).values(ultimoAviso=nowForDb() - timedelta(hours=1, minutes=10)))
    db.commit()

    for _ in range(4):
        assert client.get("/api/v1/notificaciones").status_code == 200

    assert len(rows(db, holder["user"], "RECORDATORIO_MEDICION")) == 1
