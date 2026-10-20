> **Evidencia histórica (16/10/2026).** Informe de las pruebas de concurrencia del ciclo de vida de cuentas sobre una base SQL Server aislada, conservado sin cambios de contenido. El esquema `v2` y los scripts `001`–`029` que menciona fueron retirados (DEC-02, [BASE_DE_DATOS.md](../BASE_DE_DATOS.md)); la regla vigente está en [funcional/INSTITUCION.md](../funcional/INSTITUCION.md) §5.

# Pruebas de concurrencia del ciclo de vida de cuentas (SQL Server)

Fecha: 16/10/2026. Prototipo experimental de GlucoLume; estas pruebas verifican integridad de datos, no funciones clínicas.

## Entorno

| Elemento | Valor |
|---|---|
| Base de pruebas | `GlucoLume_pruebas_ciclo` en la misma instancia (`localhost,1435`), **aislada de `GlucoLume`** |
| Esquema | `database/reference/GlucoLume_DB_v2.sql` + scripts `001` a `029` (con `USE` reemplazado por la base temporal) |
| Intercalación | `Modern_Spanish_CI_AS`, igual que la real |
| Usuario de la aplicación | `glucolume_app` con solo `db_datareader` y `db_datawriter`, como en la base real |
| Datos | 100 % sintéticos (`zz-conc-<marca>@example.com`), sin datos personales reales, sin correos reales (interceptados) |
| Base real | No se usó para crear usuarios, instituciones, mediciones ni auditorías sintéticas |

Comparación de catálogos real vs. temporal (columnas, claves foráneas, restricciones CHECK, índices y valores por defecto): **idénticos para las
tablas del ciclo de vida** (`Usuario`, `InstitucionUsuario`, `ReasignacionPaciente`, `Auditoria`, `PerfilMedicion`, `TransferenciaPerfil`). Difieren
solo cosas ajenas: la temporal tiene 6 restricciones `CK_Medicion_*` (script 021) que la real no tiene, y la real tiene la variante de
`ReglaMatriz` con edad opcional (`MATRIZ.SQL`).

## Cómo se ejecuta

Desde la raíz del repositorio, apuntando explícitamente a la base temporal (el comando se niega a correr contra `GlucoLume`):

```
docker compose run --rm --no-deps -T -e DB_NAME=GlucoLume_pruebas_ciclo -e LIFECYCLE_CONCURRENCY_CONFIRM=GlucoLume_pruebas_ciclo \
  -v <ruta>/backend/tests:/srv/backend/tests:ro backend python -m tests.lifecycle_concurrency --rondas 60
... python -m tests.lifecycle_concurrency --bloqueos      # comprobación determinista del bloqueo UPDLOCK
```

Cada hilo usa **su propia conexión**; arrancan juntos con una barrera y una espera aleatoria de hasta 20 ms.

## Resultados

### Segunda ronda: depuración de cuenta invitada contra nueva invitación (R4) y reenvío (R5)

La primera versión del código **falló** en SQL Server real, y por eso se corrigió antes de activar el servicio:

- **Carrera lógica** (visible también en SQLite): una invitación nueva podía quedar cancelada si la depuración de la cuenta ganaba por milisegundos.
  Corrección: `invite` y `resendInvitation` toman el bloqueo de fila del `Usuario` antes de crear el vínculo y, si la cuenta ya fue depurada,
  invitan como a una cuenta nueva; ambas partes cierran con un `UPDATE` condicionado (`confirmNotDeleted` y el reclamo de `pendingAccounts`,
  que vuelve a exigir «sin invitación ni enlace vigentes» al escribir).
- **Deadlock real de SQL Server** (error 1205), detectado solo en SQL Server: la búsqueda de la cuenta por correo (bloquea la clave del índice y
  luego la fila) y la actualización de esa misma fila por la depuración (bloquea la fila y luego el índice) se bloqueaban entre sí; en 18 de 40
  rondas la invitación era elegida víctima. El grafo de bloqueo (`system_health`) mostró `PK_Usuario` contra `UX_Usuario_correoElectronico`.
  Corrección: reintento estándar ante deadlock (`app/utils/dbRetry.py`, hasta 4 intentos con espera aleatoria) en `invite`, `deleteExpired` y
  `purgeOne`. Solo se reintenta ese error y solo antes del commit (los correos salen después).

Resultado con el código final, dos corridas de 40 rondas por escenario (todos los escenarios, conexiones independientes):

| Escenario | Rondas | Resultado |
|---|---|---|
| R1 aceptar invitación vs. eliminación automática | 80 | Correctas (ganó la incorporación 14 veces, la eliminación 66) |
| R2 crear institución vs. eliminación automática | 80 | Correctas (ganó la propietaria 32 veces, la eliminación 48) |
| R3 tres eliminaciones simultáneas | 80 | Una sola eliminación, un solo evento y un solo correo |
| R4 nueva invitación vs. depuración | 80 | Correctas: siempre queda una sola cuenta pendiente con la invitación nueva viva y su enlace utilizable (ganó la invitación 9 veces, la depuración 71) |
| R5 reenvío vs. depuración | 80 | Correctas (ganó el reenvío 13 veces, la depuración 67); el reenvío perdedor falla limpiamente |
| Comprobaciones automáticas | | 480 de 480, 0 errores técnicos |

### Primera ronda (R1 a R3 y bloqueo de fila)

| Escenario | Rondas | Resultado |
|---|---|---|
| R1 aceptar invitación vs. eliminación automática | 20 + 60 + 60 | 140 rondas correctas: ganó la incorporación 23 veces y la eliminación 117; nunca ambas |
| R2 crear institución vs. eliminación automática | 20 + 60 + 60 | 140 rondas correctas: ganó la propietaria 37 veces y la eliminación 103; nunca ambas |
| R3 tres pasadas de eliminación simultáneas | 20 + 60 + 60 | 140 rondas correctas: una sola eliminación, un solo evento y un solo correo por cuenta |
| Bloqueo de fila `UPDLOCK` (determinista) | 1 | Correcto: una segunda sesión no obtiene la fila (error 1222 por tiempo de espera) y la obtiene al liberarse |
| Comprobaciones automáticas | 560 | 560 correctas, 0 fallas |

Verificación de integridad posterior sobre la base temporal (primera ronda; 561 cuentas sintéticas, 360 eliminadas, 177 instituciones):

- Cuentas eliminadas con vínculo `ACTIVO`: **0**.
- Cuentas eliminadas con datos personales, credenciales o sesiones activas: **0**.
- Cuentas activas con plazo y vínculo `ACTIVO` a la vez: **0**.
- Cuentas con más de una eliminación automática exitosa: **0**; cuentas eliminadas sin su evento: **0**.
- Personas con más de un vínculo vigente en una institución: **0**; vínculos `ACTIVO` sin fecha de incorporación: **0**.
- Vínculos históricos conservados de cuentas eliminadas: 117; referencias huérfanas `idUsuarioInvitado` / `idUsuarioInvitador`: **0 / 0**.
- `DBCC CHECKCONSTRAINTS WITH ALL_CONSTRAINTS`: **sin violaciones**.

## Qué protege cada carrera

1. **Bloqueo de fila**: `accountGrace.lockUser` toma `UPDLOCK, ROWLOCK` sobre `Usuario` al aceptar, crear institución y eliminar. Una de las dos
   operaciones espera a la otra y revalida después.
2. **Última barrera condicionada** (`accountGrace.confirmStillActive`): un `UPDATE ... WHERE estado = 'ACTIVO'` antes de confirmar cualquier
   incorporación. Si la eliminación ganó, no actualiza nada y la incorporación se deshace por completo.
3. **Reclamo condicionado de la eliminación**: `UPDATE ... WHERE estado = 'ACTIVO' AND plazo vencido`. Solo una ejecución lo gana.

## Condiciones de carrera pendientes

Ninguna detectada en los cinco escenarios. Límite conocido: no se cubren reinicios del contenedor en medio de una pasada; cada cuenta se procesa
en su propia transacción, por lo que una caída deja la cuenta íntegra y se reintenta en la pasada siguiente.

## Limpieza

La base `GlucoLume_pruebas_ciclo` **se conserva** hasta que se confirme que las verificaciones terminaron. Para eliminarla: `DROP DATABASE [GlucoLume_pruebas_ciclo]`.
