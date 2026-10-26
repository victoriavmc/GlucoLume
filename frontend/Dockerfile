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
# Go actual para recompilar esbuild (solo imagen de desarrollo, 25/10/2026): el binario publicado de esbuild 0.25.12 está compilado con
# Go 1.23.12 (~60 CVE de stdlib) y ninguna versión publicada usa un Go sin CVE (0.28.2 trae Go 1.26.5 y además rompe Vite 6).
ARG GO_IMAGE=golang:1.26.10-alpine@sha256:27f2d3b83cfc5803c8078f8e730af0f7c431bf067afaec8f60a36fb763187cba
# Misma versión que instala Vite (npm ls esbuild): el paquete npm de esbuild exige que el binario coincida.
ARG ESBUILD_VERSION=0.25.12

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund


# esbuild compilado desde el código fuente con Go actual y golang.org/x/sys al día (mismo comportamiento, sin CVE del runtime de Go).
FROM ${GO_IMAGE} AS esbuild
ARG ESBUILD_VERSION
RUN apk add --no-cache git \
    && git clone --depth 1 --branch v${ESBUILD_VERSION} https://github.com/evanw/esbuild.git /src
WORKDIR /src
RUN go get golang.org/x/sys@latest && go mod tidy \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/esbuild ./cmd/esbuild \
    && /out/esbuild --version | grep -qx "${ESBUILD_VERSION}"


# Dependencias de desarrollo con el binario publicado de esbuild (en las dos rutas donde puede quedar) reemplazado por el recompilado.
# Etapa intermedia: dev copia node_modules ya corregido en una sola capa, así el binario viejo no queda en ninguna capa de la imagen.
FROM deps AS devdeps
COPY --from=esbuild /out/esbuild /app/node_modules/@esbuild/linux-x64/bin/esbuild
RUN if [ -f /app/node_modules/esbuild/bin/esbuild ]; then cp /app/node_modules/@esbuild/linux-x64/bin/esbuild /app/node_modules/esbuild/bin/esbuild; fi


FROM ${NODE_IMAGE} AS dev
# Desarrollo con recarga en caliente. El código fuente se monta como volumen desde compose.dev.yaml.
# Parches de Alpine (zlib, musl desde edge como en runtime) y sin el npm/npx/corepack que trae Node: Vite se ejecuta directo y
# el npm empaquetado arrastra dependencias vulnerables (pacote, sigstore, brace-expansion...). Las dependencias ya están instaladas.
RUN apk upgrade --no-cache \
    && apk upgrade --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main musl musl-utils \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
WORKDIR /app
COPY --from=devdeps /app/node_modules ./node_modules
ENV CHOKIDAR_USEPOLLING=true
COPY . .
EXPOSE 5173
CMD ["node", "node_modules/vite/bin/vite.js", "--host", "0.0.0.0"]


FROM deps AS build
ARG VITE_API_BASE_URL=/
# Orígenes públicos del login y de la aplicación (vacíos = sin separación). Ver docs/DESPLIEGUE.md.
ARG VITE_LOGIN_ORIGIN=
ARG VITE_APP_ORIGIN=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_LOGIN_ORIGIN=${VITE_LOGIN_ORIGIN}
ENV VITE_APP_ORIGIN=${VITE_APP_ORIGIN}
COPY . .
# Precompresión (gzip -9) de lo que Nginx sirve con gzip_static: no se comprime en cada pedido y pesa ~18 % menos que el gzip al vuelo.
RUN npm run build && find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.svg' -o -name '*.html' -o -name '*.txt' \) -exec gzip -9 -k -f {} +


FROM ${NGINX_IMAGE} AS runtime
# Parches de seguridad de Alpine posteriores a la imagen base (curl, openssl, zlib, musl...).
USER root
# musl desde edge (24/10/2026): el fix de CVE-2026-107891 (1.2.6-r6) todavía no está en 3.24; solo se toman musl y
# musl-utils de edge (sin dependencias), el resto sigue en la rama estable. Quitar el segundo comando cuando 3.24 lo publique.
RUN apk upgrade --no-cache \
    && apk upgrade --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main musl musl-utils
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
