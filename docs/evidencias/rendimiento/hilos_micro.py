"""Microbenchmarks por hilos: ¿qué componente infla la CPU cuando hay 8 hilos? (a) Python puro, (b) SELECT 1 con pyodbc, (c) 20 filas con pyodbc,
(d) 20 filas con SQLAlchemy Core. Cada fila: llamadas/s y ms de CPU por llamada con 1, 4 y 8 hilos."""
import os, sys, threading, time
sys.path.insert(0, os.getcwd())
assert os.environ.get("DB_NAME") == "GlucoLume_perf"
import pyodbc
from sqlalchemy import text
from app.db.session import getEngine
from app.core.config import getSettings

engine = getEngine()
s = getSettings()
cs = (f"DRIVER={{{s.DB_DRIVER}}};SERVER={s.DB_HOST},{s.DB_PORT};DATABASE={s.DB_NAME};UID={s.DB_USER};PWD={s.DB_PASSWORD.get_secret_value()};Encrypt=yes;TrustServerCertificate=yes")

def pure(n):
    for _ in range(n):
        sum(i * i for i in range(20000))

def rawSelect1(n):
    c = pyodbc.connect(cs)
    for _ in range(n):
        c.cursor().execute("SELECT 1").fetchall()
    c.close()

def rawRows(n):
    c = pyodbc.connect(cs)
    for _ in range(n):
        c.cursor().execute("SELECT TOP 20 idPerfilMedicion, nombre, apellido, dni, fechaNacimiento FROM dbo.PerfilMedicion ORDER BY apellido").fetchall()
    c.close()

def coreRows(n):
    with engine.connect() as c:
        for _ in range(n):
            c.execute(text("SELECT TOP 20 idPerfilMedicion, nombre, apellido, dni, fechaNacimiento FROM dbo.PerfilMedicion ORDER BY apellido")).all()

for name, fn, total in (("python puro", pure, 80), ("pyodbc SELECT 1", rawSelect1, 800), ("pyodbc 20 filas", rawRows, 800), ("SQLAlchemy 20 filas", coreRows, 800)):
    fn(3)
    for threads in (1, 4, 8):
        per = total // threads
        c0, t0 = time.process_time(), time.perf_counter()
        ts = [threading.Thread(target=fn, args=(per,)) for _ in range(threads)]
        [t.start() for t in ts]; [t.join() for t in ts]
        wall, cpu = time.perf_counter() - t0, time.process_time() - c0
        print(f"{name:20} {threads} hilos: {total / wall:8.1f}/s  CPU {cpu / total * 1000:7.2f} ms por llamada")
