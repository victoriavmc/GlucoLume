# Evidencia de Notificaciones con SQL Server real (29–30/10/2026)

Pruebas de extremo a extremo del módulo de [Notificaciones](../../NOTIFICACIONES.md): **evento → backend (contenedor) → SQL Server 2022 → API → frontend**, y para
recordatorios **horario configurado → servicio `notifications` → persistencia → API → correo**. Todo con datos sintéticos, en una instancia **descartable** y aparte de la
instalación en uso (no se tocó su base, sus contenedores ni sus volúmenes).

Resultados reales de la última corrida: [resultados/](resultados/). Qué se probó y qué no: [NOTIFICACIONES.md](../../NOTIFICACIONES.md) §10 y §11.

## Entorno del ensayo

| Pieza | Cómo |
|---|---|
| SQL Server | `docker run … glucolume/mssql:2022-CU16-pdev` (la imagen del proyecto), contenedor `glucolume-notiftest-db`, puerto 127.0.0.1:14330, sin volumen, contraseñas generadas al azar para `sa`, `glucolume_app` y `glucolume_jobs` |
| Esquema | Se instala el `GlucoLume_DB_v5.sql` **anterior** (el de la instalación en uso, con las tablas v1), se siembran datos heredados (avisos con fecha UTC), se aplica `GlucoLume_permisos.sql`, y recién entonces `GlucoLume_notificaciones_v2.sql` (dos veces, para probar la idempotencia). `rebuild.sh` repite todo desde cero |
| Esquema nuevo | Una segunda base con el `GlucoLume_DB_v5.sql` **nuevo** (instalación limpia: 38 tablas) es la que usa `tests/test_user_notifications_sqlserver.py` |
| Backend | La imagen `glucolume/backend:dev` con el código de la rama montado en `/srv/backend` (solo lectura), `API_ENV=development`, cuenta `glucolume_app` y `DB_JOBS_USER=glucolume_jobs` |
| Servicio `notifications` | La misma imagen: `python -m app.jobs.reminders --loop` con `NOTIFICATIONS_INTERVAL_SECONDS=10` |
| SMTP | `fake_smtp.py`: SMTP de prueba con STARTTLS y certificado verificado por el backend (autofirmado, para `host.docker.internal`); guarda cada correo en un JSONL. **No es una entrega real por Gmail.** |
| Frontend | `npx vite` con `VITE_API_BASE_URL=http://localhost:18000` y el navegador del entorno de desarrollo, con la cuenta sintética `ana` |

## Cómo repetirlo

Variables: `IT_DIR` (carpeta con `secrets.json`, `backend.env` y el certificado), `BACKEND_DIR` (carpeta `backend` del repositorio) y `REPO_DIR` (raíz del repositorio).

```text
python e2e_security.py     # inicio de sesión (equipo nuevo / habitual), contraseña, MFA, actividad sospechosa, preferencias, autorización, lectura
python e2e_groups.py       # invitación recibida/aceptada/rechazada, nuevo integrante, desvinculación, medición compartida con y sin permiso
python e2e_reminders.py    # horario sin servicio (no llega), con servicio (llega), simultáneo, periódico, cambio, eliminación, SMTP caído y reintento
python e2e_delete.py       # eliminar de la bandeja: uno, leídas, todas; persistencia, contadores, aislamiento, hecho repetido vs. nuevo, auditoría, 5 000 avisos
```

Cada script termina con `RESUMEN: N/N comprobaciones` y sale con código distinto de 0 si alguna falla. `rebuild.sh` (en la carpeta del ensayo) deja la base como al principio.
`seed_legacy.sql` y `seed_old.sql` son los datos sintéticos de partida. `rebuild.sh` aplica el esquema anterior, la migración v2 y la v3. `verificar_depuracion_y_lifecycle.sh` comprueba la depuración física de lo eliminado y que `lifecycle` no toca avisos.
