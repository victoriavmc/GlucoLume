# TechnicalRetention - Anulación técnica de IP y agente vencidos (independiente del servicio «lifecycle»)
#
#     python -m app.jobs.technicalRetention --loop      servicio «technical-retention» de Compose: una pasada cada
#                                                        TECHNICAL_RETENTION_INTERVAL_SECONDS, sin terminar
#     python -m app.jobs.technicalRetention             una pasada y termina (manual o programador externo)
#     python -m app.jobs.technicalRetention --dry-run   solo cuenta lo que anularía; no modifica nada
#     python -m app.jobs.technicalRetention --health    healthcheck del contenedor (0 = sano)
#
# Solo hace una cosa: anula `AuditoriaContexto.ipOrigen` y `agenteUsuario` de los eventos vencidos (services/auditRetention.py). No elimina
# cuentas, pacientes, mediciones ni eventos de auditoría, y no depende del servicio «lifecycle», que puede estar apagado.
#
# Seguridad operativa:
#   - Corre con su propia cuenta de base (DB_RETENCION_USER), que solo puede UPDATE de esas dos columnas (migración
#     database/reference/GlucoLume_retencion_ip_tecnica.sql). Sin esa cuenta no corre: no hay fallback a la de la API ni a la de los jobs.
#   - Exclusión mutua: un applock de SQL Server (sp_getapplock, sin espera). Si otra pasada tiene el lock, esta se omite sin error.
#   - Lotes de TECHNICAL_RETENTION_BATCH filas, cada uno con su COMMIT: una interrupción deja lo ya anulado y nada más.
#   - Idempotente: solo toca filas que todavía tienen IP o agente; lo anulado no se restaura.
#   - Registro: cada pasada deja la marca de vida (healthcheck) y, cuando anula algo o falla, un evento de auditoría sin datos personales.

import logging
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core.config import getSettings
from app.db.session import getRetentionEngine, getRetentionSessionFactory
from app.services import auditRetention
from app.services.audit import registerEvent
from app.utils.timeZone import nowForDb

logger = logging.getLogger("glucolume.technicalRetention")
HEARTBEAT = Path(tempfile.gettempdir()) / "glucolume-technical-retention.heartbeat"
HEALTH_MARGIN_SECONDS = 600
LOCK_RESOURCE = "GlucoLume.anonimizacionIpTecnica"
ACCION_RESULTADO = "ANONIMIZAR_IP_TECNICA"
ACCION_FALLA = "ANONIMIZAR_IP_TECNICA_FALLIDA"


def _acquireLock(engine: Engine) -> Connection | None:
    """Toma el applock de sesión. Devuelve la conexión que lo sostiene, o None si otra pasada ya lo tiene.
    En SQLite (pruebas) no hay applock: la exclusión la aportan las propias pruebas."""
    connection = engine.connect()
    if engine.dialect.name != "mssql":
        return connection
    result = connection.execute(text(
        "DECLARE @r int; EXEC @r = sp_getapplock @Resource = :resource, @LockMode = 'Exclusive', "
        "@LockOwner = 'Session', @LockTimeout = 0; SELECT @r;"), {"resource": LOCK_RESOURCE}).scalar()
    connection.commit()
    if result is None or result < 0:
        connection.close()
        return None
    return connection


def _releaseLock(connection: Connection, engine: Engine) -> None:
    try:
        if engine.dialect.name == "mssql":
            connection.execute(text("EXEC sp_releaseapplock @Resource = :resource, @LockOwner = 'Session'"), {"resource": LOCK_RESOURCE})
            connection.commit()
    finally:
        connection.close()


def beat() -> None:
    try:
        HEARTBEAT.touch()
    except OSError:
        logger.warning("No se pudo escribir la marca de vida del mantenimiento técnico de IP.")


def healthy() -> bool:
    """Sano si la última pasada correcta es más reciente que dos intervalos (más margen)."""
    interval = getSettings().TECHNICAL_RETENTION_INTERVAL_SECONDS
    try:
        return time.time() - HEARTBEAT.stat().st_mtime < 2 * interval + HEALTH_MARGIN_SECONDS
    except OSError:
        return False


def _recordFailure(error: Exception) -> None:
    try:
        with getRetentionSessionFactory()() as db:
            registerEvent(db, "CRUD", ACCION_FALLA, False, modulo="AUDITORIA", motivo="ERROR_INTERNO",
                          observacion=f"La anulación técnica de IP se interrumpió ({type(error).__name__}).")
            db.commit()
    except Exception:  # noqa: BLE001 - registrar la falla nunca debe tapar la falla original
        logger.exception("No se pudo registrar la falla del mantenimiento técnico de IP.")


def run(now=None) -> dict:
    """Una pasada. Devuelve el resultado; nunca lanza: un fallo se registra y el ciclo sigue."""
    settings = getSettings()
    now = now or nowForDb()
    connection = None
    engine = None
    try:
        engine = getRetentionEngine()
        connection = _acquireLock(engine)
        if connection is None:
            logger.info("Mantenimiento técnico de IP: otra pasada tiene el lock; esta se omite.")
            return {"omitidaPorConcurrencia": True}
        with getRetentionSessionFactory()() as db:
            changed = auditRetention.anonymizeDueContext(db, now)
            if changed:
                registerEvent(db, "CRUD", ACCION_RESULTADO, True, modulo="AUDITORIA",
                              observacion="Anulación técnica de IP y agente vencidos (sin datos personales).",
                              datosNuevos={"contextosAnonimizados": changed,
                                           "contextoDias": settings.AUDIT_CONTEXT_RETENTION_DAYS,
                                           "eliminadaDias": settings.AUDIT_DELETED_ACCOUNT_RETENTION_DAYS})
                db.commit()
        beat()
        logger.info("Mantenimiento técnico de IP: %s contextos anulados.", changed)
        return {"contextosAnonimizados": changed}
    except Exception as error:  # noqa: BLE001 - un fallo queda registrado; el servicio sigue y reintenta en el próximo ciclo
        logger.exception("Falló el mantenimiento técnico de IP")
        _recordFailure(error)
        return {"error": type(error).__name__}
    finally:
        if connection is not None and engine is not None:
            _releaseLock(connection, engine)


def dryRun(now=None) -> dict:
    now = now or nowForDb()
    with getRetentionSessionFactory()() as db:
        settings = getSettings()
        return {"contextosVencidos": auditRetention.countDueContext(db, now),
                "contextoDias": settings.AUDIT_CONTEXT_RETENTION_DAYS,
                "eliminadaDias": settings.AUDIT_DELETED_ACCOUNT_RETENTION_DAYS}


def loop() -> None:
    interval = getSettings().TECHNICAL_RETENTION_INTERVAL_SECONDS
    logger.info("Mantenimiento técnico de IP activo (cada %s s).", interval)
    while True:
        run()
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = sys.argv[1:]
    if "--health" in args:
        sys.exit(0 if healthy() else 1)
    if "--dry-run" in args:
        print(dryRun())
        sys.exit(0)
    if "--loop" in args:
        loop()
    else:
        print(run())
