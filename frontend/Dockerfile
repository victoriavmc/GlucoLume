# syntax=docker/dockerfile:1.7
# GlucoLume Frontend (React + Vite) servido por Nginx. Contexto de construcción: ./frontend
#
#   docker build -t glucolume/frontend:dev --build-context nginxconf=docker/nginx frontend
#   (la configuración de Nginx vive en docker/nginx/ y entra como contexto adicional "nginxconf"; Compose ya lo hace)
#
# Etapas: deps -> dev (servidor de Vite, solo desarrollo) | build -> runtime (Nginx sin privilegios).
#
# VITE_API_BASE_URL es PÚBLICA (queda dentro del JavaScript compilado): nunca poner secretos. El valor "/" compila el
# frontend para llamar a la API en el mismo origen (/api/v1/...), que Nginx reenvía al backend: la misma imagen sirve
# para cualquier dominio, sin CORS y sin reconstruir al cambiar de servidor.

# Imágenes fijadas por digest (GL-13, 19/10/2026): el mismo build siempre parte de la misma base. Para actualizar: docker buildx imagetools
# inspect <imagen:etiqueta> --format '{{.Manifest.Digest}}', escanear (docker scout cves) y reemplazar el digest.
# Node solo compila (no llega a la imagen final). 22.12 → 22.23 (misma versión mayor): de 63 a 11 vulnerabilidades altas en la etapa de build.
ARG NODE_IMAGE=node:22.23-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
# alpine-slim: Nginx sin los módulos de imágenes/XML/njs (y sin sus librerías libxml2, libtiff, libpng...).
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.30-alpine-slim@sha256:5d8bb9437d74a600ec5dbf90c035451c724dc33eac8d3a71078f6f8612c345f6

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund


FROM deps AS dev
# Desarrollo con recarga en caliente. El código fuente se monta como volumen desde compose.dev.yaml.
ENV CHOKIDAR_USEPOLLING=true
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0"]


FROM deps AS build
ARG VITE_API_BASE_URL=/
# Orígenes públicos del login y de la aplicación (vacíos = sin separación). Ver docs/DESPLIEGUE.md.
ARG VITE_LOGIN_ORIGIN=
ARG VITE_APP_ORIGIN=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_LOGIN_ORIGIN=${VITE_LOGIN_ORIGIN}
ENV VITE_APP_ORIGIN=${VITE_APP_ORIGIN}
COPY . .
RUN npm run build


FROM ${NGINX_IMAGE} AS runtime
# Parches de seguridad de Alpine posteriores a la imagen base (curl, openssl, zlib, musl...).
USER root
RUN apk upgrade --no-cache
USER 101
# La plantilla se procesa al iniciar (envsubst): BACKEND_UPSTREAM y DNS_RESOLVER vienen de Compose.
COPY --from=nginxconf default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# TRUSTED_PROXY_CIDR: desde qué red se confía en X-Forwarded-For (proxy HTTPS delante). Por defecto, las redes privadas de Docker.
ENV BACKEND_UPSTREAM=backend:8080 \
    DNS_RESOLVER=127.0.0.11 \
    TRUSTED_PROXY_CIDR=172.16.0.0/12
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
