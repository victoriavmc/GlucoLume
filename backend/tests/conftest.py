# Configuración común de las pruebas.

import os
from pathlib import Path

import pytest

# GL-12: las pruebas nunca leen el .env real (base, SMTP, claves). Se fija antes de que cualquier prueba importe la aplicación.
os.environ["GLUCOLUME_ENV_FILE"] = str(Path(__file__).with_name("test.env"))


@pytest.fixture(autouse=True)
def resetRateLimits():
    """Los límites por IP (app/api/rateLimit.py) cuentan en memoria durante todo el proceso: cada prueba parte de cero para que no se
    afecten entre sí (las pruebas HTTP llegan todas desde la misma IP de TestClient)."""
    from app.api import rateLimit
    from app.services import resultEmailConfirmation

    rateLimit.resetLimits()
    resultEmailConfirmation.resetLimits()
    yield
    rateLimit.resetLimits()


@pytest.fixture(autouse=True)
def auditAppendOnly():
    """GL-03: fuera de la política de conservación (app/services/auditRetention.py), la aplicación nunca modifica ni borra la auditoría:
    la cuenta de la API queda con DENY UPDATE, DELETE sobre Auditoria y AuditoriaContexto (database/reference/GlucoLume_permisos.sql).
    Falla la prueba en la que el código de app/ emita una de esas sentencias; las pruebas sí pueden hacerlo para preparar datos."""
    import re
    import traceback

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    pattern = re.compile(r'^\s*(UPDATE|DELETE\s+FROM)\s+(\[?dbo\]?\.)?["\[]?(Auditoria|AuditoriaContexto)["\]]?\s', re.IGNORECASE)
    violations = []

    def check(conn, cursor, statement, parameters, context, executemany):
        if not pattern.match(statement):
            return
        for frame in reversed(traceback.extract_stack()[:-1]):  # sin este mismo marco (conftest)
            path = frame.filename.replace("\\", "/")
            if "/site-packages/" in path:
                continue
            if "/backend/tests/" in path:
                return
            if "/backend/app/" in path:
                if not path.endswith("/app/services/auditRetention.py"):
                    violations.append(f"{path.split('/backend/', 1)[1]}:{frame.lineno}: {statement.strip().splitlines()[0][:100]}")
                return

    event.listen(Engine, "before_cursor_execute", check)
    yield
    event.remove(Engine, "before_cursor_execute", check)
    assert not violations, "La aplicación modificó o borró auditoría fuera de auditRetention.py (GL-03): " + "; ".join(violations)


def _grantedDeletes() -> dict[str, set[str]]:
    """Tablas con GRANT DELETE por rol en database/reference/GlucoLume_permisos.sql (lectura del script, nunca de una base)."""
    import re
    from pathlib import Path

    script = (Path(__file__).resolve().parents[2] / "database" / "reference" / "GlucoLume_permisos.sql").read_text(encoding="utf-8")
    granted: dict[str, set[str]] = {}
    for table, role in re.findall(r"^GRANT DELETE ON OBJECT::dbo\.(\w+) TO (\w+);", script, re.M):
        granted.setdefault(role, set()).add(table)
    return granted


@pytest.fixture(autouse=True)
def deleteGrants():
    """H-02 (minimo privilegio): el script de permisos concede DELETE tabla por tabla. Falla la prueba en la que el codigo de app/ emita un DELETE
    sobre una tabla que el rol correspondiente no tiene concedida en GlucoLume_permisos.sql: en produccion esa operacion fallaria con el error 229.
    La depuracion de la auditoria (services/auditRetention.py) y la de los avisos (services/notificationRetention.py) se comparan con el rol de conservacion; todo lo demas, con el de la API."""
    import re
    import traceback

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    pattern = re.compile(r'^\s*DELETE\s+FROM\s+(?:\[?dbo\]?\.)?["\[]?(\w+)["\]]?', re.IGNORECASE)
    found: list[tuple[str, str, str]] = []  # (tabla, rol, origen)

    def check(conn, cursor, statement, parameters, context, executemany):
        match = pattern.match(statement)
        if not match:
            return
        for frame in reversed(traceback.extract_stack()[:-1]):
            path = frame.filename.replace("\\", "/")
            if "/site-packages/" in path:
                continue
            if "/backend/tests/" in path:
                return  # preparar datos en una prueba no es el codigo de la aplicacion
            if "/backend/app/" in path:
                retentionFiles = ("/app/services/auditRetention.py", "/app/services/notificationRetention.py")
                role = "rol_glucolume_retencion" if path.endswith(retentionFiles) else "rol_glucolume_api"
                found.append((match.group(1), role, f"{path.split('/backend/', 1)[1]}:{frame.lineno}"))
                return

    event.listen(Engine, "before_cursor_execute", check)
    yield
    event.remove(Engine, "before_cursor_execute", check)
    granted = _grantedDeletes()
    missing = [f"{origin}: DELETE sobre {table} sin GRANT para {role}" for table, role, origin in found if table not in granted.get(role, set())]
    assert not missing, "El codigo borra tablas sin permiso en GlucoLume_permisos.sql (H-02): " + "; ".join(sorted(set(missing)))


@pytest.fixture(autouse=True)
def isolateSecurityMonitor(monkeypatch):
    """El monitor de ráfagas (services/securityMonitor.py) cuenta en memoria y, al cruzar un umbral, escribe en la base: ninguna prueba debe
    tocar la base real por esa vía. Las pruebas del monitor reemplazan persistBurst/persistRateLimit por su propia base."""
    from app.services import securityMonitor

    securityMonitor.monitor.clear()
    monkeypatch.setattr(securityMonitor, "persistBurst", lambda burst: None)
    monkeypatch.setattr(securityMonitor, "persistRateLimit", lambda limit: None)
    monkeypatch.setattr(securityMonitor, "alertAdministrator", lambda burst, now=None: False)
    securityMonitor.resetAlerts()
    yield
    securityMonitor.monitor.clear()


# test_email.py y test_connection.py son SCRIPTS manuales (se ejecutan al importarse: envían un correo real por SMTP y consultan
# SQL Server con las credenciales del .env). Pytest no debe importarlos al juntar pruebas; se ejecutan a mano con `python tests/<archivo>`.
collect_ignore = ["test_email.py", "test_connection.py"]


@pytest.fixture(autouse=True)
def deviceMode(monkeypatch):
    """Modo del dispositivo compartido (DEC-01) aislado del .env real: las pruebas no dependen de lo que tenga el equipo de quien las
    ejecuta. Por defecto FALSE (uso restringido por asignación); una prueba pasa al modo compartido llamando a deviceMode(True).
    Variable de entorno + cache_clear, como el resto de la configuración de las pruebas (tests/test_account_deletion.py::engine)."""
    from app.core.config import getSettings

    def setMode(shared: bool) -> None:
        monkeypatch.setenv("ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE", "true" if shared else "false")
        getSettings.cache_clear()

    setMode(False)
    yield setMode
    getSettings.cache_clear()


@pytest.fixture(scope="session")
def referenceSchema() -> str:
    """Esquema SQL consolidado vigente (DEC-02): database/reference/GlucoLume_DB_v5.sql, generado por SSMS en UTF-16. Las pruebas de
    estructura lo validan a él; los scripts incrementales históricos se retiraron a propósito."""
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "database" / "reference" / "GlucoLume_DB_v5.sql").read_text(encoding="utf-16")


@pytest.fixture(autouse=True)
def noRealSmtp(monkeypatch):
    """Ninguna prueba envía correo real aunque el .env tenga SMTP configurado: smtplib falla como una red caída. Las pruebas que
    verifican el envío reemplazan sender.sendHtmlEmail o smtplib por su propio doble y no se ven afectadas."""
    import smtplib

    def blocked(*args, **kwargs):
        raise OSError("SMTP bloqueado en las pruebas")

    monkeypatch.setattr(smtplib, "SMTP", blocked)
    monkeypatch.setattr(smtplib, "SMTP_SSL", blocked)
