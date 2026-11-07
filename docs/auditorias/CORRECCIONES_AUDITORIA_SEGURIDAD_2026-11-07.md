# Auditoría técnica de seguridad del 07/11/2026: diagnóstico y correcciones

> **Rama:** `claude/intelligent-keller-ujcsuf`, sobre `a3908c0`. **No se desplegó nada, no se tocó el servidor ni la base de demostración.**
> **Hallazgos:** los del PDF «Auditoría técnica de seguridad — GlucoLume — 07/11/2026».
> **Evidencia:** `docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/` (sondas reproducibles, antes y después).

## 1. Estado por hallazgo

| ID | Sev. (PDF) | Estado | Resumen |
|---|---|---|---|
| M-1 | Media | **CORREGIDO** (código + validación local) | `/api` redirigía a `http://<host>:8080/api/`. Ahora `Location: /api/`. |
| M-2 | Media | **PARCIAL** (decisión pendiente) | El límite existe (60 intentos/10 min por IP, 429 desde el 61.º). Falta decidir si se ajusta. |
| M-3 | Media | **PARCIAL** | Login acotado a 256 caracteres. El sobrecoste de CPU **no se reprodujo**. |
| M-4 | Media | **PENDIENTE** (requiere aprobación de diseño) | El access token ya está en memoria y el refresh en cookie HttpOnly. Quedan tokens en la URL de 4 flujos. |
| B-1 | Baja | **PARCIAL** | Auth limitado a 16 KB. `/api/` general sigue en 1 MB (el puente lo necesita). |
| B-2 | Baja | **PENDIENTE** | El soft 404 se reproduce. `noindex` en rutas sensibles ya estaba en la plantilla. |
| B-3 | Baja | **CORREGIDO** (código + validación local) | Cada cabecera de seguridad aparece una sola vez en la API. |
| B-4 | Baja | **NO APLICA** (preload) / **PENDIENTE** (308) | `preload` no es posible sobre `*.ts.net`. El 302→308 lo emite Tailscale Serve, fuera del repo. |
| B-5 | Baja | **PENDIENTE** | HTTP/2 lo negocia el borde de Tailscale. COOP/CORP requiere validar el flujo de login en navegador. |
| B-6 | Baja | **CORREGIDO** (liveness) | `/api/v1/healthz` publicado. La readiness con base no se publica. |
| B-7 | Baja | **PENDIENTE** | Requiere un colector de reportes CSP. Los reportes incluyen URLs, que pueden llevar tokens. |
| Anexo C | — | **PENDIENTE** | Requiere acceso al host (nginx -T, cookies en vivo, kernel, Tailscale). `pip-audit` local: sin vulnerabilidades conocidas. |

## 2. Detalle por hallazgo

### M-1 · Redirección de `/api` (CORREGIDO)

- **Diagnóstico (reproducido):** `GET /api` → `301 Location: http://127.0.0.1:8080/api/` en Nginx 1.24 con la plantilla de `HEAD`.
- **Causa raíz:** Nginx redirige automáticamente la ubicación prefija `/api/` cuando se pide `/api`. Con `absolute_redirect` activo (valor por defecto), la URL absoluta toma el esquema y el puerto del socket de escucha.
- **Archivos:** `docker/nginx/default.conf.template`; `backend/tests/test_security_hardening.py`.
- **Solución:** `absolute_redirect off;` en el bloque `server`.
- **Pruebas:** sonda `sondas_nginx.sh` antes/después (evidencias); `verificar-rutas.sh` 17/17 con ambas plantillas; `test_nginx_redirige_con_ruta_relativa_sin_puerto_interno` (no existe en `HEAD`).
- **Efecto colateral:** todas las redirecciones que genera Nginx pasan a relativas (p. ej. `/assets` → `/assets/`). Los navegadores las resuelven igual.
- **Fuera de alcance:** las redirecciones que genera **el backend** (FastAPI `redirect_slashes`, p. ej. `/api/v1/auth/login/` → 307) usan el `Host` del pedido y el esquema del proxy. Local, con esquema `http`: `Location: http://127.0.0.1:8080/api/v1/auth/login`. Verificar en el servidor (ver Anexo C).
- **Riesgos y rollback:** bajo. Rollback: quitar la línea `absolute_redirect off;` y recargar Nginx.

### M-2 · Límite de intentos de login (PARCIAL, decisión pendiente)

- **Diagnóstico (medido, app local con SQLite):** cuenta inexistente ×70 → 60 respuestas `401` y la 61.ª `429 DEMASIADAS_SOLICITUDES` con `Retry-After`.
- **Lo que sí es cierto del PDF:** con 15 intentos no se llega a ningún límite. Y el límite por IP es amplio: 60 intentos/10 min ≈ 8 640 por día desde una misma IP, repartidos entre cuentas.
- **Lo que no es cierto:** que no hay límite. Además, una cuenta real se bloquea tras 3 contraseñas incorrectas durante 15 min (`app/services/auth.py`, cubierto por `test_login_lockout.py`). Una cuenta inexistente no se bloquea, por diseño (no revelar existencia).
- **Decisión que necesito:** el PDF propone `limit_req 5r/m` por IP. Con una IP compartida por una institución, eso bloquearía a todos sus usuarios. Opciones: (a) mantener 60/10 min; (b) bajar el límite de la app a ~20/10 min; (c) añadir en Nginx una zona dedicada a `POST /api/v1/auth/login` a ~10 r/min con ráfaga.

### M-3 · Longitud de la contraseña en login (PARCIAL)

- **Diagnóstico (medido):** el login aceptaba contraseñas de 100 000 caracteres. El tiempo de respuesta no creció (≈0,06 s para 100 000 caracteres frente a ≈0,18 s en la primera llamada, que incluye calentamiento). Argon2id (`app/core/security.py`) no trunca.
- **Causa:** `LoginRequest.password` era `Password` (`min_length=1`, sin máximo). El registro sí limita a 128 (`PASSWORD_MAX_LENGTH`).
- **Solución:** tope de 256 en `LoginRequest.password`. Se usa 256 y no 128 porque las contraseñas creadas antes de que existiera el tope de 128 pueden superarlo. 256 es el tope que ya usa `app/schemas/platform.py`.
- **Pruebas:** `test_login_acota_la_contrasena_de_entrada` (nueva); subconjunto de login (ver §3).
- **Cambio de contrato:** un login con más de 256 caracteres responde `422` en lugar de `401`. Afecta solo a entradas que no pueden corresponder a ninguna cuenta.
- **Rollback:** restaurar `password: Password` en `backend/app/schemas/auth.py`.

### M-4 · Tokens en la URL y sesión (PENDIENTE, requiere aprobación)

- **Diagnóstico (verificado en código):**
  - El access token vive solo en memoria (`frontend/src/auth/tokenStore.js`). `localStorage` solo guarda una marca no secreta.
  - El refresh token va en la cookie `glucolume_refresh`: `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Secure` en producción (`backend/app/api/sessionCookie.py`). Esto ya es H-09.
  - El SSE usa `fetch` con cabecera `Authorization`, no `EventSource` con token en la URL.
  - Quedan tokens en la URL de cuatro páginas: `/verificar-correo?token=`, `/activar-cuenta?token=`, `/restablecer-contrasena?token=` y `/cuenta/eliminar/confirmar?token=`. Y un GET con token en query a la API: `GET /api/v1/auth/verify-email?token=` (`frontend/src/api/authApi.js:57`).
  - Nginx no registra la query (`log_format sin_query`, H-14). Uvicorn corre con `--no-access-log`. El riesgo residual es el historial del navegador, capturas y el GET.
- **Diseño propuesto (no implementado):**
  1. Los enlaces de correo nuevos llevan el token en el fragmento `#token=`, igual que el correo de resultados (`/confirmar-correo-resultados#token=`) y la activación de plataforma (`#codigo=`). La página lo lee del hash, lo borra con `history.replaceState` y lo envía por **POST** en el cuerpo.
  2. El backend agrega los POST equivalentes: verificación de correo, activación, recuperación y eliminación. Los GET y los `?token=` actuales se mantienen durante una ventana de transición (propuesta: `EMAIL_VERIFICATION_EXPIRE_HOURS`, 24 h) para los enlaces ya enviados.
  3. Sin cambios en el access token ni en la cookie de refresh. Mover el access token a cookie HttpOnly romperia el SSE y el modelo Bearer; no se recomienda.
- **Archivos afectados (estimado):** `backend/app/api/v1/auth.py`, `backend/app/api/v1/platform.py`, `backend/app/emails/**` (enlaces), `frontend/src/pages/**` (cuatro páginas), `frontend/src/api/authApi.js`, pruebas de correo y de flujos de cuenta.
- **Riesgos:** cambia el formato de los enlaces enviados por correo; requiere la ventana de compatibilidad; afecta a flujos de autenticación. Por eso espera tu aprobación.

### B-1 · Tamaño del cuerpo (PARCIAL)

- **Diagnóstico (medido):** con `HEAD`, `client_max_body_size 1m` aceptaba cualquier cuerpo hasta 1 MiB (1 MB → 422, 10 MB → 413).
- **Solución aplicada:** `client_max_body_size 16k;` en `location ^~ /api/v1/auth/`. Medido: 1 MB y 17 KB → 413; 15 KB → llega al backend (422).
- **Por qué no 256 KB en `/api/`:** el puente envía lotes de hasta 200 líneas (`MAX_BATCH = 200`, `backend/acquisition/bridge/glucolume_bridge.py`) con texto de hasta 512 caracteres. El JSON escapado llega a ~600 KB en el peor caso. Un 413 haría que el puente reintente sin fin. Medir el lote real antes de bajar el límite general.

### B-2 · Soft 404 (PENDIENTE)

- **Diagnóstico (medido):** `/ruta-inexistente`, `/.git/config`, `/phpinfo.php` → `200 text/html` (index de la SPA). No hay fuga de contenido: son el mismo HTML de la SPA.
- **Ya presente:** `X-Robots-Tag: noindex` en `/login`, `/registro`, `/app`, `/plataforma`, `/administracion` (mapa `$robots_tag`).
- **Pendiente:** devolver 404 real exige la lista de rutas de la SPA (`frontend/src/App.jsx`). Una ruta omitida daría 404 de estado aunque la SPA la renderice. Requiere inventario y decisión.

### B-3 · Cabeceras de seguridad duplicadas (CORREGIDO)

- **Diagnóstico (reproducido en `HEAD`):** `/api/` recibía `Content-Security-Policy` ×2 (`default-src 'none'` del backend y la completa de Nginx), `Referrer-Policy` ×2 y `X-Content-Type-Options` ×2.
- **Causa raíz:** Nginx agrega con `add_header` y el `SecurityHeadersMiddleware` del backend (`backend/app/api/securityHeaders.py`) agrega las mismas.
- **Solución:** en las ubicaciones proxy (`/api/`, `^~ /api/v1/auth/`, `/docs`, SSE) se usa `proxy_hide_header` para X-Content-Type-Options, Referrer-Policy, Strict-Transport-Security y Content-Security-Policy. Nginx queda como único emisor. La ubicación SSE conserva la CSP del backend (no define una propia).
- **Trade-off:** detrás de Nginx, la API pasa a usar la CSP de Nginx en lugar de la más estricta del backend (`default-src 'none'`). Para respuestas JSON no cambia nada práctico. Si prefieren la del backend, el cambio es el inverso (ocultar en Nginx, no en el backend).
- **Pruebas:** `test_nginx_es_unico_emisor_de_cabeceras_que_el_backend_repite` (no existe en `HEAD`); medido después: cada cabecera ×1 en `/api/`, `/api/v1/auth/login`, `/api/v1/acquisition/stream`, `/docs`, `/index.html`; HSTS ×1 tras un proxy de confianza con `X-Forwarded-Proto: https`.
- **Rollback:** quitar las líneas `proxy_hide_header` del template.

### B-4 · HSTS y redirección (NO APLICA / PENDIENTE)

- **`preload`:** la lista de preload exige un dominio registrable que controlemos. El nombre `glucolume-server.tailb27487.ts.net` cuelga de `ts.net`, que es de Tailscale. Agregarlo sería rechazado. **No aplicar.**
- **302 → 308:** la redirección HTTP→HTTPS la hace Tailscale Serve, que está fuera del repo. Verificar con `tailscale serve status` en el servidor. Con el perfil `https` (Caddy + dominio), Caddy redirige automáticamente.

### B-5 · HTTP/2 y COOP/CORP (PENDIENTE)

- HTTP/2 lo negocia el borde (Tailscale Serve); Nginx escucha HTTP/1.1 en 8080.
- COOP/CORP: el frontend no usa `window.open` ni `opener` (verificado con grep), y el login de Google es navegación completa (`window.location.assign`). Por eso COOP `same-origin` parece seguro, pero el flujo login (`localhost`) → app (`glucolume.local`) entre orígenes debe validarse en navegador antes de activarlo. CORP solo debería aplicarse a HTML y estáticos, no a la API.

### B-6 · Endpoint de salud (CORREGIDO, liveness)

- **Diagnóstico:** `/api/v1/healthz`, `/api/v1/readyz`, `/api/health` → 404. El backend ya tenía `/healthz` (`backend/app/main.py`, responde `{"estado":"ok"}` sin consultar la base).
- **Solución:** `location = /api/v1/healthz` con `rewrite ^ /healthz break;` hacia el backend. Medido: 200 con cabeceras únicas; `POST` → 405.
- **Pendiente:** readiness con base de datos (`/api/v1/readyz`). No se publica: revelaría el estado de SQL Server desde internet. Si se quiere, debe ir solo a monitoreo interno.
- **Pruebas:** `test_nginx_expone_solo_la_liveness_de_la_api` (no existe en `HEAD`).

### B-7 · Reporte de CSP (PENDIENTE)

- Propuesta: `Content-Security-Policy-Report-Only` con `report-to` a un colector. **Antes**, definir el colector: los reportes incluyen la URL bloqueada, que puede contener `?token=`. El colector debe descartar la query y no guardar IP completa (política de retención del proyecto).

## 3. Pruebas ejecutadas

| Prueba | Resultado |
|---|---|
| `pytest tests/test_security_hardening.py tests/test_login_lockout.py tests/test_healthz.py tests/test_unhandled_errors.py` (línea base, antes de cambios) | 45 pasan |
| `pytest` sobre los archivos de login, auth, sesión, cookies, MFA, seguridad y nginx (subconjunto dirigido, 4 procesos) | **614 pasan, 79 fallan** |
| Las 79 fallas: `test_emails.py::test_banner_adjunto_como_cid` (78) y `test_security_config.py::test_las_pruebas_no_leen_el_env_real` (1) | **Idénticas en `HEAD`** (mismo worktree, mismo `test.env`). Causa de entorno: el `test.env` sintético no define `SMTP_USERNAME`/`SMTP_FROM` y el test de configuración espera el nombre de base del entorno real del proyecto. No son regresiones de esta rama. |
| `pytest tests/test_security_hardening.py tests/test_retencion_logs.py` tras los cambios de nginx | 35 pasan (y 32 solo `test_security_hardening.py`, al agregar pruebas) |
| `docker/nginx/verificar-rutas.sh` (script del proyecto) | 17/17 con `HEAD` y con la rama |
| Sondas `sondas_nginx.sh` | Antes/después en `evidencias/` |
| `pip-audit -r backend/requirements.txt` | Sin vulnerabilidades conocidas |

**No ejecutado:** la suite completa del backend. En serie tardaba horas en este contenedor (bcrypt/argon2 y tiempos de red de las pruebas de correo). Se corrió el subconjunto anterior.

**Limitaciones del entorno:** Nginx 1.24 local (producción: 1.30 alpine); backend uvicorn sin SQL Server (los login con base devuelven 500 en las sondas, por eso el comportamiento del login se prueba con pytest); webroot de prueba sin build del frontend.

## 4. Riesgos de regresión y rollback

| Cambio | Riesgo | Rollback |
|---|---|---|
| M-1 `absolute_redirect off` | Redirecciones de Nginx pasan a relativas | Quitar la línea y recargar Nginx |
| B-3 `proxy_hide_header` | La API usa la CSP de Nginx, no la del backend | Quitar las líneas `proxy_hide_header` |
| B-1 `client_max_body_size 16k` en auth | Un formulario de auth > 16 KB daría 413 (ninguno legítimo) | Quitar la línea |
| B-6 `/api/v1/healthz` | Nueva ruta pública (solo liveness) | Quitar el bloque `location` |
| M-3 tope 256 en login | Contraseñas > 256 caracteres → 422 en lugar de 401 | Restaurar `password: Password` |

**Despliegue:** requiere reconstruir la imagen `frontend` (la plantilla se procesa al arrancar el contenedor) y reiniciar el backend por el cambio de esquema. **No hay migraciones de base de datos.**

## 5. Decisiones pendientes

1. **M-2:** ¿mantener 60/10 min por IP, bajar a ~20/10 min, o agregar zona de Nginx para login (~10 r/min)?
2. **M-4:** aprobar el diseño de la sección correspondiente (fragmento + POST + ventana de transición).
3. **B-3:** confirmar que Nginx sea el único emisor de la CSP de la API.
4. **B-1:** medir el lote real del puente antes de bajar `/api/` de 1 MB.
5. **B-6:** confirmar que no se publica la readiness.
