import asyncio, sys, time, statistics
import httpx
BASE = "http://127.0.0.1:8099"
async def main(concurrent: int):
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        blockers = [asyncio.create_task(c.post("/simula-registro-con-smtp")) for _ in range(concurrent)]
        await asyncio.sleep(1.0)  # los bloqueantes ya tomaron sus hilos
        out = {}
        for path in ["/otro-endpoint-def", "/otro-endpoint-async"]:
            t0 = time.perf_counter(); r = await c.get(path); out[path] = round((time.perf_counter() - t0) * 1000)
        await asyncio.gather(*blockers)
        return out
if __name__ == "__main__":
    n = int(sys.argv[1])
    print(n, "requests bloqueantes en vuelo ->", asyncio.run(main(n)))
