# Suites completas sobre el último commit (23/10/2026)

| Suite | Comando | Resultado |
|---|---|---|
| Backend (pytest) | `TEST_SQLSERVER_URL=<SQL Server 2022 descartable> TEST_SQLSERVER_CONFIRM=DESCARTABLE python -m pytest -q -rfEs` (ODBC Driver 18, Python 3.14) | **1983 pasaron, 0 fallaron, 0 omitidas** en 17 min 11 s (incluye las pruebas opcionales de SQL Server real y las de Redis) |
| Frontend (Vitest) | `npx vitest run` | **695/695** en 52 archivos |
| Build de producción del frontend | `VITE_API_BASE_URL=/ npx vite build` | correcto (4 min 30 s); con `http://localhost:8000` también (6 min 17 s) |

Corridas anteriores de la misma sesión: la primera corrida completa del día (antes de corregir el log de Nginx y la prueba del certificado) dio 1981 pasaron y 2 fallaron; ambas fallas se
investigaron (una era la prueba escrita contra la plantilla vieja mientras se editaba; la otra dependía del sistema operativo) y se corrigieron en commits propios.
