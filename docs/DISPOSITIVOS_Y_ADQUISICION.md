# Dispositivos y adquisición de datos

Fuente única sobre el dispositivo de medición, el puente serie, el protocolo, la identidad del equipo, el inventario y las reglas de uso
compartido (**DEC-01**). Funciones por tipo de cuenta: [`funcional/`](funcional/). Despliegue: [DESPLIEGUE.md](DESPLIEGUE.md).

> GlucoLume es un **prototipo experimental**. La glucosa que informa el dispositivo no tiene validez diagnóstica ni reemplaza un
> glucómetro de referencia. La seguridad del software no valida clínicamente el dispositivo.

## 1. Arquitectura de la adquisición

```text
Arduino UNO + MAX30100 ──USB (115200) / Bluetooth HC-05/HC-06 (9600)──▶ puerto COM de Windows
        │ pySerial
        ▼
Puente local (acquisition/bridge) ──HTTP + X-Bridge-Token──▶ backend FastAPI (Docker) ──▶ SQL Server
                                                                   ▲
                                         React ◀── estado (SSE) ───┘   «Guardar medición» ──▶ Medicion
```

| Componente | Responsabilidad |
|---|---|
| Arduino y firmware `GlucoLume_MAX30100` | Capta la señal óptica y envía métricas ya calculadas (telemetría procesada) |
| Puente (`acquisition/bridge/`) | Único proceso que abre el COM; reenvía líneas al backend; reconexión; nunca escribe en el Arduino ni conoce usuarios |
| Backend | Valida (no recalcula) las métricas, administra dispositivos, control y sesiones, autoriza y guarda |
| React | Muestra conexión, diagnóstico y lecturas; pide órdenes y guardado al backend |
| SQL Server | Guarda solo las mediciones confirmadas |

Docker Desktop no puede pasar un COM a un contenedor Linux: por eso existe el puente en Windows. Alternativa (Linux con el Arduino en el
host): `compose.serial.yaml` pasa `/dev/ttyACM0` al backend (protocolo de muestras crudas, sección 5). Nunca hay dos lectores sobre el mismo
puerto: Windows no abre un COM dos veces, el puente tiene un candado de instancia única y el backend rechaza un segundo puente (`409 PUENTE_DUPLICADO`).

El estado en vivo (puente, control, sesión) vive en la memoria de **un** proceso del backend (`TelemetryHub`): uvicorn con un solo worker.

## 2. DEC-01 — Dispositivo compartido

**Decisión (definitiva para el prototipo):** GlucoLume tiene un único dispositivo físico experimental. Con
`ALLOW_INDIVIDUAL_ON_INSTITUTIONAL_DEVICE=true` (modo actual) ese mismo equipo lo usan cuentas individuales, integrantes de grupos
familiares y operadores activos de **cualquier** institución, sin transferir su titularidad. Con `false` (modo futuro, varios equipos) se
respeta la asignación administrativa.

**Regla independiente del modo:** compartir el hardware **no** comparte mediciones, datos personales ni el control de una sesión ajena.

### 2.1 Qué decide cada cosa

| Aspecto | Dónde se decide | Regla |
|---|---|---|
| Quién **puede** usar el equipo | `telemetry.bridgeAuthority`, `device.usableBy`, `measurement._deviceUsable` | Según el modo (tabla 2.2) |
| Titularidad administrativa | `Dispositivo.idInstitucionAsignada` / responsable | Nunca cambia por usarlo; solo por vinculación o asignación explícitas |
| Quién lo **usa ahora** | Control temporal (`hub.session`) | Una sola cuenta a la vez (2.3) |
| A qué perfil va la medición | `measurement._access` | Perfil propio (individual o integrante de grupo) o paciente a cargo del operador; nunca el de otra cuenta |
| Quién ve resultados e historiales | Permisos de cada módulo (`patientAccess`, grupos) | Sin cambios por compartir el equipo |
| Órdenes al puente | `hub.requestCommand` | Solo quien tiene el control; nunca durante una medición (salvo REANUDAR) |

### 2.2 Comportamiento por modo (verificado con pruebas)

| Situación | `true` (compartido) | `false` (restringido) |
|---|---|---|
| Equipo sin institución | Todas las cuentas habilitadas | Cuentas individuales; un paciente institucional exige vincularlo antes |
| Equipo de una institución, cuenta individual o familiar | Lo usa; mide en su propio perfil | No lo usa (`DISPOSITIVO_NO_DISPONIBLE`), órdenes `PERMISO_INSUFICIENTE` |
| Equipo de una institución, operador de esa institución | Lo usa | Lo usa (con la regla del responsable del equipo) |
| Equipo de una institución, operador de **otra** | Lo usa para sus pacientes (confirma el equipo sin vincularlo) | No lo ve ni lo usa (`DISPOSITIVO_NO_ENCONTRADO`) |
| Institución titular **pausada** | La pausa no impide a las demás cuentas usar el equipo; el personal de la institución pausada no opera | Nadie opera con sus equipos (`INSTITUCIONAL_PAUSADA`) |
| Vincular el equipo a una institución | Cambia la titularidad, no la disponibilidad | Deja de estar disponible para las cuentas individuales |
| Estado administrativo (`EN_MANTENIMIENTO`, `BAJA`…) | Siempre rige: solo un equipo `OPERATIVO` mide | Igual |

No existe la asignación de un equipo a una cuenta individual: un equipo sin institución es de uso individual común en ambos modos.

Pruebas: `backend/tests/test_device_context_authority.py` (ambos modos), `test_device_control.py` (control), y las cinco pruebas de modo
restringido de `test_bridge_command_authority`, `test_device_connection`, `test_measurements` y `test_telemetry`. El modo de cada prueba lo
fija `tests/conftest.py` (`deviceMode`), independiente del `.env` real.

### 2.3 Control temporal del dispositivo

El control reutiliza la reserva de sesión que ya existía en el hub; no es un sistema nuevo.

| Regla | Detalle |
|---|---|
| Se toma con una acción explícita | «Usar dispositivo» (`POST /api/v1/acquisition/telemetry/control`) o «Iniciar medición» (`POST …/telemetry/session`). Una orden al puente **no** toma el control (`CONTROL_REQUERIDO`) |
| Atómico | `hub.reserve` bajo un candado: si dos cuentas lo piden a la vez, lo obtiene una; la otra recibe `DISPOSITIVO_EN_USO` |
| Quién puede tomarlo | Quien puede medir y tiene autoridad según el modo (2.2); los rechazos se auditan |
| Lecturas en vivo | Valores y señal PPG (estado, SSE y eventos) solo para quien controla. Con el equipo libre no los ve nadie; el resto recibe `ocupado`, `controlPropio` y `edadUltimaLectura` (sin valores) para el diagnóstico |
| Órdenes | `CONFIGURAR`, `PAUSAR`, `REANUDAR`, `DETENER`, `REINICIAR` solo para quien controla; durante una medición solo `REANUDAR` |
| Vencimiento sin medición | 5 min desde la última acción explícita (tomarlo de nuevo o dar una orden lo renueva) o 30 s sin que su dueño consulte el estado (pantalla cerrada, conexión perdida) |
| Medición activa | No vence por los 5 min: se libera si su dueño deja de consultar 120 s (se cancela por abandono) o a los 30 min de duración máxima |
| Liberación | Al guardar o cancelar la medición, al cerrar sesión, con «Dejar de usar» (`DELETE …/telemetry/control`, rechazado con una medición en curso) o por vencimiento |
| Interferencia | Otra cuenta no guarda, cancela, ve ni ordena sobre la sesión ajena (`DISPOSITIVO_EN_USO`) |
| Trazabilidad | `TOMAR_CONTROL_DISPOSITIVO`, `SOLTAR_CONTROL_DISPOSITIVO`, `ORDEN_PUENTE_SERIE` (éxito y rechazo) en `Auditoria` |

En el frontend, «Usar dispositivo» y «Dejar de usar» están en **Conectar dispositivo → Configuración del puente**; la medición toma el
control al iniciarla. Constantes: `RESERVATION_SECONDS`, `PREVIEW_MAX_SECONDS`, `ABANDON_SECONDS`, `SESSION_MAX_SECONDS`
(`backend/app/acquisition/telemetry.py`).

### 2.4 Limitaciones conocidas

- El control vive en la memoria de un proceso: un reinicio del backend lo libera (las mediciones abiertas se cierran por abandono).
- Las pruebas usan un puente simulado y SQLite: falta la verificación con el Arduino real y con SQL Server ([PENDIENTES.md](PENDIENTES.md)).

## 3. Puente serie de Windows

**Instalación (una vez):** `BRIDGE_TOKEN` (≥ 32 caracteres) en el `.env` del proyecto y backend en marcha; luego doble clic en
`acquisition\bridge\Instalar-Puente.bat`. El asistente crea el entorno Python (pyserial con hashes), pregunta USB o Bluetooth y el puerto
(no asume ningún COM), valida el backend y el token, escribe `bridge.env` con acceso solo para el usuario y ofrece el inicio automático
(tarea programada de usuario, sin permisos de administrador; alternativa: clave `Run`). Automatizable: `bridge_ctl.py install --yes …`.

| Medio | Puerto | Velocidad |
|---|---|---|
| USB | COM del Arduino o adaptador (CH340/ATmega16U2) | 115200 |
| Bluetooth HC-05/HC-06 | COM **saliente** del módulo emparejado (PIN 1234/0000) | 9600 |

**Variables de `bridge.env`** (no se versiona; plantilla `bridge.env.example`): `SERIAL_PORT`, `SERIAL_MEDIUM`, `SERIAL_BAUDRATE`,
`BRIDGE_API_URL`, `BRIDGE_TOKEN` (igual al del backend), `BRIDGE_DEVICE_CODE` (respaldo para firmware sin ID; no prueba identidad),
`BRIDGE_LOCK_PORT`.

**Administración:** el servicio corre sin ventana (`pythonw`); `Puente-GlucoLume.bat` (menú) o `python acquisition\bridge\bridge_ctl.py status|ports|doctor|logs|start|stop|restart|setup|autostart|uninstall`;
`run_bridge.bat` con consola para depurar. Registro rotativo sin secretos y `status.json` en `%LOCALAPPDATA%\GlucoLume\bridge\`.

| Incidencia | Respuesta |
|---|---|
| COM inexistente, ocupado o equipo fuera de alcance | Diagnóstico de la causa y reintentos progresivos de 1 a 30 s |
| Puerto abierto sin datos 60 s | Cierra y reabre el enlace |
| Backend inaccesible | Cola de hasta 1000 líneas; secuencia (`seq`) para no duplicar |
| Token rechazado (403) / segundo puente (409) | El puente se detiene |
| Backend sin token (503) | Reintenta |

Seguridad: el token viaja en `X-Bridge-Token` (comparación en tiempo constante), nunca llega a React, a respuestas de la API, al registro ni a
`status.json`; el puente rechaza `http://` hacia otra máquina. El backend nunca ejecuta comandos locales: deja una orden de una lista cerrada
que el puente toma en su próximo latido.

## 4. Telemetría procesada (`GlucoLume_MAX30100`)

```text
BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.41492,SenalValida:1,Dedo:1,Muestras:58
```

| Campo | Significado |
|---|---|
| `BPM` / `SpO2` | Frecuencia cardíaca (lpm) y saturación (%); `0.00` = sin valor, nunca una lectura clínica de cero |
| `GluExp_mgdl` | Glucosa experimental o sintética (mg/dL); `NA` = sin dato |
| `Origen` | `DEMO`, `EXPERIMENTAL` o `SIN_CALIBRAR` |
| `IndiceOptico` | Índice del procesamiento óptico (Beer-Lambert) |
| `SenalValida` / `Dedo` | 1 sí / 0 no |
| `Muestras` | Muestras procesadas en el intervalo |

El backend valida y descarta `NA`, no finitos, repetidos, truncados o fuera de rango; cuenta las líneas inválidas sin cortar el servicio.
`ERROR:` informa fallos del firmware; los mensajes de estado no son mediciones.

**PPG** (firmware compatible): `PPG,<seq>,<mascara>,<v0>…<v9>`, 25 muestras/s en bloques de 10; se muestra en vivo sin interpolar cortes y
**no se guarda**. No es un ECG.

**Estados de comunicación:** `SIN_PUENTE`, `PUERTO_DESCONECTADO`, `SIN_DATOS`, `CONECTADO`. No prueban una lectura estable ni la
autorización para medir.

### 4.1 Sesión, estabilidad y guardado

1. Se abre la sesión (`POST /api/v1/acquisition/telemetry/session`) con un perfil autorizado y un dispositivo usable; toma el control y
   crea la `Medicion` en `ADQUIRIENDO`. Exige el consentimiento de datos experimentales del perfil propio.
2. Solo cuentan las lecturas posteriores al inicio.
3. «Guardar medición» (`…/session/save`) evalúa las **últimas 8 lecturas consecutivas** (separación ≤ 3 s, la última ≤ 5 s): `Dedo=1`,
   `SenalValida=1`, `Muestras ≥ 25`, BPM 20–250, SpO₂ e índice disponibles, mismo origen, variación ≤ 8 lpm, ≤ 2 puntos de SpO₂ y ≤ 15 mg/dL
   de glucosa `EXPERIMENTAL`. Guarda la **mediana** en una transacción con auditoría; si no, `409 LECTURA_NO_ESTABLE`.
4. La sesión se libera recién después del commit. Para pacientes con correo de resultados vigente se envía el resultado automáticamente
   ([PRIVACIDAD_Y_RETENCION.md](PRIVACIDAD_Y_RETENCION.md)).

`glucosaDispositivo` (del firmware) y `glucosaEstimada` (reservada a un estimador del servidor, que **no existe**) no se mezclan. Las
mediciones `DEMO` se guardan identificadas y quedan fuera de estadísticas, dashboards, avisos y última medición ordinaria.

## 5. Protocolo de muestras crudas (antecedente)

El backend conserva un segundo contrato (`POST /acquisition/connect`, muestras RED/IR, comandos `ID?`, `PING`, `START`, `STOP`) que solo
funciona con el backend en el mismo equipo que el puerto. Su sketch fue retirado del repositorio; no se combina con el firmware de
telemetría procesada. Si el puente tiene el puerto abierto, `connect` responde `PUERTO_EN_USO_PUENTE`.

## 6. Identidad del equipo e inventario

**El COM no identifica al Arduino.** El firmware v1.1.0+ genera una vez un UUID v4, lo guarda en EEPROM (dirección 100) y lo informa con
`GLUCOLUME,ID=<uuid>,SENSOR=MAX30100,FW=<versión>,SR=50` al arrancar, cada 10 s y ante el comando manual `ID` (el puente no lo envía).

| Nivel | Origen | Efecto |
|---|---|---|
| `FISICA` | ID propio del firmware | Reconocimiento automático; alta desde la conexión |
| `DECLARADA` | Solo `BRIDGE_DEVICE_CODE` | No prueba qué Arduino es: un operador debe **confirmar** el equipo antes de registrarlo, vincularlo o medir (auditado) |

El ID no es una prueba criptográfica: borrar la EEPROM crea otro dispositivo lógico. El `codigoDispositivo` es único: reconectar o cambiar de
COM no duplica. Alta automática para firmware sin ID: tras ≥ 15 s de telemetría estable y si el puente nunca vio un ID; un equipo en
mantenimiento o de baja no se reactiva.

**Flujo del operador (Conectar dispositivo en su institución):** comprobar comunicación real → identificar o confirmar → registrar si es nuevo
(queda en su institución, a cargo del propietario vigente, el operador no adquiere la titularidad; dos registros simultáneos devuelven el
mismo) → vincular un equipo sin institución (confirmación explícita, atómica, no con mediciones ajenas en curso, conserva sus mediciones) →
elegir el paciente al medir. Con el modo restringido, un equipo de otra institución no se usa ni se revela; con el compartido se confirma y
usa sin vincularlo.

**Inventario y estados administrativos:** `OPERATIVO`, `EN_MANTENIMIENTO`, `FUERA_DE_SERVICIO`, `BAJA` (terminal). Solo `OPERATIVO` mide.
Nunca se borran dispositivos ni mediciones; retirar o desvincular con mediciones en curso se rechaza. Tres estados independientes:
administrativo, de comunicación y disponibilidad para medir. Permisos de inventario por rol: [funcional/INSTITUCION.md](funcional/INSTITUCION.md)
y [funcional/PLATAFORMA.md](funcional/PLATAFORMA.md).

## 7. Firmware

Cada sketch vive en su carpeta (`firmware/GlucoLume_MAX30100/` y la variante `_optimizado`). Compilación opcional:
`docker compose --profile firmware run --rm firmware`. Compilados el 17/10/2026 para `arduino:avr:uno`: 19 432 bytes de flash (60 %) y
1 728 de RAM (84 %) el principal; 19 646 bytes (60 %) y 924 de RAM (45 %) el optimizado. No se cargaron en una placa.

## 8. Estado de verificación

| Verificado | Pendiente |
|---|---|
| Pruebas automatizadas del protocolo, reconexión, sesiones, control, permisos y persistencia (puerto y puente simulados) | Adquisición sostenida con el Arduino real por USB y Bluetooth |
| Pruebas operativas en Windows (13/10/2026): enumeración de puertos, instalación con hashes, ACL de `bridge.env`, instancia única, 409 y 403 del backend real | Reconexión con el sensor activo y guardado completo con datos reales |
| Compilación del firmware | Calidad de señal PPG y de las estimaciones sobre personas |
