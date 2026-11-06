# Arnés de medición (fuera del repositorio): la aplicación real de GlucoLume + un endpoint síncrono que bloquea un hilo del threadpool
# como lo hace un envío SMTP colgado. Solo se usa para medir /healthz bajo saturación.
import os
import sys
import time

sys.path.insert(0, "/home/user/GlucoLume/backend")
os.environ.setdefault("GLUCOLUME_ENV_FILE", "/home/user/GlucoLume/backend/tests/test.env")
from app.main import app  # noqa: E402


@app.post("/_prueba/bloqueo")
def bloqueo():
    time.sleep(float(os.environ.get("BLOQUEO_S", "8")))
    return {"ok": True}
