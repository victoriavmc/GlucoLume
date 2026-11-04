# Anulación técnica de IP y agente vencidos: plazos de 90 días desde el evento, extensión de hasta 90 días desde la eliminación de la cuenta
# (solo eventos de seguridad), cuentas activas y eliminadas, eventos sin cuenta, IPv4 e IPv6, idempotencia, bloqueo de ejecución concurrente,
# revocación de sesiones tras la baja, ausencia de borrado de auditoría, permisos SQL y funcionamiento con «lifecycle» apagado.
# Datos sintéticos sobre el esquema SQLite temporal de las pruebas; no toca ninguna base real.

import re
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.core.exceptions import AuthError
from app.jobs import technicalRetention
from app.models.audit import Audit
from app.models.auditContext import AuditContext
from app.models.user import User
from app.models.userSession import UserSession
from app.services import auditRetention
from app.services import auth as authService
from app.services import consent as consentService
from app.utils.timeZone import argentinaToUtc, nowForDb
from tests.test_account_deletion import EMAIL, PASSWORD, db, engine, mails, makeUser  # noqa: F401 - fixtures

NOW = nowForDb()
REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "database" / "reference" / "GlucoLume_retencion_ip_tecnica.sql"
POLICY = REPO / "frontend" / "src" / "pages" / "Privacy" / "PrivacyPolicy.jsx"


@pytest.fixture(autouse=True)
def retentionSettings(monkeypatch):
    """Plazos de la política (90/90) fijados explícitamente para que las pruebas no dependan de los valores por defecto."""
    from app.core.config import getSettings

    monkeypatch.setenv("AUDIT_CONTEXT_RETENTION_DAYS", "90")
    monkeypatch.setenv("AUDIT_DELETED_ACCOUNT_RETENTION_DAYS", "90")
    monkeypatch.setenv("TECHNICAL_RETENTION_BATCH", "2")  # lotes chicos: se prueban varias vueltas
    getSettings.cache_clear()
    yield
    getSettings.cache_clear()


def event(db, *, when, accion="LOGIN_LOCAL", tipo="LOGIN", resultado="EXITO", user=None, ip="203.0.113.7", agente="Mozilla/5.0 (test)"):
    """Un evento de auditoría con su contexto técnico (IP y agente), con la fecha indicada."""
    # `when` llega en hora de Argentina (como nowForDb); la base guarda los eventos en UTC (sysutcdatetime()).
    row = Audit(idAuditoria=uuid.uuid4(), idUsuario=user.idUsuario if user is not None else None, tipoEvento=tipo, accion=accion,
                resultado=resultado, fechaHora=argentinaToUtc(when), modulo="AUTENTICACION")
    db.add(row)
    db.flush()
    db.add(AuditContext(idAuditoria=row.idAuditoria, ipOrigen=ip, agenteUsuario=agente, idCorrelacion="corr-prueba"))
    db.commit()
    return row


def context(db, row) -> AuditContext:
    db.expire_all()
    return db.get(AuditContext, row.idAuditoria)


def sweep(db, now=NOW):
    return auditRetention.anonymizeDueContext(db, now)


def deleted(db, user, days_ago):
    """Cuenta eliminada hace `days_ago` días (estado ELIMINADO y fecha de eliminación), como la deja la baja real."""
    user.estado = "ELIMINADO"
    user.fechaEliminacion = NOW - timedelta(days=days_ago)
    db.commit()
    return user


# --- Plazo general: 90 días cumplidos desde el evento -----------------------------------------------------------------

@pytest.mark.parametrize("age, anulada", [(89, False), (90, True), (91, True)])
def test_evento_de_cuenta_activa_vence_a_los_90_dias(db, mails, age, anulada):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=age), user=user)
    sweep(db)
    ctx = context(db, row)
    assert (ctx.ipOrigen is None and ctx.agenteUsuario is None) is anulada
    assert ctx.idCorrelacion == "corr-prueba"  # la trazabilidad sigue


def test_vencimiento_usa_utc_del_evento_no_la_hora_local(db, mails):
    """El evento queda guardado en UTC: a las 12:00 UTC (09:00 en Argentina) vence exactamente a los 90 días de esa instante UTC."""
    from datetime import datetime, timezone
    user = makeUser(db)
    utcEvent = datetime(2026, 1, 1, 12, 0, 0)  # instante UTC guardado
    row = Audit(idAuditoria=uuid.uuid4(), idUsuario=user.idUsuario, tipoEvento="LOGIN", accion="LOGIN_LOCAL", resultado="FALLO",
                fechaHora=utcEvent, modulo="AUTENTICACION")
    db.add(row)
    db.flush()
    db.add(AuditContext(idAuditoria=row.idAuditoria, ipOrigen="203.0.113.7", agenteUsuario="prueba", idCorrelacion="corr-utc"))
    db.commit()
    justBefore = datetime(2026, 4, 1, 8, 59, 59)  # hora de Argentina: 11:59:59 UTC
    atExpiry = datetime(2026, 4, 1, 9, 0, 0)  # hora de Argentina: 12:00:00 UTC
    assert sweep(db, justBefore) == 0 and context(db, row).ipOrigen is not None
    assert sweep(db, atExpiry) == 1 and context(db, row).ipOrigen is None
    assert timezone.utc is not None  # referencia explícita a la zona UTC del cálculo

def test_ipv6_y_ipv4_se_anulan_y_el_agente_tambien(db, mails):
    user = makeUser(db)
    v4 = event(db, when=NOW - timedelta(days=120), user=user, ip="198.51.100.9")
    v6 = event(db, when=NOW - timedelta(days=120), user=user, ip="2001:db8::1")
    assert sweep(db) == 2
    for row in (v4, v6):
        ctx = context(db, row)
        assert ctx.ipOrigen is None and ctx.agenteUsuario is None


# --- Cuentas eliminadas: extensión de hasta 90 días desde la eliminación (solo seguridad) ----------------------------

@pytest.mark.parametrize("deletedAgo, anulada", [(89, False), (90, True), (91, True)])
def test_evento_de_seguridad_de_cuenta_eliminada_vence_a_los_90_dias_de_la_baja(db, mails, deletedAgo, anulada):
    user = deleted(db, makeUser(db), deletedAgo)
    row = event(db, when=NOW - timedelta(days=120), accion="MFA_CODIGO_INVALIDO", tipo="LOGIN", resultado="FALLO", user=user)
    sweep(db)
    assert (context(db, row).ipOrigen is None) is anulada


def test_evento_que_no_es_de_seguridad_de_cuenta_eliminada_sigue_el_plazo_general(db, mails):
    user = deleted(db, makeUser(db), 10)  # eliminada hace 10 días
    row = event(db, when=NOW - timedelta(days=120), accion="CONSULTAR_MEDICIONES", tipo="ACCESO", user=user)
    sweep(db)
    assert context(db, row).ipOrigen is None  # no extiende: vence por el plazo del evento


def test_evento_posterior_a_la_baja_sigue_su_plazo_del_evento(db, mails):
    user = deleted(db, makeUser(db), 100)  # eliminada hace 100 días
    row = event(db, when=NOW - timedelta(days=10), accion="LOGIN_LOCAL", resultado="FALLO", user=user)
    sweep(db)
    assert context(db, row).ipOrigen is not None  # 10 días desde el evento: vigente, aunque la cuenta ya no exista


def test_evento_de_seguridad_posterior_a_la_baja_no_se_anula_antes_de_su_plazo(db, mails):
    user = deleted(db, makeUser(db), 100)
    row = event(db, when=NOW - timedelta(days=95), accion="MFA_CODIGO_INVALIDO", tipo="LOGIN", resultado="FALLO", user=user)
    sweep(db)
    # 95 días desde el evento (vence) pero la baja fue hace 100: el vencimiento de la baja (hace 10 días) ya pasó: se anula.
    assert context(db, row).ipOrigen is None


# --- Eventos sin cuenta, cuentas activas y eventos de sesión revocada ------------------------------------------------

def test_evento_sin_usuario_sigue_solo_el_plazo_general(db, mails):
    old = event(db, when=NOW - timedelta(days=120), user=None, accion="LOGIN_LOCAL", resultado="FALLO")
    young = event(db, when=NOW - timedelta(days=30), user=None, accion="LOGIN_LOCAL", resultado="FALLO")
    sweep(db)
    assert context(db, old).ipOrigen is None and context(db, young).ipOrigen is not None


def test_sin_contexto_util_no_se_cuenta_ni_se_toca(db, mails):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=200), user=user, ip=None, agente=None)
    assert sweep(db) == 0
    assert context(db, row).ipOrigen is None


# --- Nunca restaurar ni borrar: idempotencia y trazabilidad del evento ----------------------------------------------

def test_es_idempotente_y_no_restaura_nada(db, mails):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=120), user=user)
    assert sweep(db) == 1
    assert sweep(db) == 0 and sweep(db) == 0
    assert context(db, row).ipOrigen is None  # lo anulado no vuelve, aunque otra pasada corra después


def test_no_borra_eventos_ni_altera_sus_campos(db, mails):
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=400), user=user, accion="LOGIN_LOCAL", resultado="FALLO")
    before = db.scalar(select(func.count()).select_from(Audit))
    sweep(db)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Audit)) == before
    kept = db.get(Audit, row.idAuditoria)
    assert (kept.accion, kept.resultado, kept.tipoEvento, kept.idUsuario, kept.fechaHora) == \
        ("LOGIN_LOCAL", "FALLO", "LOGIN", user.idUsuario, row.fechaHora)


def test_lotes_pequenos_procesan_todo(db, mails):
    user = makeUser(db)
    for days in (100, 101, 102, 103, 104):
        event(db, when=NOW - timedelta(days=days), user=user)
    assert sweep(db) == 5  # batch=2 por el fixture: varias vueltas, mismo total


# --- Concurrencia: una segunda pasada que llega tarde no falla ni repite -------------------------------------------

def test_pasada_concurrente_que_llega_tarde_no_repite_ni_falla(db, engine, mails, monkeypatch):
    user = makeUser(db)
    event(db, when=NOW - timedelta(days=120), user=user)
    event(db, when=NOW - timedelta(days=121), user=user)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    first, second = maker(), maker()
    try:
        # La segunda ve las mismas filas vencidas antes de que la primera confirme (lectura del plan).
        rowsSeenBySecond = second.scalars(auditRetention._contextQuery(NOW, 90, 90).limit(10)).all()
        assert sweep(first) == 2  # la primera anula todo y confirma
        # La segunda intenta anular lo que ya no tiene IP: el UPDATE condicional no cambia nada y no falla.
        from sqlalchemy import or_
        from sqlalchemy import update as sqlUpdate
        stillHasContext = or_(AuditContext.ipOrigen.is_not(None), AuditContext.agenteUsuario.is_not(None))
        result = second.execute(sqlUpdate(AuditContext).where(AuditContext.idAuditoria.in_(rowsSeenBySecond), stillHasContext)
                                .values(ipOrigen=None, agenteUsuario=None).execution_options(synchronize_session=False))
        second.commit()
        assert result.rowcount == 0
        assert sweep(second) == 0
    finally:
        first.close()
        second.close()


def test_si_otra_pasada_tiene_el_lock_esta_se_omite(db, mails, monkeypatch):
    monkeypatch.setattr(technicalRetention, "_acquireLock", lambda engine: None)
    monkeypatch.setattr(technicalRetention, "getRetentionEngine", lambda: db.get_bind())
    assert technicalRetention.run(NOW) == {"omitidaPorConcurrencia": True}


# --- Mantenimiento independiente de «lifecycle» -------------------------------------------------------------------

def test_corre_con_lifecycle_apagado_y_registra_el_resultado(db, engine, mails, monkeypatch):
    from app.core.config import getSettings

    monkeypatch.setenv("ACCOUNT_LIFECYCLE_INTERVAL_SECONDS", "0")
    getSettings.cache_clear()
    user = makeUser(db)
    row = event(db, when=NOW - timedelta(days=120), user=user)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(technicalRetention, "getRetentionEngine", lambda: engine)
    monkeypatch.setattr(technicalRetention, "getRetentionSessionFactory", lambda: maker)
    monkeypatch.setattr(technicalRetention, "_acquireLock", lambda e: e.connect())
    monkeypatch.setattr(technicalRetention, "_releaseLock", lambda c, e: c.close())
    result = technicalRetention.run(NOW)
    assert result == {"contextosAnonimizados": 1}
    assert context(db, row).ipOrigen is None
    registered = db.scalars(select(Audit).where(Audit.accion == technicalRetention.ACCION_RESULTADO)).all()
    assert len(registered) == 1 and "IP" not in (registered[0].observacion or "").upper().replace("IP Y AGENTE", "")
    beat = technicalRetention.HEARTBEAT
    assert beat is not None


def test_sin_cuenta_propia_no_corre_y_no_usa_la_de_la_api(db, mails, monkeypatch):
    def missing():
        raise RuntimeError("Falta DB_RETENCION_USER y DB_RETENCION_PASSWORD")

    monkeypatch.setattr(technicalRetention, "getRetentionEngine", missing)
    result = technicalRetention.run(NOW)
    assert result == {"error": "RuntimeError"}  # falla visible; no hay fallback a DB_USER ni a DB_JOBS_USER


def test_configuracion_de_la_cuenta_propia_es_completa_y_distinta_de_la_api(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    base = {"_env_file": None, "DB_HOST": "localhost", "DB_NAME": "x", "DB_USER": "api", "DB_PASSWORD": "x", "JWT_SECRET": "j" * 40}
    with pytest.raises(ValidationError):
        Settings(**base, DB_RETENCION_USER="ret")  # sin contraseña
    with pytest.raises(ValidationError):
        Settings(**base, DB_RETENCION_USER="api", DB_RETENCION_PASSWORD="x" * 12)  # igual a la de la API
    assert Settings(**base, DB_RETENCION_USER="ret", DB_RETENCION_PASSWORD="x" * 12).DB_RETENCION_USER == "ret"
    with pytest.raises(ValidationError):
        Settings(**base, AUDIT_CONTEXT_RETENTION_DAYS=3651)
    with pytest.raises(ValidationError):
        Settings(**base, TECHNICAL_RETENTION_INTERVAL_SECONDS=30)


# --- Revocación de sesiones tras la baja: rechazo sin tratarlo como ataque ------------------------------------------

def test_intento_con_sesion_revocada_tras_la_baja_no_genera_alerta_de_reutilizacion(db, mails):
    user = deleted(db, makeUser(db), 5)
    token = security.generateOpaqueToken()
    db.add(UserSession(idUsuario=user.idUsuario, refreshTokenHash=security.hashOpaqueToken(token),
                       fechaExpiracion=NOW + timedelta(days=7), fechaRevocacion=NOW - timedelta(days=5)))
    db.commit()
    with pytest.raises(AuthError) as error:
        authService.refreshSession(db, token)
    assert error.value.code == "TOKEN_INVALIDO"
    db.expire_all()
    alerts = db.scalars(select(Audit).where(Audit.accion == "REFRESH_REUTILIZADO")).all()
    assert alerts == []  # rechazo de una cuenta eliminada: no se clasifica como ataque confirmado


# --- Política de privacidad y aceptación -------------------------------------------------------------------------

def test_version_de_la_politica_coincide_entre_backend_y_frontend():
    frontend = re.search(r"export const POLICY_VERSION = '([0-9.]+)';", POLICY.read_text(encoding="utf-8")).group(1)
    assert frontend == consentService.POLICY_VERSION == "1.3"


def test_la_politica_informa_los_90_dias_y_la_extension_por_baja():
    text = " ".join(POLICY.read_text(encoding="utf-8").split())  # el JSX parte las frases en varias líneas
    assert "90 días desde el" in text and "90 días después de la fecha de eliminación" in text
    assert "No son plazos impuestos por la Ley" in text


def test_una_version_anterior_no_bloquea_el_inicio_de_sesion(db, mails):
    user = makeUser(db)
    consentService.record(db, user, consentService.TipoConsentimiento.POLITICA_PRIVACIDAD, True)
    db.commit()
    db.expire_all()
    assert authService.loginLocal(db, EMAIL, PASSWORD).estado == "AUTENTICADO"


# --- Migración de permisos (sin ejecutarla) ----------------------------------------------------------------------

def test_la_cuenta_de_mantenimiento_solo_anula_ip_y_agente():
    script = MIGRATION.read_text(encoding="utf-8")
    grants = re.findall(r"^GRANT (UPDATE|INSERT|SELECT) ON OBJECT::dbo\.(\w+) \(?([^)\n;]*)\)? TO rol_glucolume_ip_tecnica;", script, re.M)
    updates = [(table, cols.strip()) for verb, table, cols in grants if verb == "UPDATE"]
    assert updates == [("AuditoriaContexto", "ipOrigen, agenteUsuario")]
    assert not re.search(r"GRANT\s+DELETE", script, re.I)  # ningún DELETE concedido
    assert re.search(r"DENY UPDATE, DELETE ON OBJECT::dbo\.Auditoria TO rol_glucolume_ip_tecnica;", script)
    assert re.search(r"DENY DELETE ON OBJECT::dbo\.AuditoriaContexto TO rol_glucolume_ip_tecnica;", script)
    assert not re.search(r"TO\s+rol_glucolume_api", script)  # la API no recibe nada de este script
    assert "APLICAR_RETENCION_IP_TECNICA" in script  # no corre sin confirmación explícita


def test_los_permisos_existentes_no_conceden_nada_al_rol_nuevo():
    permisos = (REPO / "database" / "reference" / "GlucoLume_permisos.sql").read_text(encoding="utf-8")
    assert "rol_glucolume_ip_tecnica" not in permisos


def test_el_servicio_de_mantenimiento_no_recibe_la_cuenta_de_la_api_ni_la_de_los_jobs():
    override = (REPO / "compose.retencion.yaml").read_text(encoding="utf-8")
    assert 'DB_RETENCION_USER: ""' in override and 'DB_RETENCION_PASSWORD: ""' in override  # la API no recibe la cuenta de mantenimiento
    service = override.split("\n  technical-retention:")[1]
    assert '"app.jobs.technicalRetention", "--loop"' in service and '"--health"' in service
    assert 'profiles: ["retention"]' in service  # no arranca con un `up` normal
    assert 'DB_JOBS_USER: ""' in service
