# Evidencia de la remediación de rendimiento (5/11/2026)

Mediciones reproducibles de las correcciones del informe `docs/auditorias/REMEDIACION_RENDIMIENTO_2026-11-05.md`.
Ningún dato sale de la máquina: el SMTP es un servidor de **pruebas local** y las bases son SQLite de pruebas.

## Contenido

| Archivo | Qué mide |
|---|---|
| `smtp_bench.py` | Flujo de contacto y envíos pareados contra aiosmtpd (STARTTLS + AUTH), con RTT y ancho de banda de subida simulados. Cuenta conexiones TCP y mensajes DATA. |
| `medicion_historial.py` | Conteo de sentencias SQL del historial de glucosa (3 y 15 mediciones) y lista de semáforos. Se copia a `backend/tests/` para ejecutarse. |
| `medicion_panel_operador.py` | Conteo de sentencias SQL del dashboard del operador y de sus contadores (JSON). Se copia a `backend/tests/` para ejecutarse. |
| `resultados/` | Salidas medidas (JSON) y resúmenes de las suites completas. |

## Preparación (fuera del repositorio)

Usar un entorno virtual **fuera** del repositorio, con `requirements.txt` y `requirements-dev.txt` instalados por hash, y
`aiosmtpd` (solo para estas mediciones).

Certificado de prueba para el servidor SMTP local (la clave privada no debe quedar en el repositorio):

```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 3 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"
```

`backend/tests/test.env` (no versionado; valores ficticios) debe declarar, como mínimo: `API_ENV=development`,
`DB_NAME=GlucoLume_Pruebas_SinConexion`, `DB_HOST` inexistente (`*.invalid`), `SMTP_HOST=smtp.glucolume.invalid`,
`SMTP_PORT=587`, `SMTP_FROM=glucolume@example.com`, `CONTACT_EMAIL` y claves de prueba. Lo exigen las pruebas de
`test_security_config.py` y `test_register_contact.py`.

## Ejecución

```bash
# Flujo de contacto (código de referencia y código modificado)
python smtp_bench.py --certs CARPETA_CERT --backend RUTA_BACKEND --escenario flujo_contacto --rtt-ms 50 --subida-mbps 2 --n 10 --salida salida.json

# Envíos pareados sobre el código modificado: sin sesión compartida y con sesión compartida
python smtp_bench.py --certs CARPETA_CERT --backend RUTA_BACKEND --escenario par_sin_sesion --rtt-ms 50 --subida-mbps 2 --n 10 --salida salida.json
python smtp_bench.py --certs CARPETA_CERT --backend RUTA_BACKEND --escenario par_con_sesion --rtt-ms 50 --subida-mbps 2 --n 10 --salida salida.json

# Conteo de consultas (copiar el script a backend/tests/ con nombre test_zz_*.py, ejecutar desde backend/ y borrar la copia)
cp medicion_historial.py backend/tests/test_zz_medicion_historial.py
cd backend && METRICS_OUT=salida.json python -m pytest tests/test_zz_medicion_historial.py -q
rm tests/test_zz_medicion_historial.py
```

`MFA_KEY_BENCH` debe contener una clave Fernet generada para la prueba (`Fernet.generate_key()`).
`RUTA_BACKEND` es `backend/` del árbol a medir. La línea base se obtiene con `git archive <commit> | tar -x` en una carpeta
temporal, para no tocar la rama de trabajo.

## Notas de validez

- Los tiempos son de laboratorio: no reemplazan una medición con el proveedor SMTP real ni con SQL Server.
- Los conteos de consultas son de SQLite (mismo código de consulta); el plan y el costo en SQL Server quedan **pendientes**.
- `resultados/suite_linea_base.txt` corresponde a una primera corrida con un árbol parcial (solo `backend/` y `database/`):
  11 de sus 15 fallos se debían a archivos ausentes, no al código. Se repitieron sobre el árbol completo de HEAD
  (11 pasan; los 4 restantes son de entorno).
- `resultados/suite_remediacion_final.txt` es la corrida final sobre el árbol commiteado: 2370 pasan, 3 fallan por entorno
  (Windows, `libodbc`), 203 omitidas. `suite_remediacion.txt` es una corrida intermedia superada (ver su nota).
