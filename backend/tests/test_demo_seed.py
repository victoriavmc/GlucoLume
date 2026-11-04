# Carga de DATOS DEMO (sintéticos) para la demostración académica. Ejecutar desde backend/:
#     python -m pytest tests/test_demo_seed.py -v
#
# Cubre: dry-run sin escritura, aplicación con las cantidades del catálogo, idempotencia, colisiones, producción bloqueada,
# autenticación real de las cuentas demo, ausencia de correo saliente, permisos por configuración de privacidad del grupo,
# aislamiento de pacientes entre operadores e instituciones, propietario con dos instituciones, administrador existente intacto,
# limpieza solo de datos demo (y bloqueo por auditoría), archivo privado sin contraseñas en el inventario público, y la CLI.

import smtplib
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.core.exceptions import AuthError
from app.demo import catalog as C
from app.demo import inventory, limpieza, seeder
from app.models.localCredential import LocalCredential
from app.models.measurement import Measurement
from app.models.user import User
from app.services import auth
from app.services import group as groups
from app.services import institution as institutions
from app.services import measurement as measurements
from app.services.audit import registerEvent
from app.cli import demoSeed
from tests.test_account_deletion import db, engine  # noqa: F401  (fixtures: esquema SQLite con el modelo real)

ANCHOR = datetime(2026, 10, 1)


def account(key: str) -> C.Account:
    return C.ACCOUNTS_BY_KEY[key]


def actor(db, key: str) -> User:
    return db.get(User, account(key).id)


def allPasswords() -> dict[str, str]:
    return {a.key: seeder.generatePassword(a) for a in C.ACCOUNTS}


@pytest.fixture
def seeded(db):
    """Carga completa aplicada sobre la base de prueba. Devuelve las contraseñas (solo en memoria, nunca se imprimen)."""
    passwords = allPasswords()
    plan = seeder.buildPlan(db, anchor=ANCHOR, passwords=passwords)
    assert not plan.bloqueado, plan.bloqueos
    seeder.apply(db, plan)
    return passwords


def countRows(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- Dry-run, aplicación e idempotencia ----------------------------------------------------------------------------------


def test_dry_run_no_escribe_nada_y_prevee_las_cantidades(db):
    plan = seeder.buildPlan(db, anchor=ANCHOR)
    assert not plan.bloqueado
    assert plan.conteo()["Usuario"] == {"CREAR": 21}
    assert plan.conteo()["PerfilMedicion"] == {"CREAR": 39}
    assert all(not etapa for etapa in plan.etapas)  # ningún registro preparado para insertar
    assert countRows(db, User) == 0
    assert countRows(db, Measurement) == 0


def test_aplicar_crea_exactamente_lo_previsto(db, seeded):
    expected = C.expectedCounts()
    assert countRows(db, User) == expected["usuarios"]
    counts = seeder.countDemoRows(db)
    assert counts["Institucion"] == expected["instituciones"]
    assert counts["Grupo"] == expected["grupos"]
    assert counts["Dispositivo"] == expected["dispositivos"]
    assert counts["PerfilMedicion"] == expected["perfiles_individuales"] + expected["pacientes_asignados"]
    assert counts["Medicion"] == expected["mediciones_individuales"] + expected["mediciones_pacientes"]
    assert countRows(db, LocalCredential) == expected["credenciales"]


def test_segunda_ejecucion_no_duplica_ningun_registro(db, seeded):
    before = seeder.countDemoRows(db)
    plan = seeder.buildPlan(db, anchor=ANCHOR)
    assert all(item.accion != "CREAR" for item in plan.items), [i for i in plan.items if i.accion == "CREAR"]
    assert seeder.countDemoRows(db) == before


def test_cada_medicion_se_identifica_como_sintetica_y_no_estima_glucosa(db, seeded):
    rows = db.scalars(select(Measurement)).all()
    assert rows and all(row.observacion == C.NOTA_MEDICION for row in rows)
    assert all(row.glucosaEstimada is None for row in rows)  # la demo no fabrica estimaciones clínicas
    assert all(row.origenGlucosa in (None, "DEMO") for row in rows)
    glucose = [row for row in rows if row.glucosaDispositivo is not None]
    assert glucose and all(row.origenGlucosa == "DEMO" for row in glucose)


def test_mediciones_con_variedad_de_fechas_modos_estados_y_alimentacion(db, seeded):
    own = db.scalars(select(Measurement).where(Measurement.idPerfilMedicion == C.demoId("perfil", "individual-a"))).all()
    assert len({row.fechaHoraInicio.date() for row in own}) >= 8  # distintos días
    assert len({row.fechaHoraInicio.hour for row in own}) >= 5  # distintos horarios
    assert {row.modoMedicion for row in own} == {C.MODO_GLUCOSA, C.MODO_OXIMETRIA}
    assert {row.condicionComida for row in own} >= {"AYUNO", "POSTPRANDIAL"}
    everything = db.scalars(select(Measurement)).all()
    assert {row.estadoMedicion for row in everything} >= {"COMPLETADA", "CANCELADA", "INVALIDA"}
    completed = [row for row in everything if row.estadoMedicion == "COMPLETADA"]
    assert all(row.spo2 is not None and row.frecuenciaCardiaca is not None for row in completed)
    assert all(40 <= row.frecuenciaCardiaca <= 130 and 90 <= row.spo2 <= 100 for row in completed)  # rangos verosímiles
    assert all(row.fechaHoraFin >= row.fechaHoraInicio for row in everything)


# --- Colisiones y producción ---------------------------------------------------------------------------------------------


def test_colision_con_dato_real_bloquea_la_carga_sin_escribir(db):
    real = User(idUsuario=uuid.uuid4(), nombre="Real", apellido="Persona", correoElectronico=account("individual-a").correo,
                tipoCuenta="CONSUMIDOR_FINAL", estado="ACTIVO", fechaCreacion=ANCHOR, fechaActualizacion=ANCHOR,
                notificarNuevoInicioSesion=True)
    db.add(real)
    db.commit()
    plan = seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords())
    assert plan.bloqueado and "demo.individual-a@example.com" in plan.bloqueos[0]
    with pytest.raises(seeder.SeedError):
        seeder.apply(db, plan)
    assert countRows(db, User) == 1  # solo el dato real


def test_produccion_exige_autorizacion_explicita_y_nombre_de_base(monkeypatch):
    monkeypatch.setattr(seeder, "getSettings", lambda: SimpleNamespace(API_ENV="production", DB_NAME="GlucoLume"))
    with pytest.raises(seeder.SeedError):
        seeder.assertAllowed()
    with pytest.raises(seeder.SeedError):
        seeder.assertAllowed(autorizarProduccion=True, confirmarBase="OtraBase")
    seeder.assertAllowed(autorizarProduccion=True, confirmarBase="GlucoLume")  # decisión explícita: pasa


# --- Autenticación, privacidad y correo ----------------------------------------------------------------------------------


def test_cuentas_demo_inician_sesion_con_el_flujo_real_sin_mfa_ni_correo(db, seeded, monkeypatch):
    sent: list[str] = []

    def recorder(*args, **kwargs):  # cualquier intento de SMTP durante la carga o el ingreso queda registrado
        sent.append("SMTP")
        raise OSError("SMTP bloqueado en las pruebas")

    monkeypatch.setattr(smtplib, "SMTP", recorder)
    monkeypatch.setattr(smtplib, "SMTP_SSL", recorder)
    for demo in C.ACCOUNTS:
        response = auth.loginLocal(db, demo.correo, seeded[demo.key])
        assert response.estado == "AUTENTICADO", demo.key
        assert response.tokens is not None
    assert sent == []  # ningún correo saliente
    results = seeder.verifyAccounts(db, seeded)
    assert all(result.ok for result in results), [r for r in results if not r.ok]


def test_contrasena_incorrecta_no_entra(db, seeded):
    with pytest.raises(AuthError):
        auth.loginLocal(db, account("operador-a-1").correo, seeded["operador-a-2"])


def test_cinco_configuraciones_de_privacidad_del_grupo(db, seeded):
    admin = actor(db, "grupo-admin")
    group = C.demoId("grupo", C.GROUP_KEY)

    def allowed(call) -> bool:
        try:
            call()
            return True
        except AuthError as error:
            assert error.code == "DATOS_NO_COMPARTIDOS", error.code
            return False

    expected = {  # perfil, última medición, historial, avisos
        "grupo-integrante-1": (True, False, False, False),
        "grupo-integrante-2": (False, True, False, False),
        "grupo-integrante-3": (False, False, True, False),
        "grupo-integrante-4": (False, False, False, True),
        "grupo-integrante-5": (True, True, True, True),
    }
    for key, (perfil, ultima, historial, avisos) in expected.items():
        link = C.demoId("vinculo-grupo", key)
        assert allowed(lambda: groups.sharedProfile(db, admin, group, link)) is perfil, key
        assert allowed(lambda: groups.sharedLatest(db, admin, group, link)) is ultima, key
        assert allowed(lambda: groups.sharedHistory(db, admin, group, link)) is historial, key
        assert allowed(lambda: groups.sharedNotices(db, admin, group, link)) is avisos, key


def test_avisos_no_exponen_valores_y_el_administrador_no_ve_sus_propios_datos_en_el_grupo(db, seeded):
    admin = actor(db, "grupo-admin")
    group = C.demoId("grupo", C.GROUP_KEY)
    notices = groups.sharedNotices(db, admin, group, C.demoId("vinculo-grupo", "grupo-integrante-4"))
    assert notices.total == len(next(specs for key, specs in C.individualMeasurements() if key == "grupo-integrante-4"))
    assert all(set(item.model_dump().keys()) == {"fechaHoraInicio"} for item in notices.items)
    with pytest.raises(AuthError):  # tus propios datos se consultan desde tu perfil
        groups.sharedProfile(db, admin, group, C.demoId("vinculo-grupo", "grupo-admin"))


# --- Instituciones, propietarios, operadores ----------------------------------------------------------------------------


def test_propietario_administra_dos_instituciones_con_el_mismo_titular(db, seeded):
    owner = actor(db, "propietario-a")
    mine = {row.idInstitucion for row in institutions.listMine(db, owner)}
    assert C.INSTITUTIONS_BY_KEY["a"].id in mine and C.INSTITUTIONS_BY_KEY["c"].id in mine
    assert C.INSTITUTIONS_BY_KEY["b"].id not in mine  # no ve la institución del otro propietario
    detail = institutions.getDetail(db, owner, C.INSTITUTIONS_BY_KEY["c"].id)
    assert detail is not None


def test_propietario_de_b_no_accede_a_la_institucion_a(db, seeded):
    with pytest.raises(AuthError):
        institutions.getDetail(db, actor(db, "propietario-b"), C.INSTITUTIONS_BY_KEY["a"].id)


def test_operador_solo_consulta_sus_propios_pacientes(db, seeded):
    own = max((p for p in C.PATIENTS if p.institution == "a" and p.operator == "operador-a-1"), key=lambda p: p.mediciones)
    ownProfile = C.demoId("perfil", own.key)
    page = measurements.listPatientHistory(db, actor(db, "operador-a-1"), C.INSTITUTIONS_BY_KEY["a"].id, ownProfile)
    assert page.total == own.mediciones
    other = next(p for p in C.PATIENTS if p.institution == "a" and p.operator == "operador-a-2")
    with pytest.raises(AuthError):  # asignado a otro operador: no se consulta su historial
        measurements.listPatientHistory(db, actor(db, "operador-a-1"), C.INSTITUTIONS_BY_KEY["a"].id,
                                        C.demoId("perfil", other.key))


def test_operador_de_otra_institucion_no_accede_a_pacientes_ajenos(db, seeded):
    patientOfA = next(p for p in C.PATIENTS if p.institution == "a")
    with pytest.raises(AuthError):
        measurements.listPatientHistory(db, actor(db, "operador-b-1"), C.INSTITUTIONS_BY_KEY["b"].id,
                                        C.demoId("perfil", patientOfA.key))


def test_cada_paciente_tiene_un_unico_operador_y_los_documentos_son_unicos(db, seeded):
    perOperator: dict[str, int] = {}
    for patient in C.PATIENTS:
        perOperator[patient.operator] = perOperator.get(patient.operator, 0) + 1
    assert set(perOperator.values()) <= {3, 4, 5}
    assert len(C.PATIENTS) == sum(perOperator.values()) == 32
    documents = [p.dni for p in C.PATIENTS if p.dni]
    assert len(documents) == len(set(documents))


# --- Administrador existente, limpieza y auditoría ----------------------------------------------------------------------


def _platformAdmin(db) -> User:
    admin = User(idUsuario=uuid.uuid4(), nombre="Administrador", apellido="Real", correoElectronico="admin.real@example.org",
                 tipoCuenta="ADMINISTRADOR_PLATAFORMA", estado="ACTIVO", fechaCreacion=ANCHOR, fechaActualizacion=ANCHOR,
                 notificarNuevoInicioSesion=True)
    db.add(admin)
    db.commit()
    return admin


def _snapshot(user: User) -> tuple:
    return (user.correoElectronico, user.tipoCuenta, user.estado, user.nombre, user.apellido)


def test_administrador_existente_no_cambia_con_la_carga_ni_con_la_limpieza(db, engine):
    admin = _platformAdmin(db)
    before = _snapshot(admin)
    seeded = allPasswords()
    seeder.apply(db, seeder.buildPlan(db, anchor=ANCHOR, passwords=seeded))
    assert _snapshot(db.get(User, admin.idUsuario)) == before
    cleanup = limpieza.plan(db)
    assert not cleanup.bloqueada
    limpieza.execute(cleanup, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    assert _snapshot(db.get(User, admin.idUsuario)) == before
    assert seeder.countDemoRows(db) == {k: 0 for k in seeder.countDemoRows(db)}


def test_limpieza_elimina_solo_lo_demo_y_conserva_datos_reales(db, engine):
    real_user = User(idUsuario=uuid.uuid4(), nombre="Real", apellido="Usuario", correoElectronico="persona@example.org",
                     tipoCuenta="CONSUMIDOR_FINAL", estado="ACTIVO", fechaCreacion=ANCHOR, fechaActualizacion=ANCHOR,
                     notificarNuevoInicioSesion=True)
    db.add(real_user)
    db.commit()
    seeder.apply(db, seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords()))
    assert db.get(User, real_user.idUsuario) is not None
    cleanup = limpieza.plan(db)
    assert not cleanup.bloqueada, cleanup.bloqueos
    assert set(cleanup.resumen()) >= {"Usuario", "Institucion", "Medicion", "PerfilMedicion", "Dispositivo", "Grupo"}
    borrados = limpieza.execute(cleanup, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    assert borrados["Usuario"] == len(C.ACCOUNTS)
    assert seeder.countDemoRows(db) == {k: 0 for k in seeder.countDemoRows(db)}
    assert db.get(User, real_user.idUsuario) is not None  # el dato real sigue ahí


def test_limpieza_se_bloquea_si_hay_auditoria_de_cuentas_demo_y_no_borra_nada(db, engine):
    seeder.apply(db, seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords()))
    registerEvent(db, "LOGIN", "LOGIN_LOCAL", True, account("individual-a").id)
    db.commit()
    cleanup = limpieza.plan(db)
    assert cleanup.bloqueada
    assert any("Auditoria" in motivo for motivo in cleanup.bloqueos)
    with pytest.raises(limpieza.LimpiezaBloqueada):
        limpieza.execute(cleanup, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    assert countRows(db, User) == len(C.ACCOUNTS)  # nada se borró


# --- Credenciales: archivo privado, regeneración e inventario público ---------------------------------------------------


def test_archivo_privado_fuera_del_repositorio_y_sin_contrasenas_en_el_inventario_publico(tmp_path, seeded):
    private = tmp_path / "privado" / "credenciales-demo.txt"
    public = tmp_path / "inventario.md"
    inventory.writePrivateFile(private, seeded, ANCHOR)
    assert inventory.readPasswords(private) == seeded
    inventory.writePublicMarkdown(public, ANCHOR)
    text = public.read_text(encoding="utf-8")
    assert not any(password in text for password in seeded.values())
    assert "demo.individual-a@example.com" in text
    with pytest.raises(seeder.SeedError):
        seeder.assertOutsideRepo(seeder.repoRoots()[0] / "credenciales.txt")
    seeder.assertOutsideRepo(private)  # fuera del repositorio: permitido


@pytest.mark.skipif(__import__("os").name == "nt", reason="los permisos POSIX se verifican solo fuera de Windows")
def test_archivo_privado_con_permisos_restrictivos(tmp_path, seeded):
    private = tmp_path / "credenciales-demo.txt"
    inventory.writePrivateFile(private, seeded, ANCHOR)
    assert oct(private.stat().st_mode & 0o777) == "0o600"


def test_cli_dry_run_luego_aplicar_idempotente_y_sin_imprimir_contrasenas(db, engine, tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.session.getSessionFactory", lambda: sessionmaker(bind=engine, autoflush=False,
                                                                                 expire_on_commit=False))
    private = tmp_path / "privado" / "credenciales-demo.txt"
    public = tmp_path / "inventario.md"
    lines: list[str] = []
    args = ["--fecha-ancla", "2026-10-01", "--credenciales", str(private), "--inventario-publico", str(public)]

    assert demoSeed.run(args, out=lines.append) == 0  # dry-run
    assert countRows(db, User) == 0 and not private.exists()

    assert demoSeed.run(args + ["--aplicar"], out=lines.append) == 0
    passwords = inventory.readPasswords(private)
    assert set(passwords) == {a.key for a in C.ACCOUNTS}
    output = "\n".join(lines)
    assert not any(password in output for password in passwords.values())  # la consola nunca muestra contraseñas
    assert not any(password in public.read_text(encoding="utf-8") for password in passwords.values())

    lines.clear()
    assert demoSeed.run(args + ["--aplicar"], out=lines.append) == 0  # segunda vez: no duplica ni cambia contraseñas
    assert inventory.readPasswords(private) == passwords
    assert countRows(db, User) == len(C.ACCOUNTS)

    lines.clear()
    assert demoSeed.run(args + ["--verificar"], out=lines.append) == 0
    assert any("Cuentas verificadas: 21 de 21" in line for line in lines)

    old = passwords["operador-a-1"]
    assert demoSeed.run(args + ["--aplicar", "--regenerar-contrasenas"], out=lines.append) == 0
    fresh = inventory.readPasswords(private)
    assert fresh["operador-a-1"] != old
    stored = db.get(LocalCredential, C.demoId("credencial", "operador-a-1"))
    assert security.verifyPassword(fresh["operador-a-1"], stored.passwordHash)[0]
    assert not security.verifyPassword(old, stored.passwordHash)[0]


def test_cli_limpieza_dry_run_no_borra(db, engine, tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.session.getSessionFactory", lambda: sessionmaker(bind=engine, autoflush=False,
                                                                                 expire_on_commit=False))
    seeder.apply(db, seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords()))
    lines: list[str] = []
    assert demoSeed.run(["--limpiar"], out=lines.append) == 0
    assert countRows(db, User) == len(C.ACCOUNTS)
    assert any("Dry-run" in line for line in lines)


# --- Matrices, historial propio y clasificación de glucosa -------------------------------------------------------------


def _activeGlobalMatrix(db) -> uuid.UUID:
    from datetime import date

    from app.models.matrix import Matrix
    matrixId = uuid.uuid4()
    db.add(Matrix(idMatriz=matrixId, idInstitucion=None, nombre="Matriz de prueba", version="1", ambito="GLOBAL",
                  fechaVigenciaDesde=date(2020, 1, 1), fechaVigenciaHasta=None, descripcion=None, urlReferencia=None,
                  referenciaBase="Fuente de prueba", estado="ACTIVA", fechaCreacion=ANCHOR))
    db.commit()
    return matrixId


def test_glucosa_demo_referencia_la_matriz_activa_y_puede_clasificarse(db, engine):
    from app.services import glucoseReference
    matrixId = _activeGlobalMatrix(db)
    plan = seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords())
    assert not any("SIN_MATRIZ" in advertencia for advertencia in plan.advertencias)
    seeder.apply(db, plan)
    glucose = db.scalars(select(Measurement).where(Measurement.glucosaDispositivo.is_not(None))).all()
    assert glucose and all(row.idMatriz == matrixId for row in glucose)
    assert all(row.idMatriz is None for row in db.scalars(select(Measurement).where(
        Measurement.glucosaDispositivo.is_(None))).all())
    assert glucoseReference.build(db, glucose[0]).estado != "SIN_MATRIZ"


def test_sin_matriz_activa_la_carga_avisa_y_no_la_inventa(db):
    plan = seeder.buildPlan(db, anchor=ANCHOR, passwords=allPasswords())
    assert any("SIN_MATRIZ" in advertencia for advertencia in plan.advertencias)
    assert not plan.bloqueado


def test_individuo_ve_su_historial_propio_completadas_y_canceladas_se_ocultan(db, seeded):
    """Regla de la aplicación (services/measurementVisibility.py): CANCELADA e INVALIDA dejan el historial personal 30 minutos
    después de cerrarse; las COMPLETADAS permanecen. Por eso la vista personal muestra solo las completadas."""
    specs = dict(C.individualMeasurements())["individual-a"]
    completed = sum(1 for spec in specs if spec.estado == C.ESTADO_COMPLETADA)
    hidden = len(specs) - completed
    assert hidden == 2  # una cancelada y una inválida en la cuenta de la escena A
    page = measurements.listOwnHistory(db, actor(db, "individual-a"), tamanioPagina=50)
    assert page.total == completed
    assert all(item.estadoMedicion == "COMPLETADA" for item in page.items)
