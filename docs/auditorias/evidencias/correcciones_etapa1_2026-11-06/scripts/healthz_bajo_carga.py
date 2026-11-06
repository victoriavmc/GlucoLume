# Mide /healthz con el threadpool libre y con N peticiones bloqueadas (simulan N envíos SMTP colgados).
import asyncio, json, statistics, sys, time
import httpx
BASE = "http://127.0.0.1:8100"
async def medir(c, n=7):
    v = []
    for _ in range(n):
        t0 = time.perf_counter(); r = await c.get("/healthz"); v.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200 and r.json() == {"estado": "ok"}, r.text
    return {"p50_ms": round(statistics.median(v), 1), "max_ms": round(max(v), 1)}
async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        libre = await medir(c)
        bloqueos = [asyncio.create_task(c.post("/_prueba/bloqueo")) for _ in range(40)]
        await asyncio.sleep(1.0)
        saturado = await medir(c, n=3)
        await asyncio.gather(*bloqueos)
        return {"threadpool_libre": libre, "con_40_bloqueadas": saturado}
print(json.dumps(asyncio.run(main())))
