"""¿Es una convoy de la GIL (cada SQLGetData suelta y retoma la GIL)? Prueba pyodbc con 8 hilos variando sys.setswitchinterval y limitando los hilos simultáneos."""
import os, sys, threading, time
sys.path.insert(0, os.getcwd())
import pyodbc
from app.core.config import getSettings
s = getSettings()
cs = (f"DRIVER={{{s.DB_DRIVER}}};SERVER={s.DB_HOST},{s.DB_PORT};DATABASE={s.DB_NAME};UID={s.DB_USER};PWD={s.DB_PASSWORD.get_secret_value()};Encrypt=yes;TrustServerCertificate=yes")
Q = "SELECT TOP 20 idPerfilMedicion, nombre, apellido, dni, fechaNacimiento FROM dbo.PerfilMedicion ORDER BY apellido"

import contextlib
null = contextlib.nullcontext()

def make(gate, mode="todo"):
    def work(n):
        c = pyodbc.connect(cs)
        for _ in range(n):
            g = gate or null
            if mode == "todo":
                with g:
                    c.cursor().execute(Q).fetchall()
            elif mode == "solo-execute":
                cur = c.cursor()
                with g:
                    cur.execute(Q)
                cur.fetchall()
            elif mode == "solo-fetch":
                cur = c.cursor().execute(Q)
                with g:
                    cur.fetchall()
        c.close()
    return work

def run(label, threads, gate=None, total=800, mode="todo"):
    fn = make(gate, mode); fn(3)
    per = total // threads
    c0, t0 = time.process_time(), time.perf_counter()
    ts = [threading.Thread(target=fn, args=(per,)) for _ in range(threads)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    print(f"{label:46} {total / wall:8.1f}/s  CPU {cpu / total * 1000:6.2f} ms/llamada")

run("8 hilos, switchinterval 5 ms (defecto)", 8)
for si in (0.001, 0.0002):
    sys.setswitchinterval(si)
    run(f"8 hilos, switchinterval {si * 1000:g} ms", 8)
sys.setswitchinterval(0.005)
for mode in ("todo", "solo-execute", "solo-fetch"):
    run(f"8 hilos, a lo sumo 3 dentro ({mode})", 8, threading.BoundedSemaphore(3), mode=mode)
run("8 hilos sin límite", 8)
run("1 hilo (referencia)", 1)
