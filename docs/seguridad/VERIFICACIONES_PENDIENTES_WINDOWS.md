# Verificaciones pendientes en Windows (remediación del informe del 21/10/2026)

Los cambios de la rama `claude/vigilant-shannon-legfop` se desarrollaron en un contenedor Linux sin SQL Server, sin driver ODBC, sin Docker, sin
PowerShell y sin tu `.env`. Esta lista es lo que **falta ejecutar en tu equipo** antes de dar la remediación por verificada. Marcá cada ítem con la
fecha y el resultado. Ninguna de estas verificaciones se ejecutó contra una base real, y el informe **no debe clasificarse como aprobado** mientras
haya ítems sin marcar.

## 1. Las seis pruebas del backend no confirmadas

Cinco fallan en Linux **también en el commit original `1d80d84`** (antes de estos cambios) y una se excluyó de la corrida. Desde `backend/`, con el
`.env`/`tests/test.env` reales de tu equipo y el driver ODBC 18:

```powershell
python -m pytest -q `
  "tests/test_security_config.py::test_en_produccion_se_verifica_el_certificado_de_sql_server" `
  "tests/test_patient_access.py::test_la_api_directa_sin_autenticacion_es_rechazada" `
  "tests/test_reference_schema.py::test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro" `
  "tests/test_register_contact.py::test_confirmacion_from_es_la_cuenta_smtp" `
  "tests/test_register_contact.py::test_mensaje_from_es_la_cuenta_smtp_y_reply_to_el_usuario" `
  "tests/test_stream_limits.py"
```

| # | Prueba | Causa probable del fallo en Linux | Resultado en Windows |
|---|---|---|---|
| 1 | `test_security_config::test_en_produccion_se_verifica_el_certificado_de_sql_server` | Usa una ruta de Windows (`/certs/sql.crt`) que no existe en Linux | ☐ |
| 2 | `test_patient_access::test_la_api_directa_sin_autenticacion_es_rechazada` | Sin `libodbc.so.2`, `getDb` no puede crear el motor; con estos cambios se ve como 500 en vez de una excepción | ☐ |
| 3 | `test_reference_schema::test_los_indices_de_los_modelos_estan_en_el_esquema_con_el_mismo_filtro` | **Era un defecto real, ya corregido:** el esquema `GlucoLume_DB_v5.sql` había perdido sus 31 índices (no solo `IX_AuditoriaContexto_ip`). Se restauraron en esta rama con una prueba de que no se duplica ningún objeto. Debe pasar también en Windows | ☐ |
| 4 | `test_register_contact::test_confirmacion_from_es_la_cuenta_smtp` | Espera el remitente SMTP del `.env` real; allí se usó uno ficticio | ☐ |
| 5 | `test_register_contact::test_mensaje_from_es_la_cuenta_smtp_y_reply_to_el_usuario` | Ídem | ☐ |
| 6 | `test_stream_limits::test_los_streams_no_retienen_conexiones_del_pool[/api/v1/acquisition/telemetry/stream]` | En Linux sin `libodbc.so.2` el motor de base no se puede crear (mismo origen que la #2); con ODBC debería pasar. Confirmarlo | ☐ |

Estado en el entorno Linux de desarrollo al cerrar la remediación: las pruebas #1, #2 y #6 siguen fallando solo por la ruta de Windows y la falta de ODBC; la #3 se corrigió; la #4 y la #5 pasan con un `tests/test.env` sintético (dependen del `.env` local, que no se versiona).

Además, corré la suite completa (`python -m pytest`) y confirmá que las ~35 pruebas omitidas de SQL Server (opcionales) se ejecutan o se justifican.
Si alguna de las seis falla en Windows, no es un problema del entorno: hay que revisarla antes de fusionar.

## 2. Respaldos (H-01) — `database/respaldos/GlucoLume_respaldo.ps1`

El script con `-CopiaExterna` **no se ejecutó nunca** (no hay PowerShell en el entorno de desarrollo). Probalo primero sobre una copia, no sobre la
base real:

1. ☐ Ejecutarlo con `-CopiaExterna` apuntando a un disco o carpeta de prueba y verificar: respaldo local creado, copia externa creada, líneas
   `Copia externa verificada` en `respaldo.log` y código de salida 0.
2. ☐ Forzar un fallo de la copia (destino inexistente): debe quedar el respaldo local, aplicarse la retención local y salir con código 2.
3. ☐ Ejecutarlo **sin** `-CopiaExterna`: debe registrar el aviso de regla 3-2-1 incompleta y salir con 0.
4. ☐ Restaurar desde la copia externa con `GlucoLume_prueba_restauracion.ps1 -Archivo <ruta de la copia>`.
5. ☐ Revisar la sintaxis del script (`powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw .\GlucoLume_respaldo.ps1)) | Out-Null"`).
6. ☐ Decidir el destino definitivo, actualizar la tarea programada y guardar la frase de cifrado fuera del equipo (acciones tuyas).

## 3. Configuración de Nginx (H-14) — `docker/nginx/default.conf.template`

Solo hay una prueba de texto; el archivo **no se cargó en un Nginx real**.

1. ☐ Levantar el frontend con Docker y verificar que Nginx arranca: `docker compose up -d frontend` y `docker compose logs frontend` sin errores de
   configuración (`log_format sin_query` y `access_log /dev/stdout sin_query`).
2. ☐ Abrir un enlace con token (p. ej. `/verificar-correo?token=PRUEBA123`) y confirmar en `docker compose logs frontend` que la línea muestra la ruta
   **sin** `?token=...`.
3. ☐ Confirmar que los logs siguen siendo útiles (IP real, método, ruta, estado, `rid=`).

## 4. Build de producción del frontend (H-15, H-17)

Las pruebas del frontend (685/685) pasan con React 19.1.10, pero **`vite build` no terminó** en el entorno de desarrollo.

1. ☐ `cd frontend && npm ci && npm test` (esperado 685/685).
2. ☐ `npm run build` con `VITE_API_BASE_URL` definido; debe terminar sin errores.
3. ☐ Construir y levantar la imagen (`docker compose build frontend`) y comprobar en el navegador: la CSP no bloquea la pantalla de error
   (`ErrorBoundary`), que se puede provocar temporalmente lanzando un error en un componente.
4. ☐ `npm audit` / escaneo de la imagen tras la actualización de React.

## 5. Imagen del backend y arranque (H-07, H-15, H-11)

1. ☐ `docker compose build backend`: la imagen define `GLUCOLUME_RUNTIME=container`.
2. ☐ Con `.env` **sin** `API_ENV` (o vacío), el backend debe negarse a arrancar con el mensaje "API_ENV debe definirse explícitamente". Con
   `API_ENV=development` (desarrollo) o `compose.prod.yaml` (producción) debe arrancar.
3. ☐ Actualizar tu `.env`: `.env.example` ahora trae `API_ENV=development`; una línea `API_ENV=` vacía deja de funcionar dentro de Docker.
4. ☐ Con un usuario real, navegar la aplicación y comprobar que el límite de 1800 pedidos por minuto por IP no molesta a un uso normal.

## 6. Verificaciones nuevas de esta ampliación (H-02, H-04, H-05, H-06, H-08, H-09, H-10, H-16)

Todo lo siguiente se implementó y probó con datos sintéticos; **nada se aplicó a una base, Redis, placa ni despliegue reales**. Hacerlo en este orden:

1. ☐ **H-02 (permisos SQL):** sobre una **copia restaurada** de la base (nunca primero sobre la real): `GlucoLume_permisos.sql`, `GlucoLume_permisos_quitar_roles_fijos.sql`,
   `GlucoLume_permisos_verificar.sql`; usar la aplicación (login, mediciones, instituciones, baja de cuenta) y buscar errores 229 en el log. Probar también
   `GlucoLume_permisos_restaurar_roles_fijos.sql`. El T-SQL no pudo compilarse en el entorno (sin SQL Server).
2. ☐ **H-16 (puentes):** aplicar `GlucoLume_agregar_puente_credencial.sql` a la copia; `python -m app.cli.bridgeTokens` (crear, listar, rotar, revocar); conectar un puente
   con su credencial; luego `BRIDGE_ALLOW_SHARED_TOKEN=false` y confirmar que el token compartido se rechaza.
3. ☐ **H-04 (retención):** `python -m app.jobs.retention previsualizar` y `purgeInstitutionalRetention --simular` sobre la copia. No definir `RETENTION_APPROVAL_REFERENCE`
   ni plazos hasta tener el dictamen legal; no programar ninguna purga.
4. ☐ **H-08 (secretos):** ensayar el procedimiento de SEGURIDAD §5.1 («Rotación de secretos») en un entorno de prueba, incluida la reversión.
5. ☐ **H-06 (Redis):** con un Redis descartable (contraseña, sin puerto publicado) y `RATE_LIMIT_REDIS_URL`, dos réplicas del backend comparten el límite de `/auth/login`.
6. ☐ **H-09 (cookie):** con el build de producción detrás de Nginx/Caddy por HTTPS: iniciar sesión (local, Google, con MFA, con y sin «Recordarme»), recargar, esperar la
   rotación y cerrar sesión; en las herramientas del navegador confirmar `HttpOnly`, `Secure`, `SameSite=Strict` y que `localStorage`/`sessionStorage` no contienen el
   refresh token. Probar el flujo `VITE_LOGIN_ORIGIN` si lo usás. Cuando no queden puentes ni scripts heredados: `REFRESH_TOKEN_IN_BODY=false`.
7. ☐ **H-05 (firma de líneas):** compilar y cargar `GlucoLume_MAX30100_optimizado` en la placa real, provisionar la clave por USB (`bridge_ctl.py genkey`), medir con el HC-06,
   cambiar el PIN del módulo (acción física) y decidir sobre la confidencialidad del enlace. Sigue **abierto**.
8. ☐ **H-10 (zlib):** repetir `python docker/tools/baseImageVersions.py` y reconstruir con `--build-arg ZLIB_MIN_VERSION=<versión corregida>` cuando Debian la publique. Sigue **abierto**.

## 7. Qué NO se hizo (y no debe hacerse sin tu decisión)

- No se aplicaron migraciones ni permisos sobre ninguna base real (H-02: `GlucoLume_permisos.sql` y la tabla de H-16 siguen pendientes).
- No se ejecutó ni se programó `purgeInstitutionalRetention` ni ninguna purga (H-04).
- No se tocaron credenciales ni se rotaron secretos reales (H-08: solo código y procedimiento).
- No se desplegó nada.
- No se aceptó ningún riesgo de seguridad en tu nombre. H-03 no se tocó (pendiente de infraestructura). H-05 y H-10 siguen abiertos; H-06 y H-09 quedan implementados pero sin validar en tu entorno.
