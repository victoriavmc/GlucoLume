// Modelo de la página «Conectar dispositivo»: funciones puras que traducen el estado REAL que informa el backend (puente,
// puerto, telemetría, inventario) a etapas, indicadores y pasos de las guías. No consulta nada ni asume ningún puerto COM.
//
// Distinciones que la pantalla nunca mezcla:
//   emparejado / reconocido  -> Windows muestra el puerto (Bluetooth emparejado o adaptador USB reconocido)
//   puerto abierto           -> el puente abrió ese puerto
//   telemetría recibida      -> llegan lecturas recientes del firmware
//   disponible para medir    -> además está registrado, operativo y asociado al perfil (diagnóstico del backend)

import { webSerialSupported } from '../../../utils/browserSerialLink.js';

export const MEDIA = {
  BLUETOOTH: { label: 'Bluetooth', device: 'Arduino UNO + HC-05/HC-06', baud: 9600 },
  USB: { label: 'USB', device: 'Arduino UNO por cable USB', baud: 115200 },
};

/** Comando que el usuario ejecuta UNA vez en su equipo (el navegador no puede iniciar programas locales). */
export const LOCAL_COMMANDS = {
  install: 'Instalar-Puente.bat',
  menu: 'Puente-GlucoLume.bat',
  start: 'python backend\\acquisition\\bridge\\bridge_ctl.py start',
  status: 'python backend\\acquisition\\bridge\\bridge_ctl.py status',
  doctor: 'python backend\\acquisition\\bridge\\bridge_ctl.py doctor',
};

const STATE = { OK: 'OK', PENDING: 'PENDIENTE', ERROR: 'ERROR' };

/** La conexión activa la abrió un navegador (Web Serial), no un puente instalado. */
export const fromBrowser = (status) => status?.puente?.origen === 'NAVEGADOR';

export const bridgeRunning = (status) => Boolean(status) && status.estado !== 'SIN_PUENTE' && Boolean(status.puente);

export const portsOf = (status) => status?.puente?.puertosDisponibles ?? [];

export function readinessStep(readiness, id) {
  return readiness?.pasos?.find((step) => step.id === id) ?? null;
}

/** Windows muestra el puerto seleccionado: Bluetooth emparejado (puerto saliente) o adaptador USB reconocido. */
export function recognized(status, medium) {
  if (fromBrowser(status)) return status.puente.estadoEnlace === 'CONECTADO'; // el navegador eligió el puerto: no hay lista de Windows que comparar
  const configured = status?.puente?.puerto;
  if (!configured) return false;
  const port = portsOf(status).find((item) => item.puerto.toLowerCase() === configured.toLowerCase());
  if (!port) return false;
  return medium === 'BLUETOOTH' ? port.esBluetooth : port.esArduino || !port.esBluetooth;
}

/** Las cuatro etapas: reconocido → puerto abierto → telemetría → disponible. Cada una con su propio estado. */
export function pipeline(status, readiness, medium) {
  const running = bridgeRunning(status);
  const stateOf = (step) => step?.estado ?? STATE.PENDING;
  return [
    {
      id: 'RECONOCIDO',
      title: medium === 'BLUETOOTH' ? 'Bluetooth emparejado' : 'USB reconocido',
      state: !running ? STATE.PENDING : recognized(status, medium) ? STATE.OK : STATE.ERROR,
      hint: !running ? 'Se comprueba cuando el puente esté en ejecución.'
        : fromBrowser(status) ? (recognized(status, medium) ? `El navegador abrió el puerto (${status.puente.puerto}).` : 'El navegador perdió el puerto: volvé a conectar el Arduino.')
          : recognized(status, medium) ? `Windows muestra ${status.puente.puerto}.`
          : medium === 'BLUETOOTH' ? 'Windows no muestra el puerto seleccionado: Bluetooth no emparejado o puerto equivocado.'
            : 'Windows no muestra el puerto seleccionado: revisá el cable, el controlador y el puerto.',
    },
    { id: 'PUERTO', title: 'Puerto abierto', state: stateOf(readinessStep(readiness, 'PUERTO')), hint: readinessStep(readiness, 'PUERTO')?.detalle ?? '' },
    { id: 'TELEMETRIA', title: 'Telemetría recibida', state: stateOf(readinessStep(readiness, 'TELEMETRIA')), hint: readinessStep(readiness, 'TELEMETRIA')?.detalle ?? '' },
    { id: 'DISPONIBLE', title: 'Disponible para medir', state: stateOf(readinessStep(readiness, 'DISPONIBLE')), hint: readinessStep(readiness, 'DISPONIBLE')?.detalle ?? '' },
  ];
}

/** Indicadores pedidos: puente, medio, puerto, velocidad, registro, asociación, puerto abierto, telemetría, sensor, disponibilidad. */
export function indicators(status, readiness, institutional = false) {
  const running = bridgeRunning(status);
  const bridge = status?.puente;
  const step = (id) => readinessStep(readiness, id);
  const pending = 'Sin datos todavía';
  const baudMatches = bridge && MEDIA[bridge.medio]?.baud === bridge.baudios;
  const age = status?.lectura?.edadSegundos ?? status?.edadUltimaLectura;  // sin el control solo llega la antigüedad, sin valores
  return [
    { id: 'PUENTE', label: 'Servicio puente', state: running ? (bridge.estadoEnlace === 'CONECTADO' ? STATE.OK : STATE.PENDING) : STATE.ERROR,
      value: running ? (fromBrowser(status) ? 'Navegador (Web Serial)' : `Ejecutándose${bridge.versionPuente ? ` (v${bridge.versionPuente})` : ''}`) : 'Detenido' },
    { id: 'MEDIO', label: 'Medio de conexión', state: running ? STATE.OK : STATE.PENDING, value: running ? (MEDIA[bridge.medio]?.label ?? bridge.medio) : '—' },
    { id: 'PUERTO_SEL', label: 'Puerto seleccionado', state: running && bridge.puerto ? STATE.OK : STATE.PENDING, value: running ? (bridge.puerto ?? '—') : '—' },
    { id: 'VELOCIDAD', label: 'Velocidad', state: !running || !bridge.baudios ? STATE.PENDING : baudMatches ? STATE.OK : STATE.ERROR,
      value: running && bridge.baudios ? `${bridge.baudios} baudios${baudMatches ? '' : ` (el firmware usa ${MEDIA[bridge.medio]?.baud ?? '—'})`}` : '—' },
    ...(institutional ? [{ id: 'IDENTIDAD', label: 'Dispositivo identificado', state: step('IDENTIDAD')?.estado ?? STATE.PENDING,
      value: step('IDENTIDAD')?.estado === 'OK' ? 'Sí' : step('IDENTIDAD')?.estado === 'ERROR' ? 'No' : pending }] : []),
    { id: 'REGISTRADO', label: 'Dispositivo registrado', state: step('REGISTRADO')?.estado ?? STATE.PENDING, value: step('REGISTRADO')?.estado === 'OK' ? 'Sí' : step('REGISTRADO')?.estado === 'ERROR' ? 'No' : pending },
    { id: 'ASOCIADO', label: institutional ? 'Asociado a tu institución' : 'Asociado al perfil', state: step('ASOCIADO')?.estado ?? STATE.PENDING, value: step('ASOCIADO')?.estado === 'OK' ? 'Sí' : step('ASOCIADO')?.estado === 'ERROR' ? 'No' : pending },
    { id: 'PUERTO', label: 'Puerto abierto', state: step('PUERTO')?.estado ?? STATE.PENDING, value: step('PUERTO')?.estado === 'OK' ? 'Sí' : step('PUERTO')?.estado === 'ERROR' ? 'No' : 'Sin comprobar' },
    { id: 'TELEMETRIA', label: 'Última telemetría', state: step('TELEMETRIA')?.estado ?? STATE.PENDING, value: age !== undefined && age !== null ? `Hace ${Math.round(age)} s` : 'Ninguna reciente' },
    { id: 'SENSOR', label: 'Estado del sensor', state: step('SENSOR')?.estado ?? STATE.PENDING, value: step('SENSOR')?.estado === 'OK' ? 'Responde' : step('SENSOR')?.estado === 'ERROR' ? 'Con error' : 'Sin comprobar' },
    { id: 'DISPONIBLE', label: 'Disponible para medir', state: step('DISPONIBLE')?.estado ?? STATE.PENDING, value: readiness?.listo ? 'Dispositivo listo para medir' : 'No todavía' },
  ];
}

/** Qué hacer ahora: el primer paso que no está bien, con su explicación y su solución. */
export function nextAction(status, readiness, medium, browserSupported = webSerialSupported()) {
  if (readiness?.listo) return { kind: 'success', title: 'Dispositivo listo para medir', detail: 'Todo está comprobado: podés ir a «Mis mediciones».', solution: null };
  if (!bridgeRunning(status) && browserSupported) {
    return { kind: 'error', title: 'El Arduino todavía no está conectado', detail: 'Este navegador puede leerlo directamente, sin instalar nada.',
      solution: `Tocá «Conectar Arduino» y elegí el puerto. (Alternativa: iniciar el puente instalado con ${LOCAL_COMMANDS.menu}.)` };
  }
  if (!bridgeRunning(status)) {
    return { kind: 'error', title: 'El puente de GlucoLume no está ejecutándose', detail: 'El navegador no puede iniciarlo: es un programa de esta computadora.',
      solution: `Iniciá el puente con el acceso directo (${LOCAL_COMMANDS.menu}) o con «${LOCAL_COMMANDS.start}». La primera vez ejecutá ${LOCAL_COMMANDS.install}.` };
  }
  if (!recognized(status, medium) && readinessStep(readiness, 'PUERTO')?.estado === 'ERROR') {
    const missing = medium === 'BLUETOOTH' ? 'Bluetooth no emparejado' : 'Dispositivo USB no reconocido';
    return { kind: 'error', title: missing, detail: readinessStep(readiness, 'PUERTO')?.detalle,
      solution: medium === 'BLUETOOTH' ? 'Emparejá el HC-05/HC-06 en Windows (PIN 1234 o 0000) y elegí su puerto COM saliente.' : 'Conectá el cable USB de datos, instalá el controlador CH340 si hace falta y elegí el puerto.' };
  }
  const blocker = readiness?.pasos?.find((step) => step.estado !== 'OK' && step.id !== 'DISPONIBLE');
  if (blocker?.estado === 'ERROR') {
    // Un problema comprobado se titula con lo que pasa («Puerto COM4 ocupado por otra aplicación»), no con el nombre del paso.
    const [headline, ...rest] = blocker.detalle.split(/:\s+/);
    return { kind: 'error', title: headline.replace(/\.$/, ''), detail: rest.join(': ') || null, solution: blocker.solucion };
  }
  if (blocker) return { kind: 'info', title: blocker.titulo, detail: blocker.detalle, solution: blocker.solucion };
  const last = readinessStep(readiness, 'DISPONIBLE');
  return { kind: 'info', title: last?.titulo ?? 'Comprobando', detail: last?.detalle ?? 'Comprobando el estado del dispositivo…', solution: last?.solucion ?? null };
}

/** Pasos de «Cómo realizar una medición» (los tiempos salen del firmware, 1 lectura por segundo, y del criterio del backend). */
export const STABLE_READINGS = 8;
export const MEASUREMENT_STEPS = [
  { titulo: 'Seleccioná el perfil autorizado', detalle: 'En «Mis mediciones» se usa tu perfil. Para pacientes de una institución, el perfil del paciente a tu cargo.' },
  { titulo: 'Seleccioná el dispositivo registrado', detalle: 'Es el que atiende el puente; solo se ofrece si está registrado, operativo y asociado al perfil.' },
  { titulo: 'Verificá que esté conectado y transmitiendo', detalle: 'El indicador «Disponible para medir» de esta página tiene que estar en verde.' },
  { titulo: 'Colocá el dedo sobre el sensor MAX30100', detalle: 'Dedo índice sobre el sensor, cubriéndolo por completo, sin presionar de más.' },
  { titulo: 'Mantenelo quieto durante la adquisición', detalle: `Hacen falta ${STABLE_READINGS} lecturas válidas consecutivas y parecidas entre sí. El firmware envía una por segundo: como mínimo ${STABLE_READINGS} segundos con el dedo quieto; si el dedo se mueve o la señal se pierde, el conteo vuelve a empezar.` },
  { titulo: 'Esperá a obtener una señal óptica válida', detalle: 'Mientras «Señal válida» diga No, seguí quieto: el sistema no guarda lecturas inválidas ni desactualizadas.' },
  { titulo: 'Mirá BPM, SpO₂, índice óptico y glucosa experimental', detalle: 'Son los valores que calcula el firmware (BPM, SpO2, IndiceOptico, GluExp_mgdl).' },
  { titulo: 'Identificá el origen del dato', detalle: 'DEMO es un valor sintético de prueba, no una medición. EXPERIMENTAL y SIN_CALIBRAR se distinguen siempre.' },
  { titulo: 'Confirmá manualmente el guardado', detalle: 'Nada se guarda solo: tocá «Guardar medición» cuando la lectura sea estable.' },
  { titulo: 'Consultá la medición en el historial', detalle: 'La medición guardada aparece en «Mis mediciones» → Historial. Las DEMO quedan separadas.' },
];

export const FINGER_TIPS = [
  'Apoyá la yema del dedo índice sobre el sensor, cubriéndolo por completo.',
  'No presiones fuerte: apretar corta la circulación y la señal se vuelve inválida.',
  'Mantené la mano apoyada y sin moverte hasta que el dedo figure como detectado.',
  'Evitá luz solar directa o lámparas intensas sobre el sensor.',
];

/** Avisos del bloque «Importante» de la guía de medición. */
export const IMPORTANT_NOTES = [
  'Los valores son de prueba (DEMO/EXPERIMENTAL).',
  'La estimación de glucosa no está calibrada.',
  'Usá siempre el mismo dedo y evitá movimientos.',
  'No es un glucómetro ni reemplaza un diagnóstico médico.',
];
