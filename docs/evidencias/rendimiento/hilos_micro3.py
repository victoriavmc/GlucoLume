"""Causa raíz: 8 hilos con pyodbc bajo distintas condiciones (cifrado, pooling, MARS, tamaño de lectura). Solo diagnóstico."""
import os, sys, threading, time
sys.path.insert(0, os.getcwd())
import pyodbc
from app.core.config import getSettings
s = getSettings()
base = f"DRIVER={{{s.DB_DRIVER}}};SERVER={s.DB_HOST},{s.DB_PORT};DATABASE={s.DB_NAME};UID={s.DB_USER};PWD={s.DB_PASSWORD.get_secret_value()};TrustServerCertificate=yes;"
Q = "SELECT TOP 20 idPerfilMedicion, nombre, apellido, dni, fechaNacimiento FROM dbo.PerfilMedicion ORDER BY apellido"
print(open("/etc/odbcinst.ini").read())

def run(label, cs, threads=8, total=800, pooling=None):
    if pooling is not None:
        pyodbc.pooling = pooling
    def work(n):
        c = pyodbc.connect(cs)
        for _ in range(n):
            c.cursor().execute(Q).fetchall()
        c.close()
    work(3)
    per = total // threads
    c0, t0 = time.process_time(), time.perf_counter()
    ts = [threading.Thread(target=work, args=(per,)) for _ in range(threads)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    print(f"{label:48} {total / wall:8.1f}/s  CPU {cpu / total * 1000:6.2f} ms/llamada", flush=True)

run("Encrypt=yes, 8 hilos", base + "Encrypt=yes")
run("Encrypt=no, 8 hilos (solo diagnóstico)", base + "Encrypt=no")
run("Encrypt=yes, MARS_Connection=yes", base + "Encrypt=yes;MARS_Connection=yes")
run("Encrypt=yes, 4 hilos", base + "Encrypt=yes", threads=4)
run("Encrypt=yes, 6 hilos", base + "Encrypt=yes", threads=6)
run("Encrypt=yes, 8 hilos, pooling=False", base + "Encrypt=yes", pooling=False)
