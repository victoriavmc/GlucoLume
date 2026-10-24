"""¿Se degrada el CÓDIGO de la aplicación con hilos (sin uvicorn ni HTTP)? Llama al servicio de listado de pacientes N veces desde 1 y desde K hilos,
cada uno con su sesión de base, y compara tiempo de pared y CPU del proceso.
    ... run --rm --no-deps -T -v ./docs/evidencias/rendimiento:/perf:ro backend-perf python /perf/hilos_servicio.py
"""
import json, os, sys, threading, time, uuid
sys.path.insert(0, os.getcwd())
assert os.environ.get("DB_NAME") == "GlucoLume_perf"
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
import app.db.session as session_module

# POOL=<n>: prueba con pool_size=n (por defecto el del código: SQLAlchemy 5 + 10 de desborde).
if os.environ.get("POOL"):
    _create = session_module.create_engine
    session_module.create_engine = lambda url, **kw: _create(url, pool_size=int(os.environ["POOL"]), max_overflow=10, **kw)
connects = [0]
event.listen(Engine, "connect", lambda *a: connects.__setitem__(0, connects[0] + 1))
from app.db.session import getSessionFactory
from app.models.user import User
from app.services import institutionPatients as patients

ids = json.load(open("/perf/resultados/seed_ids.json", encoding="utf-8"))
inst = uuid.UUID(ids["idInstitucion"])
factory = getSessionFactory()
with factory() as db:
    actor = db.scalar(select(User).where(User.usuario == "perfoperador1"))
    db.expunge(actor)

def work(n):
    db = factory()
    try:
        for _ in range(n):
            patients.listPatients(db, actor, inst, estado="ACTIVO", pagina=1, tamanioPagina=20)
            db.rollback()
    finally:
        db.close()

work(5)
for threads in (1, 2, 4, 8):
    total = 160
    per = total // threads
    c0, t0 = time.process_time(), time.perf_counter()
    ts = [threading.Thread(target=work, args=(per,)) for _ in range(threads)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    print(f"conexiones nuevas: {connects[0]}", end="  ")
    connects[0] = 0
    print(f"{threads} hilos: {total} llamadas en {wall:5.2f} s  = {total / wall:6.1f}/s  CPU {cpu:5.2f} s ({cpu / total * 1000:5.1f} ms CPU por llamada)")
