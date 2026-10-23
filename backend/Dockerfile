# syntax=docker/dockerfile:1.7
# GlucoLume API (FastAPI + Uvicorn). Contexto de construcción: ./backend
#
#   docker build -t glucolume/backend:dev backend
#
# Etapas:
#   builder  -> compila las dependencias con requirements.txt (lock con hashes: instalación reproducible).
#   runtime  -> solo el entorno virtual, el controlador ODBC 18 y el código; usuario sin privilegios.
# La imagen NO contiene .env ni secretos: la configuración llega por variables de entorno en tiempo de ejecución.

# Imágenes fijadas por digest (GL-13, 19/10/2026): el mismo build siempre parte de la misma base. Para actualizar: docker buildx imagetools
# inspect <imagen:etiqueta> --format '{{.Manifest.Digest}}', escanear (docker scout cves) y reemplazar el digest.
# Rama 3.14; los parches de Debian posteriores al digest llegan con el apt-get upgrade del runtime; el lock de pip fija las librerías.
ARG PYTHON_IMAGE=python:3.14-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --require-hashes -r /tmp/requirements.txt


FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    GLUCOLUME_RUNTIME=container

# Microsoft ODBC Driver 18 para SQL Server (repositorio oficial de Microsoft, paquete firmado). libgssapi-krb5-2 y
# unixodbc se instalan explícitos: el driver los necesita y el purge de curl los quitaría como dependencias huérfanas.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft-2025.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/13/prod trixie main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc libgssapi-krb5-2 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Guarda opcional de zlib (H-10): sin ARG no hace nada. Cuando Debian publique la corrección de la CVE de zlib1g, construir con
# --build-arg ZLIB_MIN_VERSION=<versión que la corrige> hace FALLAR el build si el apt-get upgrade de arriba no la trajo (la CVE no se da por
# resuelta por reconstruir: se comprueba la versión instalada). Ver docs/evidencias/CVE_ZLIB_2026-10-23.md.
ARG ZLIB_MIN_VERSION=
RUN if [ -n "$ZLIB_MIN_VERSION" ]; then \
        dpkg --compare-versions "$(dpkg-query -W -f='${Version}' zlib1g)" ge "$ZLIB_MIN_VERSION" \
        || { echo "zlib1g instalada ($(dpkg-query -W -f='${Version}' zlib1g)) es anterior a $ZLIB_MIN_VERSION" >&2; exit 1; }; \
    fi

COPY --from=builder /opt/venv /opt/venv
# pip, setuptools y wheel no hacen falta para ejecutar la API (y traen librerías internas con CVE): se quitan.
RUN rm -rf /opt/venv/lib/python*/site-packages/pip* /opt/venv/bin/pip* \
           /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* \
           /usr/local/lib/python*/site-packages/wheel* /usr/local/lib/python*/site-packages/pkg_resources* \
           /usr/local/bin/pip* /usr/local/bin/wheel

RUN groupadd --system --gid 10001 glucolume \
    && useradd --system --uid 10001 --gid glucolume --no-create-home --shell /usr/sbin/nologin glucolume

WORKDIR /srv/backend
COPY --chown=root:root app ./app

USER glucolume
EXPOSE 8000

# Liveness: la API responde. No consulta la base, para que una caída de SQL Server no reinicie en bucle el contenedor.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

# --proxy-headers: detrás de Nginx/Caddy toma el esquema y la IP reales de X-Forwarded-*.
# FORWARDED_ALLOW_IPS se limita a la red interna de Docker desde Compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
