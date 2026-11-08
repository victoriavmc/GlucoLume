# Verificación en SQL Server descartable (08/11/2026)

## Resultado

- **Las 204 pruebas `*_sqlserver` pasan: 204 pasadas, 0 fallidas, 0 omitidas** (salida por prueba en
  [sqlserver_descartable_resultados_2026-11-08.txt](evidencias/auditoria_seguridad_2026-11-07/verificacion_final/sqlserver_descartable_resultados_2026-11-08.txt)).
  Son las 203 que la suite normal omitía más la prueba nueva de concurrencia de la reautenticación.
- **Defecto encontrado y corregido por esta verificación:** SQLAlchemy no emite ningún bloqueo para `with_for_update()` en el dialecto de SQL Server.
  La consulta de la reautenticación salía sin `UPDLOCK`: 8 intentos simultáneos registraban 8 fallos y el límite de 3 no se aplicaba.
  Corrección: hint de tabla `WITH (UPDLOCK, ROWLOCK)`, el mismo patrón que usa el resto del backend. Verificado con la consulta compilada y con la prueba.
- **Dos pruebas de telemetría** (`test_telemetry_sqlserver.py`) fallaban por una variable de otra prueba (`NameError`), código heredado de `a3908c0`.
  Se apuntaron a la medición que la misma prueba crea; las restricciones CHECK verificadas no cambian. La aserción de «un DEMO borrado» pasa a
  esperar solo la medición real, que es lo que las aserciones previas de la misma prueba implican.

## Entorno

- Contenedor propio, imagen fijada por digest igual a la del proyecto (`docker/mssql/Dockerfile`): SQL Server **16.0.4165.4 (2022 CU16), Express**.
- Sin volúmenes, publicado solo en `127.0.0.1`, claves generadas por corrida (no impresas ni en la línea de comandos), contenedor eliminado al terminar.
- Base `GlucoLume_Descartable`. **No se usó la base GlucoLume ni ningún servidor distinto de 127.0.0.1.**
- Driver: `ODBC Driver 18 for SQL Server` (msodbcsql18 + unixODBC), instalado **solo en el entorno de pruebas**.

Reproducción (CI o equipo de desarrollo con el driver instalado):

```bash
PY=backend/.venv/bin/python bash docs/auditorias/evidencias/auditoria_seguridad_2026-11-07/verificacion_final/sqlserver_descartable.sh
```

El script aplica `GlucoLume_DB_v5.sql` (en una copia con el `USE` apuntado a la base descartable), crea las cuentas de prueba, aplica
`GlucoLume_permisos.sql` y `GlucoLume_retencion_ip_tecnica.sql`, corre las seis pruebas en secuencia y elimina el contenedor.

## Qué se comprobó, además de las pruebas

| Verificación | Resultado |
|---|---|
| Esquema v5 aplicado | 40 tablas, 135 CHECK |
| `CK_TokenCuenta_tipo` vivo | 7 valores, iguales al enum del backend y a la migración `GlucoLume_migracion_codigo_cambio_password.sql` |
| Permisos de la cuenta de la aplicación sobre `Auditoria` | `UPDATE` y `DELETE` rechazados; `INSERT` permitido |
| Bloqueo `UPDLOCK` entre dos sesiones (con el hint) | La segunda espera hasta el commit de la primera; una lectura normal no espera |
| Persistencia del contador ante reinicio del motor | La fila sobrevive a `docker restart` |
| Transacción con error | Rollback completo; la fila de contador no queda |
| Valor por defecto de `Auditoria.fechaHora` | `sysutcdatetime()`; la aplicación completa hora de Argentina antes de insertar (hook `before_flush`) |
| Corte de retención (conteo, sin borrar) | Con el corte antiguo (UTC), vence un evento que aún no cumplió el plazo; con el nuevo (hora de Argentina), no. Corrección en `ab6327f` |

## Limitaciones

- La purga real (`purgeAll`, `anonymizeDueContext`) no se ejecutó contra SQL Server: solo se verificó el cálculo del corte.
- Las pruebas corren con las cuentas y el esquema del proyecto, pero en un motor Express de Linux, no en la instancia de producción de Windows.
