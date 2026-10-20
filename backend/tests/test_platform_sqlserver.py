# Administración de la plataforma contra SQL Server REAL pero DESCARTABLE: el índice UX_Usuario_administradorUnico, las activaciones y
# recuperaciones concurrentes y los mismos escenarios de tests/test_platform_recovery.py con el motor de verdad (bloqueos, CHECK, índices
# filtrados) en lugar del esquema SQLite temporal. Es OPCIONAL y nunca toca la base real:
#
#   1. Crear una base descartable GlucoLume_Descartable con database/reference/GlucoLume_DB_v5.sql (procedimiento en docs/BASE_DE_DATOS.md §6).
#   2. Apuntar la prueba a ella (la URL debe ser localhost y NO la base GlucoLume; se VACÍAN todas sus tablas antes de cada prueba):
#          set TEST_SQLSERVER_URL=mssql+pyodbc://@localhost/GlucoLume_Descartable?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes&TrustServerCertificate=yes
#          set TEST_SQLSERVER_CONFIRM=DESCARTABLE
#   3. Desde backend/:   python -m pytest tests/test_platform_sqlserver.py -v
#   4. Al terminar, borrar el contenedor o la base descartable.
#
# Sin esas variables se omite. NUNCA apuntar a la base real.

import threading

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from tests.test_platform_recovery import *  # noqa: E402, F403 - los mismos escenarios, contra SQL Server
from tests.test_platform_recovery import (  # noqa: E402, F401
    ADMIN, MOD, NEW_PASSWORD, admins, db, mails, makeUser, platform, platformUser, select, User,
)
# Después del import con *: si no, el `engine` SQLite de test_platform_recovery reemplaza al de SQL Server y las pruebas corren sobre SQLite.
from tests.test_device_connection_sqlserver import engine, pytestmark  # noqa: E402, F401 - fixture `engine` descartable y la omisión


def run_in_threads(engine, jobs):
    """Ejecuta cada job(session) en su propio hilo y conexión, arrancando todos a la vez; devuelve los resultados ('ok' o el código de error)."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    results, barrier = [], threading.Barrier(len(jobs))

    def runner(job):
        session = factory()
        try:
            barrier.wait()
            job(session)
            results.append("ok")
        except Exception as error:  # noqa: BLE001 - se clasifica en la aserción
            results.append(getattr(error, "code", type(error).__name__))
        finally:
            session.close()

    threads = [threading.Thread(target=runner, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_el_indice_unico_filtrado_existe_y_la_base_rechaza_un_segundo_administrador(db, engine, mails):
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT is_unique, filter_definition FROM sys.indexes WHERE name = N'UX_Usuario_administradorUnico' AND object_id = OBJECT_ID(N'dbo.Usuario')")).one()
    assert row.is_unique and "ADMINISTRADOR_PLATAFORMA" in row.filter_definition and "ELIMINADO" in row.filter_definition
    first, _ = platformUser(db, ADMIN, "admin1@example.com", "admin1")
    other, _ = platformUser(db, MOD, "mod1@example.com", "mod1")
    try:
        db.execute(text("UPDATE dbo.Usuario SET tipoCuenta = N'ADMINISTRADOR_PLATAFORMA' WHERE idUsuario = :id"), {"id": other.idUsuario})
        db.commit()
        raise AssertionError("SQL Server debía rechazar un segundo administrador vigente")
    except IntegrityError:
        db.rollback()
    assert [u.idUsuario for u in admins(db)] == [first.idUsuario]


def test_dos_inicializaciones_simultaneas_dejan_un_solo_administrador(db, engine, mails):
    jobs = [lambda session, mail=mail: platform.initializeFirstAdmin(session, "Ana", "Pérez", mail) for mail in ("a1@example.com", "a2@example.com")]
    results = run_in_threads(engine, jobs)
    assert results.count("ok") >= 1, results
    assert len(admins(db)) == 1  # el índice (y el control previo) impiden dos, aunque corran a la vez


def test_dos_activaciones_simultaneas_del_mismo_enlace_activan_una_sola_en_sql_server(db, engine, mails):
    _, link, _, _ = platform.initializeFirstAdmin(db, "Ana", "Pérez", "ana@example.com")
    token = link.split("codigo=")[1]
    jobs = [lambda session, name=name: platform.completeActivation(session, token, name, NEW_PASSWORD) for name in ("anauno", "anados")]
    results = run_in_threads(engine, jobs)
    assert results.count("ok") == 1, results
    assert len(admins(db)) == 1 and admins(db)[0].estado == "ACTIVO"


def test_dos_recuperaciones_simultaneas_con_destinos_distintos_dejan_un_solo_administrador(db, engine, mails, admin):
    first, _ = platformUser(db, MOD, "primero@example.com", "primeromod")
    second, _ = platformUser(db, MOD, "segundo@example.com", "segundomod")
    jobs = [lambda session, mail=user.correoElectronico: platform.replaceAdministrator(session, mail, "Recuperación simultánea") for user in (first, second)]
    results = run_in_threads(engine, jobs)
    assert results.count("ok") >= 1, results
    winners = admins(db)
    assert len(winners) == 1 and winners[0].idUsuario in (first.idUsuario, second.idUsuario)  # nunca dos ni ninguno
    assert db.scalar(select(User.tipoCuenta).where(User.idUsuario == admin[0].idUsuario)) == MOD


def test_una_cuenta_vencida_con_auditoria_libera_el_correo_sin_tocar_la_auditoria_en_sql_server(db, engine, mails):
    # GL-03 contra el motor real: FK_Auditoria_Usuario es NO ACTION; la baja anónima conserva la fila y la auditoría no se modifica.
    from datetime import timedelta

    from app.models.audit import Audit
    from app.schemas.auth import RegisterRequest
    from app.services import auth as authService
    from app.utils.timeZone import nowForDb

    def register():
        return authService.registerLocal(db, RegisterRequest(
            nombre="Lia", apellido="Mora", correoElectronico="lia.sql@example.com", password="Zafiro#Montana2026", usuario="liasql",
            tipoCuenta="CONSUMIDOR_FINAL", aceptaPoliticaPrivacidad=True))

    first = register()
    first.fechaCreacion = nowForDb() - timedelta(days=3)
    db.commit()
    before = db.scalar(select(Audit.idAuditoria).where(Audit.idUsuario == first.idUsuario))
    second = register()
    assert second.idUsuario != first.idUsuario and db.get(User, first.idUsuario).estado == "ELIMINADO"
    assert db.scalar(select(Audit.idAuditoria).where(Audit.idUsuario == first.idUsuario)) == before
