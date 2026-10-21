# ETAPA 01 — INVENTARIO PRELIMINAR (GlucoLume)

Fecha: 2026-10-20 · Mode: read-only sobre el project; esta folder `OpenCode/` is the authorized exception.
Provenance legend: [V] = verified directly in project files (glob/listing) · [R] = from `README.md` only.

## 1. Inventario

### Root [V]
`backend/`, `frontend/`, `database/`, `acquisition/`, `firmware/`, `docker/`, `docs/`,
compose: `compose.yaml`, `compose.dev.yaml`, `compose.prod.yaml`, `compose.serial.yaml` [V],
`README.md` [V], `.env` present [R-V: listing of root showed `.env`, `.env.example`, `.gitignore`].

### Backend — FastAPI + SQLAlchemy → SQL Server [V dirs; stack claimed in README R]
- `backend/app/api/v1/` [V]: `auth.py`, `measurements.py`, `institutions.py`, `groups.py`, `platform.py`, `devices.py`, `audit.py`, `acquisition.py`, `matrices.py`, `contact.py`, `telemetry.py`, `user.py`
- `backend/app/api/` shared: `deps.py`, `rateLimit.py`, `errors.py`, `securityHeaders.py`, `streams.py`, `requestContext.py` [V]
- `backend/app/services/` [V]: ~50 modules (auth, mfa, mfaRecovery, audit*, consent, measurement*, institution*, patient*, account*, device*, email, resultEmail*, quota, telemetry, securityMonitor…)
- `backend/app/models/` [V]: ~30 SQLAlchemy model modules (user, userSession, audit, matrix, matrixRule, device, mfaFactor, consent, subscription*, payment*, institution*, group*, measurement*…)
- `backend/app/core/` [V]: `config.py`, `security.py`, `exceptions.py`, `requestContext.py`, `commonPasswords.txt`
- `backend/app/db/` [V]: `base.py`, `session.py`
- `backend/app/cli/` [V]: `initAdmin.py`, `recoverAdmin.py`, `mfaKeys.py`, `schemaCheck.py`
- `backend/app/jobs/` [V]: `accountLifecycle.py`, `cleanupUnverifiedAccounts.py`, `purgeInstitutionalRetention.py`
- `backend/app/utils/` [V]: `dbRetry.py`, `normalizers.py`, `timeZone.py`, `userAgent.py`
- `backend/app/main.py` [V]
- `backend/tests/` [V]: 80+ `test_*.py` (platform, patient, security, telemetry_sqlserver…)
- `backend/Dockerfile`, `requirements*.txt/in` [V]

### Frontend — React (Vite) SPA [V structure; Vite/React stack R]
`frontend/src/` [V]: `main.jsx`, `api/` (client.js + per-domain `*Api.js`), `auth/` (tokenStore, originGuard, googleLogin, errorMessages), `pages/` (Account, Register, Privacy, ResultEmail…), `components/` (charts: TrendChart, PpgChart, LiveChart, EvolutionChart; UI: Modal, Navbar, Badge…), `layouts/`, `routes/ProtectedRoute.jsx`, `test/`; co-located `*.test.*` files [V].

### Database [V]
- `database/reference/`: `GlucoLume_DB_v5.sql`, `MATRIZ.SQL`, `GlucoLume_permisos*.sql`, `GlucoLume_cifrado_y_respaldo.sql`, `GlucoLume_actualizar_instalada.sql`, `BorrarRap.sql` [V]
- `database/respaldos/`: `GlucoLume_respaldo.ps1`, `GlucoLume_prueba_restauracion.ps1`, `GlucoLume_clave_respaldo.ps1` [V]

### Acquisition (Windows bridge) [V]
- `acquisition/bridge/`: `glucolume_bridge.py`, `bridge_ctl.py`, `run_bridge.bat`, `Puente-GlucoLume.bat`, `Instalar-Puente.bat`, `bridge.env.example` [V]
- `acquisition/requirements.txt|.in` [V]

### Firmware [V]
- `firmware/GlucoLume_MAX30100/GlucoLume_MAX30100.ino`, `firmware/GlucoLume_MAX30100_optimizado/GlucoLume_MAX30100_optimizado.ino` [V]

### Docker [V]
- `docker/nginx/default.conf.template`, `docker/mssql/Dockerfile`, `docker/firmware/Dockerfile`, `docker/caddy/Caddyfile`, `docker/db.env.example`, `docker/certs/` [V]

## 2. Arquitectura preliminar

Diagram as printed in README [R]:
`Arduino MAX30100 —USB/Bluetooth→ Bridge Windows (Python) —HTTP+token→ FastAPI —ODBC→ SQL Server`;
`Browser —HTTPS→ Caddy (opcional) → Nginx + React SPA —/api→ FastAPI`.

Consistent components verified by files [V]: bridge script exists, FastAPI app (`app/main.py`), nginx/Caddy configs, compose files, two Dockerfiles.
Claim [R, not yet verified in files]: service named `lifecycle` in compose and the ODBC→SQL Server link; to confirm in Etapa 02 by reading `compose.yaml` and `backend/app/core/config.py`.

## 3. Location of documentation

- Index table in `README.md` [V].
- Top-level docs [V]: `docs/BASE_DE_DATOS.md`, `DESPLIEGUE.md`, `DISPOSITIVOS_Y_ADQUISICION.md`, `FRONTEND.md`, `HISTORIAL.md`, `MANUAL_USUARIO.md`, `PENDIENTES.md`, `PRIVACIDAD_Y_RETENCION.md`, `SEGURIDAD.md`
- `docs/funcional/` [V]: `INDIVIDUAL.md`, `GRUPO_FAMILIAR.md`, `INSTITUCION.md`, `PLATAFORMA.md`
- `docs/seguridad/auditorias/AUDITORIA_CIBERSEGURIDAD_GLUCOLUME.pdf` [V] (not opened)
- `docs/evidencias/` [V]: `CVE_LINEA_BASE_2026-10-10.md`, `PRUEBAS_CONCURRENCIA_SQLSERVER_2026-10-16.md`, `scan_summary.py`

## 4. Recommended order of analysis

1. `README.md` + `compose.yaml` (global map)
2. `docs/funcional/*` + `docs/SEGURIDAD.md` + `docs/PENDIENTES.md`
3. `backend/app/main.py` → `core/config.py` → `models/` → `api/v1/` → `services/` → `jobs/`
4. `frontend/src/main.jsx` → `api/client.js` → `auth/` → `pages/`
5. `database/reference/GlucoLume_DB_v5.sql` ↔ `app/models/`
6. `acquisition/bridge/glucolume_bridge.py` + `firmware/*.ino`

## Corrigenda / not backed by verified routes

- Backend stack "FastAPI/SQLAlchemy/ODBC" and frontend "React/Vite": claimed in README [R]; not confirmed by opening those source files yet.
- Compose service names (`backend`, `frontend`, `lifecycle`): only file names verified [V]; their content not read.
- Security features (Argon2id, JWT, MFA TOTP, PKCE, DEC-01): from README [R]; file existence (e.g., `mfa.py`, `security.py`) is [V] but behavior not audited — cibersecurity auditorias not performed.

No secrets, `.env` values, ni personal data were recorded.
