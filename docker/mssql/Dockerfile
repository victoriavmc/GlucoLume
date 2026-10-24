# SQL Server 2022 con los paquetes del sistema (OpenSSL, GnuPG) actualizados. Mismo motor y misma configuración que
# la imagen oficial; solo se aplican los parches de seguridad de Ubuntu publicados después de esa versión.
# (CU27 trae un componente Go con 3 críticas y 24 altas propias: por eso se queda en CU16 + parches del sistema.)
FROM mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04@sha256:45a1a9d13ca5574cf8e0fe4ae73ab77248b66d9c3132ac9658fb6c16dd72a8af
USER root
# Todos los paquetes de Ubuntu con parche publicado (python3.10, sqlite3, systemd, tar, wget...); los de Microsoft
# (ODBC y sqlcmd) quedan retenidos para no cambiar de versión junto con el sistema.
RUN apt-mark hold msodbcsql18 mssql-tools18 \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
USER mssql
