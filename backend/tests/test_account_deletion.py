# Pruebas de la eliminación de cuenta propia (app/services/accountDeletion.py).
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_account_deletion.py -v
#
# Estas pruebas:
# - NO usan la base SQL Server real: recrean el esquema de los modelos en SQLite (archivos
#   temporales), con sus CHECK y claves foráneas activas;
# - NO envían correos reales (el envío SMTP se reemplaza por un registro en memoria).

import importlib
import json
import logging
import pkgutil
import re
import sqlite3
import uuid
from datetime import date, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import CheckConstraint, DefaultClause, MetaData, create_engine, event, select, text
from sqlalchemy.dialects.mssql import BIT, DATETIME2, TIME, TINYINT, UNIQUEIDENTIFIER
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

import app.models
import app.models.technicalAudit  # noqa: F401 - tabla anonimizada de auditoría técnica
from app.core import security
from app.core.config import getSettings
from app.core.exceptions import AuthError
from app.db.base import Base
from app.emails.formatting import maskEmail
from app.integrations.email import sender
from app.models.accountToken import AccountToken
from app.models.audit import Audit
from app.models.device import Device
from app.models.externalIdentity import ExternalIdentity
from app.models.group import Group
from app.models.groupUser import GroupUser
from app.models.institution import Institution
from app.models.institutionUser import InstitutionUser
from app.models.localCredential import LocalCredential
from app.models.measurement import Measurement
from app.models.measurementProfile import MeasurementProfile
from app.models.mfaFactor import MfaFactor
from app.models.mfaRecoveryCode import MfaRecoveryCode
from app.models.user import User
from app.models.userSession import UserSession
from app.services import accountDeletion as deletion
from app.services import auth as authService
from app.services import email as emailService
from app.services import mfa as mfaService
from app.utils.timeZone import nowForDb

PASSWORD = "Glucolume#Prueba2026"  # nosec B105 - contraseña de prueba
EMAIL = "victoria.prueba@example.com"


# --- Esquema SQL Server -> SQLite --------------------------------------------------------

for _module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_module.name}")


@compiles(UNIQUEIDENTIFIER, "sqlite")
def _uuidSqlite(type_, compiler, **kw):
    return "CHAR(32)"


@compiles(DATETIME2, "sqlite")
def _datetime2Sqlite(type_, compiler, **kw):
    return "DATETIME"


@compiles(BIT, "sqlite")
def _bitSqlite(type_, compiler, **kw):
    return "BOOLEAN"


@compiles(TINYINT, "sqlite")
def _tinyintSqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(TIME, "sqlite")
def _timeSqlite(type_, compiler, **kw):
    return "TIME"


def _sqliteCheck(sqltext: str) -> str:
    sqltext = re.sub(r"\bN'", "'", sqltext)
    # SQLite no admite date('now') en un CHECK: se usa una función registrada como determinística.
    return sqltext.replace("CONVERT([date],sysutcdatetime())", "todayDb()")


def _isJson(value) -> int:
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return 0
    return 1


# Tablas que involucran la eliminación de cuenta y la de institución; se agregan también las que referencian por FK.
TABLES = ("Usuario", "TokenCuenta", "Auditoria", "CredencialLocal", "IdentidadExterna", "FactorMfa",
          "CodigoRecuperacionMfa", "SesionUsuario", "Grupo", "GrupoUsuario", "Institucion", "InstitucionUsuario",
          "PerfilMedicion", "Medicion", "Dispositivo", "TransferenciaPerfil", "MuestraSensor",
          "MedicionReferenciaCapilar", "Matriz", "ReglaMatriz", "TransferenciaAdministracion", "EnvioResultado",
          "ConsentimientoUsuario", "AuditoriaTecnicaMedicion", "ReasignacionPaciente", "AuditoriaContexto", "PuenteCredencial",
          "PreferenciaNotificacion", "RecordatorioMedicion", "NotificacionUsuario")


def _withDependencies(names) -> set:
    pending, tables = [Base.metadata.tables[f"dbo.{name}"] for name in names], set()
    while pending:
        table = pending.pop()
        if table not in tables:
            tables.add(table)
            pending.extend(fk.column.table for fk in table.foreign_keys)
    return tables


def _sqliteMetadata() -> MetaData:
    """Copia del esquema de los modelos con CHECK y DEFAULT traducidos y sin columnas calculadas."""
    metadata = MetaData(schema="dbo")
    needed = _withDependencies(TABLES)
    for table in (t for t in Base.metadata.sorted_tables if t in needed):
        copy = table.to_metadata(metadata)
        for constraint in list(copy.constraints):
            if isinstance(constraint, CheckConstraint):
                constraint.sqltext = text(_sqliteCheck(str(constraint.sqltext)))
        for column in copy.columns:
            if column.computed is not None:
                column.computed = None
                column.server_default = None
            elif column.server_default is not None and "N'" in str(getattr(column.server_default, "arg", "")):  # FetchedValue: sin DDL
                column.server_default = DefaultClause(text(_sqliteCheck(str(column.server_default.arg))))
    return metadata


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("API_ENV", "test")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "GlucoLumeTest")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    # Las pruebas heredadas usan cuentas de plataforma sin MFA; tests/test_platform.py activa la política.
    monkeypatch.setenv("PLATFORM_MFA_REQUIRED", "false")
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")
    getSettings.cache_clear()

    dboPath = tmp_path / "dbo.sqlite"
    engine = create_engine(f"sqlite:///{tmp_path / 'main.sqlite'}")

    @event.listens_for(engine, "connect")
    def _connect(connection: sqlite3.Connection, record):
        connection.execute(f"ATTACH DATABASE '{dboPath}' AS dbo")
        connection.execute("PRAGMA dbo.foreign_keys = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.create_function("newid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("newsequentialid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("sysutcdatetime", 0, lambda: nowForDb().isoformat(" "))
        connection.create_function("isjson", 1, _isJson, deterministic=True)
        connection.create_function("todayDb", 0, lambda: nowForDb().date().isoformat(), deterministic=True)

    _sqliteMetadata().create_all(engine)
    yield engine
    engine.dispose()
    getSettings.cache_clear()


@pytest.fixture
def db(engine) -> Session:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def mails(monkeypatch, engine):
    """Reemplaza SMTP. Cada envío registra si, en ese momento, la cuenta ya estaba confirmada en la base."""
    sent = []

    class InlineExecutor:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    def fakeSend(recipient, subject, html, plainText, inlineImages=(), replyTo=None):
        # Conexión independiente: solo ve lo confirmado (COMMIT) por el servicio.
        with engine.connect() as connection:
            committed = {
                "tokens": connection.execute(text("SELECT tipo, fechaUso FROM dbo.TokenCuenta")).all(),
                "estados": connection.execute(text("SELECT estado FROM dbo.Usuario")).scalars().all(),
            }
        sent.append({"to": recipient, "subject": subject, "html": html, "text": plainText, "replyTo": replyTo,
                     "committed": committed})

    monkeypatch.setattr(sender, "sendHtmlEmail", fakeSend)
    monkeypatch.setattr(emailService, "_executor", InlineExecutor())
    return sent


# --- Datos de prueba ---------------------------------------------------------------------


def makeUser(db, tipoCuenta="CONSUMIDOR_FINAL", local=True, google=False, email=EMAIL, usuario="victoria",
             consent=True) -> User:
    """`consent=True`: persona que ya confirmó la política y autorizó sus mediciones experimentales (como quien terminó
    el alta). Los tests de consentimiento usan consent=False."""
    user = User(
        idUsuario=uuid.uuid4(), nombre="Victoria", apellido="Cortés", correoElectronico=email, usuario=usuario,
        tipoCuenta=tipoCuenta, estado="ACTIVO", fechaNacimiento=date(1990, 5, 17), sexo="FEMENINO",
    )
    db.add(user)
    db.flush()
    if local:
        db.add(LocalCredential(idUsuario=user.idUsuario, passwordHash=security.hashPassword(PASSWORD)))
    if google:
        db.add(ExternalIdentity(idUsuario=user.idUsuario, proveedor="GOOGLE", subjectProveedor=f"sub-{user.idUsuario}",
                                emailProveedor=email, emailVerificado=True))
    if consent:
        from app.models.consent import TipoConsentimiento
        from app.services import consent as consentService

        consentService.record(db, user, TipoConsentimiento.POLITICA_PRIVACIDAD, True)
        consentService.record(db, user, TipoConsentimiento.DATOS_EXPERIMENTALES, True)
    db.commit()
    return user


def makeSession(db, user) -> UserSession:
    session = UserSession(idUsuario=user.idUsuario, refreshTokenHash=security.hashOpaqueToken(uuid.uuid4().hex),
                          fechaExpiracion=nowForDb() + timedelta(days=7))
    db.add(session)
    db.commit()
    return session


def enableMfa(db, user) -> str:
    secret, _ = mfaService.startSetup(db, user)
    factor = mfaService.getFactor(db, user)
    factor.habilitado = True
    factor.fechaConfirmacion = nowForDb()
    db.add(MfaRecoveryCode(idFactorMfa=factor.idFactorMfa, codigoHash=security.hashRecoveryCode("ABCD-EFGH")))
    db.commit()
    return secret


def totpCode(secret: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


def addGroup(db, user, rolGrupo="MIEMBRO", estadoGrupo="ACTIVO", estadoRelacion="ACTIVO") -> GroupUser:
    group = Group(idGrupo=uuid.uuid4(), nombre="Familia", estado=estadoGrupo)
    db.add(group)
    db.flush()
    relation = GroupUser(
        idGrupo=group.idGrupo, idUsuario=user.idUsuario, rolGrupo=rolGrupo, estadoRelacion=estadoRelacion,
        fechaIncorporacion=nowForDb(), fechaBaja=nowForDb() if estadoRelacion == "BAJA" else None,
    )
    db.add(relation)
    db.commit()
    return relation


def addInstitution(db, user, rol="OPERADOR", estadoRelacion="ACTIVO", matricula="MP-1234") -> InstitutionUser:
    institution = Institution(idInstitucion=uuid.uuid4(), identificadorLegal=uuid.uuid4().hex[:11],
                              nombre="Clínica", tipoInstitucion="CLINICA")
    db.add(institution)
    db.flush()
    relation = InstitutionUser(
        idInstitucionUsuario=uuid.uuid4(), idInstitucion=institution.idInstitucion, idUsuarioInvitado=user.idUsuario,
        rolInstitucion=rol, matriculaProfesional=matricula, estadoRelacion=estadoRelacion,
        origenVinculo="CREACION_INSTITUCION", fechaIncorporacion=nowForDb(),
        fechaBaja=nowForDb() if estadoRelacion == "BAJA" else None,
    )
    db.add(relation)
    db.commit()
    return relation


def addMeasurement(db, user) -> tuple[MeasurementProfile, Measurement]:
    profile = MeasurementProfile(
        idPerfilMedicion=uuid.uuid4(), tipoPerfil="CONSUMIDOR_FINAL", idUsuario=user.idUsuario,
        nombre="Victoria", apellido="Cortés", dni="30111222", fechaNacimiento=date(1990, 5, 17), sexoModelo="FEMENINO",
    )
    device = Device(idDispositivo=uuid.uuid4(), codigoDispositivo=uuid.uuid4().hex, modeloSensor="MAX30102")
    db.add_all([profile, device])
    db.flush()
    measurement = Measurement(
        idMedicion=uuid.uuid4(), idPerfilMedicion=profile.idPerfilMedicion, idDispositivo=device.idDispositivo,
        modoMedicion="OXIMETRIA", estadoMedicion="COMPLETADA", edadAlMomento=36, sexoModelo="FEMENINO",
        condicionComida="POSTPRANDIAL", fechaHoraInicio=nowForDb() - timedelta(days=3),
        fechaHoraUltimaComida=nowForDb() - timedelta(days=3, hours=2), spo2=97, frecuenciaCardiaca=72,
        modeloSensorAlMomento="MAX30102",
    )
    db.add(measurement)
    db.commit()
    return profile, measurement


def tokenFrom(mail) -> str:
    match = re.search(r"/cuenta/eliminar/confirmar\?token=([A-Za-z0-9_\-]+)", mail["text"] + mail["html"])
    assert match, "El correo debe incluir el enlace de confirmación con el token."
    return match.group(1)


def requestAndGetToken(db, user, mails) -> str:
    deletion.requestDeletion(db, user)
    return tokenFrom(mails[-1])


def confirm(db, token, password=PASSWORD, **kwargs):
    """Paso 2 con la contraseña de prueba por defecto (password=None para cuentas sin contraseña local)."""
    return deletion.confirmDeletion(db, token, password, **kwargs)


def tokenRow(db) -> AccountToken:
    db.expire_all()
    return db.scalar(select(AccountToken).where(AccountToken.tipo == "ELIMINAR_CUENTA"))


def audits(db, accion=None) -> list[Audit]:
    query = select(Audit).order_by(Audit.fechaHora)
    if accion:
        query = query.where(Audit.accion == accion)
    return list(db.scalars(query))


def reload(db, model, key):
    db.expire_all()
    return db.get(model, key)


# --- Solicitud -----------------------------------------------------------------------------


def test_solicitud_valida_consumidor_final_token_30_minutos(db, mails):
    user = makeUser(db)
    before = nowForDb()

    result = deletion.requestDeletion(db, user)

    token = db.scalar(select(AccountToken).where(AccountToken.tipo == "ELIMINAR_CUENTA"))
    assert token.fechaUso is None
    assert token.fechaExpiracion - token.fechaCreacion == timedelta(minutes=30)
    assert token.fechaCreacion >= before - timedelta(seconds=1)
    assert result.vigenciaMinutos == 30 and result.fechaExpiracion == token.fechaExpiracion
    # Solo se guarda el hash: el token del enlace es el que corresponde a ese hash.
    plain = tokenFrom(mails[0])
    assert token.tokenHash == security.hashOpaqueToken(plain) and token.tokenHash != plain
    assert mails[0]["to"] == EMAIL and mails[0]["subject"] == "Solicitud de eliminación de cuenta"
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"


def test_nueva_solicitud_invalida_token_anterior(db, mails):
    user = makeUser(db)
    first = requestAndGetToken(db, user, mails)
    second = requestAndGetToken(db, user, mails)

    pending = db.scalars(select(AccountToken).where(AccountToken.tipo == "ELIMINAR_CUENTA")).all()
    assert [t.tokenHash for t in pending] == [security.hashOpaqueToken(second)]
    with pytest.raises(AuthError) as error:
        confirm(db, first)
    assert error.value.code == "TOKEN_INVALIDO"


def test_solicitud_no_pide_password_ni_mfa_y_no_elimina(db, mails):
    user = makeUser(db, google=True)
    enableMfa(db, user)
    session = makeSession(db, user)

    result = deletion.requestDeletion(db, user)

    assert result.vigenciaMinutos == 30 and len(mails) == 1
    db.expire_all()
    stored = db.get(User, user.idUsuario)
    assert stored.estado == "ACTIVO" and stored.correoElectronico == EMAIL and stored.fechaEliminacion is None
    assert db.get(UserSession, session.idSesion).fechaRevocacion is None
    for model in (LocalCredential, ExternalIdentity, MfaFactor):
        assert db.scalars(select(model)).all(), model.__tablename__
    assert tokenRow(db).fechaUso is None
    assert audits(db, "ELIMINACION_CUENTA") == []


# --- Confirmación: reautenticación -------------------------------------------------------


def test_confirmacion_password_correcta_e_incorrecta(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)

    with pytest.raises(AuthError) as missing:
        confirm(db, token, password=None)
    assert missing.value.code == "PASSWORD_REQUERIDA"

    with pytest.raises(AuthError) as wrong:
        confirm(db, token, password="OtraClave#2026")
    assert wrong.value.code == "PASSWORD_INCORRECTA"
    assert db.scalar(select(LocalCredential)).intentosFallidosConsecutivos == 1
    fail = audits(db, "ELIMINACION_CUENTA")[-1]
    assert json.loads(fail.datosNuevos) == {"etapa": "CONFIRMACION", "motivo": "PASSWORD_INCORRECTA"}
    # Un error de reautenticación no consume el token ni elimina la cuenta.
    assert tokenRow(db).fechaUso is None
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"

    confirm(db, token)
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_password_incorrecta_reiterada_bloquea_como_el_login(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    for _ in range(3):
        with pytest.raises(AuthError):
            confirm(db, token, password="OtraClave#2026")

    with pytest.raises(AuthError) as locked:
        confirm(db, token)
    assert locked.value.code == "CUENTA_BLOQUEADA"
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"


def test_confirmacion_sin_mfa_no_pide_codigo(db, mails):
    user = makeUser(db)
    confirm(db, requestAndGetToken(db, user, mails))
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_confirmacion_con_mfa_totp(db, mails):
    user = makeUser(db)
    secret = enableMfa(db, user)
    token = requestAndGetToken(db, user, mails)

    with pytest.raises(AuthError) as missing:
        confirm(db, token)
    assert missing.value.code == "CODIGO_MFA_REQUERIDO"
    with pytest.raises(AuthError) as wrong:
        confirm(db, token, codigo="000000")
    assert wrong.value.code == "CODIGO_INVALIDO"
    assert tokenRow(db).fechaUso is None and reload(db, User, user.idUsuario).estado == "ACTIVO"

    confirm(db, token, codigo=totpCode(secret))
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_confirmacion_con_codigo_de_recuperacion(db, mails):
    user = makeUser(db)
    enableMfa(db, user)
    token = requestAndGetToken(db, user, mails)

    with pytest.raises(AuthError) as wrong:
        confirm(db, token, codigoRecuperacion="ZZZZ-ZZZZ")
    assert wrong.value.code == "CODIGO_INVALIDO"

    confirm(db, token, codigoRecuperacion="ABCD-EFGH")
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_rechaza_codigo_y_recuperacion_juntos(db, mails):
    from pydantic import ValidationError

    from app.schemas.auth import AccountDeletionConfirmRequest

    with pytest.raises(ValidationError) as schemaError:
        AccountDeletionConfirmRequest(token="t", password=PASSWORD, codigo="123456", codigoRecuperacion="ABCD-EFGH")
    assert "solo uno" in str(schemaError.value)

    # Segunda barrera en el servicio.
    user = makeUser(db)
    secret = enableMfa(db, user)
    token = requestAndGetToken(db, user, mails)
    with pytest.raises(AuthError) as error:
        confirm(db, token, codigo=totpCode(secret), codigoRecuperacion="ABCD-EFGH")
    assert error.value.code == "FACTOR_MFA_DUPLICADO"
    assert tokenRow(db).fechaUso is None and reload(db, User, user.idUsuario).estado == "ACTIVO"


def test_cuenta_solo_google_sin_password_local(db, mails):
    user = makeUser(db, local=False, google=True)
    token = requestAndGetToken(db, user, mails)

    confirm(db, token, password=None)

    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"
    assert db.scalars(select(ExternalIdentity)).all() == []


def test_cuenta_solo_google_con_mfa(db, mails):
    user = makeUser(db, local=False, google=True)
    secret = enableMfa(db, user)
    token = requestAndGetToken(db, user, mails)

    with pytest.raises(AuthError) as missing:
        confirm(db, token, password=None)
    assert missing.value.code == "CODIGO_MFA_REQUERIDO"

    confirm(db, token, password=None, codigo=totpCode(secret))
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


# --- Token -------------------------------------------------------------------------------


def test_token_invalido(db, mails):
    makeUser(db)
    with pytest.raises(AuthError) as error:
        confirm(db, "no-existe")
    assert error.value.code == "TOKEN_INVALIDO"
    fail = audits(db, "ELIMINACION_CUENTA")[-1]
    assert fail.resultado == "FALLO" and fail.idUsuario is None
    assert json.loads(fail.datosNuevos) == {"etapa": "CONFIRMACION", "motivo": "TOKEN_INVALIDO"}


def test_token_vencido_se_audita_una_sola_vez(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    stored = db.scalar(select(AccountToken))
    stored.fechaCreacion = nowForDb() - timedelta(minutes=45)
    stored.fechaExpiracion = nowForDb() - timedelta(minutes=15)
    db.commit()

    for _ in range(2):
        with pytest.raises(AuthError) as error:
            confirm(db, token)
        assert error.value.code == "TOKEN_VENCIDO"

    fails = [a for a in audits(db, "ELIMINACION_CUENTA") if a.resultado == "FALLO"]
    assert len(fails) == 1 and json.loads(fails[0].datosNuevos)["motivo"] == "TOKEN_VENCIDO"
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"


def test_no_permite_confirmar_dos_veces(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    confirm(db, token)

    with pytest.raises(AuthError) as error:
        confirm(db, token)
    assert error.value.code == "TOKEN_YA_UTILIZADO"
    fail = audits(db, "ELIMINACION_CUENTA")[-1]
    assert fail.resultado == "FALLO" and json.loads(fail.datosNuevos)["motivo"] == "TOKEN_YA_UTILIZADO"


# --- Consumidor final y grupos -----------------------------------------------------------


def test_consumidor_sin_grupo_eliminacion_completa(db, mails):
    user = makeUser(db, google=True)
    enableMfa(db, user)
    session = makeSession(db, user)
    token = requestAndGetToken(db, user, mails)

    confirm(db, token, codigoRecuperacion="ABCD-EFGH")

    deleted = reload(db, User, user.idUsuario)
    assert deleted.idUsuario == user.idUsuario
    assert deleted.estado == "ELIMINADO" and deleted.fechaEliminacion is not None
    assert (deleted.nombre, deleted.apellido, deleted.correoElectronico, deleted.usuario,
            deleted.fechaNacimiento, deleted.sexo) == (None,) * 6
    assert deleted.tipoCuenta == "CONSUMIDOR_FINAL"


def test_credenciales_y_sesiones_revocadas(db, mails):
    user = makeUser(db, google=True)
    enableMfa(db, user)
    sessions = [makeSession(db, user), makeSession(db, user)]
    token = requestAndGetToken(db, user, mails)

    confirm(db, token, codigoRecuperacion="ABCD-EFGH")
    db.expire_all()

    for model in (LocalCredential, ExternalIdentity, MfaFactor, MfaRecoveryCode):
        assert db.scalars(select(model)).all() == [], model.__tablename__
    for session in sessions:
        assert db.get(UserSession, session.idSesion).fechaRevocacion is not None
    # Solo queda el token de esta eliminación, consumido.
    remaining = db.scalars(select(AccountToken)).all()
    assert len(remaining) == 1 and remaining[0].fechaUso is not None

    # La cuenta no puede volver a autenticarse.
    with pytest.raises(AuthError) as login:
        authService.loginLocal(db, EMAIL, PASSWORD)
    assert login.value.code == "CREDENCIALES_INVALIDAS"
    with pytest.raises(AuthError):
        authService.loginLocal(db, "victoria", PASSWORD)
    claims = {"sub": str(user.idUsuario), "sid": str(sessions[0].idSesion)}
    with pytest.raises(AuthError):
        authService.resolveAccessSession(db, claims)


def test_consumidor_miembro_normal_sale_del_grupo(db, mails):
    user = makeUser(db)
    # Un solo grupo ACTIVO por cuenta (UX_GrupoUsuario_grupoActivo, 010): el resto son invitaciones pendientes.
    member = addGroup(db, user, "MIEMBRO")
    moderator = addGroup(db, user, "MODERADOR", estadoRelacion="PENDIENTE")
    pending = addGroup(db, user, "MIEMBRO", estadoRelacion="PENDIENTE")
    token = requestAndGetToken(db, user, mails)

    confirm(db, token)
    db.expire_all()

    for relation in (member, moderator, pending):
        stored = db.get(GroupUser, relation.idGrupoUsuario)
        assert stored is not None, "La relación no se borra físicamente."
        assert stored.estadoRelacion == "BAJA" and stored.fechaBaja is not None
    assert db.get(User, user.idUsuario).estado == "ELIMINADO"
    ok = audits(db, "ELIMINACION_CUENTA")[-1]
    assert json.loads(ok.datosNuevos)["gruposAbandonados"] == 3


def test_consumidor_propietario_de_grupo_bloqueado(db, mails):
    user = makeUser(db)
    addGroup(db, user, "PROPIETARIO")

    with pytest.raises(AuthError) as error:
        deletion.requestDeletion(db, user)

    assert error.value.code == "PROPIETARIO_GRUPO_ACTIVO"
    assert "transferir la administración" in error.value.message
    assert db.scalar(select(AccountToken)) is None and not mails
    fail = audits(db, "ELIMINACION_CUENTA")[-1]
    assert json.loads(fail.datosNuevos) == {"etapa": "SOLICITUD", "motivo": "PROPIETARIO_GRUPO_ACTIVO"}


def test_propietario_de_grupo_cerrado_puede_eliminar(db, mails):
    user = makeUser(db)
    addGroup(db, user, "PROPIETARIO", estadoGrupo="CERRADO")
    confirm(db, requestAndGetToken(db, user, mails))
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_confirmacion_revalida_reglas(db, mails):
    """La situación puede cambiar en los 30 minutos: si pasó a ser propietario, se bloquea al confirmar."""
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    ownership = addGroup(db, user, "PROPIETARIO")

    with pytest.raises(AuthError) as error:
        confirm(db, token)

    assert error.value.code == "PROPIETARIO_GRUPO_ACTIVO"
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"
    fail = audits(db, "ELIMINACION_CUENTA")[-1]
    assert json.loads(fail.datosNuevos) == {"etapa": "CONFIRMACION", "motivo": "PROPIETARIO_GRUPO_ACTIVO"}
    assert len(mails) == 1, "No se envía CUENTA_ELIMINADA."
    assert tokenRow(db).fechaUso is None, "El bloqueo no consume el token."

    # Resuelto el bloqueo dentro de los 30 minutos, el mismo enlace sirve.
    relation = db.get(GroupUser, ownership.idGrupoUsuario)
    relation.estadoRelacion, relation.fechaBaja = "BAJA", nowForDb()
    db.commit()
    confirm(db, token)
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


def test_confirmacion_revalida_vinculo_institucional(db, mails):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    token = requestAndGetToken(db, user, mails)
    addInstitution(db, user, "OPERADOR")

    with pytest.raises(AuthError) as error:
        confirm(db, token)
    assert error.value.code == "VINCULO_INSTITUCIONAL_ACTIVO"
    assert reload(db, User, user.idUsuario).estado == "ACTIVO"


# --- Institucional -----------------------------------------------------------------------


def test_institucional_sin_vinculos_activos_puede_eliminar(db, mails):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    addInstitution(db, user, "MODERADOR", estadoRelacion="BAJA")
    confirm(db, requestAndGetToken(db, user, mails))
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"


@pytest.mark.parametrize("rol", ["OPERADOR", "MODERADOR"])
def test_operador_o_moderador_activo_bloqueado(db, mails, rol):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    relation = addInstitution(db, user, rol)

    with pytest.raises(AuthError) as error:
        deletion.requestDeletion(db, user)

    assert error.value.code == "VINCULO_INSTITUCIONAL_ACTIVO"
    assert error.value.message == deletion.ACTIVE_BONDS_MESSAGE
    assert "finalizar tus vinculaciones institucionales" in error.value.message
    assert db.scalar(select(AccountToken)) is None and not mails
    # Auth nunca desvincula automáticamente una relación institucional.
    assert reload(db, InstitutionUser, relation.idInstitucionUsuario).estadoRelacion == "ACTIVO"


def test_propietario_institucion_activo_bloqueado(db, mails):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    addInstitution(db, user, "PROPIETARIO")

    with pytest.raises(AuthError) as error:
        deletion.requestDeletion(db, user)

    assert error.value.code == "PROPIETARIO_INSTITUCION_ACTIVA"
    assert error.value.message == deletion.ACTIVE_BONDS_MESSAGE
    assert db.scalar(select(AccountToken)) is None


def test_multiples_instituciones_una_activa_bloqueado(db, mails):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    addInstitution(db, user, "OPERADOR", estadoRelacion="BAJA")
    addInstitution(db, user, "OPERADOR", estadoRelacion="BAJA")
    addInstitution(db, user, "OPERADOR", estadoRelacion="ACTIVO")

    with pytest.raises(AuthError) as error:
        deletion.requestDeletion(db, user)
    assert error.value.code == "VINCULO_INSTITUCIONAL_ACTIVO"


def test_operador_historico_conserva_identidad_profesional(db, mails):
    user = makeUser(db, tipoCuenta="USUARIO_INSTITUCIONAL")
    past = addInstitution(db, user, "OPERADOR", estadoRelacion="BAJA", matricula="MP-1234")
    alreadySet = addInstitution(db, user, "OPERADOR", estadoRelacion="BAJA", matricula="MN-9")
    alreadySet.nombreProfesionalHistorico = "Vicky"
    db.commit()

    confirm(db, requestAndGetToken(db, user, mails))
    db.expire_all()

    stored = db.get(InstitutionUser, past.idInstitucionUsuario)
    assert (stored.nombreProfesionalHistorico, stored.apellidoProfesionalHistorico) == ("Victoria", "Cortés")
    assert stored.matriculaProfesional == "MP-1234" and stored.estadoRelacion == "BAJA"
    assert stored.idUsuarioInvitado == user.idUsuario
    # Un valor histórico ya cargado no se pisa.
    kept = db.get(InstitutionUser, alreadySet.idInstitucionUsuario)
    assert (kept.nombreProfesionalHistorico, kept.apellidoProfesionalHistorico) == ("Vicky", "Cortés")
    assert db.get(User, user.idUsuario).nombre is None


def test_cuenta_de_plataforma_no_se_autoelimina(db, mails):
    user = makeUser(db, tipoCuenta="ADMINISTRADOR_PLATAFORMA")
    with pytest.raises(AuthError) as error:
        deletion.requestDeletion(db, user)
    assert error.value.code == "TIPO_CUENTA_NO_ELIMINABLE"


# --- Histórico de mediciones -------------------------------------------------------------


def test_mediciones_conservadas_y_perfil_anonimizado(db, mails):
    user = makeUser(db)
    profile, measurement = addMeasurement(db, user)

    confirm(db, requestAndGetToken(db, user, mails))
    db.expire_all()

    stored = db.get(Measurement, measurement.idMedicion)
    assert stored is not None and stored.idPerfilMedicion == profile.idPerfilMedicion
    assert (stored.edadAlMomento, stored.sexoModelo, stored.condicionComida) == (36, "FEMENINO", "POSTPRANDIAL")
    assert stored.fechaHoraUltimaComida is not None and stored.spo2 == 97 and stored.idDispositivo is not None
    assert stored.modeloSensorAlMomento == "MAX30102" and stored.estadoMedicion == "COMPLETADA"

    perfil = db.get(MeasurementProfile, profile.idPerfilMedicion)
    assert perfil.idUsuario == user.idUsuario, "La FK al Usuario conservado no se rompe."
    assert (perfil.nombre, perfil.apellido, perfil.dni, perfil.fechaNacimiento, perfil.edadDeclarada) == (None,) * 5
    assert perfil.fechaDepuracionDatosPersonales is not None and perfil.sexoModelo == "FEMENINO"
    # El correo informa qué se conserva desidentificado.
    assert "Edad al momento de cada medición" in mails[-1]["text"]


# --- Auditoría ---------------------------------------------------------------------------


def test_auditoria_solicitud_y_exito_sin_datos_sensibles(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    confirm(db, token)

    request = audits(db, "SOLICITUD_ELIMINACION_CUENTA")
    assert len(request) == 1
    assert (request[0].tipoEvento, request[0].resultado, request[0].tablaAfectada, request[0].idRegistro) == (
        "CRUD", "EXITO", "Usuario", user.idUsuario)
    assert json.loads(request[0].datosNuevos) == {
        "solicitud": "GENERADA", "confirmacionRequerida": True, "vigenciaMinutos": 30}

    success = audits(db, "ELIMINACION_CUENTA")
    assert len(success) == 1
    assert (success[0].tipoEvento, success[0].resultado, success[0].idRegistro) == ("CRUD", "EXITO", user.idUsuario)
    data = json.loads(success[0].datosNuevos)
    assert data["estadoAnterior"] == "ACTIVO" and data["estadoNuevo"] == "ELIMINADO"
    assert data["datosPersonales"] == "ANONIMIZADOS" and data["autenticacion"] == "REVOCADA"

    # Solo dos acciones para todo el flujo y ningún dato sensible en la auditoría.
    flow = {a.accion for a in audits(db)} - {"REGISTRO_LOCAL"}
    assert flow == {"SOLICITUD_ELIMINACION_CUENTA", "ELIMINACION_CUENTA"}
    stored = db.scalar(select(AccountToken))
    for audit in audits(db):
        dump = " ".join(str(v) for v in (audit.datosPrevios, audit.datosNuevos, audit.observacion, audit.detalle))
        for secret in (token, stored.tokenHash, EMAIL, PASSWORD, "Victoria", "Cortés", "victoria"):
            assert secret not in dump


# --- Correos -----------------------------------------------------------------------------


def test_correos_se_envian_despues_del_commit(db, mails):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)
    # ELIMINACION_SOLICITADA: el token ya estaba confirmado cuando se envió el correo.
    assert mails[0]["committed"]["tokens"] and mails[0]["committed"]["tokens"][0][0] == "ELIMINAR_CUENTA"

    confirm(db, token)
    # CUENTA_ELIMINADA: la baja ya estaba confirmada y el destinatario es el correo previo a anonimizar.
    final = mails[1]
    assert final["subject"] == "Tu cuenta de GlucoLume fue eliminada"
    assert final["to"] == EMAIL and final["committed"]["estados"] == ["ELIMINADO"]
    assert token not in final["html"]


def test_fallo_smtp_no_revierte_eliminacion_y_log_enmascarado(db, mails, monkeypatch, caplog):
    user = makeUser(db)
    token = requestAndGetToken(db, user, mails)

    def smtpDown(*args, **kwargs):
        raise OSError("SMTP caído")

    monkeypatch.setattr(sender, "sendHtmlEmail", smtpDown)
    with caplog.at_level(logging.INFO):
        confirm(db, token)

    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"
    assert audits(db, "ELIMINACION_CUENTA")[-1].resultado == "EXITO"
    assert "CUENTA_ELIMINADA" in caplog.text and maskEmail(EMAIL) in caplog.text
    assert EMAIL not in caplog.text and token not in caplog.text


def test_log_de_solicitud_enmascarado(db, mails, caplog):
    user = makeUser(db)
    with caplog.at_level(logging.INFO):
        token = requestAndGetToken(db, user, mails)
    assert f"Correo ELIMINACION_SOLICITADA enviado a {maskEmail(EMAIL)}" in caplog.text
    assert EMAIL not in caplog.text and token not in caplog.text
    assert security.hashOpaqueToken(token) not in caplog.text


def test_fallo_sql_hace_rollback_completo(db, mails, monkeypatch):
    user = makeUser(db)
    addGroup(db, user, "MIEMBRO")
    token = requestAndGetToken(db, user, mails)

    from sqlalchemy.exc import OperationalError

    def broken(*args, **kwargs):
        raise OperationalError("UPDATE", {}, Exception("falla simulada"))

    original = deletion._anonymizeMeasurementProfiles
    monkeypatch.setattr(deletion, "_anonymizeMeasurementProfiles", broken)
    with pytest.raises(OperationalError):
        confirm(db, token)

    db.expire_all()
    stored = db.get(User, user.idUsuario)
    assert stored.estado == "ACTIVO" and stored.correoElectronico == EMAIL
    assert db.scalar(select(GroupUser)).estadoRelacion == "ACTIVO"
    assert db.scalar(select(AccountToken)).fechaUso is None, "El token no queda consumido."
    assert len(mails) == 1
    # Corregida la falla, el mismo enlace sigue siendo válido. Se restaura solo esta función: undo()
    # también desharía el SMTP simulado del fixture mails y el correo saldría por el servidor real.
    monkeypatch.setattr(deletion, "_anonymizeMeasurementProfiles", original)
    confirm(db, token)
    assert reload(db, User, user.idUsuario).estado == "ELIMINADO"
    assert [mail["subject"] for mail in mails][-1] == "Tu cuenta de GlucoLume fue eliminada"


def test_cuenta_ya_eliminada_no_vuelve_a_procesarse(db, mails):
    user = makeUser(db)
    first = requestAndGetToken(db, user, mails)
    # Un segundo token emitido antes de confirmar el primero queda invalidado por la nueva solicitud;
    # aquí se fuerza un token pendiente sobre una cuenta ya eliminada.
    confirm(db, first)
    orphan = security.generateOpaqueToken()
    db.add(AccountToken(idUsuario=user.idUsuario, tipo="ELIMINAR_CUENTA", tokenHash=security.hashOpaqueToken(orphan),
                        fechaCreacion=nowForDb(), fechaExpiracion=nowForDb() + timedelta(minutes=30)))
    db.commit()

    with pytest.raises(AuthError) as error:
        confirm(db, orphan)
    assert error.value.code == "CUENTA_NO_ACTIVA"
    assert len(mails) == 2



def test_harness_aplica_check_y_claves_foraneas(db):
    """Control del entorno de prueba: las CHECK y FK del esquema se aplican de verdad."""
    from sqlalchemy.exc import IntegrityError

    user = makeUser(db)
    user.estado = "ELIMINADO"  # sin fechaEliminacion: viola CK_Usuario_eliminacion
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(GroupUser(idGrupo=uuid.uuid4(), idUsuario=user.idUsuario, estadoRelacion="PENDIENTE"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(AccountToken(idUsuario=user.idUsuario, tipo="OTRO", tokenHash="x",
                        fechaCreacion=nowForDb(), fechaExpiracion=nowForDb() + timedelta(minutes=1)))
    with pytest.raises(IntegrityError):
        db.commit()


# --- Inicio de sesión por correo o username ----------------------------------------------


@pytest.mark.parametrize("identificador", [EMAIL, "victoria", f"  {EMAIL}  ", "  victoria  "])
def test_login_con_correo_o_username(db, mails, identificador):
    makeUser(db)
    response = authService.loginLocal(db, identificador, PASSWORD)
    assert response.estado == "AUTENTICADO" and response.tokens is not None


@pytest.mark.parametrize("identificador", [EMAIL, "victoria"])
def test_login_con_correo_o_username_y_password_incorrecta(db, mails, identificador):
    makeUser(db)
    with pytest.raises(AuthError) as error:
        authService.loginLocal(db, identificador, "OtraClave#2026")
    assert error.value.code == "CREDENCIALES_INVALIDAS"


# --- Contrato HTTP (OpenAPI) -------------------------------------------------------------


def test_openapi_solicitud_sin_body_y_confirmacion_con_reautenticacion(engine):
    from app.api.v1.auth import router

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    paths = app.openapi()["paths"]

    request = paths["/api/v1/auth/account-deletion/request"]["post"]
    assert "requestBody" not in request
    assert request["security"] == [{"HTTPBearer": []}], "Requiere sesión (Bearer)."
    assert "security" not in paths["/api/v1/auth/account-deletion/confirm"]["post"], "El token identifica la cuenta."
    assert "202" in request["responses"]

    body = paths["/api/v1/auth/account-deletion/confirm"]["post"]["requestBody"]["content"]["application/json"]
    examples = body["examples"]
    assert {"sinMfa", "conTotp", "conRecuperacion", "soloGoogle"} <= set(examples)
    for example in examples.values():
        assert "token" in example["value"]
        assert not {"codigo", "codigoRecuperacion"} <= set(example["value"])
    schema = app.openapi()["components"]["schemas"]["AccountDeletionConfirmRequest"]
    assert set(schema["properties"]) == {"token", "password", "codigo", "codigoRecuperacion"}
    assert schema["required"] == ["token"]
