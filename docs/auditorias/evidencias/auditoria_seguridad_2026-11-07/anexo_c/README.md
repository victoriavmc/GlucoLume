# Anexo C: diagnóstico de infraestructura (Ubuntu, Docker, dependencias)

Procedimiento de **solo lectura** para ejecutar en el servidor (notebook HP con Ubuntu Server, Docker Compose, Tailscale y SQL Server).
No actualiza, no reinicia, no cambia el firewall, no modifica Docker Compose ni los contenedores y no imprime valores de secretos
(solo nombres de variables, permisos y conteos). La clasificación y el plan de remediación están en
[ANALISIS_Y_REMEDIACION.md](ANALISIS_Y_REMEDIACION.md).

## Dónde se ejecuta cada script

| Script | Dónde | Permisos | Cubre (Anexo C) |
|---|---|---|---|
| `01_ubuntu_host.sh` | **Ubuntu** (host) | `sudo` (sshd, ufw, nft, logs de autenticación) | 1 sistema y actualizaciones, 5 puertos y firewall, 7 Tailscale, 8 SSH, 9 secretos (nombres), 10 permisos y copias, 10b cifrado del disco, 12 logs del host |
| `02_docker_host.sh` | **Ubuntu** (host), con el usuario del grupo `docker` o `sudo` | solo lectura de Docker | 3 imágenes, 4 usuarios y capacidades, 5 puertos publicados y redes, 10 volúmenes, 12 logs de contenedores |
| `03_contenedores.sh` | **Ubuntu**, desde el directorio del repo (ejecuta `docker compose exec`) | `docker compose exec` | 4 identidad y capacidades dentro de cada contenedor, versiones de librerías, configuración efectiva de Nginx y Caddy |
| `04_sqlserver.sh` | **Ubuntu** (caso A: base en el contenedor `db`) o **Windows** (caso B: base externa, consultas a mano) | consultas de catálogo `sys.*` | 11 SQL Server |
| Dependencias | **Tu PC de desarrollo**, no el servidor | — | 2 y 3: pip-audit y npm audit sobre los lock, y escaneo de imágenes |

No hace falta instalar nada en el servidor. Si una herramienta no existe (`ufw`, `tailscale`, `docker scout`), el script lo indica y sigue.

## Orden recomendado

```bash
# 1) Host Ubuntu (con sudo, para ver sshd, ufw y los logs de autenticación)
cd ~/GlucoLume/docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/anexo_c
sudo bash 01_ubuntu_host.sh ~/GlucoLume 2>&1 | tee ~/diag_01_host_$(date +%F).txt

# 2) Docker en el host
bash 02_docker_host.sh glucolume 2>&1 | tee ~/diag_02_docker_$(date +%F).txt

# 3) Dentro de los contenedores (desde el directorio del repo, con el mismo .env de siempre)
cd ~/GlucoLume && bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/anexo_c/03_contenedores.sh 2>&1 | tee ~/diag_03_contenedores_$(date +%F).txt

# 4) SQL Server
#    Caso A (base en el contenedor db, perfil "db"):
bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/anexo_c/04_sqlserver.sh A 2>&1 | tee ~/diag_04_sql_$(date +%F).txt
#    Caso B (base externa): prueba de alcance desde Ubuntu; las consultas se corren en Windows (ver el script)
bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/anexo_c/04_sqlserver.sh B IP_DEL_SQL_SERVER 1433
```

Los pasos 1 a 4 no escriben en el sistema. Los únicos archivos nuevos son las salidas que tú guardas con `tee` en tu directorio personal.

## Qué revisar en la salida, sin editarla

Antes de compartir una salida, busca y elimina cualquier cadena que no quieras compartir. Los scripts ya evitan imprimir valores,
pero revísala igual. Si aparece algo parecido a una contraseña, un token o una cadena de conexión, detente y avísame sin copiarla.

## Qué enviar de vuelta

Las cuatro salidas completas (`diag_01` a `diag_04`). Y, por separado, las respuestas a estas preguntas manuales, que los scripts no pueden responder:

1. ¿El SQL Server que usa el backend es el contenedor `db` o la instancia de Windows? ¿Desde qué IP se conecta?
2. En la consola de Tailscale: ¿quién tiene acceso de administrador, qué ACL están activas y cuándo expira la clave del equipo del servidor?
3. ¿Dónde está el último respaldo de la base y cuándo se probó restaurarlo por última vez?
4. ¿Qué usuarios humanos deberían tener acceso al servidor (SSH, sudo, grupo `docker`)?

## Qué NO ejecutar en el servidor

- `apt-get update`, `apt-get upgrade`, `unattended-upgrade` manual, `reboot`, `shutdown`: son cambios; las actualizaciones se planifican en la fase 1 del plan.
- `docker compose up`, `down`, `restart`, `build`, `pull`, `system prune`: cambian el estado de los servicios.
- `ufw enable`, `ufw allow|deny`, `nft` o `iptables` con `-A`/`-I`/`-D`: cambian el firewall.
- `cat .env`, `docker compose config` sin `--no-interpolate`, `docker inspect` completo sobre contenedores con secretos: muestran valores.

## Dependencias (en tu PC de desarrollo)

Estas comprobaciones consultan bases de vulnerabilidades y no instalan nada en el servidor. Se pueden repetir cuando se quiera:

```bash
# Python: lock con hashes del backend (pip-audit en un entorno temporal de tu PC)
python -m venv /tmp/pa && /tmp/pa/bin/pip install pip-audit
/tmp/pa/bin/pip-audit -r backend/requirements.txt

# npm: producción del frontend, solo con el lock
cd frontend && npm audit --omit=dev --package-lock-only

# Imágenes desplegadas (en el servidor, solo lectura; requiere el plugin docker scout o trivy)
docker scout cves --only-severity critical,high --format packages local://glucolume/backend:<VERSION>
docker scout cves --only-severity critical,high --format packages local://glucolume/frontend:<VERSION>
```

Resultados del 07/11/2026 (en el banco): `pip-audit` sobre los 44 paquetes del lock del backend, **sin vulnerabilidades conocidas**;
`npm audit --omit=dev` del frontend, **0 vulnerabilidades**. Lo que no cubren es el sistema operativo de las imágenes:
para eso, el escaneo de imágenes (Trivy del 23/10/2026 en `docs/evidencias/validacion_integral/`, ver `docs/DESPLIEGUE.md` §6).
