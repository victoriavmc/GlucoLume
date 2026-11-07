# Auditoría técnica de seguridad del 07/11/2026: diagnóstico y correcciones

> **Rama:** `claude/intelligent-keller-ujcsuf`, sobre `a3908c0`. **No se desplegó nada, no se tocó el servidor ni la base de demostración.**
> **Hallazgos:** los del PDF «Auditoría técnica de seguridad — GlucoLume — 07/11/2026».
> **Evidencia:** `docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/` (sondas reproducibles, antes y después).

## 1. Estado por hallazgo

| ID | Sev. (PDF) | Estado | Resumen |
|---|---|---|---|
| M-1 | Media | **CORREGIDO en la rama** (pendiente de despliegue) | `/api` redirigía a `http://<host>:8080/api/`. Ahora `308` a `/api/` relativo. Ver §2. |
| M-2 | Media | **CORREGIDO** (con riesgo residual: ataque distribuido) | El PDF no reprodujo el límite porque probó 15 intentos. Sí había fallas reales: oráculo de enumeración, bloqueo de la cuenta por terceros y 429 del borde sin forma de API. Ver §2. |
| M-3 | Media | **CORREGIDO** (coste acotado; el sobrecoste por longitud no se reproduce) | Argon2 con control de concurrencia (2 a la vez, 8 en espera, 503 con `Retry-After`). Sin cambios de coste ni de hashes. Ver §2. |
| M-4 | Media | **PENDIENTE** (requiere aprobación de diseño) | El access token ya está en memoria y el refresh en cookie HttpOnly. Quedan tokens en la URL de 4 flujos. |
| B-1 | Baja | **CORREGIDO** | Tope general de 160 KB (antes 1 MB); tramos por operación para lotes legítimos (ingesta 768 KB, muestras y offboarding 384 KB); autenticación 16 KB; 413 en JSON. Ver §2. |
| B-2 | Baja | **PENDIENTE** | El soft 404 se reproduce. `noindex` en rutas sensibles ya estaba en la plantilla. |
| B-3 | Baja | **CORREGIDO** (código + validación local) | Cada cabecera de seguridad aparece una sola vez en la API. |
| B-4 | Baja | **NO APLICA** (preload) / **PENDIENTE** (308) | `preload` no es posible sobre `*.ts.net`. El 302→308 lo emite Tailscale Serve, fuera del repo. |
| B-5 | Baja | **PENDIENTE** | HTTP/2 lo negocia el borde de Tailscale. COOP/CORP requiere validar el flujo de login en navegador. |
| B-6 | Baja | **CORREGIDO** (liveness) | `/api/v1/healthz` publicado. La readiness con base no se publica. |
| B-7 | Baja | **PENDIENTE** | Requiere un colector de reportes CSP. Los reportes incluyen URLs, que pueden llevar tokens. |
| Anexo C | — | **PENDIENTE** | Requiere acceso al host (nginx -T, cookies en vivo, kernel, Tailscale). `pip-audit` local: sin vulnerabilidades conocidas. |

## 2. Detalle por hallazgo

### M-1 · Redirección de `/api` a HTTP con el puerto 8080 (CORREGIDO en la rama, pendiente de despliegue)

**1. Componente que genera la redirección: el Nginx del contenedor `frontend`.** Reproducido con la plantilla de `a3908c0` y el `Host` del acceso por Tailscale (sin puerto):

```
GET /api                  → 301  Location: http://glucolume-server.tailb27487.ts.net:8080/api/
GET /api?x=1              → 301  Location: http://glucolume-server.tailb27487.ts.net:8080/api/?x=1
POST /api                 → 301  Location: http://glucolume-server.tailb27487.ts.net:8080/api/
```

- El **esquema** es `$scheme`: el Nginx del contenedor recibe la conexión por HTTP. La cabecera `X-Forwarded-Proto: https` **no** la cambia (la redirección automática no usa `$fwd_proto`).
- El **puerto** es el de escucha del contenedor (`listen 8080`), que es el puerto interno, no el público.
- El **host** es el `Host` del cliente. Tailscale Serve no aparece en esta cadena: solo reenvía la respuesta; nada en el repo añade `:8080`. Confirmarlo en el servidor con `tailscale serve status` (§6).
- **No es FastAPI**: `/api` no es una ruta del backend. La redirección ocurre antes de llegar a él.

**2. Configuración real verificada (no la del PDF):**

| Elemento | Valor real | Fuente |
|---|---|---|
| Puerto de escucha del frontend | 8080 (dentro del contenedor) | `frontend/Dockerfile` `EXPOSE 8080`; `compose.yaml` `ports` |
| Publicación del frontend | `127.0.0.1:80` y `127.0.0.1:8080` del host | `compose.yaml` (`FRONTEND_PORT`, `FRONTEND_LOGIN_PORT`) |
| Upstream del backend | `backend:8000` | `compose.yaml` `BACKEND_UPSTREAM: ${FRONTEND_BACKEND_UPSTREAM:-backend:8000}`; `backend/Dockerfile` `EXPOSE 8000` y `uvicorn --port 8000` |
| Default de la imagen del frontend | **`backend:8080` (incorrecto)** | `frontend/Dockerfile` `ENV BACKEND_UPSTREAM` — corregido a `backend:8000` en este parche |
| TLS | Caddy (perfil `https`) → `frontend:8080`, o un proxy del host | `docker/caddy/Caddyfile`, `compose.prod.yaml`, `docs/DESPLIEGUE.md` |

**3. Causa raíz.** Nginx redirige por sí mismo una ubicación prefija (`location /api/`) cuando se pide `/api`. Con `absolute_redirect on` (el valor por defecto), la URL absoluta se arma con `$scheme`, `$host` y el puerto de escucha. Es un defecto de la configuración por omisión, no de la API.

**4. Por qué no se copia la propuesta del PDF.** El informe propone `proxy_pass http://127.0.0.1:8080` y `proxy_redirect off; port_in_redirect off;`. Medido:

- **`proxy_pass` a `127.0.0.1:8080` dentro del contenedor → 502.** Ese `127.0.0.1` es el propio Nginx: se proxifica a sí mismo (`upstream sent too big header…` en `error.log`).
- `proxy_redirect` reescribe cabeceras del **upstream**; el `Location` de `/api` lo genera Nginx, no el upstream. No tiene efecto aquí.
- `port_in_redirect` es irrelevante una vez que la redirección es relativa.

**5. Solución (parche mínimo, `docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/M1_redireccion_api.patch`):**

1. `docker/nginx/default.conf.template`: ubicación exacta `location = /api { return 308 /api/$is_args$args; }`, sin proxy. El `308` conserva el método (un `POST /api` no se convierte en `GET`), y la query se mantiene.
2. `absolute_redirect off;` en el `server` (ya en `446f967`): defensa para cualquier otra redirección de Nginx.
3. `frontend/Dockerfile`: `ENV BACKEND_UPSTREAM=backend:8000` (antes `8080`). Compose ya fija `backend:8000`, así que en el despliegue por compose no cambia nada; evita un 502 si la imagen se usa sin compose.

**Antes y después** (`evidencias/.../resultados_redireccion_api_*.txt`, sonda `sondas_redireccion_api.sh`):

| Solicitud | `a3908c0` (auditoría) | HEAD previo (`1931580`) | Este parche |
|---|---|---|---|
| `GET /api` (Host tailnet) | 301 `http://…:8080/api/` | 301 `/api/` | **308 `/api/`** |
| `POST /api` | 301 `http://…:8080/api/` | 301 `/api/` | **308 `/api/`** (método conservado) |
| `GET /api?x=1` | 301 `http://…:8080/api/?x=1` | 301 `/api/?x=1` | **308 `/api/?x=1`** |
| Seguimiento `curl -L` | 1 salto, al puerto interno | 1 salto | 1 salto, sin 5xx |
| `GET /api/` | 404 JSON del backend | 404 JSON | 404 JSON (sin cambio) |
| `GET /api/v1/auth/login` | 405 JSON | 405 JSON | 405 JSON (sin cambio) |
| `GET /api/v1/healthz` | 404 (anterior a B-6) | 200 | 200 |
| `POST /api/v1/auth/login` | 500 (sin base en el banco) | 500 | 500 (sin cambio) |
| Mixed content (`X-Forwarded-Proto: https`) | `Location` `http://…` | `/api/` | `/api/` |

Notas: el `500` del login es el banco sin SQL Server, igual en ambas columnas; la fila de healthz de la primera columna no aísla M-1 (es anterior a B-6). `verificar-rutas.sh` (17/17) pasa en las tres plantillas.

**6. Verificación en el servidor (solo lectura, antes del despliegue):**

```bash
# Redirección actual (esperado hoy: 301 con http:// y :8080)
curl -sI https://glucolume-server.tailb27487.ts.net/api | grep -i '^HTTP\|^location'
# Plantilla renderizada dentro del contenedor (esperado hoy: sin "location = /api")
docker compose -f compose.yaml -f compose.prod.yaml exec frontend grep -n "location = /api\|absolute_redirect" /etc/nginx/conf.d/default.conf
# Upstream efectivo
docker compose -f compose.yaml -f compose.prod.yaml config | grep BACKEND_UPSTREAM
# Proxy del host (si existe): ¿agrega o reescribe redirecciones?
sudo nginx -T 2>/dev/null | grep -n "location\|proxy_pass\|absolute_redirect" | head -20
tailscale serve status
```

**7. Procedimiento de despliegue (no aplicado; requiere aprobación):**

1. Respaldo de la imagen actual: anotar `GLUCOLUME_VERSION` vigente (no borrar su imagen).
2. `GLUCOLUME_VERSION=<nueva>`; `docker compose -f compose.yaml -f compose.prod.yaml build frontend`; `docker compose … up -d frontend`. El backend, la base y los workers no se tocan. Corte esperado: segundos del frontend; la API sigue respondiendo.
3. Validación: `sondas_redireccion_api.sh http://127.0.0.1:8080 glucolume-server.tailb27487.ts.net` y `verificar-rutas.sh`. Esperado: `308 /api/` y 17/17.
4. Validación externa por HTTPS: `curl -sI https://<dominio>/api` → `308` con `Location: /api/`.

**8. Rollback:** `GLUCOLUME_VERSION=<anterior>` y `docker compose … up -d frontend`. Sin cambios de base ni de datos. Comprobación: `curl -sI …/api` vuelve a `301` (comportamiento anterior, con el `Location` previo). Riesgo: los clientes que cacheen un `301` de `/api` verán el `308`; nadie usa `/api` como endpoint.

**Pendiente (decisión, no implementado):** la barra final en la **API** (`/api/v1/auth/login/`) produce un `307` del backend (`redirect_slashes`) con URL absoluta armada desde el `Host` y el esquema. Medido: con un peer no confiable, `http://<host>/…`; con un proxy HTTPS de confianza, `https://<host>/…`. El puerto no aparece con el `Host` de Tailscale. Ningún cliente del proyecto usa barra final (frontend: 0 rutas; bridge: `/api/v1/acquisition/bridge/check`). Dos opciones: (a) `FastAPI(redirect_slashes=False)`, que cambia el 307 por 404 para barras finales (cambio de contrato para clientes externos); (b) dejarlo y verificar que el proxy del host envíe `X-Forwarded-Proto: https` y esté en `TRUSTED_PROXY_CIDR`. Requiere tu decisión.

### M-2 · Protección del inicio de sesión contra intentos automatizados (CORREGIDO, con riesgo residual)

**Diagnóstico (medido en la app real con base de prueba, antes de los cambios):**

- El PDF afirma «sin 429 ni Retry-After tras 15 intentos». **Esa observación es correcta, pero no prueba que falte el límite:** el límite por IP es de 60 intentos cada 10 min, y 15 no lo alcanzan (`app/api/rateLimit.py`).
- Lo que el PDF no vio, y medimos (`evidencias/.../resultados_login_antes.txt`):
  - **Oráculo de enumeración (S1 vs S2):** tras 3 contraseñas erróneas, una cuenta **real** responde `429 CUENTA_BLOQUEADA` con `Retry-After`, y una **inexistente** responde `401` siempre. Quien ataca distingue qué cuentas existen.
  - **Bloqueo por terceros (S3):** un atacante desde otra IP deja fuera a la víctima, que con la contraseña correcta recibe el mismo `429`.
  - **Renovación (S4):** el bloqueo vence a los 15 min, y tres intentos más lo reabren. Un atacante lo mantiene indefinidamente.
  - **Borde inconsistente:** el `limit_req` de Nginx respondía la página HTML `429 Too Many Requests`, sin `Retry-After` ni el JSON de la API (72 de 90 respuestas 429 en la ráfaga medida).

**Causa raíz:** el bloqueo era **global por cuenta** (3 fallos → `CredencialLocal.bloqueadoHasta`). Esa decisión es la que produce a la vez el oráculo (la respuesta difiere solo para cuentas reales), el bloqueo por terceros y la renovación. El límite por IP existente nunca vio a un atacante que rota IPs ni a una cuenta atacada desde varias.

**Solución implementada:**

1. **Límite por (identificador, origen)** en `backend/app/services/loginThrottle.py`, sobre `RateLimiter` (con Redis compartido si está configurado). Dos ventanas deslizantes: **5 fallos en 15 min** y **15 fallos en 1 h**. El origen es la IP real normalizada (`normalizeIp`), que Nginx fija desde el proxy de confianza. Un tercero desde otra IP **no** afecta a la víctima.
2. **Se evalúa antes de buscar la cuenta** y con el mismo contador para identificadores existentes e inexistentes. La respuesta (código, mensaje, `Retry-After`) es idéntica, y los intentos limitados no consultan la base ni verifican Argon2.
3. **Se quita el bloqueo global por cuenta del login.** `_loginLocal` ya no lee ni incrementa `CredencialLocal` para el login. La **reautenticación con sesión** (`verifyCurrentPassword`) conserva su bloqueo: exige sesión, así que no es una vía anónima.
4. **Retry-After exacto** en memoria: el instante en que vence el fallo que libera un lugar en la ventana (`RateLimiter.retryAfter`). Con Redis compartido es la cota superior (la ventana entera).
5. **Decisiones serializadas por par** (`loginThrottle.exclusivo`, 256 cerrojos fijos): comprobar el límite, verificar la contraseña y registrar el fallo ocurren juntos. **Hallazgo de la prueba:** sin esto, 8 intentos simultáneos pasaban todos la comprobación y se verificaban las 8 contraseñas.
6. **Aviso al titular una sola vez** al alcanzar el límite (evento de seguridad, aviso en página y correo). Nunca aparece en la respuesta a quien ataca.
7. **Borde de Nginx** (`error_page 429 = @auth_limite`): el rechazo de ráfaga tiene el mismo JSON que la API, `Retry-After: 1` y las cabeceras de seguridad (la ubicación nombrada las repite porque un `add_header` local anula las del `server`).
8. **Documentación** actualizada: manual de usuario, ficha funcional, tabla de controles de `SEGURIDAD.md`, regla de negocio del TIF y comentario de `AUTH_LOCKOUT_MINUTES` (ahora sólo para la reautenticación).

**Qué no cambia:** login normal (tokens en el cuerpo, o cookie en modo `X-GlucoLume-CSRF`), recuperación de contraseña (`/auth/password/forgot` responde con el límite de login activo), intercambio de Google (`/auth/google/exchange`), MFA, y los tipos de cuenta (consumidor, institucional, administración de plataforma: el límite aplica igual, `acceso=PLATAFORMA` incluido).

**Riesgo residual (decisión que necesito confirmar):**

- **Ataque distribuido a una cuenta:** un atacante con muchas IPs puede probar 5 contraseñas cada 15 min por IP contra una misma cuenta. Antes, el bloqueo global cortaba eso a 3 intentos por ventana, **pero era exactamente el mecanismo que permitía bloquear una cuenta ajena**. Hoy no hay tope global por cuenta: elegí no reintroducirlo porque reabre el bloqueo por terceros que pediste evitar. Si querés un tope global (con ese costo), es un cambio de constante, pero requiere tu aprobación.
- **Origen compartido:** si el proxy del host **no** envía la IP real del cliente, todos llegan a Nginx con la misma IP y el límite por origen se vuelve global. **Verificar en el servidor** (ver §5).
- **Múltiples réplicas:** sin `RATE_LIMIT_REDIS_URL` los contadores son por proceso (igual que el resto de los límites del proyecto). La configuración actual tiene una sola réplica.

**Pruebas:**

- `backend/tests/test_login_throttle.py` (11): la secuencia del auditor (15 intentos: 5 × 401 y 10 × 429 con `Retry-After`), forma consistente del rechazo, respuestas iguales para cuenta existente e inexistente, tercero que no bloquea a la víctima, recuperación al vencer, recuperación de contraseña y Google sin afectación, login normal, tipos de cuenta, y la ventana deslizante exacta.
- `backend/tests/test_login_lockout.py` (16): límite por par, sin renovación, normalización del identificador, límite por identificador, límite de administración, aviso una sola vez, sin correos para cuentas inexistentes, **ráfaga concurrente** (8 hilos: 5 verificados, 3 rechazados), `Retry-After` en cabecera, y la reautenticación sin cambios.
- Actualizadas: `test_auth_access_flows::test_sesiones_denegadas…` y `test_audit_security::test_el_bloqueo_temporal…` (codificaban el bloqueo global de 3 intentos).
- `test_security_hardening::test_nginx_responde_el_limite_de_rafaga…` (nueva).
- **Lo que se midió que falla con la lógica anterior:** el oráculo, el bloqueo por terceros y la renovación (sonda S1–S4, `resultados_login_antes.txt`), y la ráfaga concurrente sin serializar (8 de 8 contraseñas verificadas). Las pruebas nuevas no se ejecutaron contra la lógica anterior: importan módulos que antes no existían.

**Evidencia (`docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/`):**

- `resultados_login_antes.txt`: S1–S4 del estado anterior (oráculo, bloqueo por terceros, renovación).
- `resultados_login_pytest.txt`: salida `-v` de las pruebas del límite (ver §3).
- `resultados_login_borde.txt`: ráfaga de 150 solicitudes en nginx, antes (72 HTML) y después (0 HTML), con la respuesta del borde.
- `resultados_login_nginx_despues.txt` y `sondas_login.sh`: falsificación de `X-Forwarded-For` con 70 pedidos, cada uno con una IP distinta. El 429 aparece en el pedido 46 de esa parte (61 en total): **la cabecera del cliente no evade el límite.** La parte 1 de la sonda (15 intentos) devuelve 500 en el banco sin SQL Server, porque la app falla antes de registrar el fallo; la evidencia de esa parte es la prueba de pytest con base de prueba.

**Rollback:** revertir `backend/app/services/auth.py` (`_loginLocal`), `loginThrottle.py`, la sección de `RateLimiter.retryAfter` y el bloque `error_page` / `@auth_limite` del template. El bloqueo anterior se restaura sin migración de base.

**Cambio de contrato:** el login sigue respondiendo `CUENTA_BLOQUEADA` (429 con `Retry-After`), igual que antes, así que el frontend no cambia. Lo que cambia: cuando la cuenta existe, el quinto fallo desde un origen recibe `401 CREDENCIALES_INVALIDAS` (antes el tercero recibía 429), y el límite es por origen.

### M-3 · Coste de Argon2 y procesamiento de intentos de login (CORREGIDO)

**Diagnóstico (medido en la máquina de prueba: Xeon 2,1 GHz, 4 núcleos, 16 GB; `evidencias/.../bench_argon2.py`):**

1. **Algoritmo y coste.** Argon2id con t=3, m=64 MiB, p=4 (OWASP). Están fijados en `core/security.py` y **no se cambian**. Una verificación cuesta 59 ms de reloj y ~180 ms de CPU (Argon2 con p=4 usa varios núcleos).
2. **Validación previa al hash.** Ya existían topes antes de cualquier operación costosa: identificador ≤254, contraseña de login ≤256 (agregado en M-3 previo), contraseña nueva o cambio ≤128, reautenticación ≤256, y el cuerpo de auth ≤16 KB (B-1). Verificado: un login de 257 caracteres o un identificador de 300 responden 422 sin consultar la base ni calcular Argon2.
3. **Contraseñas excesivamente largas.** La longitud **no es la causa del coste**: 50 ms para 8 caracteres, 53 ms para 100 000. El problema es la *cantidad* de verificaciones simultáneas.
4. **Bloqueos de workers y del event loop.** Los handlers de login son síncronos, así que FastAPI los corre en el threadpool (40 hilos por defecto), no en el event loop (`inspect.iscoroutinefunction` es falso; prueba de regresión). Argon2 libera el GIL: con 8 verificaciones en hilos, el retraso máximo del loop fue ~20 ms. El riesgo real no es el loop sino el **threadpool compartido**: sin límite, las verificaciones podían ocupar los 40 hilos y dejar sin hilo a los endpoints que consultan la base.
5. **Interacción con M-2.** Los intentos limitados por M-2 no calculan Argon2 (prueba de regresión). El rechazo por saturación nuevo **no** cuenta como fallo de contraseña: un equipo ocupado no bloquea usuarios.
6. **Memoria y CPU.** Sin límite: 8 verificaciones simultáneas → 556 MB de pico; 16 → 1068 MB. Con 40 hilos se estimaban ~2,5 GB, sobre una notebook con 16 GB y un contenedor de 512 MB–1 GB (`compose.yaml`).

**Hallazgo adicional, corregido.** En la reescritura de M-2 quité un `db.commit()` que cerraba la transacción de lectura antes de verificar la contraseña. La conexión a SQL Server quedaba ocupada durante Argon2, y con el control nuevo esa espera (hasta 5 s) podía agotar el pool. Prueba de regresión: `test_ninguna_verificacion_ocurre_con_la_transaccion_de_lectura_abierta` (falla en `HEAD`: `[('real', True), ('dummy', True)]`).

**Lo que no se reproduce:** los **2,7–3,5 s** del informe. En esta máquina una verificación cuesta 59 ms. La diferencia probablemente viene de SQL Server en el mismo equipo y de la red tailnet, y hay que medirla en el servidor (§5).

**Solución implementada:**

- `core/security.py`: `_argonSlot` envuelve `hashPassword`, `verifyPassword` y `verifyDummyPassword`. Corren a la vez como máximo `ARGON2_MAX_CONCURRENT` (2), esperan como máximo `ARGON2_MAX_WAITING` (8) y la espera tiene tope de 5 s. Lo que no entra responde **503 `SERVIDOR_OCUPADO`** con `Retry-After: 2`; si la lista de espera está llena, responde de inmediato (no retiene hilos). El lugar se libera también si la operación falla.
- `app/api/errors.py`: `SERVIDOR_OCUPADO` → 503. `loginLocal` no alerta a administradores por este rechazo.
- `_loginLocal`: cierra la transacción antes de cada verificación (real y dummy).
- Configuración: `ARGON2_MAX_CONCURRENT` (1–16) y `ARGON2_MAX_WAITING` (0–64). En una notebook con poca memoria, `ARGON2_MAX_CONCURRENT=1` reduce el pico a ~64 MB a costa de latencia.
- **Sin cambios de coste ni de formato**: los parámetros no cambian, y un hash fijado como literal sigue verificando sin pedir rehash (`test_un_hash_existente_sigue_verificando_sin_rehashearse`).

**Medición (mismo script, `HEAD` frente a la rama; 2 operaciones por hilo):**

| Medida | Sin control (`HEAD`) | Con control |
|---|---|---|
| Verificación (reloj / CPU) | 58,8 ms / 187 ms | 58,8 ms / 179 ms (sin cambio) |
| Longitud 8 → 100 000 caracteres | 50 → 56 ms | 53 → 54 ms (sin efecto) |
| 8 simultáneas: pico de memoria | 556 MB | **171 MB** |
| 8 simultáneas: latencia p50 | 460 ms | **123 ms** |
| 16 simultáneas: pico de memoria | 1068 MB | **172 MB** |
| 16 simultáneas: respuestas | 32 atendidas | 19 atendidas, **13 × 503** |
| Retraso máximo del loop (8 hilos) | 20 ms | 9 ms |

El precio: con 8 simultáneas, la latencia p95 sube (≈770 ms frente a ≈500 ms) porque las últimas esperan su lugar. Con 16, las que exceden la espera reciben 503.

**Pruebas:**

- `backend/tests/test_argon2_gate.py` (17): concurrencia acotada, 503 inmediato con la espera llena, tope de espera sin contar la espera fallida, liberación ante excepciones, cada operación pasa por el control, validación antes del hash, login síncrono, intentos limitados por M-2 sin Argon2, saturación sin contar como fallo, 503 con `Retry-After` por HTTP, coste fijo, compatibilidad de hashes, y transacción cerrada antes de verificar.
- **Regresión comprobada contra `HEAD`** (worktree sin el control): fallan 2 y dan error 7 de las pruebas de concurrencia y saturación (el fixture usa `_argonSlots`, que no existe sin el control); la prueba de transacción falla. Las demás pasan en `HEAD` a propósito: son guardas de comportamiento que ya existía.
- Suite del subconjunto de login/auth (32 archivos, 4 procesos): ver el resultado final en el commit.

**Pendiente (no bloquea el login):**

- **Cambio de contraseña y reset**: `previousPasswordError` verifica la actual y hasta `PASSWORD_HISTORY_SIZE` (3) anteriores, así que un cambio hace hasta 6 verificaciones por pedido (~360 ms de CPU). Está protegido por sesión (cambio) o por token de un solo uso con límite por IP (reset), y el control lo acota. Cerrar la transacción antes de ese bucle exige decidir qué commit corresponde al llamador: queda para una revisión aparte.
- **Medición en el servidor**: la tabla es de la máquina de prueba, sin SQL Server. Medir con `docker stats` durante un login lento y con `bench_argon2.py` en el equipo del servidor antes de fijar `ARGON2_MAX_CONCURRENT`.

### B-1 · Tamaño del cuerpo de las solicitudes (CORREGIDO)

**Inventario (medido, no estimado a mano):** la API es JSON puro. Hay 104 operaciones con cuerpo, todas `application/json`. No hay subida de archivos, ni formularios `multipart`, ni lectura de cuerpo crudo: los dos `is_disconnected` son de SSE. El peor caso legítimo de cada operación se calculó generando el JSON máximo que permite su esquema (`evidencias/.../calcular_tamanos_maximos.py`, `json.dumps` con escapes; salida en `resultados_tamanos_maximos.tsv`):

| Operación | Peor caso legítimo | Límite final |
|---|---|---|
| Ingesta del puente / navegador (`lineas` ≤ 200, texto ≤ 512) | 665 KB / 627 KB | **768 KB** |
| Muestras de medición (`muestras` ≤ 2000) | 196 KB (enteros; hasta ~280 KB con 19 dígitos) | **384 KB** |
| Offboarding (`asignaciones` ≤ 2000 UUID) | ~260 KB | **384 KB** |
| Reglas de matriz (`reglas` ≤ 300) | 96 KB | 160 KB (general) |
| Exportaciones de pacientes/personal | 123 KB (artificial; 22 KB reales) | 160 KB (general) |
| Resto (contacto, vínculos, administración…) | ≤ 25 KB | 160 KB (general) |
| Autenticación | ≤ 12,6 KB | **16 KB** |

**Revisión de `client_max_body_size` y de Pydantic:**
- Nginx tenía `client_max_body_size 1m` global: aceptaba 1 MB en **cualquier** operación, incluidas las de 24 KB. Un 413 de Nginx era HTML.
- Pydantic acota casi todo: `max_length` en strings, `max_length` en listas. Quedaban dos huecos de largo: el patrón `^\s*\d{6}\s*$` de los códigos MFA admite cualquier cantidad de espacios (corregido con `max_length=16`), y los `Decimal` aceptan ceros a la izquierda sin límite en el patrón del OpenAPI (en tiempo de ejecución no se usa ese patrón; lo acota el tope de cuerpo).
- Un falso positivo de mi estimación: el `Offboarding` daba 1,06 MB en el peor caso, pero ese valor usaba UUID con caracteres no ASCII, que el esquema no admite. El real es ~260 KB.

**Solución implementada (acotada, sin límite global de 1 MB):**
1. `client_max_body_size 160k` como tope general (antes 1m).
2. Tramos por operación con lotes legítimos grandes, con el mismo proxy que `/api/` y las mismas cabeceras ocultas de B-3: ingesta (`bridge|browser/ingest`) 768k, muestras 384k y offboarding 384k.
3. Autenticación: 16k (ya en el commit de B-1 previo); su `error_page` también declara el 413 (si no, el de la ubicación reemplaza al del server).
4. 413 en formato JSON de la API: `error_page 413 = @cuerpo_grande` devuelve `{"codigo":"CUERPO_DEMASIADO_GRANDE","detail":"…"}`. El frontend muestra el `detail` cuando no conoce el código.
5. Pydantic: `max_length=16` en los dos códigos MFA con patrón de espacios.

**Códigos de error:** el tamaño lo corta Nginx con **413** en JSON. Los errores de contenido los responde la API con **422** (validación: listas fuera de rango, JSON inválido, campos fuera de esquema). La prueba `test_cuerpo_fuera_de_esquema_responde_422_no_413` cubre esa diferencia.

**Antes y después (mismo backend, mismos pedidos de tamaño exacto, `sondas_tamano_cuerpo.sh`):**

| Caso | Antes (HEAD) | Después |
|---|---|---|
| Contacto, 163 840 B (bajo 160k) | llega al backend | llega al backend |
| Contacto, 163 841 B (160k + 1) | llega al backend | **413 JSON** |
| Contacto, 1 000 000 B | llega al backend | **413 JSON** |
| Login, 16 384 B | llega al backend | llega al backend |
| Login, 16 385 B | 413 **HTML** | **413 JSON** |
| Puente, 786 432 B (bajo 768k) | llega al backend | llega al backend |
| Puente, 786 433 B (768k + 1) | llega al backend | **413 JSON** |
| Muestras, 393 217 B (384k + 1) | llega al backend | **413 JSON** |
| Offboarding, 393 217 B (384k + 1) | llega al backend | **413 JSON** |

Los casos "llega al backend" devuelven 422 o 500 según el caso; el 500 es del entorno de prueba (sin SQL Server), no del tamaño.

**Compatibilidad verificada:**
- El lote más grande legítimo del puente (665 KB) cabe en 768 KB; el mayor por operación cabe en su tramo con margen.
- Mediciones, matrices, exportaciones, registros, formularios y funciones institucionales: mismos contratos. Ninguna operación cuyo peor caso legítimo supere su tope.
- Frontend: sin cambios de código. No reejecuté su suite en esta fase (no tocó ningún archivo del frontend).

**Pruebas:** `test_tamano_solicitudes.py` (14: cerca y por encima de cada límite de elementos, código MFA, 422 para JSON inválido), y en `test_security_hardening.py` los tres tests de tramos, 413 JSON y el tope de autenticación. Contra HEAD fallan los que dependen del cambio. Resultados en `evidencias/.../resultados_pruebas_b1.txt`.

**Riesgos y rollback:** el riesgo es rechazar un cuerpo legítimo grande que hoy pasa. Está medido: ninguna operación supera su tope legítimo. Rollback: restaurar `client_max_body_size 1m` y quitar los tramos y el `error_page 413`.

**Pendiente (no es parte de B-1):** el puente decodifica las líneas con `errors="replace"`, y cada byte no ASCII viaja como `\ufffd` (6 bytes en JSON). Si el puente usara `errors="ignore"` o un carácter ASCII, el peor caso bajaría de 665 KB a ~110 KB. Es un cambio del software del puente, que se despliega en Windows: se propone aparte.

### B-2 · Soft 404 (PENDIENTE)

- **Diagnóstico (medido):** `/ruta-inexistente`, `/.git/config`, `/phpinfo.php` → `200 text/html` (index de la SPA). No hay fuga de contenido: son el mismo HTML de la SPA.
- **Ya presente:** `X-Robots-Tag: noindex` en `/login`, `/registro`, `/app`, `/plataforma`, `/administracion` (mapa `$robots_tag`).
- **Pendiente:** devolver 404 real exige la lista de rutas de la SPA (`frontend/src/App.jsx`). Una ruta omitida daría 404 de estado aunque la SPA la renderice. Requiere inventario y decisión.

### B-3 · Cabeceras de seguridad duplicadas (CORREGIDO)

**Diagnóstico (medido, `evidencias/.../resultados_cabeceras_antes.txt` y `resultados_politicas_antes.txt`):** en `a3908c0`, las respuestas de la API recibían `Content-Security-Policy` ×2, `Referrer-Policy` ×2 y `X-Content-Type-Options` ×2; `/docs` recibía `X-Content-Type-Options` ×2.

**Componentes que generan cada cabecera:**

| Cabecera | Nginx (`docker/nginx/default.conf.template`) | Backend (`app/api/securityHeaders.py`) |
|---|---|---|
| Content-Security-Policy | Server (SPA), `/docs`, respuesta de ráfaga | `API_CSP` solo en rutas `/api/` |
| Referrer-Policy | Server, `/docs`, SSE | `no-referrer` solo en rutas `/api/` |
| X-Content-Type-Options | Server y cada ubicación con `add_header` | `nosniff` en todas las respuestas |
| Strict-Transport-Security | Server (según `$fwd_proto`) | En producción, si el pedido es HTTPS |

**Análisis de compatibilidad:**
- **CSP duplicada en la API:** el navegador aplica las dos, es decir, la intersección. Como la del backend es `default-src 'none'`, la intersección equivale a `'none'` para cualquier recurso. No había restricciones inesperadas, pero la política efectiva dependía de dos fuentes.
- **Referrer-Policy duplicada:** el navegador usa la **última** cabecera válida. Nginx venía después del backend, así que la efectiva era `strict-origin-when-cross-origin`; el `no-referrer` del backend nunca tuvo efecto.
- **X-Content-Type-Options:** mismo valor en ambas fuentes; sin efecto funcional.
- **Riesgo de corregir mal:** quitar la CSP del backend sin cuidado habría **debilitado** la API (la intersección era más estricta que la política de la aplicación sola). Por eso la corrección no la descarta: la elige.

**Solución implementada (cambio mínimo):**
1. **Un único punto de decisión para la CSP:** `map $request_uri $csp_value` en nginx. `/api` y `/api/…` reciben exactamente `API_CSP`; el resto, la política de la aplicación. La cadena de la API aparece una sola vez en la plantilla, y una prueba verifica que sea igual a `API_CSP`.
2. **Las ubicaciones proxy descartan las cabeceras que el backend repite** (`proxy_hide_header`, de la corrección anterior). La CSP del backend ya no se pierde: nginx la reemplaza por la misma política.
3. **Cabeceras que faltaban** (porque su `add_header` propio anula las del server): `Permissions-Policy` en SSE y `X-Frame-Options` + `Permissions-Policy` en `/docs`.
4. **Sin cambios** en la política de la aplicación, en Referrer-Policy, en HSTS ni en las páginas de error de nginx (fuera de la CSP que ahora se elige por ruta).

**Diferencias que se conservan:** la API recibe su política estricta (`default-src 'none'`); la SPA y los estáticos, la de la aplicación; `/docs` tiene la suya (permite cdn.jsdelivr.net para Swagger); la respuesta de ráfaga de autenticación usa la de la API.

**Antes y después (política efectiva por respuesta, `resultados_politicas_*.txt`):**

| Respuesta | CSP antes | CSP después | Referrer antes → después |
|---|---|---|---|
| API JSON (`/api/…`) | intersección de dos (efectiva: `'none'`) | `default-src 'none'; frame-ancestors 'none'` | `no-referrer` + `strict-…` → `strict-…` (efectiva igual) |
| SSE `/api/v1/acquisition/stream` | igual que la API | igual (backend) | igual |
| Redirección `/api` | política de la app | política de la API | igual |
| SPA, estáticos, 404 de nginx | política de la app | sin cambio | sin cambio |
| `/docs` | sin cambio | sin cambio | sin cambio |

**Matriz de cabeceras (conteo por respuesta, `resultados_cabeceras_*.txt`):** antes, CSP, Referrer y XCTO ×2 en la API; después, todas ×1 en las 15 respuestas medidas.

**Funcionamiento verificado** (`resultados_pruebas_b3.txt` y `resultados_errores_y_oauth.txt`):
- **Frontend:** SPA en Chromium con 0 violaciones de CSP y 0 errores de consola en las 8 páginas del SPA, antes y después. Vitest: 856 de 857; la que falla es un timeout de 5 s ajeno a las cabeceras.
- **Backend:** 111 pruebas de cabeceras, errores, OAuth (SQLite) y cookies pasan.
- **OAuth:** el inicio devuelve `302` a `accounts.google.com` con los mismos parámetros antes y después. El callback responde 500 en ambos casos por falta del driver ODBC del contenedor de prueba; su lógica se prueba con SQLite.
- **Páginas de error:** el 502 con backend caído conserva las cabeceras de seguridad. El 429 de ráfaga pasó de HTML sin `Retry-After` a JSON con `Retry-After: 1`, con las cabeceras completas.

**Pendiente de verificar en el servidor:** Caddy (perfil `https`) declara HSTS con `header`, que reemplaza el valor de la respuesta, así que no debería duplicarse. No lo pude probar aquí porque no hay Docker. Verificar con `curl -sI https://<dominio>/` que aparezca una sola `Strict-Transport-Security`.

**Rollback:** revertir el commit (plantilla y pruebas). No hay cambios de datos ni de API.

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
| M-3 control Argon2 | Login con más de 2 verificaciones en curso responde 503 tras 8 en espera; la latencia sube en pico | `ARGON2_MAX_CONCURRENT` / `ARGON2_MAX_WAITING`, o quitar `_argonSlot` en `core/security.py` |

**Despliegue:** requiere reconstruir la imagen `frontend` (la plantilla se procesa al arrancar el contenedor) y reiniciar el backend por el cambio de esquema. **No hay migraciones de base de datos.**

## 5. Decisiones pendientes

1. **M-2:** ¿mantener 60/10 min por IP, bajar a ~20/10 min, o agregar zona de Nginx para login (~10 r/min)?
2. **M-4:** aprobar el diseño de la sección correspondiente (fragmento + POST + ventana de transición).
3. **B-3:** confirmar que Nginx sea el único emisor de la CSP de la API.
4. **B-1:** medir el lote real del puente antes de bajar `/api/` de 1 MB.
5. **B-6:** confirmar que no se publica la readiness.
