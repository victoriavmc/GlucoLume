# Anexo C: análisis de infraestructura y plan de remediación

Fecha: 07/11/2026. Alcance: Ubuntu Server en la notebook HP, Docker Compose, Nginx, FastAPI, SQL Server y Tailscale.

**Cómo leer esta tabla.** Cada hallazgo tiene una de tres fuentes:

- **Repo**: confirmado leyendo los archivos de configuración del repositorio.
- **Banco**: medido en el contenedor de trabajo (dependencias y pruebas de Nginx). No es el servidor.
- **Diagnóstico**: depende del estado real del servidor. Se resuelve con los scripts de [README.md](README.md) (no ejecutados aún).

La severidad asume el uso real del equipo: un servidor de demostración con datos de salud de pacientes, y el mismo equipo es estación de trabajo.

## 1. Resumen

| Severidad | Hallazgo | Fuente | Estado |
|---|---|---|---|
| **Alta** | Sin procedimiento de respaldo para la base en el servidor Ubuntu (todo lo documentado es para Windows) | Repo | Abierto |
| **Alta** | Puertos publicados fuera de loopback, y UFW no filtra puertos publicados por Docker | Repo + Diagnóstico | Verificar (`02`, `01` §5) |
| **Alta** | Quien pertenezca al grupo `docker` tiene root en el host y puede leer los secretos de cada contenedor | Repo + Diagnóstico | Verificar (`02`, `01` §9) |
| **Media** | Disco de la notebook sin cifrado (si no hay LUKS, pérdida o robo expone datos y secretos) | Diagnóstico | Verificar (`01` §10b) |
| **Media** | Parches de seguridad de Ubuntu pendientes y posible reinicio pendiente | Diagnóstico | Verificar (`01` §1) |
| **Media** | Acceso remoto: Tailscale sin revisar (Funnel, ACL, expiración de clave) y SSH sin revisar | Diagnóstico | Verificar (`01` §7, §8) |
| **Media** | Secretos en `.env` en texto plano sobre disco sin cifrar; permisos no verificados | Repo + Diagnóstico | Verificar (`01` §9) |
| **Media** | Vulnerabilidades del sistema base de la imagen del backend (zlib y 44 HIGH) sin parche en Debian | Repo (Trivy 23/10) | Riesgo aceptado con mitigación (H-10) |
| **Media** | Escaneo de imágenes desactualizado (último el 23/10/2026) | Repo | Pendiente de repetir |
| **Baja** | `DESPLIEGUE.md` §6 dice que las bases no se fijan por digest; los Dockerfile sí | Repo | Documentación |
| **Informativa** | SQL Server Express sin TDE ni respaldos cifrados (H-03) | Repo | Abierto desde la auditoría de octubre |

Fortalezas confirmadas en el repo, para no sobredimensionar lo que falta: ver §3.

## 2. Hallazgos

### 2.1 Respaldos de la base sin procedimiento en Ubuntu (Alta)

- **Repo:** `docs/BASE_DE_DATOS.md` y `docs/SEGURIDAD.md` describen respaldos con tareas programadas de Windows, `GlucoLume_respaldo.ps1`, `copia_docker.ps1` (que copia desde el contenedor hacia Windows) y cifrado con DPAPI. Nada de eso corre en Ubuntu. `docs/DESPLIEGUE.md` §4 (servidor Linux) no menciona respaldos.
- **Riesgo real:** si la base vive en el volumen `mssql-data` de Docker (perfil `db`), un fallo de disco de la notebook o un `docker compose down -v` la destruyen sin copia. Si la base es una instancia de Windows, el servidor Ubuntu no tiene ningún respaldo propio.
- **Qué confirmar:** `04_sqlserver.sh` (último respaldo por base y si está cifrado) y la respuesta a la pregunta 3 del README.
- **Remediación (fase 2):** procedimiento Linux que usa `BACKUP DATABASE ... WITH CHECKSUM, INIT` dentro del contenedor (no copiar el volumen en crudo), cifrado con `openssl enc -aes-256-cbc -pbkdf2` o `gpg`, copia fuera del equipo, y restauración de prueba en un contenedor descartable. Edición Express: sin compresión ni cifrado nativo, por eso el cifrado es externo.
- **Rollback:** es aditivo; no toca la base. Se borran copias antiguas solo después de verificar una restauración.

### 2.2 Puertos publicados y firewall (Alta, condicional)

- **Repo:** la configuración por defecto publica el frontend en `127.0.0.1` (`FRONTEND_BIND=127.0.0.1` en `compose.yaml` y `.env.example`). El backend y SQL Server no publican puertos en producción (solo en `compose.dev.yaml`, en loopback). Caddy publica 80 y 443 en todas las interfaces, pero solo con el perfil `https`.
- **Riesgo real:** Docker escribe sus propias reglas en `iptables`, antes que UFW. Un puerto publicado sin `127.0.0.1` queda abierto aunque UFW diga `deny`. La única forma de filtrarlo es la cadena `DOCKER-USER`.
- **Qué confirmar:** `02_docker_host.sh` (columna PORTS) y `01_ubuntu_host.sh` §5 (`ss -tulpn` busca `0.0.0.0` y `[::]`).
- **Remediación (fase 1):** si se publica en `0.0.0.0` sin necesidad, volver a `127.0.0.1` y acceder desde el tailnet. Si el perfil `https` no se usa, no levantarlo. Política de UFW: denegar entrante por defecto y permitir SSH; conviene hacerlo desde la consola física o con una sesión SSH abierta.
- **Rollback:** restablecer `FRONTEND_BIND`, `docker compose up -d frontend` en ventana. Para UFW: `ufw disable` desde la consola física.

### 2.3 Grupo `docker` y exposición de secretos (Alta, condicional)

- **Repo:** los secretos llegan a los contenedores por `env_file` (`.env`) y `docker/db.env`. Eso los deja en el entorno de cada contenedor, que `docker inspect` muestra. Quien pueda ejecutar `docker` puede leerlos y, además, montar `/` en un contenedor.
- **Riesgo real:** en un equipo con más de una cuenta humana, cualquier miembro del grupo `docker` es root en la práctica.
- **Qué confirmar:** `02` (`ls -l /var/run/docker.sock` y miembros del grupo) y `01` §8 (cuentas humanas).
- **Remediación (fase 1):** dejar en el grupo solo la cuenta que opera el servicio; usar `sudo` para el resto. Si hubo acceso no autorizado, rotar los secretos. Rootless Docker o `userns-remap` son migraciones: fuera de alcance.
- **Rollback:** `gpasswd -a <usuario> docker` restablece el acceso.

### 2.4 Disco de la notebook sin cifrado (Media, diagnóstico)

- **Riesgo real:** un equipo portátil que se pierde o se roba expone la base (si está en el disco), los respaldos y el `.env`.
- **Qué confirmar:** `01` §10b (`lsblk` busca volúmenes `crypt`).
- **Remediación:** cifrar en sitio requiere reinstalar o migrar el sistema; no se propone sin tu aprobación. Mientras tanto: los respaldos cifrados fuera del equipo (2.1) reducen el daño, y el `.env` debe tener permisos restrictivos (2.5).
- **Estado:** riesgo aceptado hasta una migración, justificado por la restricción de no reinstalar. Documentar la decisión.

### 2.5 Secretos en `.env` y permisos (Media)

- **Repo:** `.env` y `docker/db.env` están en `.gitignore` y **no hay secretos versionados** (verificado en el historial completo: `git log --all` sin resultados para `.env`, `*.pem`, `*.key`, `db.env`). `docker/certs/` tiene solo un `.gitignore`.
- **Riesgo real:** los permisos del archivo en el servidor no se pueden ver desde el repo. Si `.env` es legible por todos, cualquier usuario local lo lee.
- **Qué confirmar:** `01` §9 (`stat` de `.env`, `docker/db.env` y `docker/certs/`; nombres de variables; claves de ejemplo sin cambiar; `DATABASE_URL` duplicada). En producción, la aplicación no arranca con `SESSION_SECRET` de menos de 32 caracteres, ni con secretos iguales entre sí (`reusedSecrets`, GL-20).
- **Remediación (fase 1):** `chmod 600` sobre `.env` y `docker/db.env`, con el propietario que ejecuta `docker compose` (si es otro usuario, `640` con el grupo correcto). Rotar cualquier valor de ejemplo que siga vigente.
- **Rollback:** `chmod 640` o el modo anterior; no hay cambio funcional.

### 2.6 Parches de Ubuntu y reinicio pendiente (Media, diagnóstico)

- **Riesgo real:** un sistema sin parches de seguridad es el vector más común en servidores pequeños.
- **Qué confirmar:** `01` §1 (`apt list --upgradable`, origen de seguridad, `reboot-required`, estado de `unattended-upgrades`). El script no ejecuta `apt-get update`: usa la caché actual, que puede estar vieja. Si está vieja, el resultado subestima los pendientes.
- **Remediación (fase 1):** `sudo unattended-upgrade --dry-run -d` para ver qué instalaría; luego aplicar solo los de seguridad en una ventana planificada. Si hay kernel nuevo, reiniciar en esa ventana, con la base y los servicios detenidos de forma ordenada (`docker compose stop`).
- **Rollback:** el kernel anterior queda en GRUB; `apt` guarda el historial (`/var/log/apt/history.log`) para revertir paquetes concretos.

### 2.7 Tailscale: Serve, Funnel, ACL y claves (Media, diagnóstico)

- **Repo:** no hay configuración de Tailscale en el repo; es configuración del servidor y de la consola de administración.
- **Riesgo real:** Funnel publicaría el servicio en Internet abierta. Una ACL permisiva deja que cualquier equipo del tailnet llegue al servidor. Una clave de nodo que no expira mantiene el acceso indefinidamente si el equipo se compromete.
- **Qué confirmar:** `01` §7 (`tailscale serve status`, `tailscale funnel status`, preferencias). Manual: ACL, roles de administrador y expiración de la clave (preguntas 2 del README).
- **Remediación (fase 1):** `tailscale funnel off` si está activo. ACL mínima: solo tus equipos a `:443` del servidor. Desactivar la expiración de la clave solo si el servidor no tiene administración remota; si la hay, mantener la expiración y renovarla.
- **Rollback:** la consola de Tailscale guarda el historial de ACL; `tailscale funnel` se vuelve a activar con el mismo comando.

### 2.8 SSH (Media, diagnóstico)

- **Riesgo real:** autenticación por contraseña y `PermitRootLogin yes` son la puerta de entrada más probable.
- **Qué confirmar:** `01` §8 (`sshd -T`, intentos fallidos, claves autorizadas por usuario sin mostrarlas).
- **Remediación (fase 1):** `PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers <usuario>`. Antes de recargar: `sudo sshd -t`, copia de `sshd_config`, y una sesión SSH abierta de respaldo. Usar `systemctl reload ssh`, no `restart`.
- **Rollback:** restaurar la copia de `sshd_config`, `sshd -t` y `systemctl reload ssh` desde la sesión abierta.

### 2.9 Imagen del backend: zlib y HIGH del sistema base (Media, riesgo aceptado)

- **Repo:** `docs/evidencias/validacion_integral/resultados/ESCANEO_TRIVY_2026-10-23.md`: la base `python:3.14-slim-trixie` tiene 44 HIGH y `zlib1g` (CVE-2026-85091) sin corrección publicada por Debian a esa fecha. La imagen de Nginx del frontend tiene 0. El `Dockerfile` del backend ya acepta `ZLIB_MIN_VERSION` para fallar el build cuando Debian publique la corrección (H-10).
- **Mitigación presente:** contenedor de solo lectura, `cap_drop: ALL`, `no-new-privileges`, usuario no root (10001), sin puertos publicados, red interna.
- **Remediación:** reconstruir con `--pull` al menos una vez al mes y antes de cada despliegue (ya lo indica `DESPLIEGUE.md` §6), y repetir el escaneo sobre la imagen que se despliega (`03`, `anexo_c/README.md`).
- **Rollback:** conservar la etiqueta anterior (`GLUCOLUME_VERSION`); volver a ella con `docker compose up -d` en ventana.

### 2.10 Escaneo de imágenes desactualizado (Media)

- **Repo:** el último escaneo documentado es del 23/10/2026. Desde entonces pudieron aparecer CVE nuevos y Debian pudo publicar la corrección de zlib.
- **Remediación:** repetir el escaneo de las imágenes **desplegadas** (no solo de las bases) en la fase 2. Mismo criterio: documentar cada HIGH y CRITICAL con estado (corregible, sin corrección, no aplicable).

### 2.11 Documentación desactualizada sobre digest (Baja)

- **Repo:** `DESPLIEGUE.md` §6: "Las bases se fijan por etiqueta de rama … fijarlas por digest es una mejora pendiente". Los tres Dockerfile (backend, frontend, mssql, firmware) ya fijan digest.
- **Remediación:** corregir el párrafo en la fase 1. Sin cambio de código.

### 2.12 SQL Server Express en Windows (Informativa)

- **Repo:** `docs/SEGURIDAD.md` H-03: sin TDE ni respaldos cifrados (Express no los admite). Abierto desde octubre.
- **Qué confirmar:** `04` caso B (alcance de red desde Ubuntu) y las consultas manuales en Windows: `sa` deshabilitado, sin logins de `sysadmin` para la aplicación, `xp_cmdshell` apagado, y 1433 permitido solo desde la IP del servidor en el firewall de Windows.
- **Validación de TLS ya implementada:** en producción el backend rechaza `DB_TRUST_SERVER_CERTIFICATE=true` (`config.py`), y el driver `msodbcsql18` cifra por defecto.
- **Remediación:** la de H-03 (BitLocker y respaldos cifrados externos) corresponde al administrador de Windows, no al servidor Ubuntu.

## 3. Fortalezas confirmadas en el repo

- `cap_drop: ALL` y `no-new-privileges` en backend, lifecycle, notifications, frontend, redis y technical-retention. La excepción documentada es el contenedor `db`, que necesita capacidades de archivo para `sqlservr`.
- `read_only: true` en todos los servicios de aplicación; `tmpfs` solo para `/tmp` y la configuración de Nginx.
- Redes separadas: `edge` (frontend y proxy) y `data` (backend y base). El frontend no alcanza la base.
- Puertos del backend y de SQL Server **sin publicar** en la configuración de producción.
- Imágenes fijadas por digest, usuarios no root (backend 10001, Nginx 101), `HEALTHCHECK` en el backend.
- Logs: `json-file` con rotación de 10 MB × 5 por contenedor. El backend se arranca con `--no-access-log`. Nginx registra la IP anonimizada a /24 y sin query (los tokens de los enlaces de un solo uso no quedan en el log).
- Privilegio mínimo en la base: cuentas separadas por servicio (`DB_USER`, `DB_JOBS_*`, `DB_RETENCION_*`), y la API no recibe las cuentas de los jobs.
- Secretos fuera de Git, y verificado sin historial.
- Validación al arrancar en producción: `SESSION_SECRET` de al menos 32 caracteres, secretos distintos entre sí, `DB_JOBS_USER` distinto de `DB_USER`, y `DB_TRUST_SERVER_CERTIFICATE` no admitido en producción (`backend/app/core/config.py`).
- Dependencias: `pip-audit` sobre los 44 paquetes del lock del backend, **0 vulnerabilidades conocidas**; `npm audit --omit=dev` del frontend, **0**. (07/11/2026, en el banco.)

## 4. Plan de remediación gradual

Ningún paso requiere reinstalar ni migrar. Cada fase se puede detener sin dejar el servicio roto.

**Fase 0: diagnóstico (solo lectura, ahora).** Ejecutar `01` a `04`, responder las cuatro preguntas del README y compartir las salidas. Criterio de paso a la fase 1: se tienen las salidas completas y las respuestas manuales.

**Fase 1: bajo riesgo, reversible, sin cortes (ventana corta, una cosa a la vez).**

| Paso | Acción | Rollback |
|---|---|---|
| 1.1 | Dejar el grupo `docker` solo con la cuenta del servicio (2.3) | `gpasswd -a <usuario> docker` |
| 1.2 | `chmod 600` a `.env` y `docker/db.env` con el propietario correcto (2.5) | `chmod 640` o modo anterior |
| 1.3 | `FRONTEND_BIND=127.0.0.1` si estaba en `0.0.0.0` (2.2) | Volver al valor anterior y `docker compose up -d frontend` |
| 1.4 | Tailscale: `funnel off`, ACL mínima, revisar expiración de la clave (2.7) | Historial de ACL de la consola |
| 1.5 | SSH: solo claves, sin root, `sshd -t`, `reload` con sesión de respaldo (2.8) | Copia de `sshd_config` y `reload` |
| 1.6 | Parches de seguridad de Ubuntu con `unattended-upgrade --dry-run` primero (2.6) | Kernel anterior en GRUB; historial de apt |
| 1.7 | UFW: denegar entrante y permitir SSH **antes** de habilitarlo (2.2) | `ufw disable` desde la consola física |
| 1.8 | Corregir `DESPLIEGUE.md` §6 sobre el digest (2.11) | Revertir el commit |

Verificación después de cada paso: `01` §5 y §8 no muestran cambios no esperados, y `curl -sI` al servicio responde igual.

**Fase 2: ventana planificada (requiere tu decisión).**

| Paso | Acción | Rollback |
|---|---|---|
| 2.1 | Procedimiento de respaldo Linux (2.1), y una restauración de prueba en un contenedor descartable | No afecta la base; borrar copias solo tras verificar |
| 2.2 | Reconstruir las imágenes con `--pull` y repetir el escaneo de las imágenes desplegadas (2.9, 2.10) | Volver a la etiqueta anterior |
| 2.3 | Rotar los secretos **solo si** el diagnóstico muestra acceso no autorizado | Mantener los valores anteriores fuera de línea hasta verificar; el cambio requiere reiniciar los servicios |

**Fase 3: fuera de alcance sin tu aprobación.**

- Cifrado de disco (LUKS) y rootless Docker: requieren reinstalación o migración. Se documentan como riesgo aceptado (2.4).
- Remediación de SQL Server (H-03): corresponde al administrador de Windows.

## 5. Qué no se puede concluir sin el servidor

Lo que este análisis no puede confirmar, y por qué:

- La versión real y los parches de Ubuntu (depende de la caché del servidor).
- Los puertos realmente abiertos y las reglas de Docker en `iptables` (depende del servidor).
- Quién tiene acceso al grupo `docker`, SSH y Tailscale (depende de la configuración del servidor y de la consola).
- Si el `.env` tiene permisos seguros y si el disco está cifrado.
- La configuración real de `tailscale serve` y de Funnel.

Todo lo anterior queda marcado como **Diagnóstico** en la tabla del resumen, y no se considera resuelto hasta que las salidas lo confirmen.
