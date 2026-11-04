# Datos de demostración (sintéticos) para la defensa académica

Esta guía describe la carga de **datos sintéticos de demostración** de GlucoLume: qué crea, cómo se ejecuta, cómo se verifica, cómo se elimina y cómo se gestionan las credenciales. Todo el código vive en `backend/app/demo/`, la CLI en `backend/app/cli/demoSeed.py`.

> **Ningún dato corresponde a personas, instituciones ni dispositivos reales.** Los correos usan el dominio reservado `example.com`, los documentos llevan el prefijo `DEMO`, los dispositivos son `DEMO-DISP-*` y todas las mediciones se identifican como sintéticas (ver [§5](#5-mediciones-sintéticas)). El equipo Arduino real no se registra ni se suplanta.

---

## 1. Análisis del repositorio

Antes de implementar se revisaron los modelos SQLAlchemy (`backend/app/models/`), los servicios de negocio, la autenticación, los permisos de rol de base (`database/reference/GlucoLume_permisos.sql`) y las pruebas existentes.

### 1.1 Estructura relevante

| Área | Modelo / tabla | Servicio que aplica las reglas |
|---|---|---|
| Cuentas | `Usuario`, `CredencialLocal`, `FactorMfa`, `ConsentimientoUsuario` | `services/auth.py`, `services/consent.py`, `core/security.py` |
| Grupos familiares | `Grupo`, `GrupoUsuario` (4 permisos de compartición) | `services/group.py` |
| Instituciones | `Institucion`, `InstitucionUsuario` (PROPIETARIO, MODERADOR, OPERADOR) | `services/institution.py`, `schemas/institution.py` (CUIT con dígito verificador) |
| Pacientes | `PerfilMedicion` (tipos `CONSUMIDOR_FINAL`, `INSTITUCIONAL`) | `services/institutionPatients.py`, `services/measurementProfile.py`, `services/patientAccess.py` |
| Dispositivos | `Dispositivo` (OPERATIVO, asignación institucional) | `services/device.py` |
| Mediciones | `Medicion`, `Matriz`, `ReglaMatriz` | `services/measurement.py`, `services/matrix.py`, `services/glucoseReference.py` |
| Auditoría | `Auditoria`, `AuditoriaContexto` (solo inserción para la API, GL-03) | `services/audit.py` |

### 1.2 Lo que el modelo permite (y cómo se usa)

- **Permisos de grupo.** Los cuatro permisos (`compartePerfil` = datos básicos, `comparteUltimaMedicion`, `comparteHistorial`, `notificaMedicion` = avisos) son **independientes** y se pueden combinar libremente. Las cinco configuraciones pedidas son válidas tal como están. El administrador del grupo es el `GrupoUsuario` con `rolGrupo = PROPIETARIO`. Pertenecer al grupo o administrarlo no da acceso a datos ajenos.
- **Propietario con varias instituciones.** Permitido: `createInstitution` solo exige una cuenta institucional y un CUIT no repetido. El propietario A administra las instituciones A y C sin replicar el personal de C. Lo verifica una prueba.
- **Asignación de pacientes.** Un paciente tiene **un único responsable** (`idInstitucionUsuarioResponsable`). Por eso no se generan asignaciones múltiples. Un operador ve solo sus pacientes (`patientAccess.requireMeasurementAccess`); el resto recibe rechazo explícito.
- **Verificación de correo.** El login exige `Usuario.estado = ACTIVO` (`PENDIENTE` bloquea con `CORREO_NO_VERIFICADO`). No hay columna aparte: el estado es la verificación.
- **MFA.** Solo se exige si existe un `FactorMfa` con `habilitado = 1`. La demo no configura ningún factor, así que no se modifica ni se debilita el flujo.
- **Glucosa.** El servidor no tiene algoritmo de estimación definido (`measurement.glucoseEstimator` es `None`): no fabrica estimaciones. La glucosa informada por el firmware se guarda en `glucosaDispositivo` con `origenGlucosa`. El valor `DEMO` queda **excluido de indicadores clínicos** por la propia aplicación.
- **Última medición.** La aplicación no cuenta las mediciones `DEMO` como «última medición» del perfil (`services/telemetry.py`). Ver la decisión en [§6](#6-decisiones-y-desviaciones).
- **Visibilidad.** Las `CANCELADA` e `INVALIDA` salen del historial personal 30 minutos después de cerrarse (`services/measurementVisibility.py`). Las `COMPLETADA` permanecen.

### 1.3 Incompatibilidades y restricciones encontradas

| # | Restricción | Consecuencia y tratamiento |
|---|---|---|
| R1 | La cuenta de la API (`rol_glucolume_api`) **no tiene DELETE** sobre `Institucion`, `InstitucionUsuario`, `Grupo`, `GrupoUsuario`, `PerfilMedicion` ni `Dispositivo`, y el esquema no concede DELETE. | Una limpieza con la cuenta de la API es imposible. Se crea un **rol propio** de limpieza (`database/reference/GlucoLume_demo_permisos.sql`) con su cuenta `DB_DEMO_USER`. La API no cambia. |
| R2 | `Auditoria` es de solo inserción para la API (DENY UPDATE/DELETE, GL-03) y tiene claves foráneas a `Usuario` e `Institucion`. | Los registros de auditoría que apunten a cuentas demo **bloquean** la limpieza: no se borra nada. Ver riesgo K2. |
| R3 | `Medicion.idDispositivo` es obligatorio y el dispositivo debe ser OPERATIVO. | Se crean 6 dispositivos `DEMO-DISP-*`. Ninguno corresponde al equipo físico. |
| R4 | `CK_Medicion_demoSinEstimacion`: una medición `DEMO` no puede tener `glucosaEstimada`. | La demo nunca estima glucosa; solo informa el valor del firmware. |
| R5 | Índice `UX_PerfilMedicion_dniInstitucion`: un documento activo por institución. Requiere `PerfilMedicion.idInstitucion` (migración 031). | La carga fija la institución con `measurementRetention.stampInstitution` (servicio existente). |
| R6 | `dni` normalizado (`CK_PerfilMedicion_dniNormalizado`: solo A-Z0-9). | Los documentos sintéticos son `DEMO` + letra de institución + número (p. ej. `DEMOA001`). |
| R7 | La demo no tiene un algoritmo de estimación ni matriz propia. | Las mediciones de glucosa referencian la **matriz activa existente** (institucional si la hay; si no, la global), como hace la aplicación al iniciar una medición. Si no hay ninguna activa, la carga lo advierte y la clasificación aparece como `SIN_MATRIZ`. |

---

## 2. Estrategia de implementación

1. **Catálogo determinista** (`app/demo/catalog.py`). Describe las cuentas, instituciones, personal, grupo, dispositivos, pacientes y mediciones. Todo identificador es `uuid5` de una clave fija: ejecutar dos veces produce los mismos IDs. Las mediciones usan un generador sembrado con la clave del perfil: la misma fecha de ancla produce siempre los mismos valores.
2. **Plan de solo lectura** (`app/demo/seeder.py: buildPlan`). Decide, registro por registro, si se **crea** o **ya existe**, y detecta **colisiones** con datos que no son demo (correo, CUIT, código de dispositivo, documento de paciente). Con una colisión, no se escribe nada.
3. **Aplicación en una transacción por etapas** (`seeder.apply`): usuarios e instituciones → credenciales, grupo y dispositivos → vínculos → perfiles → mediciones. Cualquier error deshace todo. Las cuentas se crean con el **hash real** (`security.hashPassword`), la **credencial local** y los **consentimientos** del servicio real, con estado `ACTIVO` (la verificación de correo la realiza este proceso autorizado) y sin MFA.
4. **Sin correo saliente.** Ningún módulo de `app/demo` usa `services/email` ni `services/notifications`. Las cuentas se crean con `notificarNuevoInicioSesion = 0`. La prueba de login verifica que no hay ningún intento de SMTP.
5. **Idempotencia.** Una segunda ejecución marca todo como `YA_EXISTE` y no duplica nada (prueba dedicada). Las contraseñas existentes no cambian salvo con `--regenerar-contrasenas`.
6. **Limpieza acotada** (`app/demo/limpieza.py`). Parte de los IDs del catálogo y sigue las claves foráneas del modelo para encontrar los dependientes (sesiones, consentimientos, mediciones, etc.). Borra hijos antes que padres, en una transacción. Se **bloquea** si algún dependiente es auditoría o está fuera de la lista permitida del rol de limpieza.
7. **Credenciales** (`app/demo/inventory.py`). Contraseñas de 20 caracteres generadas con `secrets`, que cumplen la política real y no son comunes. Van **solo** al archivo privado (fuera del repositorio, permisos restrictivos). El inventario público no contiene contraseñas.

### 2.1 Cantidades previstas

| Entidad | Cantidad | Detalle |
|---|---:|---|
| Usuarios | 21 | 7 individuales + 14 institucionales |
| Credenciales locales | 21 | una por cuenta, con hash |
| Consentimientos | 14 | política y datos experimentales de las 7 cuentas individuales |
| Instituciones | 3 | A (consultorio), B (clínica), C (consultorio, del propietario A) |
| Vínculos institucionales | 15 | 3 propietarios, 4 moderadores, 8 operadores (cada moderador incorpora a dos: el 1 a los operadores 1 y 2, el 2 a los 3 y 4) |
| Grupo familiar | 1 | administrador + 5 integrantes (6 vínculos) |
| Dispositivos | 6 | 2 individuales, 2 en A, 2 en B |
| Perfiles de medición | 39 | 7 individuales + 32 pacientes |
| Pacientes asignados | 32 | A: 16 (3/5/4/4 por operador) · B: 16 (4/3/5/4) |
| Cómo llegó cada paciente | 32 | 12 dados de alta por el propio operador · 10 dados de alta por un moderador y asignados a un operador · 10 transferidos entre operadores (transferencia aceptada) |
| Mediciones individuales | 82 | cuenta A: 14 · administrador: 9 · integrantes: 4, 11, 16, 6, 22 |
| Mediciones de pacientes | 80 | de 1 a 4 por paciente, según un ciclo fijo |

---

## 3. Escenarios y verificación funcional

| Escenario | Qué demuestra | Cómo se verifica |
|---|---|---|
| **A — individual sin grupo** (`individual-a`) | Perfil propio, mediciones en distintos días y horarios, historial, estadísticas, última medición, sin vínculos institucionales | Historial propio (`listOwnHistory`); las canceladas e inválidas se ocultan a los 30 min, por regla de la aplicación |
| **B — administrador con grupo** (`grupo-admin` + 5 integrantes) | Cinco configuraciones de privacidad distintas | Matriz de permisos por integrante (`sharedProfile`, `sharedLatest`, `sharedHistory`, `sharedNotices`); el administrador no ve datos no compartidos ni los propios |
| **C — propietarios y moderadores** | Propietario A con dos instituciones (A y C), propietario B aislado de A, moderadores de cada institución | `listMine`, `getDetail` |
| **D — operadores y pacientes** | Un operador ve sus pacientes; no ve los de otro operador ni los de otra institución | `listPatientHistory` con las cuentas correspondientes |

**Grupo familiar (escenario B):**

| Integrante | Datos básicos | Última medición | Historial | Avisos | Mediciones |
|---|:-:|:-:|:-:|:-:|---:|
| Administrador (sin compartir nada) | no | no | no | no | 9 |
| Integrante 1 | sí | no | no | no | 4 |
| Integrante 2 | no | sí | no | no | 11 |
| Integrante 3 | no | no | sí | no | 16 |
| Integrante 4 | no | no | no | sí | 6 |
| Integrante 5 | sí | sí | sí | sí | 22 |

Los **avisos** muestran solo fecha y hora de cada medición completada, nunca valores, modo ni estado.

---

## 4. Archivos

**Creados**

| Archivo | Función |
|---|---|
| `backend/app/demo/__init__.py` | Paquete |
| `backend/app/demo/catalog.py` | Catálogo determinista (cuentas, instituciones, grupo, dispositivos, pacientes, mediciones) |
| `backend/app/demo/seeder.py` | Plan de solo lectura, aplicación transaccional, verificación sin sesión |
| `backend/app/demo/limpieza.py` | Limpieza acotada por claves foráneas, con bloqueo por auditoría |
| `backend/app/demo/inventory.py` | Archivo privado de credenciales e inventario público |
| `backend/app/cli/demoSeed.py` | CLI: dry-run, `--aplicar`, `--verificar`, `--limpiar`, `--regenerar-contrasenas` |
| `backend/tests/test_demo_seed.py` | Pruebas de los escenarios |
| `database/reference/GlucoLume_demo_permisos.sql` | Rol de limpieza demo (lo ejecuta el DBA una vez) |
| `database/reference/GlucoLume_demo_validacion.sql` | Consultas SQL de validación (solo lectura) |
| `docs/DATOS_DEMO.md` | Esta guía |
| `docs/DATOS_DEMO_INVENTARIO.md` | Inventario de cuentas sin contraseñas |

**Modificados**

| Archivo | Cambio |
|---|---|
| `backend/app/core/config.py` | Variables opcionales `DB_DEMO_USER` / `DB_DEMO_PASSWORD` (ambas o ninguna, distintas de `DB_USER`) |
| `backend/app/db/session.py` | `getDemoSessionFactory()`: solo para la limpieza demo |
| `backend/tests/conftest.py` | La guarda de permisos de borrado reconoce el rol de limpieza demo (`app/demo/limpieza.py`). No se quita ninguna comprobación existente |
| `.gitignore`, `backend/.dockerignore` | Excluyen archivos de credenciales demo |

Sin cambios: modelos, servicios de negocio, permisos existentes, matrices, reglas, administradores y migraciones.

---

## 5. Mediciones sintéticas

- **Identificación.** Cada medición lleva en `observacion`: *«DEMO - medición sintética de demostración académica. No es un dato médico ni un resultado validado.»*
- **Origen.** Las mediciones con glucosa usan `origenGlucosa = DEMO` (el valor permitido por la base). La oximetría no informa glucosa, así que su `origenGlucosa` queda `NULL`: su identificación sintética está en la observación y en el perfil.
- **Variedad.** Modos `GLUCOSA_EXPERIMENTAL` y `OXIMETRIA`; estados `COMPLETADA`, `CANCELADA` e `INVALIDA`; condiciones `AYUNO`, `POSTPRANDIAL` y `NO_INFORMADA` (con `fechaHoraUltimaComida` cuando corresponde); fechas en los últimos 60 días, algunas con dos o más mediciones el mismo día.
- **Rangos.** Frecuencia cardíaca 52–110 lpm con una base por perfil; SpO₂ 95,0–99,5 %; glucosa 78–104 mg/dL en ayunas, 118–172 en postprandial y 92–138 sin dato de comida (solo para la demostración de gráficos, no clínicos).
- **Calidad de señal.** Calidad 0,72–0,98, índice óptico 1,8–2,9, 8–25 lecturas estabilizadas, sensor `MAX30100`.

---

## 6. Decisiones y desviaciones

Conviene que las conozcas antes de la defensa:

1. **Última medición de los perfiles seeded.** La aplicación no actualiza `PerfilMedicion.fechaUltimaMedicion` con mediciones `DEMO`. La carga **sí** la fija con la última medición completada de cada perfil, para que la pantalla de última medición muestre datos. Es una desviación deliberada y acotada a los datos demo.
2. **Glucosa solo `DEMO`.** No se usa `EXPERIMENTAL` para no mezclar valores que parezcan reales con los indicadores clínicos. Por la regla de la aplicación, las mediciones `DEMO` no entran en indicadores, así que los indicadores institucionales muestran las oximetrías (origen `NULL`, identificadas por observación).
3. **Rastro de los pacientes, como lo registra la aplicación.** La carga escribe filas `Auditoria` con el servicio real de auditoría, con la fecha del hecho y no la de la carga:
   - **Alta** (`CREAR_PACIENTE`): 12 pacientes los dio de alta su propio operador; 10 los dio de alta un moderador y los asignó a un operador.
   - **Transferencia** (`SOLICITAR_TRANSFERENCIA_PERFIL`, `ACEPTAR_TRANSFERENCIA_PERFIL`, `CAMBIAR_RESPONSABLE_PERFIL`, y una fila `TransferenciaPerfil` aceptada): 10 pacientes pasaron de un operador a otro de la misma institución.
   - **Autor de cada medición** (`INICIAR_MEDICION`, 80 en total): el operador que la inició. Las anteriores a la transferencia son del operador de origen (historial); las posteriores, del responsable actual.

   Es lo que usa el panel institucional para contar mediciones por operador y la actividad (`services/dashboard.py`). Las mediciones individuales no tienen operador y no reciben esta auditoría. Los inicios de sesión **de la demo** también generan auditoría, como cualquier login real. Todas estas filas tienen como autor una cuenta demo y **bloquean la limpieza** (riesgo K2): ver [§8.9](#89-reset-de-la-demo-cuando-cambia-su-forma).
4. **Contraseñas aleatorias, no reproducibles.** Se generan con `secrets` y se guardan solo en el archivo privado. Para reproducir las cuentas basta con reejecutar la carga: los IDs y los datos son los mismos. Para cambiar contraseñas, `--regenerar-contrasenas`.

---

## 7. Riesgos sobre la base existente

| # | Riesgo | Mitigación | Estado |
|---|---|---|---|
| K1 | Una colisión con un dato real (correo, CUIT, código de dispositivo, documento) | Detección previa con bloqueo total | Cubierto y probado |
| K2 | Auditoría generada por la demo que referencia cuentas demo: los inicios de sesión y las `INICIAR_MEDICION` de los pacientes. La limpieza no puede borrarla (GL-03). | La limpieza **se bloquea** y no borra nada. Para eliminar esos registros hace falta una decisión explícita (retención de auditoría vencida o purga por el DBA). **Decisión pendiente del responsable.** | Limitación conocida |
| K3 | Carga parcial | Una transacción por etapas con rollback | Cubierto y probado |
| K4 | Carga en producción por error | Bloqueada salvo `--autorizar-produccion` **y** `--confirmar-base <nombre exacto>` | Cubierto y probado |
| K5 | Las contraseñas aparecen en logs, consola o repositorio | La consola nunca las imprime; el archivo queda fuera del repositorio y de la imagen; permisos restrictivos | Cubierto y probado (salvo permisos en Windows, ver §8.4) |
| K6 | Correo saliente a direcciones externas | Dominio reservado `example.com`; sin llamadas a servicios de correo; `notificarNuevoInicioSesion = 0` | Cubierto y probado |
| K7 | La limpieza borra datos reales | Solo IDs del catálogo y sus dependientes; bloqueo ante tablas no permitidas | Cubierto y probado |
| K8 | Pruebas sobre SQLite y no sobre SQL Server | Las pruebas usan el modelo real sobre SQLite. **Las consultas de `GlucoLume_demo_validacion.sql` y el script de permisos no se ejecutaron en SQL Server en este entorno.** | Pendiente de verificación en el servidor |

---

## 8. Ejecución

Todos los comandos se ejecutan desde `backend/` salvo indicación. **La carga no se ejecutó contra ningún servidor.** Cuando decidas ejecutarla, empezá siempre por el dry-run.

### 8.1 Preparación (una vez, lo hace el DBA)

Solo es necesaria si vas a poder **eliminar** los datos demo. Para cargar y verificar alcanza con la cuenta de la API.

```bash
sqlcmd -S <servidor> -d GlucoLume -i database/reference/GlucoLume_demo_permisos.sql
```

Luego el DBA crea la cuenta de la limpieza (la contraseña la elegís vos y nunca va al repositorio):

```sql
CREATE LOGIN [glucolume_demo] WITH PASSWORD = N'<contraseña fuerte>', CHECK_POLICY = ON;
CREATE USER [glucolume_demo] FOR LOGIN [glucolume_demo];
ALTER ROLE rol_glucolume_demo_limpieza ADD MEMBER [glucolume_demo];
```

Y en el entorno de la demo (`.env`, nunca versionado): `DB_DEMO_USER=glucolume_demo` y `DB_DEMO_PASSWORD=<la misma>`.

### 8.2 Dry-run (no escribe nada)

```bash
python -m app.cli.demoSeed
```

Muestra qué se crearía, las colisiones (si las hay) y las advertencias (por ejemplo, si no hay matriz activa).

### 8.3 Carga

```bash
python -m app.cli.demoSeed --aplicar --fecha-ancla 2026-11-04 --credenciales "$HOME/GlucoLumeDemo/credenciales-demo.txt" --inventario-publico ../docs/DATOS_DEMO_INVENTARIO.md
```

Repetirla es seguro: no duplica registros ni cambia contraseñas.

**Desde el contenedor Docker del backend**, montando una carpeta privada del equipo (fuera del repositorio) para que el archivo quede en tu computadora:

```bash
docker compose run --rm -v "$HOME/GlucoLumeDemo:/demo-secrets" -e GLUCOLUME_DEMO_CREDENCIALES=/demo-secrets/credenciales-demo.txt backend python -m app.cli.demoSeed --aplicar --fecha-ancla 2026-11-04
```

### 8.4 Consultar el archivo privado de forma segura

- Está en `GlucoLumeDemo/credenciales-demo.txt` (en tu usuario de Windows: `%USERPROFILE%\GlucoLumeDemo\`).
- Abrilo solo con un editor (por ejemplo, el Bloc de notas). **No lo pegues** en chats, correos, capturas ni documentos, y no lo copies al repositorio.
- Los permisos se restringen con `icacls` a tu usuario. Si la CLI muestra una advertencia sobre permisos, revisalos con las propiedades del archivo → Seguridad.
- Cada cuenta tiene un bloque `[clave]` con `Correo:` y `Contraseña:`.

### 8.5 Verificación

```bash
python -m app.cli.demoSeed --verificar
```

Comprueba, sin abrir sesiones ni escribir auditoría, que cada cuenta existe, está `ACTIVO`, tiene su credencial que verifica con la contraseña del archivo, no tiene MFA habilitado y tiene su perfil o vínculo. Para el ingreso real, probá cada cuenta en el frontend.

Consultas de validación en SSMS: `database/reference/GlucoLume_demo_validacion.sql` (solo lectura, con el resultado esperado de cada una).

### 8.6 Regenerar contraseñas

```bash
python -m app.cli.demoSeed --aplicar --regenerar-contrasenas --credenciales "$HOME/GlucoLumeDemo/credenciales-demo.txt"
```

Emite una contraseña nueva para cada cuenta demo y reescribe el archivo privado. Las anteriores dejan de servir. No toca al administrador de plataforma ni a los datos reales.

### 8.7 Eliminar los datos demo

```bash
python -m app.cli.demoSeed --limpiar
python -m app.cli.demoSeed --limpiar --aplicar
```

El primer comando muestra cuántos registros se eliminarían. El segundo borra solo esos registros, en una transacción, con la cuenta `DB_DEMO_USER`. Si hay auditoría que referencia cuentas demo, **se bloquea y no borra nada** (riesgo K2).

### 8.9 Reset de la demo (cuando cambia su forma)

Si los datos cargados ya no coinciden con la versión actual (por ejemplo, cambian las cantidades de mediciones o las altas y transferencias), hay que limpiar y volver a cargar. La limpieza no borra auditoría (GL-03), así que el reset requiere al DBA:

1. Copia de seguridad completa de la base.
2. El DBA ejecuta `database/reference/GlucoLume_demo_reset_auditoria.sql` (bloque de verificación primero). Ese script no fue probado en SQL Server.
3. El DBA vuelve a ejecutar `database/reference/GlucoLume_demo_permisos.sql` para dar permiso de borrado sobre `TransferenciaPerfil` al rol de limpieza.
4. Limpieza y carga desde `backend/`:

```bash
python -m app.cli.demoSeed --limpiar --aplicar
python -m app.cli.demoSeed --aplicar --fecha-ancla 2026-11-04 --credenciales "$HOME/GlucoLumeDemo/credenciales-demo.txt"
```

La carga nueva genera contraseñas nuevas para las cuentas recreadas: el archivo privado se reescribe.

### 8.8 Producción

En `API_ENV=production` la carga queda bloqueada. Solo corre con una decisión explícita y el nombre exacto de la base:

```bash
python -m app.cli.demoSeed --aplicar --autorizar-produccion --confirmar-base <nombre-de-la-base>
```

---

## 9. Pruebas

```bash
python -m pytest tests/test_demo_seed.py -v
python -m pytest -q
```

Resultados de esta implementación: [§10](#10-resultados-de-las-pruebas).

---

## 10. Resultados de las pruebas

- **Pruebas de la demo** (`tests/test_demo_seed.py`): 25 pasaron y 1 se omitió. La omitida verifica permisos POSIX del archivo privado y solo corre fuera de Windows.
- **Suite completa del backend** (`python -m pytest -q`, última ejecución): **2291 pasaron, 216 omitidas, 0 fallidas** (código de salida 0).
- **Antes de llegar a ese resultado** hubo una ejecución con 4 fallas. Dos eran propias de esta implementación y se corrigieron: la guarda de comparaciones booleanas de SQL Server (`IS 1`) y la prueba de permisos de borrado, que leía el rol de limpieza demo. Las otras dos (`test_tipos_de_token_coinciden_con_el_esquema_consolidado` y `test_cada_check_del_esquema_admite_los_mismos_valores_que_el_modelo`) pasaron en la siguiente ejecución y en aislamiento. Coincidieron con cambios concurrentes ajenos a esta tarea en `accountToken.py` y `GlucoLume_DB_v5.sql`, que no se tocaron.
- **No verificado aquí:** las consultas de `GlucoLume_demo_validacion.sql` y el script `GlucoLume_demo_permisos.sql` no se ejecutaron en SQL Server. La carga tampoco se ejecutó contra ningún servidor.


---

## 11. Inventario de cuentas (sin contraseñas)

Versión para el anexo académico. Las contraseñas están solo en el archivo privado.

Generado por `app/demo/inventory.py` para la fecha de ancla 2026-11-04. Todas las cuentas son sintéticas: los correos usan el dominio reservado `example.com`, los documentos llevan el prefijo `DEMO` y los dispositivos son `DEMO-DISP-*`. Las contraseñas están solo en el archivo privado de credenciales (fuera del repositorio).

### Usuarios individuales

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `individual-a` | Valeria Soto | `demo.individual-a@example.com` | Individual (CONSUMIDOR_FINAL) | Individual sin grupo | Sin grupo familiar | No aplica | A: perfil propio con mediciones en distintos días, estadísticas, historial y última medición. Sin vínculos institucionales. |

### Integrantes del grupo familiar

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `grupo-admin` | Tomás Herrera | `demo.grupo-admin@example.com` | Individual (CONSUMIDOR_FINAL) | Individual - administrador de grupo familiar | Grupo familiar DEMO (administrador) | Sus datos no se comparten con el grupo (todas en no) | B: administra el grupo. Sus propios datos no están compartidos: el grupo no los ve. |
| `grupo-integrante-1` | Sofía Castro | `demo.grupo-integrante-1@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 1 | Grupo familiar DEMO (integrante) | Datos básicos: sí · Última medición: no · Historial: no · Avisos: no | B - Integrante 1: solo datos básicos (edad y sexo). No comparte última medición, historial ni avisos. |
| `grupo-integrante-2` | Nicolás Vega | `demo.grupo-integrante-2@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 2 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: sí · Historial: no · Avisos: no | B - Integrante 2: solo la última medición. No comparte datos básicos ni historial. |
| `grupo-integrante-3` | Julieta Pardo | `demo.grupo-integrante-3@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 3 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: no · Historial: sí · Avisos: no | B - Integrante 3: solo el historial (incluye gráficos y estadísticas). No comparte última medición ni avisos. |
| `grupo-integrante-4` | Mateo Ríos | `demo.grupo-integrante-4@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 4 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: no · Historial: no · Avisos: sí | B - Integrante 4: solo avisos (fecha y hora de cada medición, nunca valores). |
| `grupo-integrante-5` | Carla Núñez | `demo.grupo-integrante-5@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 5 | Grupo familiar DEMO (integrante) | Datos básicos: sí · Última medición: sí · Historial: sí · Avisos: sí | B - Integrante 5: comparte datos básicos, última medición, historial y avisos. |

### Propietarios

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `propietario-a` | Gabriel Montes | `demo.propietario-a@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Propietario | Institución Demo A, Institución Demo C | No aplica | C: propietario de la Institución Demo A y de la Institución Demo C (administra más de una institución). |
| `propietario-b` | Patricia Lencina | `demo.propietario-b@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Propietario | Institución Demo B | No aplica | C: propietaria de la Institución Demo B. No ve datos de la Institución Demo A. |

### Moderadores

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `moderador-a-1` | Lorena Acosta | `demo.moderador-a-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo A | No aplica | C: gestiona operadores y ve el panel institucional de la Institución Demo A; no administra moderadores. |
| `moderador-a-2` | Diego Salinas | `demo.moderador-a-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo A | No aplica | C: segundo moderador de la Institución Demo A. |
| `moderador-b-1` | Ezequiel Funes | `demo.moderador-b-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo B | No aplica | C: gestiona operadores de la Institución Demo B. |
| `moderador-b-2` | Romina Ledesma | `demo.moderador-b-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo B | No aplica | C: segundo moderador de la Institución Demo B. |

### Operadores

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `operador-a-1` | Camila Ortiz | `demo.operador-a-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-2` | Federico Luna | `demo.operador-a-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-3` | Irene Paz | `demo.operador-a-3@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-4` | Hernán Quiroga | `demo.operador-a-4@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-b-1` | Sabrina Dávila | `demo.operador-b-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-2` | Matías Benítez | `demo.operador-b-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-3` | Noelia Sosa | `demo.operador-b-3@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-4` | Ignacio Correa | `demo.operador-b-4@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |

