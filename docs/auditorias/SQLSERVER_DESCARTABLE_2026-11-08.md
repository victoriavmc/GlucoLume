# Verificación en SQL Server descartable (08/11/2026)

Entorno: contenedor **propio** de la sesión de trabajo, imagen fijada por digest igual a la del proyecto (`docker/mssql/Dockerfile`,
`mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04`), SQL Server **16.0.4165.4 (2022 CU16), Express**, sin volúmenes, publicado
solo en `127.0.0.1`, contraseña generada y no registrada, base `GlucoLume_Descartable`. No se tocó ninguna base real ni la de
demostración. El contenedor se elimina al cerrar la verificación.

## Qué se comprobó y resultado

| Verificación | Cómo | Resultado |
|---|---|---|
| Esquema vigente aplicable | `database/reference/GlucoLume_DB_v5.sql` aplicado sin cambios salvo el `USE` (apuntado a la base descartable en una copia de trabajo) | OK: 40 tablas, 135 CHECK |
| `CK_TokenCuenta_tipo` en la base | Definición viva en `sys.check_constraints` | OK: 7 valores (`ACTIVACION_CUENTA`, `RECUPERACION_MFA`, `INTERCAMBIO_GOOGLE`, `ELIMINAR_CUENTA`, `RECUPERACION_PASSWORD`, `VERIFICACION_EMAIL`, `CODIGO_CAMBIO_PASSWORD`) |
| Coincidencia `CK_TokenCuenta_tipo` con el enum del backend y con la migración | Comparación textual de listas | OK: iguales (enum de `accountToken.py`, v5 y `GlucoLume_migracion_codigo_cambio_password.sql`) |
| Permisos de la cuenta de la aplicación | `GlucoLume_permisos.sql` con `API_LOGIN=glucolume_app`, `JOBS_LOGIN=NINGUNA` | OK: `UPDATE` y `DELETE` sobre `Auditoria` **rechazados** (permission denied); `INSERT` permitido |
| Bloqueo `UPDLOCK` entre dos sesiones de la cuenta restringida | Sesión A toma `WITH (UPDLOCK, ROWLOCK)` 6 s; sesión B pide el mismo bloqueo | OK: B espera ~4,1 s hasta el commit de A y luego obtiene el bloqueo |
| Lectura normal mientras hay `UPDLOCK` | Lectura simple de la fila mientras A la sostiene | OK: no espera (las lecturas del login no se bloquean) |
| Persistencia ante reinicio del motor | Fila de contador confirmada, `docker restart` del contenedor, nueva consulta | OK: la fila sigue (1 de 1) |
| Transacción con error | Inserción válida + inserción que viola `CK_Auditoria_resultado` dentro de `BEGIN TRAN`/`TRY` | OK: error capturado, rollback, la fila de contador **no** queda (0) |
| Valor por defecto de `Auditoria.fechaHora` | `sys.default_constraints` | `sysutcdatetime()` (UTC). La aplicación lo completa en hora de Argentina antes de insertar (hook `before_flush`) |
| Fechas y vencimientos (dry run, sin borrar) | Dos eventos escritos como la aplicación (hora de Argentina), comparados con el corte antiguo (UTC) y con el nuevo (Argentina) | Corte antiguo: vence el evento que aún no cumplió el plazo (**adelanta la purga**). Corte nuevo: solo vence el evento que cumplió el plazo. Corrección aplicada en `ab6327f` |

## Lo que NO se pudo ejecutar aquí

- **Las 203 pruebas omitidas (`*_sqlserver` y de concurrencia del ciclo de vida).** Necesitan `pyodbc` con el driver ODBC de Microsoft
  (`msodbcsql18`) en el host. La instalación de paquetes del sistema fue denegada por el clasificador de acciones y no se intentó otra vía.
  Para ejecutarlas hace falta autorizar esa instalación, o correrlas donde el driver ya exista (procedimiento en `docs/BASE_DE_DATOS.md` §6).
- **La prueba de concurrencia a nivel de aplicación** (`tests/lifecycle_concurrency.py`): mismo motivo.
- **La purga real** (`purgeAll`, `anonymizeDueContext`) sobre datos de SQL Server: solo se verificó el cálculo del corte con una consulta de conteo.
  Las pruebas de purga corren sobre SQLite con el dominio de fechas de la aplicación (ver `ab6327f`).
- **Escritura real de la auditoría por la aplicación contra SQL Server.** El hook de fechas se verificó por código y en el harness de SQLite.
