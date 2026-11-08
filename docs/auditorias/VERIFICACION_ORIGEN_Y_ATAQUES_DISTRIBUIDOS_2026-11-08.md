# Origen del intento, cabeceras no confiables y riesgo de ataques distribuidos (08/11/2026)

Alcance: el límite por (cuenta, origen) de M-2 depende de la IP que la aplicación considera «origen». Este documento verifica cómo se
determina esa IP detrás de Nginx, de Caddy (perfil `https`) y de Tailscale Serve, y qué riesgo queda cuando el atacante usa muchos orígenes.

## Cadena de confianza

1. **Nginx** (`docker/nginx/default.conf.template`): `set_real_ip_from ${TRUSTED_PROXY_CIDR}` y `real_ip_header X-Forwarded-For`. Solo un
   par dentro de `TRUSTED_PROXY_CIDR` puede aportar una IP de origen; cualquier otro par se usa tal cual. En **todas** las ubicaciones,
   Nginx reenvía `X-Forwarded-For` con `proxy_set_header X-Forwarded-For $remote_addr`, es decir, **sobrescribe** la cabecera del
   cliente con una sola IP.
2. **Backend** (`uvicorn --proxy-headers`, `FORWARDED_ALLOW_IPS="*"` en `compose.yaml`): toma la IP de `X-Forwarded-For` de cualquier par.
   La aplicación usa `request.client` (`origenDe`, `loginThrottle.py`), nunca una cabecera directamente.
3. **Compose**: el frontend (Nginx) publica su puerto en `${FRONTEND_BIND:-127.0.0.1}` (solo loopback por defecto). El backend **no** se publica.
4. **Caddy** (perfil `https`): `reverse_proxy frontend:8080` sin configuración de cabeceras, es decir, el comportamiento por defecto:
   **añade** la IP del cliente a la `X-Forwarded-For` que llega, no la reemplaza. Nginx toma la IP más a la derecha que no sea de confianza:
   la del cliente real. Es el comportamiento documentado de Caddy; **no se ejecutó Caddy aquí**.
5. **Tailscale Serve** (edge del servidor, fuera del repo): no verificado. Depende de si Serve **reemplaza** o **añade** a `X-Forwarded-For`.

## Pruebas realizadas (Nginx real de la plantilla, con un backend de eco)

| Caso | Par que ve Nginx | Configuración de confianza | `X-Forwarded-For` forjada | Origen que recibe el backend |
|---|---|---|---|---|
| Cliente en loopback | 127.0.0.1 | por defecto (`172.16.0.0/12`) | `198.51.100.77` | `127.0.0.1` (la cabecera forjada se descarta) |
| Par dentro del rango de confianza | 127.0.0.1 | `127.0.0.0/8` (simula un proxy de confianza) | `198.51.100.77`, luego `…91`, `…92` | `198.51.100.77`, `…91`, `…92`: **acepta lo que mande el cliente** |
| Backend directo (sin Nginx) | cliente | `FORWARDED_ALLOW_IPS="*"` (uvicorn) | `198.51.100.55`; con dos saltos `198.51.100.56, 10.9.9.9` | `198.51.100.55`; `198.51.100.56` (toma el primero, controlado por el cliente) |

**Conclusión de la verificación:**

- Por el camino normal (Nginx como primer salto), el origen no se puede forjar mientras el par que ve Nginx **no** esté en `TRUSTED_PROXY_CIDR`.
- Si el par **sí** está en esa lista, Nginx confía en `X-Forwarded-For` y el origen se puede forjar en cada pedido. Eso anula el límite por origen.
- La lista por defecto (`172.16.0.0/12`) es **toda la red de Docker**. Si el tráfico del host llega a Nginx desde la pasarela del puente (según el modo
  de red de Docker, p. ej. el proxy de usuario, o cuando el edge corre en el host), ese par cae dentro de la lista y el origen queda **forjable**.
  No pude reproducir ese camino exacto en este sandbox; sí el mecanismo.
- El backend directo, si un contenedor de la misma red lo alcanza, acepta cualquier origen: `FORWARDED_ALLOW_IPS="*"` no debe quedar en producción.

## Controles que hacen falta antes de desplegar (no implementados en esta etapa)

1. **`TRUSTED_PROXY_CIDR` exacto**: la IP o el /32 del proxy que de verdad conecta con Nginx (Caddy o el edge del host), no el rango completo de Docker.
   Es un valor de despliegue; no se puede inferir desde el repo.
2. **`FORWARDED_ALLOW_IPS` = IP del contenedor Nginx**, no `"*"`, para que el backend solo confíe en Nginx.
3. **Tailscale Serve**: confirmar en el servidor que reemplaza `X-Forwarded-For` (o que la añade a la derecha), y que el puerto de Nginx no es alcanzable
   desde fuera del host.
4. Opcional: `header_up X-Forwarded-For {client_ip}` en el Caddyfile, para reemplazar en lugar de añadir.

Verificación de solo lectura en el servidor (no modifica nada):

```bash
tailscale serve status
docker port <contenedor-frontend>
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' <contenedor-frontend>
docker exec <contenedor-frontend> nginx -T 2>/dev/null | grep -n "set_real_ip_from\|real_ip_header"
# desde otra máquina de la tailnet, un pedido con cabecera forjada; el backend no la debe reflejar en el origen del límite:
curl -s -H "X-Forwarded-For: 198.51.100.77" https://<host>/api/v1/healthz
```

## Riesgo residual de ataques distribuidos

El límite es por (cuenta, origen). Un atacante con N orígenes independientes obtiene 5 intentos por origen en cada ventana de 15 min contra la misma
cuenta. Eso da hasta **5·N intentos cada 15 min** contra una cuenta, y la cuenta no queda bloqueada para su titular ni para terceros (es lo que M-2 pidió).

Orden de magnitud (estimación, no medida en producción): el servidor verifica como máximo 2 contraseñas en paralelo (M-3) y cada verificación Argon2 tarda
del orden de cientos de milisegundos. Con esa capacidad, un botnet de decenas de miles de orígenes no está limitado por el rate limit, sino por la capacidad
de verificación del servidor. **La defensa real contra adivinación en esa escala es la fortaleza de la contraseña y la MFA**, no el límite por origen.

Controles complementarios propuestos (no incorporados, para decisión posterior):

- Límite global por cuenta a un umbral alto (p. ej. 50 fallos/hora sumados de todos los orígenes), con respuesta que no revele el bloqueo a terceros.
  Riesgo: reintroduce un bloqueo entre orígenes de corta duración; debe aprobarse explícitamente.
- Verificación adicional (CAPTCHA o prueba de trabajo) tras N fallos de una cuenta desde orígenes distintos.
- Bloqueo en el edge por reputación de IP (fail2ban, Cloudflare o similar): infraestructura, fuera del alcance de este cambio.
- Aviso a la persona titular ya existe (correo y aviso en la página, acotado por ventana): sirve de detección, no de contención.

## Estado

- Código: el origen se toma de `request.client`, que es lo que el proxy de confianza informa. No hay una cabecera del cliente usada directamente.
- Vulnerabilidad crítica que requiera intervención inmediata: **no identificada en el código**. El riesgo de origen forjable depende de la configuración
  de despliegue (`TRUSTED_PROXY_CIDR`, `FORWARDED_ALLOW_IPS`, Tailscale) y debe verificarse antes de desplegar, no antes de integrar.
