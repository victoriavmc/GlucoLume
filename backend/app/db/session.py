# Session - Motor y sesiones SQLAlchemy para SQL Server

import os
import ssl
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import getSettings
from app.db.gate import limitDriverCalls

# Bundle de autoridades = las del sistema + el certificado de SQL Server (Linux/Docker). En /tmp: la imagen es de solo lectura.
TRUST_BUNDLE = Path("/tmp/glucolume-ca-bundle.pem")


def _trustOnLinux(certificate: str) -> None:
    """El driver ODBC 18 de Linux valida contra las autoridades de OpenSSL y no aplica ServerCertificate: se le suma el certificado de
    SQL Server a las del sistema (no se reemplazan, así SMTP y Google siguen validando contra las públicas). El nombre del servidor se
    sigue verificando contra DB_HOST."""
    system = ssl.get_default_verify_paths().openssl_cafile
    bundle = Path(system).read_text(encoding="utf-8") if system and Path(system).is_file() else ""
    TRUST_BUNDLE.write_text(bundle + "\n" + Path(certificate).read_text(encoding="utf-8"), encoding="utf-8")
    os.environ["SSL_CERT_FILE"] = str(TRUST_BUNDLE)


def _createEngine(username: str, password: str) -> Engine:
    settings = getSettings()
    pinned = settings.DB_SERVER_CERTIFICATE
    windows = os.name == "nt"
    if pinned and not windows:
        _trustOnLinux(pinned)
    url = URL.create(
        "mssql+pyodbc",
        username=username,
        password=password,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        query={
            "driver": settings.DB_DRIVER,
            # Cifrado obligatorio aunque el driver cambie de valor por defecto (GL-07); el certificado se verifica salvo en development.
            # Windows: el certificado fijado se compara en modo estricto (TDS 8.0, SQL Server 2022+). Linux: se confía en él (arriba).
            "Encrypt": "strict" if pinned and windows else "yes",
            "TrustServerCertificate": "yes" if settings.trustServerCertificate else "no",
            **({"ServerCertificate": pinned} if pinned and windows else {}),
            **({"HostNameInCertificate": settings.DB_CERTIFICATE_HOSTNAME} if settings.DB_CERTIFICATE_HOSTNAME else {}),
        },
    )
    engine = create_engine(url, pool_pre_ping=True)
    if settings.DB_LOCK_TIMEOUT_MS > 0:
        _limitLockWaits(engine, settings.DB_LOCK_TIMEOUT_MS)
    return limitDriverCalls(engine, settings.DB_MAX_CONCURRENT_CALLS)


def _limitLockWaits(engine: Engine, milliseconds: int) -> None:
    """Fija LOCK_TIMEOUT en cada conexión nueva (el pool la conserva). Se confirma enseguida para no dejar una transacción abierta."""
    if not isinstance(engine, Engine):  # reemplazo de prueba (como en limitDriverCalls)
        return

    @event.listens_for(engine, "connect")
    def setLockTimeout(dbapiConnection, connectionRecord):
        cursor = dbapiConnection.cursor()
        cursor.execute(f"SET LOCK_TIMEOUT {int(milliseconds)}")
        cursor.close()
        dbapiConnection.commit()


@lru_cache
def getEngine() -> Engine:
    settings = getSettings()
    return _createEngine(settings.DB_USER, settings.DB_PASSWORD.get_secret_value())


@lru_cache
def getRetentionEngine() -> Engine:
    """Motor del mantenimiento técnico de IP (DB_RETENCION_USER). Sin esa cuenta NO hay fallback: la API y los jobs de conservación no anulan IP."""
    settings = getSettings()
    if settings.DB_RETENCION_USER is None or settings.DB_RETENCION_PASSWORD is None:
        raise RuntimeError("Falta DB_RETENCION_USER y DB_RETENCION_PASSWORD: el mantenimiento técnico de IP no se ejecuta sin su cuenta propia.")
    return _createEngine(settings.DB_RETENCION_USER, settings.DB_RETENCION_PASSWORD.get_secret_value())


def getRetentionSessionFactory() -> sessionmaker[Session]:
    return sessionmaker(bind=getRetentionEngine(), autoflush=False, expire_on_commit=False)


@lru_cache
def getDemoSessionFactory() -> sessionmaker[Session]:
    """Sesiones de la limpieza de datos DEMO (DB_DEMO_USER). Sin esa cuenta no hay fallback: la API no puede borrar instituciones ni perfiles."""
    settings = getSettings()
    if settings.DB_DEMO_USER is None or settings.DB_DEMO_PASSWORD is None:
        raise RuntimeError("Falta DB_DEMO_USER y DB_DEMO_PASSWORD: la limpieza de datos demo no se ejecuta sin su cuenta propia.")
    return sessionmaker(bind=_createEngine(settings.DB_DEMO_USER, settings.DB_DEMO_PASSWORD.get_secret_value()),
                        autoflush=False, expire_on_commit=False)


@lru_cache
def getSessionFactory() -> sessionmaker[Session]:
    return sessionmaker(bind=getEngine(), autoflush=False, expire_on_commit=False)


@lru_cache
def getJobsSessionFactory() -> sessionmaker[Session]:
    """Sesiones de los procesos de conservación (app/jobs, servicio «lifecycle»): usan DB_JOBS_USER si está configurada (GL-03), la única
    cuenta con permiso para depurar la auditoría vencida. Sin ella, la misma cuenta que la API."""
    settings = getSettings()
    if settings.DB_JOBS_USER is None:
        return getSessionFactory()
    engine = _createEngine(settings.DB_JOBS_USER, settings.DB_JOBS_PASSWORD.get_secret_value())
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def getDb() -> Iterator[Session]:
    """Dependencia FastAPI: una sesión por request, cerrada al finalizar."""
    session = getSessionFactory()()
    try:
        yield session
    except Exception:
        # Nunca reutilizar ni devolver al pool una sesión con una transacción fallida a medio camino.
        session.rollback()
        raise
    finally:
        session.close()
