# Configuración de seguridad: STARTTLS con certificado verificado (GL-04), claves MFA anteriores y duplicadas (GL-06) y advertencias de
# configuración (GL-07, GL-10). Sin red, sin SMTP real y sin la base real: SQLite temporal y archivos .env temporales.
#
#     python -m pytest tests/test_security_config.py -v

import smtplib
import ssl
from email.message import EmailMessage

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.cli import mfaKeys
from app.core import security
from app.core.config import Settings, duplicatedEnvKeys, getSettings
from app.integrations.email import sender
from app.models.mfaFactor import MfaFactor
from tests.test_account_deletion import db, engine, makeUser, mails  # noqa: F401 - fixtures

# _env_file=None: estas pruebas no leen el .env real del equipo (GL-12).
BASE = {"_env_file": None, "DB_HOST": "localhost", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "JWT_SECRET": "j" * 40}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.context = host, port, None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.context = context

    def login(self, user, password):
        pass

    def send_message(self, message):
        self.sent = message


def test_starttls_verifica_el_certificado_y_el_nombre_del_servidor(monkeypatch):
    for name, value in {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USERNAME": "u@example.com", "SMTP_PASSWORD": "x"}.items():
        monkeypatch.setenv(name, value)
    getSettings.cache_clear()
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    message = EmailMessage()
    message["To"] = "destino@example.com"
    sender._send(message)
    [server] = FakeSMTP.instances
    assert server.host == "smtp.example.com"  # smtplib usa este nombre como server_hostname al verificar
    context = server.context
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_un_certificado_rechazado_se_informa_como_falla_de_conexion_segura():
    assert sender.tlsContext().verify_mode == ssl.CERT_REQUIRED
    error = ssl.SSLCertVerificationError("certificate verify failed")
    assert isinstance(error, ssl.SSLError)  # el remitente lo clasifica como error de TLS, nunca lo ignora


def test_la_clave_anterior_sigue_descifrando_y_se_puede_recifrar(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", old)
    getSettings.cache_clear()
    stored = security.encryptTotpSecret("JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", new)
    monkeypatch.setenv("MFA_PREVIOUS_ENCRYPTION_KEYS", old)
    getSettings.cache_clear()
    assert security.decryptTotpSecret(stored) == "JBSWY3DPEHPK3PXP"  # nadie pierde el MFA al cambiar la clave vigente
    rotated = security.reencryptTotpSecret(stored)
    monkeypatch.delenv("MFA_PREVIOUS_ENCRYPTION_KEYS")
    getSettings.cache_clear()
    assert security.decryptTotpSecret(rotated) == "JBSWY3DPEHPK3PXP"
    with pytest.raises(RuntimeError):
        security.decryptTotpSecret(stored)  # sin la clave anterior, lo no re-cifrado ya no se descifra


def test_el_diagnostico_dice_que_clave_descifra_los_factores_sin_mostrarla(db, mails, tmp_path, monkeypatch):
    good, other = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    env = tmp_path / ".env"
    env.write_text(f"API_ENV=development\nMFA_ENCRYPTION_KEY={good}\nX=1\nMFA_ENCRYPTION_KEY={other}\n", encoding="utf-8")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", other)  # la que queda vigente (la última), como en el .env real
    getSettings.cache_clear()
    user = makeUser(db, email="mfa@example.com", usuario="mfa")
    db.add(MfaFactor(idUsuario=user.idUsuario, secretoCifrado=Fernet(good.encode()).encrypt(b"JBSWY3DPEHPK3PXP").decode(), habilitado=False))
    db.commit()
    rows = {row["origen"]: row for row in mfaKeys.report(db, mfaKeys.candidates(env))}
    assert rows[".env línea 2"]["descifra"] == 1 and rows[".env línea 2"]["total"] == 1
    assert rows[".env línea 4 = clave vigente (la que usa la aplicación)"]["descifra"] == 0
    assert good not in repr(rows) and other not in repr(rows)  # solo huellas
    monkeypatch.setenv("MFA_PREVIOUS_ENCRYPTION_KEYS", good)
    getSettings.cache_clear()
    assert mfaKeys.reencrypt(db) == (1, 0)
    monkeypatch.delenv("MFA_PREVIOUS_ENCRYPTION_KEYS")
    getSettings.cache_clear()
    assert security.decryptTotpSecret(db.query(MfaFactor).one().secretoCifrado) == "JBSWY3DPEHPK3PXP"


def test_advertencias_de_configuracion_sin_valores(tmp_path):
    env = tmp_path / ".env"
    secret = Fernet.generate_key().decode()
    env.write_text(f"MFA_ENCRYPTION_KEY={secret}\nDATABASE_URL=mssql://u:p@h/db\nMFA_ENCRYPTION_KEY={secret}\n", encoding="utf-8")
    assert duplicatedEnvKeys(env) == ["MFA_ENCRYPTION_KEY"]
    warnings = Settings(**BASE, API_ENV="development", MFA_ENCRYPTION_KEY=secret).securityWarnings(env)
    text = " ".join(warnings)
    assert "MFA_ENCRYPTION_KEY" in text and "DATABASE_URL" in text and "TrustServerCertificate" in text
    assert secret not in text and "u:p@h" not in text


def test_en_produccion_una_clave_mfa_invalida_impide_arrancar():
    with pytest.raises(ValidationError):
        Settings(**BASE, API_ENV="production", MFA_ENCRYPTION_KEY="no-es-una-clave")
    assert Settings(**BASE, API_ENV="development", MFA_ENCRYPTION_KEY="no-es-una-clave").securityWarnings()  # fuera de producción, aviso


def test_en_la_imagen_docker_api_env_es_obligatorio(monkeypatch):
    # H-07: sin API_ENV explícito la imagen no arranca (caería en «development»); fuera de la imagen sigue el valor por defecto.
    assert Settings(**BASE).API_ENV == "development"
    monkeypatch.setenv("GLUCOLUME_RUNTIME", "container")
    with pytest.raises(ValidationError, match="API_ENV"):
        Settings(**BASE)
    assert Settings(**BASE, API_ENV="production").API_ENV == "production"


def test_la_cuenta_de_base_de_la_conservacion_es_aparte_de_la_de_la_api(monkeypatch):
    # GL-03: las dos variables juntas y una cuenta distinta de DB_USER; los jobs la usan y la API no.
    with pytest.raises(ValidationError):
        Settings(**BASE, DB_JOBS_USER="retencion")
    with pytest.raises(ValidationError):
        Settings(**BASE, DB_JOBS_USER=BASE["DB_USER"], DB_JOBS_PASSWORD="otra")
    assert any("DB_JOBS_USER" in w for w in Settings(**BASE, API_ENV="production").securityWarnings())
    from app.db import session as sessionModule

    created = []
    monkeypatch.setattr(sessionModule, "_createEngine", lambda user, password: created.append(user) or create_engine("sqlite://"))
    for settings, expected in ((Settings(**BASE), ["x"]), (Settings(**BASE, DB_JOBS_USER="retencion", DB_JOBS_PASSWORD="otra"), ["retencion"])):
        monkeypatch.setattr(sessionModule, "getSettings", lambda settings=settings: settings)
        sessionModule.getJobsSessionFactory.cache_clear()
        sessionModule.getSessionFactory.cache_clear()
        sessionModule.getEngine.cache_clear()
        created.clear()
        factory = sessionModule.getJobsSessionFactory()
        assert created == expected  # sin cuenta de jobs, la misma que la API
        assert (factory is sessionModule.getSessionFactory()) == (expected == ["x"])
    sessionModule.getJobsSessionFactory.cache_clear()
    sessionModule.getSessionFactory.cache_clear()
    sessionModule.getEngine.cache_clear()


def test_las_pruebas_no_leen_el_env_real():
    # GL-12: tests/conftest.py fija GLUCOLUME_ENV_FILE=tests/test.env; ninguna prueba toma la base, el SMTP ni las claves del .env real.
    from app.core import config

    assert config.ENV_FILE.name == "test.env" and config.ENV_FILE.parent.name == "tests"
    getSettings.cache_clear()
    settings = getSettings()
    assert settings.DB_NAME == "GlucoLume_Pruebas_SinConexion" and settings.SMTP_HOST.endswith(".invalid")


def test_el_hmac_de_los_codigos_cortos_usa_una_clave_derivada():
    # GL-17: la clave del HMAC no es JWT_SECRET; los códigos emitidos con el cálculo anterior se siguen verificando mientras vencen.
    import uuid

    ids = (uuid.uuid4(), uuid.uuid4())
    key = getSettings().JWT_SECRET.get_secret_value().encode()
    assert security.derivedKey("codigo-corto") not in (key, security.derivedKey("otro-proposito"))
    assert len(security.derivedKey("codigo-corto")) == 32
    new, old = security.hashShortCode("X", *ids, "123456"), security.hashShortCode("X", *ids, "123456", legacy=True)
    assert new != old


def test_los_errores_de_configuracion_no_muestran_el_valor_recibido():
    # GL-06/GL-20: un secreto inválido no puede quedar escrito en el log de arranque.
    secrets_ = {"BRIDGE_TOKEN": "token-corto-secreto", "JWT_SECRET": "jwt-corto", "MFA_ENCRYPTION_KEY": "clave-mfa-invalida-secreta"}
    for name, value in secrets_.items():
        extra = {name: value, **({"API_ENV": "production"} if name == "MFA_ENCRYPTION_KEY" else {})}
        with pytest.raises(ValidationError) as error:
            Settings(**{**BASE, **extra})
        assert value not in str(error.value) and BASE["DB_PASSWORD"] not in str(error.value)


def test_el_diagnostico_reconoce_export_espacios_y_comillas_y_detecta_duplicados(tmp_path, monkeypatch):
    a, b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    env = tmp_path / ".env"
    env.write_text(f'export MFA_ENCRYPTION_KEY="{a}"\n# MFA_ENCRYPTION_KEY=comentario\nMFA_ENCRYPTION_KEY = {b}\n', encoding="utf-8")
    assert duplicatedEnvKeys(env) == ["MFA_ENCRYPTION_KEY"]
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", b)
    getSettings.cache_clear()
    origins = [origin for origin, _ in mfaKeys.candidates(env)]
    assert origins == [".env línea 1", ".env línea 3 = clave vigente (la que usa la aplicación)"]
    warnings = " ".join(getSettings().securityWarnings(env))
    assert "MFA_ENCRYPTION_KEY" in warnings and a not in warnings and b not in warnings


def test_recifrar_no_toca_lo_que_ninguna_clave_descifra_y_exige_nombrar_la_base(db, mails, tmp_path, monkeypatch, capsys):
    current, lost = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", current)
    getSettings.cache_clear()
    user = makeUser(db, email="mfa2@example.com", usuario="mfados")
    orphan = Fernet(lost.encode()).encrypt(b"JBSWY3DPEHPK3PXP").decode()
    db.add(MfaFactor(idUsuario=user.idUsuario, secretoCifrado=orphan, habilitado=False))
    db.commit()
    assert mfaKeys.reencrypt(db) == (0, 1)
    assert db.query(MfaFactor).one().secretoCifrado == orphan  # sin la clave que lo descifra no se pierde: queda igual
    from app.db import session as sessionModule

    monkeypatch.setattr(sessionModule, "getSessionFactory", lambda: (lambda: db))
    monkeypatch.setattr(mfaKeys, "reencrypt", lambda _db: (_ for _ in ()).throw(AssertionError("no debía re-cifrar")))
    monkeypatch.setattr(db, "close", lambda: None)
    assert mfaKeys.main(["--env-file", str(tmp_path / "no.env"), "--reencriptar", "--confirmo-base", "otra"]) == 2
    out = capsys.readouterr()
    assert current not in out.out + out.err and lost not in out.out + out.err


def test_un_secreto_repetido_entre_variables_impide_arrancar_en_produccion():
    # GL-20: cada secreto protege algo distinto; se informan solo los nombres.
    shared = "s" * 40
    with pytest.raises(ValidationError) as error:
        Settings(**{**BASE, "API_ENV": "production", "JWT_SECRET": shared, "SESSION_SECRET": shared})
    assert shared not in str(error.value)
    with pytest.raises(ValidationError):
        Settings(**BASE, API_ENV="production", SESSION_SECRET="corto")
    dev = Settings(**{**BASE, "JWT_SECRET": shared, "BRIDGE_TOKEN": shared})
    assert dev.reusedSecrets() == ["JWT_SECRET=BRIDGE_TOKEN"]
    assert any("JWT_SECRET=BRIDGE_TOKEN" in w for w in dev.securityWarnings()) and shared not in " ".join(dev.securityWarnings())
    assert Settings(**BASE, API_ENV="production", SESSION_SECRET="t" * 40).reusedSecrets() == []


def test_en_produccion_se_verifica_el_certificado_de_sql_server(monkeypatch):
    # GL-07: producción no arranca confiando a ciegas en el certificado; un certificado fijado se pasa al driver.
    with pytest.raises(ValidationError):
        Settings(**BASE, API_ENV="production", DB_TRUST_SERVER_CERTIFICATE=True)
    production = Settings(**BASE, API_ENV="production", DB_SERVER_CERTIFICATE="/certs/sql.crt", DB_CERTIFICATE_HOSTNAME="sql.glucolume")
    assert production.trustServerCertificate is False
    from app.db import session as sessionModule

    monkeypatch.setattr(sessionModule, "getSettings", lambda: production)
    # Rama de Windows (ServerCertificate estricto): se fija el sistema para que la prueba no dependa de dónde corre; en Linux esa rama no aplica el
    # parámetro y lee el archivo (cubierto en la prueba siguiente).
    monkeypatch.setattr(sessionModule.os, "name", "nt")
    captured = {}
    monkeypatch.setattr(sessionModule, "create_engine", lambda url, **kw: captured.setdefault("url", url))
    sessionModule._createEngine("app", "x")
    query = dict(captured["url"].query)
    assert (query["Encrypt"], query["TrustServerCertificate"], query["ServerCertificate"], query["HostNameInCertificate"]) == (
        "strict", "no", "/certs/sql.crt", "sql.glucolume")



def test_en_linux_el_certificado_de_sql_server_se_suma_a_las_autoridades_del_sistema(monkeypatch, tmp_path):
    # GL-07: el driver de Linux no aplica ServerCertificate; se confía en el certificado sin reemplazar las autoridades públicas.
    from app.db import session as sessionModule

    certificate = tmp_path / "sql.crt"
    certificate.write_text("-----BEGIN CERTIFICATE-----\nPRUEBA\n-----END CERTIFICATE-----\n", encoding="utf-8")
    settings = Settings(**BASE, API_ENV="production", DB_SERVER_CERTIFICATE=str(certificate))
    monkeypatch.setattr(sessionModule, "getSettings", lambda: settings)
    monkeypatch.setattr(sessionModule, "TRUST_BUNDLE", tmp_path / "bundle.pem")
    monkeypatch.setattr(sessionModule.os, "name", "posix")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    captured = {}
    monkeypatch.setattr(sessionModule, "create_engine", lambda url, **kw: captured.setdefault("url", url))
    sessionModule._createEngine("app", "x")
    query = dict(captured["url"].query)
    assert (query["Encrypt"], query["TrustServerCertificate"]) == ("yes", "no") and "ServerCertificate" not in query
    import os

    bundle = (tmp_path / "bundle.pem").read_text(encoding="utf-8")
    assert os.environ["SSL_CERT_FILE"] == str(tmp_path / "bundle.pem") and bundle.rstrip().endswith("-----END CERTIFICATE-----")
    assert "PRUEBA" in bundle


def test_los_parametros_de_argon2_estan_fijados_y_un_hash_mas_debil_se_rehace():
    # H-12: m = 64 MiB, t = 3, p = 4 (OWASP) dentro del hash emitido; uno con parámetros menores verifica y devuelve el hash nuevo.
    assert security.hashPassword("Clave-Segura-123").startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),)).hash("Clave-Segura-123")
    ok, updated = security.verifyPassword("Clave-Segura-123", weak)
    assert ok and updated and "m=65536,t=3,p=4" in updated
    assert security.verifyPassword("Clave-Segura-123", updated) == (True, None)


def test_el_hmac_de_identificadores_de_auditoria_usa_una_clave_derivada():
    # H-13: la clave sale de HKDF (derivedKey), no de SHA-256(prefijo + JWT_SECRET); el cálculo anterior sigue disponible para las huellas ya guardadas.
    import hashlib
    import hmac as hmacModule

    from app.services.audit import hashIdentifier

    new, old = hashIdentifier("  Alguien@Example.com "), hashIdentifier("alguien@example.com", legacy=True)
    assert new == hashIdentifier("alguien@example.com") and new != old and len(new) == len(old) == 32
    expected = hmacModule.new(security.derivedKey("auditoria-identificador"), b"alguien@example.com", hashlib.sha256).hexdigest()[:32]
    assert new == expected


OLD_JWT, NEW_JWT = "a" * 40, "b" * 40


def inHours(hours):
    from datetime import timedelta

    from app.utils.timeZone import nowArgentina

    return (nowArgentina() + timedelta(hours=hours)).replace(tzinfo=None).isoformat(timespec="seconds")


def rotation(monkeypatch, until=None, previous=OLD_JWT):
    """Configuración de rotación: JWT_SECRET nuevo y, si se indica, el anterior con su plazo (en horas desde ahora)."""
    values = {**BASE, "JWT_SECRET": NEW_JWT, "JWT_PREVIOUS_SECRET": previous}
    if until is not None:
        values["JWT_PREVIOUS_SECRET_UNTIL"] = inHours(until)
    cfg = Settings(**values)
    monkeypatch.setattr(security, "getSettings", lambda: cfg)
    return cfg


def signedWith(secret, monkeypatch, minutes=5):
    from datetime import timedelta

    cfg = Settings(**{**BASE, "JWT_SECRET": secret})
    monkeypatch.setattr(security, "getSettings", lambda: cfg)
    import uuid

    return security._encodeJwt({"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "typ": security.TOKEN_TYPE_ACCESS}, timedelta(minutes=minutes))


def test_rotacion_de_jwt_acepta_el_secreto_anterior_solo_dentro_de_la_ventana(monkeypatch):
    # H-08: se firma siempre con el vigente; el anterior solo verifica hasta JWT_PREVIOUS_SECRET_UNTIL.
    import uuid
    from datetime import timedelta

    import jwt

    token = signedWith(OLD_JWT, monkeypatch)
    expired = signedWith(OLD_JWT, monkeypatch, minutes=-5)
    stranger = signedWith("c" * 40, monkeypatch)
    cfg = Settings(**{**BASE, "JWT_SECRET": NEW_JWT})
    monkeypatch.setattr(security, "getSettings", lambda: cfg)
    with pytest.raises(jwt.InvalidSignatureError):  # rotado sin ventana: el token anterior deja de valer
        security.decodeAccessToken(token)

    cfg = rotation(monkeypatch, until=2)
    assert [secret.get_secret_value() for secret in cfg.jwtVerificationSecrets] == [NEW_JWT, OLD_JWT]
    assert security.decodeAccessToken(token)["typ"] == "access"
    fresh = security._encodeJwt({"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "typ": "access"}, timedelta(minutes=5))
    assert jwt.decode(fresh, NEW_JWT, algorithms=["HS256"], audience=security.JWT_AUDIENCE)  # firma con el nuevo
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(fresh, OLD_JWT, algorithms=["HS256"], audience=security.JWT_AUDIENCE)
    with pytest.raises(jwt.ExpiredSignatureError):  # la ventana no revive tokens vencidos
        security.decodeAccessToken(expired)
    with pytest.raises(jwt.InvalidSignatureError):  # ni acepta un tercer secreto
        security.decodeAccessToken(stranger)
    rotation(monkeypatch, until=2)
    with pytest.raises(jwt.InvalidTokenError):  # ni el tipo equivocado, aunque la firma sea la anterior
        security.decodeMfaChallengeToken(token)


def test_vencida_la_ventana_el_secreto_anterior_se_ignora_aunque_siga_configurado(monkeypatch):
    # H-08: el plazo se evalúa en cada verificación, no solo al arrancar.
    import jwt

    from app.utils import timeZone

    token = signedWith(OLD_JWT, monkeypatch)
    cfg = rotation(monkeypatch, until=2)
    assert security.decodeAccessToken(token)
    from datetime import timedelta

    later = timeZone.nowArgentina() + timedelta(hours=3)
    monkeypatch.setattr("app.utils.timeZone.nowArgentina", lambda: later)
    assert [secret.get_secret_value() for secret in cfg.jwtVerificationSecrets] == [NEW_JWT]
    with pytest.raises(jwt.InvalidSignatureError):
        security.decodeAccessToken(token)
    assert "venció" in " ".join(cfg.securityWarnings())


def test_un_access_token_revocado_no_revive_por_el_secreto_anterior(db, monkeypatch):
    # H-08: la revocación vive en la sesión de la base; que el token esté firmado con el secreto anterior no la esquiva.
    import jwt
    from sqlalchemy import select

    from app.core.exceptions import AuthError
    from app.models.userSession import UserSession
    from app.services import auth as authService
    from tests.test_account_deletion import makeUser

    user = makeUser(db)
    pair = authService._createSession(db, user)
    session = db.scalar(select(UserSession).where(UserSession.idUsuario == user.idUsuario))
    claims = jwt.decode(pair.accessToken, options={"verify_signature": False}, audience=security.JWT_AUDIENCE)
    rotation(monkeypatch, until=2)
    signedByOld = jwt.encode(claims, OLD_JWT, algorithm="HS256")
    verified = security.decodeAccessToken(signedByOld)
    assert authService.resolveAccessSession(db, verified)[1].idSesion == session.idSesion
    session.fechaRevocacion = authService.nowForDb()
    db.commit()
    with pytest.raises(AuthError):
        authService.resolveAccessSession(db, security.decodeAccessToken(signedByOld))


def test_configuraciones_invalidas_de_la_rotacion_de_jwt(monkeypatch):
    # H-08: sin plazo, con plazo excesivo, igual al vigente o demasiado corto no se arranca.
    from app.core.config import JWT_ROTATION_MAX_HOURS

    with pytest.raises(ValidationError, match="JWT_PREVIOUS_SECRET_UNTIL"):
        Settings(**BASE, JWT_PREVIOUS_SECRET=OLD_JWT)  # sin plazo: ningún secreto viejo vale indefinidamente
    with pytest.raises(ValidationError, match="horas"):
        Settings(**BASE, JWT_PREVIOUS_SECRET=OLD_JWT, JWT_PREVIOUS_SECRET_UNTIL=inHours(JWT_ROTATION_MAX_HOURS + 1))
    with pytest.raises(ValidationError, match="igual"):
        Settings(**BASE, JWT_PREVIOUS_SECRET=BASE["JWT_SECRET"], JWT_PREVIOUS_SECRET_UNTIL=inHours(2))
    with pytest.raises(ValidationError):
        Settings(**BASE, JWT_PREVIOUS_SECRET="corto", JWT_PREVIOUS_SECRET_UNTIL=inHours(2))
    ok = Settings(**BASE, JWT_PREVIOUS_SECRET=OLD_JWT, JWT_PREVIOUS_SECRET_UNTIL=inHours(JWT_ROTATION_MAX_HOURS - 1))
    assert any("dos secretos" in w for w in ok.securityWarnings())
    assert any("sin JWT_PREVIOUS_SECRET" in w for w in Settings(**BASE, JWT_PREVIOUS_SECRET_UNTIL=inHours(2)).securityWarnings())
    assert Settings(**BASE).jwtVerificationSecrets == [Settings(**BASE).JWT_SECRET]


def test_en_produccion_se_advierte_si_los_plazos_de_retencion_siguen_sin_definir():
    # H-04: con 0 los datos se conservan sin límite (plazo legal sin aprobar); la advertencia no impide arrancar y desaparece al fijarlos.
    text = " ".join(Settings(**BASE, API_ENV="production").securityWarnings())
    assert "AUDIT_RETENTION_MONTHS" in text and "PERSONNEL_RETENTION_MONTHS" in text
    configured = Settings(**BASE, API_ENV="production", AUDIT_RETENTION_MONTHS=24, PERSONNEL_RETENTION_MONTHS=120,
                          RETENTION_APPROVAL_REFERENCE="Dictamen sintetico 0001")
    assert "RETENTION_MONTHS" not in " ".join(configured.securityWarnings())
    assert "RETENTION_MONTHS" not in " ".join(Settings(**BASE, API_ENV="development").securityWarnings())
    # Plazos sin la referencia de aprobación: se advierte que no se aplican (H-04).
    assert "NO corre" in " ".join(Settings(**BASE, API_ENV="production", AUDIT_RETENTION_MONTHS=24, PERSONNEL_RETENTION_MONTHS=120).securityWarnings())
