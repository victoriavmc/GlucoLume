"""Modelo mínimo (no es GlucoLume): un endpoint `def` que espera SMTP durante SMTP_WAIT segundos, como _sendVerificationEmail
con un servidor que no responde. Sirve para medir si el threadpool de Starlette (40 hilos) afecta a otros endpoints."""
import asyncio
import os
import time
from fastapi import FastAPI

SMTP_WAIT = float(os.environ.get("SMTP_WAIT", "6"))
app = FastAPI()

@app.post("/simula-registro-con-smtp")          # como POST /auth/register: def + envío SMTP síncrono dentro del request
def registro_con_smtp():
    time.sleep(SMTP_WAIT)                       # bloquea un hilo del threadpool durante todo el envío
    return {"ok": True}

@app.get("/otro-endpoint-def")                  # endpoint síncrono no relacionado (mismo tipo que casi toda la API)
def otro_def():
    return {"ok": True}

@app.get("/otro-endpoint-async")                # endpoint async no relacionado (control: no usa el threadpool)
async def otro_async():
    return {"ok": True}
