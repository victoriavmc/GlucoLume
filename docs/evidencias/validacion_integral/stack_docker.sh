#!/usr/bin/env bash
# Levanta y valida el stack Docker COMPLETO del proyecto en el ENTORNO CLOUD de validación (Linux con Docker, sin acceso a deb.debian.org). Todo sintético y descartable.
#   bash stack_docker.sh build   # imágenes: db (Dockerfile oficial), backend (imagen de ensayo) y frontend (runtime con el build de producción del host)
#   bash stack_docker.sh up      # proyecto temporal, .env y docker/db.env con contraseñas aleatorias, SQL Server + esquema + permisos, servicios, SMTP falso
#   bash stack_docker.sh test    # stack_funcional.py por HTTP (modo desarrollo)
#   bash stack_docker.sh prod    # variante producción: compose.prod.yaml + Caddy (HTTPS con su CA interna) + certificado de SQL Server verificado, y stack_funcional.py por HTTPS
#   bash stack_docker.sh down    # baja el stack (CONSERVA el volumen); `down -v` en este proyecto temporal borra solo datos sintéticos
# En Windows NO se usa este script: ver docs/DESPLIEGUE.md §3.0. No toca ninguna base real. El servicio «lifecycle» no se levanta nunca.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
WORK="${STACK_WORK:-/tmp/glucolume-stack}"; P="$WORK/proj"; VER=validacion
mkdir -p "$WORK"; cd "$WORK"
compose(){ (cd "$P" && GLUCOLUME_VERSION=$VER docker compose "$@"); }
case "${1:-}" in
build)
  # db: el Dockerfile OFICIAL
  docker build -t glucolume/mssql:2022-CU16-p$VER "$REPO/docker/mssql"
  # backend: imagen de ensayo (el Dockerfile oficial necesita deb.debian.org). Paquetes .deb del host (Ubuntu + repositorio de Microsoft) y dependencias con hashes.
  mkdir -p ctx/debs && (cd ctx/debs && rm -f *.deb && apt-get download msodbcsql18 odbcinst libodbcinst2 libodbc2 unixodbc libltdl7 libgssapi-krb5-2 libkrb5-3 libk5crypto3 libkrb5support0 libkeyutils1 libcom-err2)
  rm -rf ctx/site && uv pip install -q --require-hashes -r "$REPO/backend/requirements.txt" --target ctx/site --python 3.14
  rm -rf ctx/backend && mkdir -p ctx/backend && (cd "$REPO" && git archive HEAD backend/app | tar -x -C "$WORK/ctx")
  docker build -f "$HERE/docker/Dockerfile.backend-entorno-cloud" -t glucolume/backend:$VER ctx
  # frontend: runtime idéntico al oficial (sin «apk upgrade») + build de producción hecho en el host con VITE_API_BASE_URL=/
  [ -d "${DIST:-}" ] || { (cd "$REPO/frontend" && VITE_API_BASE_URL=/ npx vite build --outDir "$WORK/dist" --emptyOutDir); DIST="$WORK/dist"; }
  mkdir -p ctx_empty
  docker build -f "$HERE/docker/Dockerfile.frontend-runtime-entorno-cloud" -t glucolume/frontend:$VER --build-context nginxconf="$REPO/docker/nginx" --build-context distctx="$DIST" ctx_empty
  ;;
up)
  rm -rf "$P" && mkdir -p "$P" && (cd "$REPO" && git archive HEAD | tar -x -C "$P")
  [ -f "$REPO/compose.redis.yaml" ] && cp "$REPO/compose.redis.yaml" "$P/"
  python3 - "$P" "$WORK" <<'PY'
import os, secrets, sys
from cryptography.fernet import Fernet
P, W = sys.argv[1:3]
t = lambda n=48: secrets.token_urlsafe(n)
sa, api, jobs, red = ("Sa" + secrets.token_hex(8) + "#Aa1", "Api" + secrets.token_hex(8) + "#Aa1", "Job" + secrets.token_hex(8) + "#Aa1", secrets.token_urlsafe(24))
env = f"""API_ENV=development
DB_HOST=db
DB_PORT=1433
DB_NAME=GlucoLume
DB_USER=glucolume_app
DB_PASSWORD={api}
DB_JOBS_USER=glucolume_jobs
DB_JOBS_PASSWORD={jobs}
DB_TRUST_SERVER_CERTIFICATE=true
API_BASE_URL=http://localhost:18080
FRONTEND_URL=http://localhost:18080
JWT_SECRET={t(64)}
SESSION_SECRET={t(64)}
MFA_ENCRYPTION_KEY={Fernet.generate_key().decode()}
SMTP_HOST=host.docker.internal
SMTP_PORT=2525
SMTP_USERNAME=sintetico
SMTP_PASSWORD={t(12)}
BRIDGE_TOKEN={t(40)}
BRIDGE_ALLOW_SHARED_TOKEN=true
ACCOUNT_LIFECYCLE_INTERVAL_SECONDS=0
GLUCOLUME_VERSION=validacion
FRONTEND_BIND=127.0.0.1
FRONTEND_PORT=18080
FRONTEND_LOGIN_PORT=18081
REDIS_PASSWORD={red}
RATE_LIMIT_REDIS_URL=redis://:{red}@redis:6379/0
"""
for path, text in ((f"{P}/.env", env), (f"{P}/docker/db.env", f"MSSQL_SA_PASSWORD={sa}\nSQLCMDPASSWORD={sa}\n"), (f"{W}/stack_secrets.txt", f"SA={sa}\nAPI={api}\nJOBS={jobs}\nREDIS={red}\n")):
    open(path, "w").write(text); os.chmod(path, 0o600)
PY
  # SMTP falso con STARTTLS (el backend verifica certificado y nombre): certificado propio entregado como autoridad con SSL_CERT_FILE
  mkdir -p smtp && openssl req -x509 -newkey rsa:2048 -nodes -keyout smtp/key.pem -out smtp/cert.pem -days 2 -subj "/CN=host.docker.internal" -addext "subjectAltName=DNS:host.docker.internal,DNS:localhost" 2>/dev/null
  chmod 644 smtp/*.pem; : > mails.jsonl
  (setsid nohup python3 "$HERE/smtp_falso_starttls.py" "$WORK/smtp/cert.pem" "$WORK/smtp/key.pem" "$WORK/mails.jsonl" 2525 > smtp.log 2>&1 < /dev/null &)
  printf 'services:\n  backend:\n    environment:\n      SSL_CERT_FILE: /run/smtp-ca/cert.pem\n    volumes:\n      - %s/smtp/cert.pem:/run/smtp-ca/cert.pem:ro\n' "$WORK" > "$P/compose.ensayo-smtp.yaml"
  . "$WORK/stack_secrets.txt"
  C=(--profile db --profile redis -f compose.yaml -f compose.redis.yaml -f compose.ensayo-smtp.yaml)
  compose "${C[@]}" up -d --no-build db
  until [ "$(docker inspect -f '{{.State.Health.Status}}' glucolume-db-1)" = healthy ]; do sleep 4; done
  # Instalación de la base con los scripts OFICIALES (docs/BASE_DE_DATOS.md §2)
  SQ=(docker exec -e SQLCMDPASSWORD="$SA" glucolume-db-1 /opt/mssql-tools18/bin/sqlcmd -C -I -S localhost -U sa -b)
  docker exec glucolume-db-1 mkdir -p /tmp/sql
  iconv -f UTF-16LE -t UTF-8 "$REPO/database/reference/GlucoLume_DB_v5.sql" | sed '1s/^\xEF\xBB\xBF//' > "$WORK/v5.sql"; docker cp "$WORK/v5.sql" glucolume-db-1:/tmp/sql/v5.sql
  for f in MATRIZ.SQL GlucoLume_permisos.sql GlucoLume_permisos_quitar_roles_fijos.sql GlucoLume_permisos_verificar.sql; do docker cp "$REPO/database/reference/$f" glucolume-db-1:/tmp/sql/$f; done
  "${SQ[@]}" -Q "CREATE DATABASE [GlucoLume] COLLATE Modern_Spanish_CI_AS"
  "${SQ[@]}" -i /tmp/sql/v5.sql >/dev/null; "${SQ[@]}" -d GlucoLume -i /tmp/sql/MATRIZ.SQL >/dev/null
  "${SQ[@]}" -Q "CREATE LOGIN glucolume_app WITH PASSWORD='$API', CHECK_POLICY=ON; CREATE LOGIN glucolume_jobs WITH PASSWORD='$JOBS', CHECK_POLICY=ON;"
  "${SQ[@]}" -d GlucoLume -i /tmp/sql/GlucoLume_permisos.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME >/dev/null
  "${SQ[@]}" -d GlucoLume -i /tmp/sql/GlucoLume_permisos_quitar_roles_fijos.sql -v API_LOGIN=glucolume_app CONFIRMAR=QUITAR_ROLES_FIJOS_GLUCOLUME >/dev/null
  "${SQ[@]}" -d GlucoLume -h -1 -W -Q "SET NOCOUNT ON; SELECT 'tablas', COUNT(*) FROM sys.tables UNION ALL SELECT 'indices IX/UX', COUNT(*) FROM sys.indexes WHERE name LIKE 'IX[_]%' OR name LIKE 'UX[_]%' UNION ALL SELECT 'FK', COUNT(*) FROM sys.foreign_keys UNION ALL SELECT 'CHECK', COUNT(*) FROM sys.check_constraints UNION ALL SELECT 'procedimientos', COUNT(*) FROM sys.procedures UNION ALL SELECT 'reglas de matriz', COUNT(*) FROM dbo.ReglaMatriz"
  compose "${C[@]}" up -d --no-build backend frontend redis     # NO lifecycle
  until [ "$(docker inspect -f '{{.State.Health.Status}}' glucolume-backend-1)" = healthy ]; do sleep 3; done
  compose "${C[@]}" ps
  ;;
test)
  STACK_DIR="$P" MAILS="$WORK/mails.jsonl" python "$HERE/stack_funcional.py"
  ;;
prod)
  # Certificado propio para SQL Server (CN/SAN «db») cargado en el contenedor; el backend lo verifica (DB_SERVER_CERTIFICATE) en producción.
  . "$WORK/stack_secrets.txt"; mkdir -p sqlcert && openssl req -x509 -newkey rsa:2048 -nodes -keyout sqlcert/mssql.key -out sqlcert/mssql.pem -days 2 -subj "/CN=db" -addext "subjectAltName=DNS:db" 2>/dev/null
  chmod 644 sqlcert/*; for f in mssql.key mssql.pem; do docker cp sqlcert/$f glucolume-db-1:/var/opt/mssql/$f; done
  docker exec -u 0 glucolume-db-1 sh -c 'chown mssql:root /var/opt/mssql/mssql.key /var/opt/mssql/mssql.pem; chmod 600 /var/opt/mssql/mssql.key'
  docker exec glucolume-db-1 sh -c '/opt/mssql/bin/mssql-conf set network.tlscert /var/opt/mssql/mssql.pem; /opt/mssql/bin/mssql-conf set network.tlskey /var/opt/mssql/mssql.key; /opt/mssql/bin/mssql-conf set network.tlsprotocols 1.2; /opt/mssql/bin/mssql-conf set network.forceencryption 1' >/dev/null
  docker restart glucolume-db-1 >/dev/null; until [ "$(docker inspect -f '{{.State.Health.Status}}' glucolume-db-1)" = healthy ]; do sleep 4; done
  # El PEM de confianza lleva también el certificado del SMTP falso (en Linux el backend lo agrega a las autoridades al fijar el de SQL Server)
  cat sqlcert/mssql.pem smtp/cert.pem > "$P/docker/certs/sqlserver.crt"
  python3 - "$P/.env" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
s = re.sub(r"^DB_TRUST_SERVER_CERTIFICATE=.*\n", "", s, flags=re.M)
s = s.replace("http://localhost:18080", "https://localhost:18444").replace("BRIDGE_ALLOW_SHARED_TOKEN=true", "BRIDGE_ALLOW_SHARED_TOKEN=false")
s += "DB_SERVER_CERTIFICATE=/run/certs/sqlserver.crt\nDB_CERTIFICATE_HOSTNAME=db\nGLUCOLUME_DOMAIN=localhost\nREFRESH_TOKEN_IN_BODY=false\n"
open(sys.argv[1], "w").write(s)
PY
  printf 'services:\n  proxy:\n    ports: !override\n      - "127.0.0.1:18444:443"\n      - "127.0.0.1:18079:80"\n' > "$P/compose.ensayo-prod.yaml"
  PROD=(--profile db --profile redis --profile https -f compose.yaml -f compose.redis.yaml -f compose.prod.yaml -f compose.ensayo-prod.yaml)
  compose --profile db --profile redis -f compose.yaml -f compose.redis.yaml -f compose.ensayo-smtp.yaml down >/dev/null 2>&1 || true
  compose "${PROD[@]}" up -d --no-build db redis backend frontend proxy
  until [ "$(docker inspect -f '{{.State.Health.Status}}' glucolume-backend-1)" = healthy ]; do sleep 3; done
  STACK_URL=https://localhost:18444 STACK_INSECURE=1 STACK_DIR="$P" MAILS="$WORK/mails.jsonl" STACK_PROFILES=db,redis,https \
    STACK_COMPOSE_FILES=compose.yaml,compose.redis.yaml,compose.prod.yaml,compose.ensayo-prod.yaml STACK_SERVICES=db,redis,backend,frontend,proxy python "$HERE/stack_funcional.py"
  ;;
down)
  compose --profile db --profile redis --profile https -f compose.yaml -f compose.redis.yaml down 2>&1 | tail -3 ;;
*) sed -n 2,9p "$0"; exit 2 ;;
esac
