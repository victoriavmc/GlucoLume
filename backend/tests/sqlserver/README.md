# Prueba de concurrencia en SQL Server

Qué verifica: dos solicitudes simultáneas de «Conectar dispositivo» para la **misma** cuenta individual no crean dos dispositivos lógicos
ni dos vínculos. Es la única prueba que cuenta como evidencia de concurrencia real: SQLite no ejerce el bloqueo `UPDLOCK`.

## Reglas
- Nunca apuntar a `GlucoLume` ni a `GlucoLume_Copia`. La prueba **falla** si el nombre no termina en `_Concurrencia_Prueba`.
- La base es desechable: se crea, se usa y se borra. No contiene datos reales.
- La cuenta que **ejecuta la prueba** es una cuenta de prueba aparte. **No** es la cuenta de la API y no se le dan permisos de la API.

## Permisos mínimos
| Cuenta | Permisos | Quién la crea |
|---|---|---|
| Administración (solo preparación) | `CREATE DATABASE` y permisos para correr los scripts de `database/reference` en la base de prueba | Un DBA, una sola vez |
| Ejecución de la prueba | `db_datareader` y `db_datawriter` **solo** sobre la base de prueba. Sin `db_ddl_admin`, sin `sysadmin` | Un DBA |

La cuenta de la API (`DB_USER`) no cambia.

## Preparación (una vez)
1. Ejecutar `preparar_base_prueba.ps1` (ver ese archivo): crea la base y carga el esquema desde `database/reference`.
2. Crear el login de ejecución con los permisos de la tabla anterior sobre esa base.
3. Definir las variables de entorno y correr la prueba.

## Ejecución
```powershell
$env:GLUCOLUME_CONCURRENCIA_HOST = "localhost"
$env:GLUCOLUME_CONCURRENCIA_PORT = "1435"
$env:GLUCOLUME_CONCURRENCIA_NAME = "GlucoLume_Concurrencia_Prueba"
$env:GLUCOLUME_CONCURRENCIA_USER = "<login de ejecución>"
$env:GLUCOLUME_CONCURRENCIA_PASSWORD = "<contraseña>"
$env:GLUCOLUME_CONCURRENCIA_DRIVER = "ODBC Driver 18 for SQL Server"
cd backend
python -m pytest -v tests/sqlserver
```
Sin esas variables la prueba se omite (no es un fallo).

## Estado
- **PENDIENTE**: la prueba no se ha ejecutado contra SQL Server. Falta una base `*_Concurrencia_Prueba` creada por un DBA.
- Verificado de forma estática: los 41 modelos del ORM tienen su tabla en `GlucoLume_DB_v5.sql` (40) más `GlucoLume_vinculo_cuenta_dispositivo.sql`
  (la tabla de vínculos). Las tablas de auditoría (`Auditoria`, `AuditoriaContexto`, `AuditoriaRevision`, `AuditoriaTecnicaMedicion`) están en v5.
- Verificado: el hint `WITH (UPDLOCK, ROWLOCK)` se compila para SQL Server.
- Nota: el script de vínculos exige `-v CONFIRMAR=AGREGAR_VINCULO_CUENTA_DISPOSITIVO`; `preparar_base_prueba.ps1` ya lo pasa.
- Riesgo a resolver antes de integrar: `docs/BASE_DE_DATOS.md` no menciona el script de vínculos, así que una instalación nueva desde v5
  quedaría sin la tabla y la vinculación individual se desactivaría en silencio (ver `schemaCompat.hasTable`).
