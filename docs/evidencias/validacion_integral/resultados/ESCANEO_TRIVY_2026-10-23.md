# Escaneo con Trivy de las imágenes base (23/10/2026)

Herramienta: `aquasec/trivy:latest` (imagen de Docker Hub) con su base de vulnerabilidades descargada ese día; imágenes escaneadas **sin ejecutarlas**.
Comando: `docker run --rm --network host -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln <imagen>` (con el proxy de salida del entorno).

## `python:3.14-slim-trixie@sha256:a2b82f3c…3729170` (base de `backend/Dockerfile`; Debian 13.7)

Aviso: es la imagen BASE. La imagen final del backend le suma `apt-get upgrade` y el driver ODBC, y le quita pip (ver `backend/Dockerfile`); esa construcción **no se pudo ejecutar** en este entorno (deb.debian.org bloqueado), así que lo que sigue es el piso, no el resultado final.

- `os-pkgs` (python:3.14-slim-trixie@sha256:a2b82f3c4): HIGH 44, LOW 61, MEDIUM 58, UNKNOWN 4
- `lang-pkgs` (Python): CRITICAL 1, HIGH 4, MEDIUM 2

### zlib1g (H-10)

- CVE-2026-27171: severidad **MEDIUM** según esta base, instalada `1:1.3.dfsg+really1.3.1-1+b1`, corrección: ninguna publicada (affected).
- CVE-2026-85091: severidad **MEDIUM** según esta base, instalada `1:1.3.dfsg+really1.3.1-1+b1`, corrección: ninguna publicada (affected).

El informe del 10/10 (Docker Scout) la clasificó como alta; Trivy (datos de Debian) la clasifica MEDIUM. La discrepancia de severidad **no cambia el estado de H-10**: sigue sin versión corregida publicada.

### HIGH/CRITICAL del sistema operativo sin corrección publicada (no figuraban entre las altas del informe del 10/10, que usó otro escáner; no se comparó una a una)

- CVE-2025-69720: libncursesw6, libtinfo6, ncurses-base, ncurses-bin
- CVE-2026-16742: libsystemd0, libudev1
- CVE-2026-54369: libacl1
- CVE-2026-76642: bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux
- CVE-2026-78408: bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux
- CVE-2026-78409: bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux
- CVE-2026-78410: bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux
- CVE-2026-9538: perl-base

Son paquetes base del sistema (util-linux/mount/login, ncurses, systemd, libacl, perl) **sin corrección publicada** según Debian: no hay nada que actualizar hoy. No se evaluó su explotabilidad dentro del contenedor. Quedan como riesgo residual abierto, **no aceptado**; se repite el escaneo al reconstruir la imagen.

### Librerías de Python dentro de pip (CRITICAL certifi, HIGH msgpack/setuptools/urllib3)

Son las copias internas de pip (`pip/_vendor`) de la imagen base. `backend/Dockerfile` **elimina pip** de la imagen final (`rm -rf …/site-packages/pip*`), de modo que no llegan al runtime; el lock de la aplicación (`backend/requirements.txt`) no tiene hallazgos (ver abajo).

## `nginxinc/nginx-unprivileged:1.30-alpine-slim@sha256:5d8bb943…c345f6` (base de `frontend/Dockerfile`; Alpine 3.24.2)

HIGH/CRITICAL: **0**. Imagen `glucolume/frontend:validacion` (esa base + plantilla de Nginx + build de producción): vulnerabilidades 0, secretos 0.

## Dependencias del repositorio (`trivy fs`, todas las severidades)

`backend/requirements.txt` 0, `acquisition/requirements.txt` 0, `frontend/package-lock.json` 0. Además `pip-audit` sobre el lock del backend: sin hallazgos tras actualizar `opentelemetry-api` a 1.45.1; `npm audit`: 0.

## Secretos y configuración (`trivy fs --scanners secret,misconfig` sobre `git archive HEAD`)

Secretos: 0. Dockerfiles (backend, frontend, mssql, firmware): 0 configuraciones erróneas.
