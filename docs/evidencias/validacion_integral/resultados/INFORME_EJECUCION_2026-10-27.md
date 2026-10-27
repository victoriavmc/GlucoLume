# Informe de ejecución de pruebas — 27/10/2026

**Versión / commit:** `31d757a` (rama `master`) más una corrección de rutas en tres archivos de prueba, sin commit (ver "Cambios en el código")
**Entorno:** Windows 11 Pro 10.0.26300 · Python 3.14.0 · Node v22.17.0 · Vitest 5.0.3

## Comandos ejecutados

| Suite | Comando |
|---|---|
| Backend (pytest), suite completa | `cd backend && python -m pytest -q -rfEs` |
| Frontend (Vitest) | `cd frontend && npx vitest run` |

## Resultados

| Suite | Aprobadas | Fallidas | Omitidas | Duración |
|---|---|---|---|---|
| Backend (pytest), suite completa | 1914 | 0 | 80 | 1092,68 s (18 min 12 s) |
| Frontend (Vitest) | 700 / 700 (53 archivos) | 0 | 0 | 47,46 s |

Referencia: el informe del 23/10 (`suites.md`) reportaba 1983 aprobadas en backend y 695/695 en frontend. **Estos resultados no se atribuyen a esa ejecución.** La cantidad de pruebas cambió y no comparo cifras entre fechas.

### Omisiones del backend (80)

- **Pruebas opcionales con SQL Server descartable** (no se definió `TEST_SQLSERVER_URL` / `TEST_SQLSERVER_CONFIRM`).
- **redis-server no instalado** (pruebas de `test_rate_limiter_shared.py`).
- **dpkg no instalado** (`test_zlib_guard.py`).

## Cambios en el código

La primera corrida fallaba al recolectar cuatro módulos de bridge porque buscaban `acquisition/bridge/` en la raíz del repo, y esa carpeta está en `backend/acquisition/`. Se corrigieron las rutas en:

- `backend/tests/test_bridge.py`: `parents[2]` → `parents[1]`
- `backend/tests/test_bridge_ctl.py`: `parents[2]` → `parents[1]`
- `backend/tests/test_link_auth.py`: `BRIDGE_DIR = ROOT / "backend" / "acquisition" / "bridge"`

Con la corrección, `test_bridge.py`, `test_bridge_ctl.py`, `test_bridge_runtime.py` y `test_link_auth.py` ejecutaron 100 pruebas, con 1 omitida. La suite completa aparece en la tabla de arriba.

## Limitaciones

1. **Sin SQL Server descartable, redis-server ni dpkg.** Las 80 omisiones dependen de estas herramientas. Las pruebas que requieren SQL Server real no se verificaron en esta máquina.
2. **Capturas.** Las PNG son renderizaciones del texto de la salida en HTML, no pantallazos de la terminal. Las salidas originales completas están en los `.txt`.
3. **Corrección sin commit.** Los cambios en las rutas de prueba están en el árbol de trabajo. Hay que revisarlos y commitearlos aparte si se aceptan.

## Archivos de evidencia

- `K1_pytest_captura_2026-10-27.png` — captura de pytest, suite completa
- `K1_pytest_salida_completa_2026-10-27.txt` — salida completa de la suite corregida
- `K1_pytest_corrida_con_exclusiones_2026-10-27.txt` — corrida previa a la corrección, con 4 módulos excluidos (1814 aprobadas, 0 fallidas, 79 omitidas)
- `K1_pytest_primera_corrida_fallida_2026-10-27.txt` — primera corrida, que falló en la recolección
- `K2_vitest_captura_2026-10-27.png` — captura de Vitest
- `K2_vitest_salida_2026-10-27.txt` — salida completa de Vitest

## Datos sensibles

Las salidas no contienen credenciales ni datos de pacientes. Las rutas incluyen el nombre de usuario de Windows (`VictoriaVMC`).

## Firma

Fecha: 27/10/2026 · Responsable: __________________ · Firma: __________________
