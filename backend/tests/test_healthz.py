# /healthz: control de vida de la API. No consulta la base y no usa un hilo del threadpool.
#
# Ejecutar desde backend/:
#     python -m pytest tests/test_healthz.py -v
#
# Motivo (auditoría de rendimiento, AUD-03): los endpoints síncronos corren en un threadpool de 40 hilos. Cuando esos hilos están
# ocupados esperando un envío SMTP, un /healthz síncrono no responde (medido: hasta ~7 s con 40 peticiones bloqueadas). Por eso
# el handler es async. Estas pruebas fijan ese contrato y la respuesta actual.

import inspect

from fastapi.testclient import TestClient

from app.main import app, healthz


def test_healthz_responde_ok_sin_base_de_datos():
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"estado": "ok"}


def test_healthz_es_async_para_no_depender_del_threadpool():
    assert inspect.iscoroutinefunction(healthz)


def test_healthz_conserva_cabeceras_de_seguridad():
    response = TestClient(app).get("/healthz")

    assert response.headers.get("X-Content-Type-Options") == "nosniff"
