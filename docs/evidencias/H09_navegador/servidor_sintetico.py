# Servidor de verificación de H-09 (solo local, datos sintéticos, SQLite temporal): la API real con una persona de prueba.
import os, sqlite3, sys, tempfile, uuid
from pathlib import Path

os.environ.update({
    "API_ENV": "development", "DB_HOST": "localhost", "DB_NAME": "GlucoLumeTest", "DB_USER": "test", "DB_PASSWORD": "test",
    "JWT_SECRET": "x" * 40, "FRONTEND_URL": "http://localhost:5173", "PLATFORM_MFA_REQUIRED": "false",
    "API_BASE_URL": "http://localhost:8000", "SESSION_SECRET": "s" * 40,
})
from cryptography.fernet import Fernet
os.environ["MFA_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
sys.path.insert(0, "BACKEND")
os.chdir("BACKEND")
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from tests.test_account_deletion import _sqliteMetadata, _isJson, makeUser
from app.utils.timeZone import nowForDb
from app.api.deps import getDb
from app.main import app
import uvicorn

tmp = Path(tempfile.mkdtemp())
engine = create_engine(f"sqlite:///{tmp / 'main.sqlite'}", connect_args={"check_same_thread": False})
@event.listens_for(engine, "connect")
def _c(conn, rec):
    conn.execute(f"ATTACH DATABASE '{tmp / 'dbo.sqlite'}' AS dbo")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("newid", 0, lambda: uuid.uuid4().hex)
    conn.create_function("newsequentialid", 0, lambda: uuid.uuid4().hex)
    conn.create_function("sysutcdatetime", 0, lambda: nowForDb().isoformat(" "))
    conn.create_function("isjson", 1, _isJson, deterministic=True)
    conn.create_function("todayDb", 0, lambda: nowForDb().date().isoformat(), deterministic=True)
_sqliteMetadata().create_all(engine)
Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
with Session() as s:
    makeUser(s)  # usuario «victoria», contraseña de prueba de los tests
def testDb():
    with Session() as s:
        yield s
app.dependency_overrides[getDb] = testDb
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
