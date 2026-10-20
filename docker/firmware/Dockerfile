# Entorno OPCIONAL de compilación del firmware Arduino (Arduino CLI). No es parte de la aplicación web.
#   docker compose --profile firmware run --rm firmware
# Compila firmware/GlucoLume_MAX30100 (montado de solo lectura) para Arduino UNO y deja el resultado en el volumen
# firmware-build. Subirlo a la placa se hace desde el equipo con el IDE o arduino-cli (USB no se pasa a este contenedor).
#
# Tres etapas: compila Arduino CLI, instala el núcleo y la librería, y deja solo lo necesario para COMPILAR (sin
# curl/gnutls y sin las herramientas de subida y descubrimiento de placas, binarios Go antiguos útiles solo para subir
# o monitorear). La compilación no usa red.

# Etapa 0: Arduino CLI compilado con el Go más reciente de la rama 1.26 y dependencias (x/crypto, x/net, grpc, go-git...)
# actualizadas: el binario oficial de la 1.5.1 se publicó con Go 1.26.1 y dependencias con CVE altas y críticas.
FROM golang:1.26@sha256:37cfcca63222ec499bec5e8ad7aad52dbf7529db36d5812b8eae2f0621aa92d6 AS cli-build
ARG ARDUINO_CLI_VERSION=1.5.1
RUN git clone -q --depth 1 --branch "v${ARDUINO_CLI_VERSION}" https://github.com/arduino/arduino-cli /src
WORKDIR /src
RUN go get golang.org/x/crypto@latest golang.org/x/net@latest google.golang.org/grpc@latest \
        github.com/go-git/go-git/v5@latest golang.org/x/text@latest \
    && go mod tidy \
    && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X github.com/arduino/arduino-cli/internal/version.versionString=${ARDUINO_CLI_VERSION}" -o /arduino-cli .


FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS setup
ENV ARDUINO_DIRECTORIES_DATA=/opt/arduino/data ARDUINO_DIRECTORIES_USER=/opt/arduino/user \
    ARDUINO_UPDATER_ENABLE_NOTIFICATION=false
COPY --from=cli-build /arduino-cli /usr/local/bin/arduino-cli
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends ca-certificates \
    && arduino-cli core update-index && arduino-cli core install arduino:avr \
    && arduino-cli lib install "LiquidCrystal I2C" \
    && rm -rf /opt/arduino/data/staging \
    # Los binarios Go de subida/descubrimiento se reemplazan por un stub vacío en la misma ruta: el CLI sigue viendo la
    # herramienta "instalada" (si faltara intentaría descargarla) pero no queda código vulnerable en la imagen.
    && for tool in builtin/tools/serial-discovery builtin/tools/mdns-discovery builtin/tools/serial-monitor \
                   builtin/tools/dfu-discovery arduino/tools/arduinoOTA; do \
         find "/opt/arduino/data/packages/$tool" -type f -perm -u+x \
              -exec sh -c 'printf "#!/bin/sh\nexit 0\n" > "$1"' _ {} \; ; \
       done


FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS runtime
ENV ARDUINO_DIRECTORIES_DATA=/opt/arduino/data ARDUINO_DIRECTORIES_USER=/opt/arduino/user \
    ARDUINO_UPDATER_ENABLE_NOTIFICATION=false
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY --from=setup /usr/local/bin/arduino-cli /usr/local/bin/arduino-cli
COPY --from=setup /opt/arduino /opt/arduino
RUN groupadd --system --gid 10001 builder && useradd --system --uid 10001 --gid builder --home-dir /tmp builder \
    && mkdir /out && chown -R builder:builder /opt/arduino /out
USER builder
WORKDIR /work
CMD ["arduino-cli", "compile", "--fqbn", "arduino:avr:uno", "--output-dir", "/out", "GlucoLume_MAX30100"]
