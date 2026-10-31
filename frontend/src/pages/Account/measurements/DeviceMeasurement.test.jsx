// Medición con el dispositivo (Arduino + MAX30100 -> Bluetooth -> puente -> FastAPI -> React).
//
// NO hay Arduino: el stream SSE se reemplaza por uno controlado por la prueba, que inyecta los `estado` que enviaría el
// backend (el mismo contenido que GET /acquisition/telemetry/status). La pantalla no genera lecturas: se prueba que
// muestra lo que informa el backend, que no convierte NA en cero y que solo manda al backend lo que la persona decide.

import { act, configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

const stream = vi.hoisted(() => ({ emit: null, closed: false }));
vi.mock('../../../api/acquisitionApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  openStream: vi.fn(() => () => {}),
  openTelemetryStream: vi.fn(({ onEvent }) => {
    stream.emit = onEvent;
    stream.closed = false;
    return () => { stream.closed = true; };
  }),
}));

configure({ asyncUtilTimeout: 5000 });

const PROFILE_ID = 'p-own';
const MEASUREMENT_ID = 'm-1';
const DEVICE = {
  idDispositivo: 'd-1', codigoDispositivo: 'ARD-001', nombre: 'Arduino MAX30100', modelo: 'HC-06', modeloSensor: 'MAX30100',
  versionFirmware: '1.0.0',
};
const OWN_PROFILE = {
  perfilDisponible: true, datosFaltantes: [], idPerfilMedicion: PROFILE_ID, nombre: 'Victoria', apellido: 'Cortés',
  fechaNacimiento: '1990-05-17', edad: 36, sexoModelo: 'FEMENINO', fechaCreacion: '2026-10-01T10:00:00', fechaUltimaMedicion: null,
};
const EMPTY = { items: [], total: 0, pagina: 1, tamanioPagina: 10 };
const metric = (cantidad = 0) => ({ cantidad, promedio: null, minimo: null, maximo: null });
const DASHBOARD_EMPTY = {
  perfilDisponible: true, datosFaltantes: [], periodo: { dias: 30, desde: null, hasta: null },
  resumen: { total: 0, completadas: 0, enPeriodo: 0, ultimaMedicion: null, ultimaGlucosa: null, ultimaSpo2: null, ultimaFrecuencia: null },
  estadisticas: { dias: 30, cantidadMediciones: 0, glucosa: metric(), spo2: metric(), frecuenciaCardiaca: metric(), serieDiaria: [] },
  recientes: [],
};
const LINK_DOWN = {
  conectado: false, ocupado: false, puerto: null, medio: null, baudios: null, estadoDispositivo: null, ultimoError: null,
  lineasInvalidas: 0, dispositivo: null, adquisicion: null,
};
const BRIDGE = {
  puerto: 'COM4', medio: 'BLUETOOTH', baudios: 9600, codigoDispositivo: 'ARD-001', estadoEnlace: 'CONECTADO', reintento: 0, ultimoError: null,
};
const READING = {
  bpm: 76.43, spo2: 99.65, glucosa: 117, unidadGlucosa: 'mg/dL', origen: 'DEMO', esDemo: true, indiceOptico: 2.41492,
  senalValida: true, dedo: true, muestras: 58, instante: '2026-10-08T09:00:00Z', edadSegundos: 0.4,
};
const status = (overrides = {}) => ({
  estado: 'CONECTADO', ocupado: false, puente: BRIDGE, lectura: READING, avisoDispositivo: null, lineasInvalidas: 0,
  lecturasRecibidas: 30, sesion: null, ...overrides,
});
const SIN_PUENTE = status({ estado: 'SIN_PUENTE', puente: null, lectura: null });
const step = (id, titulo, estado, detalle, solucion = null) => ({ id, titulo, estado, detalle, solucion });
const READY = {
  listo: true, bloqueo: null, dispositivo: null, identificacion: null,
  pasos: [step('PUENTE', 'Servicio puente', 'OK', 'El puente está ejecutándose.'), step('PUERTO', 'Puerto abierto', 'OK', 'Puerto COM4 abierto a 9600 baudios (bluetooth).'),
    step('TELEMETRIA', 'Telemetría reciente', 'OK', 'Última lectura hace 0 s.'), step('REGISTRADO', 'Dispositivo registrado', 'OK', '«ARD-001» figura en el inventario (MAX30100).'),
    step('SENSOR', 'Sensor', 'OK', 'El sensor responde.'), step('ASOCIADO', 'Dispositivo asociado al perfil', 'OK', 'El perfil puede usar este dispositivo.'),
    step('DISPONIBLE', 'Disponible para medir', 'OK', 'Dispositivo listo para medir.')],
};
const readyWith = (changes, ready = false) => ({
  ...READY, listo: ready,
  pasos: READY.pasos.map((item) => (changes[item.id] ? { ...item, ...changes[item.id] } : item))
    .map((item) => (item.id === 'DISPONIBLE' && !ready ? { ...item, estado: 'PENDIENTE', detalle: 'Todavía no: resolvé el primer paso pendiente.' } : item)),
});

function detail(overrides = {}) {
  return {
    idMedicion: MEASUREMENT_ID, idPerfilMedicion: PROFILE_ID, modoMedicion: 'OXIMETRIA', estadoMedicion: 'ADQUIRIENDO',
    fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: null, fechaHoraUltimaComida: null, condicionComida: 'NO_INFORMADA',
    minutosDesdeUltimaComida: null, duracionMs: null, edadAlMomento: 36, sexoModelo: 'FEMENINO', versionFirmwareAlMomento: '1.0.0',
    modeloSensorAlMomento: 'MAX30100', versionAlgoritmo: null, calidadSenal: null, spo2: null, frecuenciaCardiaca: null,
    glucosaEstimada: null, observacion: null, origenGlucosa: null, glucosaDispositivo: null, unidadGlucosa: null,
    indiceOptico: null, lecturasEstabilizadas: null, esDemo: false, puedeEliminar: false, dispositivo: DEVICE, matriz: null,
    cantidadMuestras: 0, referenciaCapilar: null, puedeOperar: true,
    aviso: 'Resultado experimental de GlucoLume: no es un diagnóstico ni reemplaza una medición clínica certificada.',
    ...overrides,
  };
}
const SAVED_DEMO = detail({
  estadoMedicion: 'COMPLETADA', fechaHoraFin: '2026-10-08T09:00:12', duracionMs: 12000, spo2: '99.65', frecuenciaCardiaca: 76,
  versionAlgoritmo: 'firmware-glucolume-max30100-v1', origenGlucosa: 'DEMO', glucosaDispositivo: '114.00', unidadGlucosa: 'mg/dL',
  indiceOptico: '2.41492', lecturasEstabilizadas: 8, esDemo: true, puedeEliminar: true, puedeOperar: false,
});

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  stream.emit = null;
});

function routes(telemetry, extra = {}) {
  let current = telemetry;
  const api = mockApi({
    'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/dashboard': jsonResponse(200, DASHBOARD_EMPTY),
    'GET /measurements/evolution': jsonResponse(200, { origen: 'TODOS', desde: null, hasta: null, puntos: [], truncado: false, estadisticas: { experimental: null, demo: null } }),
    'GET /acquisition/status': jsonResponse(200, LINK_DOWN), 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
    'GET /measurements/devices': jsonResponse(200, [DEVICE]), 'GET /measurements': jsonResponse(200, EMPTY),
    'GET /measurements/statistics': jsonResponse(200, { dias: 30, cantidadMediciones: 0 }),
    'GET /acquisition/telemetry/status': () => jsonResponse(200, current), 'GET /acquisition/telemetry/readiness': jsonResponse(200, READY), ...extra,
  });
  return { ...api, set: (next) => { current = next; } };
}

const pushStatus = (next) => act(() => stream.emit({ tipo: 'estado', ...next }));
const card = async () => (await screen.findByRole('heading', { name: 'Nueva medición', level: 2 })).closest('section');

describe('Nueva medición con el dispositivo: pantalla inicial y estado de la conexión', () => {
  it('sin puente serie lo dice, no permite iniciar y no muestra ninguna lectura', async () => {
    routes(SIN_PUENTE, { 'GET /acquisition/telemetry/readiness': jsonResponse(200, readyWith({
      PUERTO: { estado: 'PENDIENTE', detalle: 'Sin puerto abierto no hay telemetría.' } })) });
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const checks = await within(section).findByLabelText('Estado del dispositivo');
    expect(checks).toHaveTextContent('Puente detenido');
    expect(await within(section).findByText(/El puente de GlucoLume no está ejecutándose/)).toBeInTheDocument();
    // Desconectado: se informa el estado, se puede ir a conectarlo desde acá y no se puede iniciar.
    expect(await within(section).findByRole('button', { name: 'Iniciar medición' })).toBeDisabled();
    expect(within(section).getByRole('link', { name: /Conectar dispositivo/ })).toHaveAttribute('href', '/app/conectar-dispositivo');
    expect(within(section).queryByText('Dispositivo compartido disponible')).not.toBeInTheDocument();
  });

  it('con el puerto caído no da la conexión por buena: «sin abrir», sin lecturas y sin iniciar', async () => {
    routes(status({
      estado: 'PUERTO_DESCONECTADO', lectura: null,
      puente: { ...BRIDGE, estadoEnlace: 'REINTENTANDO', reintento: 3, ultimoError: 'No se pudo abrir el puerto: ¿Bluetooth apagado?' },
    }), { 'GET /acquisition/telemetry/readiness': jsonResponse(200, readyWith({
      PUERTO: { estado: 'ERROR', detalle: 'Puerto COM4 no disponible: ¿Bluetooth apagado?', solucion: 'Encendé el Bluetooth del equipo.' } })) });
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const checks = await within(section).findByLabelText('Estado del dispositivo');
    await waitFor(() => expect(checks).toHaveTextContent('COM4 sin abrir'));
    expect(within(section).queryByText('Dispositivo compartido disponible')).not.toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Iniciar medición' })).toBeDisabled();
    expect(within(section).queryByText('Frecuencia cardíaca')).not.toBeInTheDocument();
  });

  it('antes de iniciar no hay monitor: ni tarjetas, ni gráfico, ni latidos, ni temporizador, ni lecturas previas', async () => {
    routes(status());
    renderAt('/app/mediciones/nueva');
    const section = await card();
    await within(section).findByRole('button', { name: 'Iniciar medición' });
    expect(within(section).queryByText(/Medición en tiempo real/)).not.toBeInTheDocument();
    expect(within(section).queryByLabelText('Vista previa del sensor')).not.toBeInTheDocument();
    for (const name of ['Frecuencia cardíaca', 'SpO₂', 'Glucosa', 'Índice óptico']) {
      expect(within(section).queryByRole('article', { name })).not.toBeInTheDocument();
    }
    expect(within(section).queryByText(/latidos detectados/)).not.toBeInTheDocument();
    expect(within(section).queryByText(/Tiempo de medición/)).not.toBeInTheDocument();
    expect(within(section).queryByRole('img', { name: /Señal de pulso/ })).not.toBeInTheDocument();
    expect(section).not.toHaveTextContent(/76,4|99,7|117 mg\/dL/); // la lectura previa (DEMO) del dispositivo libre no se muestra
    expect(screen.getAllByRole('button', { name: 'Iniciar medición' })).toHaveLength(1);
  });

  it('conectado, identificado y libre: las cuatro comprobaciones en verde y «dispositivo compartido disponible»', async () => {
    routes(status());
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const checks = await within(section).findByLabelText('Estado del dispositivo');
    await waitFor(() => expect(checks).toHaveTextContent('Listo para medir'));
    expect(checks).toHaveTextContent('Bluetooth · COM4 abierto');
    expect(checks).toHaveTextContent('ARD-001 identificado');
    expect(checks).toHaveTextContent('Responde');
    expect(await within(section).findByText('Dispositivo compartido disponible')).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Iniciar medición' })).toBeEnabled();
    expect(within(section).queryByText(/temporalmente ocupado/)).not.toBeInTheDocument();
  });

  it('puerto abierto pero Arduino sin identificar: no hay verde ni «disponible», se explica y no se puede iniciar', async () => {
    routes(status(), { 'GET /acquisition/telemetry/readiness': jsonResponse(200, readyWith({
      REGISTRADO: { estado: 'PENDIENTE', titulo: 'Dispositivo identificado', detalle: 'No se pudo confirmar qué Arduino es: este firmware no informa un identificador propio.',
        solucion: 'Confirmá explícitamente cuál es en «Dispositivo de esta conexión».' } })) });
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const checks = await within(section).findByLabelText('Estado del dispositivo');
    await waitFor(() => expect(checks).toHaveTextContent('Sin confirmar'));
    expect(checks).toHaveTextContent('Bluetooth · COM4 abierto'); // la conexión del puerto sí está bien: son comprobaciones distintas
    expect(checks).toHaveTextContent('Todavía no');
    expect(within(section).queryByText('Dispositivo compartido disponible')).not.toBeInTheDocument();
    expect(within(section).getByText(/Pendiente: Dispositivo identificado/)).toBeInTheDocument();
    expect(within(section).getByText(/No se pudo confirmar qué Arduino es/)).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Iniciar medición' })).toBeDisabled();
  });

  it('si el backend rechaza el inicio por identidad sin confirmar, el motivo se muestra y el estado se vuelve a consultar', async () => {
    const api = routes(status(), {
      'POST /acquisition/telemetry/session': jsonResponse(409, { codigo: 'IDENTIDAD_NO_CONFIRMADA', detail: 'No se pudo confirmar qué Arduino está conectado: confirmá el dispositivo en «Conectar dispositivo».' }),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    await user.click(await within(section).findByRole('button', { name: 'Iniciar medición' }));
    expect(await within(section).findByText(/No se pudo confirmar qué Arduino está conectado/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Sesión de medición con el dispositivo' })).not.toBeInTheDocument();
    expect(api.calls.filter((call) => call.key === 'GET /acquisition/telemetry/readiness').length).toBeGreaterThanOrEqual(2);
  });

  it('si otra cuenta está midiendo, no muestra lecturas ni deja iniciar', async () => {
    routes(status({ ocupado: true, lectura: null, puente: { ...BRIDGE, puerto: null } }));
    renderAt('/app/mediciones/nueva');
    const section = await card();
    expect(await within(section).findByText(/Dispositivo temporalmente ocupado/)).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: /Reintentar/ })).toBeInTheDocument();
    expect(within(section).queryByText('Dispositivo compartido disponible')).not.toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: 'Iniciar medición' })).not.toBeInTheDocument();
    expect(within(section).queryByLabelText('Vista previa del sensor')).not.toBeInTheDocument();
  });
});

describe('Nueva medición con el dispositivo: sesión y guardado', () => {
  const session = (lecturasValidas, estable, mensaje = null) => ({
    idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false,
    estabilidad: { estable, motivo: estable ? null : 'LECTURAS_INSUFICIENTES', mensaje, lecturasValidas, lecturasRequeridas: 8 },
  });

  it('inicia la sesión solo con perfil, dispositivo y contexto; guarda al confirmar y muestra el resultado DEMO', async () => {
    const api = routes(status(), {
      'POST /acquisition/telemetry/session': () => jsonResponse(201, detail()),
      'POST /acquisition/telemetry/session/save': jsonResponse(200, SAVED_DEMO),
      [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, SAVED_DEMO),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    await user.selectOptions(await within(section).findByLabelText('Alimentación'), 'AYUNO');
    await user.click(within(section).getByRole('button', { name: 'Iniciar medición' }));

    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    // El cliente no envía ninguna lectura, valor, modo ni estado: solo qué perfil, qué dispositivo y el contexto.
    expect(api.calls.find((call) => call.key === 'POST /acquisition/telemetry/session').body).toEqual({
      idPerfilMedicion: PROFILE_ID, idDispositivo: 'd-1', condicionComida: 'AYUNO', modoMedicion: 'OXIMETRIA',
    });

    api.set(status({ sesion: session(3, false, 'Todavía no hay suficientes lecturas válidas seguidas: mantené el dedo quieto.') }));
    await pushStatus(status({ sesion: session(3, false, 'Todavía no hay suficientes lecturas válidas seguidas: mantené el dedo quieto.') }));
    const live = await within(section).findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(live).getByText(/de 8/)).toBeInTheDocument();
    expect(within(live).getByRole('progressbar')).toHaveAttribute('value', '3');
    expect(within(live).getByText(/Todavía no hay suficientes lecturas/)).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Guardar medición' })).toBeDisabled(); // no hay lectura estable

    await pushStatus(status({ sesion: session(8, true) }));
    expect(within(live).getByText('Lectura estable. Podés guardar la medición.')).toBeInTheDocument();
    await user.click(within(live).getByRole('button', { name: 'Guardar medición' }));

    // Confirmado el guardado se ofrece ver la medición o volver al dashboard; desde ahí se ve la medición guardada con su origen DEMO y sus unidades.
    expect(await screen.findByRole('heading', { name: 'Medición guardada' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Ver medición' }));
    expect(await screen.findByRole('heading', { name: /Oximetría · 08\/10\/2026 09:00/ })).toBeInTheDocument();
    expect(api.calls.filter((call) => call.key === 'POST /acquisition/telemetry/session/save')).toHaveLength(1);
    const results = await screen.findByLabelText('Resultados');
    expect(results).toHaveTextContent('99,7 %');
    expect(results).toHaveTextContent('76 lpm');
    expect(results).toHaveTextContent('114 mg/dL');
    expect(results).toHaveTextContent('DEMO');
    expect(results).toHaveTextContent('2,4149');
    expect(results).toHaveTextContent('8 (se guarda la mediana)');
    expect(screen.getByText(/Datos de prueba \(DEMO\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Enviar resultado por correo/)).not.toBeInTheDocument(); // un resultado DEMO no se envía
  });

  it('sin fecha de nacimiento ni sexo se puede iniciar sin completar nada: no se envía ningún dato inventado', async () => {
    const api = routes(status(), {
      'GET /measurements/profile': jsonResponse(200, { ...OWN_PROFILE, fechaNacimiento: null, edad: null, sexoModelo: null, datosRecomendados: ['fechaNacimiento', 'sexo'] }),
      'POST /acquisition/telemetry/session': () => jsonResponse(201, detail({ edadAlMomento: null, sexoModelo: null })),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    expect(document.getElementById('datos-recomendados')).toHaveTextContent(/Podés realizar mediciones sin completar tu edad o sexo/);
    const age = await within(section).findByLabelText('Edad en años (opcional)');
    expect(age).toHaveValue(null);
    expect(age).not.toBeRequired();
    const sex = within(section).getByLabelText('Sexo (opcional)');
    expect(sex).toHaveValue('');
    expect(within(sex).getByRole('option', { name: 'Prefiero no informar' })).toBeInTheDocument();
    await user.click(within(section).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    expect(api.calls.find((call) => call.key === 'POST /acquisition/telemetry/session').body).toEqual({
      idPerfilMedicion: PROFILE_ID, idDispositivo: 'd-1', condicionComida: 'NO_INFORMADA', modoMedicion: 'OXIMETRIA',
    });
  });

  it('precarga edad y sexo del perfil; lo que se cambia vale solo para esta medición y no modifica el perfil', async () => {
    const api = routes(status(), { 'POST /acquisition/telemetry/session': () => jsonResponse(201, detail({ edadAlMomento: 25 })) });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const age = await within(section).findByLabelText('Edad en años (opcional)');
    expect(age).toHaveValue(36); // calculada desde la fecha de nacimiento
    expect(within(section).getByLabelText('Sexo (opcional)')).toHaveValue('FEMENINO'); // del perfil, sin volver a cargarlo
    await user.clear(age);
    await user.type(age, '25');
    await user.selectOptions(within(section).getByLabelText('Sexo (opcional)'), 'MASCULINO');
    await user.selectOptions(within(section).getByLabelText('Alimentación'), 'POSTPRANDIAL');
    expect(within(section).queryByLabelText(/última comida/i)).not.toBeInTheDocument(); // la hora de la última comida ya no se pide
    await user.type(within(section).getByLabelText('Observaciones (opcional)'), 'Después del desayuno');
    await user.click(within(section).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    expect(api.calls.find((call) => call.key === 'POST /acquisition/telemetry/session').body).toEqual({
      idPerfilMedicion: PROFILE_ID, idDispositivo: 'd-1', condicionComida: 'POSTPRANDIAL', modoMedicion: 'OXIMETRIA',
      observacion: 'Después del desayuno', edadAlMomento: 25, sexoModelo: 'MASCULINO',
    });
    expect(api.calls.some((call) => call.key === 'PATCH /auth/me/profile')).toBe(false);
  });

  it('el modo elegido se envía al iniciar; la oximetría es el valor por defecto', async () => {
    const api = routes(status(), { 'POST /acquisition/telemetry/session': () => jsonResponse(201, detail({ modoMedicion: 'GLUCOSA_EXPERIMENTAL' })) });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    const mode = await within(section).findByLabelText('Modo de medición');
    expect(mode).toHaveValue('OXIMETRIA');
    await user.selectOptions(mode, 'GLUCOSA_EXPERIMENTAL');
    expect(within(section).getByText(/no se cambia a Oximetría en silencio/)).toBeInTheDocument();
    await user.click(within(section).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    expect(api.calls.find((call) => call.key === 'POST /acquisition/telemetry/session').body.modoMedicion).toBe('GLUCOSA_EXPERIMENTAL');
  });

  it('usuario individual: Glucosa experimental con «Después de comer» y «Última comida» vacía inicia igual y no envía fecha; informada se envía', async () => {
    const api = routes(status(), { 'POST /acquisition/telemetry/session': () => jsonResponse(201, detail({ modoMedicion: 'GLUCOSA_EXPERIMENTAL' })) });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    await user.selectOptions(await within(section).findByLabelText('Modo de medición'), 'GLUCOSA_EXPERIMENTAL');
    expect(within(section).getByLabelText('Inicio de la última comida (opcional)')).toBeInTheDocument();
    await user.selectOptions(within(section).getByLabelText('Alimentación'), 'POSTPRANDIAL');
    await user.click(within(section).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    expect(screen.queryByText(/Indicá cuándo fue la última comida/)).not.toBeInTheDocument();
    const body = api.calls.find((call) => call.key === 'POST /acquisition/telemetry/session').body;
    expect(body).toMatchObject({ modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'POSTPRANDIAL' });
    expect(body.fechaHoraUltimaComida).toBeUndefined();
  });

  it('una medición de glucosa sin valor de glucosa explica por qué no se puede guardar y no cambia de modo', async () => {
    const message = 'Estimación de glucosa no disponible: el dispositivo no informa un valor de glucosa (sin calibrar).';
    routes(status({
      lectura: { ...READING, origen: 'SIN_CALIBRAR', esDemo: false, glucosa: null, unidadGlucosa: null },
      sesion: { idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false, modo: 'GLUCOSA_EXPERIMENTAL',
        estabilidad: { estable: false, motivo: 'GLUCOSA_NO_DISPONIBLE', mensaje: message, lecturasValidas: 8, lecturasRequeridas: 8 } },
    }));
    renderAt('/app/mediciones/nueva');
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(monitor).getByLabelText('Datos de la medición en curso')).toHaveTextContent('Glucosa experimental');
    expect(within(monitor).getByText(/Estimación de glucosa no disponible/)).toBeInTheDocument();
    expect(within(monitor).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();
    expect(within(monitor).getByRole('button', { name: /Cancelar sesión/ })).toBeEnabled();
  });

  it('no inicia la adquisición sin una acción explícita', async () => {
    const api = routes(status());
    renderAt('/app/mediciones/nueva');
    await within(await card()).findByRole('button', { name: 'Iniciar medición' });
    expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(false);
  });

  it('estado B: el monitor reemplaza al formulario y grafica la telemetría real de la sesión (sin ondas ficticias)', async () => {
    const live = (n, extra = {}) => ({
      ...READING, instante: `2026-10-08T09:00:${String(n).padStart(2, '0')}Z`, bpm: 70 + n, spo2: 97 + (n % 3) * 0.5, glucosa: 110 + n,
      esDemo: true, origen: 'DEMO', ...extra,
    });
    const inSession = (n, reading, valid = n) => status({
      lectura: reading, sesion: { idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:01Z', enlacePerdido: false,
        estabilidad: { estable: false, motivo: 'LECTURAS_INSUFICIENTES', mensaje: 'Mantené el dedo quieto.', lecturasValidas: valid, lecturasRequeridas: 8 } },
    });
    const api = routes(status(), { 'POST /acquisition/telemetry/session': () => jsonResponse(201, detail()) });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const section = await card();
    await user.click(await within(section).findByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session')).toBe(true));
    // Una lectura ANTERIOR al inicio de la sesión no se atribuye a ella.
    api.set(inSession(0, live(0), 0));
    await pushStatus(inSession(0, live(0), 0));
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(monitor).getByRole('heading', { name: /Medición en tiempo real/ })).toBeInTheDocument();
    expect(screen.queryByLabelText('Edad en años (opcional)')).not.toBeInTheDocument(); // ya no es un formulario
    expect(within(monitor).getByLabelText('Datos de la medición en curso')).toHaveTextContent('Mi perfil');
    expect(within(monitor).getByLabelText('Datos de la medición en curso')).toHaveTextContent('ARD-001 · Bluetooth · COM4');
    expect(within(monitor).getAllByText('Sin señal').length).toBeGreaterThanOrEqual(2); // todavía no hay lecturas de ESTA sesión
    // Llegan lecturas reales de la sesión (una por segundo): cada tarjeta suma su propio punto.
    for (const n of [1, 2, 3, 4]) await pushStatus(inSession(n, live(n), n));
    await pushStatus(inSession(4, live(4), 4)); // el mismo evento repetido (SSE cada 2 s) no duplica el punto
    const bpm = within(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' }));
    expect(bpm.getByText('74', { selector: 'b' })).toBeInTheDocument();
    expect(bpm.getByRole('img', { name: /Frecuencia cardíaca: 4 lecturas válidas, última 74 lpm/ })).toBeInTheDocument();
    expect(bpm.getByText(/no se detectan pulsaciones, no se informa frecuencia/)).toBeInTheDocument();
    expect(within(monitor).getByText(/no es un electrocardiograma/)).toBeInTheDocument();
    const glucose = within(within(monitor).getByRole('article', { name: 'Glucosa' }));
    expect(glucose.getByText('DEMO')).toBeInTheDocument();
    expect(glucose.getByText(/representa una simulación y no una glucemia real/)).toBeInTheDocument();
    expect(within(monitor).getByRole('article', { name: 'SpO₂' })).toBeInTheDocument();
    expect(within(monitor).getByRole('article', { name: 'Índice óptico' })).toHaveTextContent('Indicador óptico asociado al procesamiento del sensor');
    expect(within(monitor).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();
    // Una lectura inválida corta la línea y no se muestra como valor ni como cero.
    await pushStatus(inSession(5, live(5, { dedo: false, senalValida: false, bpm: null, spo2: null, glucosa: null, indiceOptico: null }), 0));
    expect(within(monitor).getByLabelText('Indicadores de la adquisición')).toHaveTextContent('no colocado');
    expect(within(within(monitor).getByRole('article', { name: 'SpO₂' })).queryByText('0')).not.toBeInTheDocument();
  });

  it('al iniciar, el monitor arranca vacío: una lectura anterior a la sesión no se muestra y las nuevas lo van llenando', async () => {
    const stale = { ...READING, instante: '2026-10-08T09:00:00Z' }; // recibida ANTES de iniciar la sesión
    const fresh = { ...READING, instante: '2026-10-08T09:00:07Z', bpm: 71, spo2: 98, glucosa: 109 };
    const open = (reading) => status({ lectura: reading, sesion: { idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:05Z', enlacePerdido: false, modo: 'OXIMETRIA',
      estabilidad: { estable: false, motivo: 'LECTURAS_INSUFICIENTES', mensaje: null, lecturasValidas: 0, lecturasRequeridas: 8 } } });
    routes(open(stale));
    renderAt('/app/mediciones/nueva');
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(monitor).getByText('Iniciando adquisición')).toBeInTheDocument();
    expect(within(monitor).getByLabelText('Indicadores de la adquisición')).toHaveTextContent('Dedo: sin dato');
    expect(within(monitor).getByLabelText('Indicador de latidos detectados')).toHaveTextContent('0 latidos detectados');
    expect(within(monitor).getByLabelText('Tiempo y muestras de la medición')).toHaveTextContent('—'); // sin muestras reales todavía
    expect(within(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' })).queryByText('76', { selector: 'b' })).not.toBeInTheDocument();
    expect(within(monitor).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();
    await pushStatus(open(fresh));
    expect(within(monitor).getByLabelText('Indicadores de la adquisición')).toHaveTextContent('Dedo: colocado');
    expect(within(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' })).getByText('71', { selector: 'b' })).toBeInTheDocument();
    expect(within(monitor).queryByText('Iniciando adquisición')).not.toBeInTheDocument();
  });

  it('secuencia de la adquisición: esperando dedo → detectando pulsaciones → analizando → señal estable, y vuelve al perder el dedo', async () => {
    const wave = Array.from({ length: 60 }, (_, i) => Math.round(80 * Math.sin(i / 3)));
    const ppg = { hz: 25, inicio: 0, valores: wave, latidos: [10, 31, 52], edadSegundos: 0.3 };
    const session = (lecturasValidas, estable, extra = {}) => ({
      idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false, ppg,
      estabilidad: { estable, motivo: estable ? null : 'LECTURAS_INSUFICIENTES', mensaje: 'Mantené el dedo quieto.', lecturasValidas, lecturasRequeridas: 8 },
      ...extra,
    });
    const reading = (n, extra = {}) => ({ ...READING, instante: `2026-10-08T09:00:${String(10 + n).padStart(2, '0')}Z`, esDemo: true, origen: 'DEMO', ...extra });
    const noFinger = status({ lectura: reading(0, { dedo: false, senalValida: false, bpm: null, spo2: null, glucosa: null, indiceOptico: null }),
      sesion: { ...session(0, false), ppg: null } });
    routes(noFinger);
    renderAt('/app/mediciones/nueva');
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    // Etapa 1: sin dedo no hay valores fisiológicos ni onda.
    expect(within(monitor).getByText('Esperando dedo')).toBeInTheDocument();
    expect(within(monitor).getByText(/Colocá el dedo sobre el sensor/)).toBeInTheDocument();
    expect(within(monitor).getByText('Esperando señal')).toBeInTheDocument(); // gráfico PPG
    expect(within(monitor).getAllByText('Sin señal').length).toBeGreaterThanOrEqual(2);
    // Etapa 2: dedo + señal óptica, todavía sin frecuencia válida.
    await pushStatus(status({ lectura: reading(1, { bpm: null, spo2: null, senalValida: false }), sesion: session(0, false) }));
    expect(within(monitor).getByText('Señal insuficiente')).toBeInTheDocument(); // dedo colocado, señal todavía no válida
    const svg = within(monitor).getByRole('img', { name: /Señal de pulso \(PPG\) en tiempo real/ });
    expect(Number(svg.getAttribute('data-muestras'))).toBeGreaterThan(10); // onda real dibujada
    expect(Number(svg.getAttribute('data-latidos'))).toBeGreaterThanOrEqual(1); // latidos detectados marcados
    expect(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' })).not.toHaveTextContent('76'); // no se inventa una frecuencia
    // Etapa 3: ya hay valores válidos.
    await pushStatus(status({ lectura: reading(2), sesion: session(3, false) }));
    expect(within(monitor).getByText('Analizando señal')).toBeInTheDocument();
    expect(within(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' })).getByText('76', { selector: 'b' })).toBeInTheDocument();
    expect(within(within(monitor).getByRole('article', { name: 'Glucosa' })).getByText('DEMO')).toBeInTheDocument();
    // Etapa 4: 8 lecturas válidas seguidas.
    await pushStatus(status({ lectura: reading(3), sesion: session(8, true) }));
    expect(within(monitor).getByText('Señal estable')).toBeInTheDocument();
    expect(within(monitor).getByRole('button', { name: 'Guardar medición' })).toBeEnabled();
    // Se pierde el dedo: el estado cambia de inmediato y los valores anteriores dejan de mostrarse como actuales.
    await pushStatus(status({ lectura: reading(4, { dedo: false, senalValida: false, bpm: null, spo2: null, glucosa: null, indiceOptico: null }),
      sesion: session(0, false, { ppg: { ...ppg, edadSegundos: 3.5 } }) }));
    expect(within(monitor).getByText('Esperando dedo')).toBeInTheDocument();
    expect(within(monitor).getByText('Esperando señal')).toBeInTheDocument();
    expect(within(within(monitor).getByRole('article', { name: 'Frecuencia cardíaca' })).queryByText('76', { selector: 'b' })).not.toBeInTheDocument();
    expect(within(monitor).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();
  });

  it('estado C: con 8 lecturas válidas muestra «Lectura estable», habilita guardar y al guardar ofrece ver la medición o volver', async () => {
    const stable = status({
      sesion: { idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false,
        estabilidad: { estable: true, motivo: null, mensaje: null, lecturasValidas: 8, lecturasRequeridas: 8 } },
    });
    const api = routes(stable, {
      'POST /acquisition/telemetry/session/save': jsonResponse(200, SAVED_DEMO),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(monitor).getByText('Lectura estable. Podés guardar la medición.')).toBeInTheDocument();
    expect(within(monitor).getByRole('button', { name: /Cancelar sesión/ })).toBeEnabled();
    expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session/save')).toBe(false); // nunca se guarda solo
    await user.click(within(monitor).getByRole('button', { name: 'Guardar medición' }));
    expect(await screen.findByRole('heading', { name: 'Medición guardada' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver medición' })).toHaveAttribute('href', `/app/mediciones/${MEASUREMENT_ID}`);
    expect(screen.getByRole('link', { name: 'Volver a mi dashboard' })).toHaveAttribute('href', '/app/mediciones');
  });

  it('al guardar muestra una pantalla de carga hasta que responde el servidor (sin saltar al formulario) y después el resultado', async () => {
    const stable = status({
      sesion: { idMedicion: MEASUREMENT_ID, iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false,
        estabilidad: { estable: true, motivo: null, mensaje: null, lecturasValidas: 8, lecturasRequeridas: 8 } },
    });
    let finish;
    const api = routes(stable, {
      'POST /acquisition/telemetry/session/save': () => new Promise((resolve) => { finish = () => resolve(jsonResponse(200, SAVED_DEMO)); }),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const monitor = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    await user.click(within(monitor).getByRole('button', { name: 'Guardar medición' }));
    // Mientras el servidor guarda (y envía el correo) se ve la carga: ni el formulario de inicio ni el resultado todavía.
    expect(screen.getByText('Guardando la medición…')).toBeInTheDocument();
    expect(screen.getByText(/No cierres ni recargues esta pantalla/)).toBeInTheDocument();
    expect(screen.queryByText('Configuración de la medición')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Medición guardada' })).not.toBeInTheDocument();
    expect(api.calls.filter((call) => call.key === 'POST /acquisition/telemetry/session/save')).toHaveLength(1);
    finish();
    expect(await screen.findByRole('heading', { name: 'Medición guardada' })).toBeInTheDocument();
    expect(screen.queryByText('Guardando la medición…')).not.toBeInTheDocument();
  });

  it('si el backend rechaza guardar (lectura no estable) muestra el motivo y la sesión sigue', async () => {
    const api = routes(status({ sesion: session(8, true) }), {
      'POST /acquisition/telemetry/session/save': jsonResponse(409, {
        codigo: 'LECTURA_NO_ESTABLE', detail: 'El dedo no está colocado sobre el sensor.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const live = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    await user.click(within(live).getByRole('button', { name: 'Guardar medición' }));
    expect(await within(live).findByText('El dedo no está colocado sobre el sensor.')).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Guardar medición' })).toBeEnabled(); // se puede reintentar
    expect(api.calls.filter((call) => call.key === 'POST /acquisition/telemetry/session/save')).toHaveLength(1);
  });

  it('con el Bluetooth caído en plena sesión no deja guardar', async () => {
    routes(status({ estado: 'PUERTO_DESCONECTADO', lectura: null, sesion: { ...session(8, true), enlacePerdido: true } }));
    renderAt('/app/mediciones/nueva');
    const live = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(live).getByText(/Se perdió la conexión con el dispositivo/)).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();
  });

  it('cancela la sesión tras confirmar', async () => {
    const api = routes(status({ sesion: session(2, false, 'x') }), {
      'POST /acquisition/telemetry/session/cancel': jsonResponse(200, detail({ estadoMedicion: 'CANCELADA' })),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/nueva');
    const live = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    await user.click(within(live).getByRole('button', { name: /Cancelar sesión/ }));
    expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session/cancel')).toBe(false);
    await user.click(within(live).getByRole('button', { name: 'Confirmar cancelación' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === 'POST /acquisition/telemetry/session/cancel')).toBe(true));
  });

  it('sin el dispositivo en el inventario del perfil lo explica y no inicia', async () => {
    routes(status({ puente: { ...BRIDGE, codigoDispositivo: 'OTRO-999' } }));
    renderAt('/app/mediciones/nueva');
    const section = await card();
    expect(await within(section).findByText(/El dispositivo conectado \(OTRO-999\) no está disponible/)).toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: 'Iniciar medición' })).not.toBeInTheDocument();
  });

  it('al abrir la medición en curso desde otra pantalla, retoma la sesión del dispositivo', async () => {
    routes(status({ sesion: session(5, false, 'Mantené el dedo quieto.') }), {
      [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, detail()),
    });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const live = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(within(live).getByText(/de 8/)).toBeInTheDocument();
    expect(screen.queryByText(/No hay un Arduino conectado/)).not.toBeInTheDocument(); // no mezcla el flujo de muestras crudas
  });
});

describe('Datos de prueba (DEMO) en el historial y el detalle', () => {
  const ITEM = {
    idMedicion: MEASUREMENT_ID, fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:00:12', modoMedicion: 'OXIMETRIA',
    estadoMedicion: 'COMPLETADA', condicionComida: 'AYUNO', edadAlMomento: 36, glucosaEstimada: null, spo2: '99.65',
    frecuenciaCardiaca: 76, calidadSenal: null, observacion: null, dispositivo: 'ARD-001', origenGlucosa: 'DEMO',
    glucosaDispositivo: '114.00', indiceOptico: '2.41492', esDemo: true,
  };

  it('el historial conserva el origen DEMO, permite filtrarlo y eliminarlo sin tocar lo real', async () => {
    const real = { ...ITEM, idMedicion: 'm-2', origenGlucosa: 'SIN_CALIBRAR', glucosaDispositivo: null, esDemo: false };
    let items = [ITEM, real];
    const api = routes(SIN_PUENTE, {
      'GET /measurements': () => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 10 }),
      'DELETE /measurements/demo': () => { items = [real]; return jsonResponse(200, { eliminadas: 1 }); },
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/historial');
    const list = await screen.findByRole('list', { name: 'Mediciones' });
    const [demoRow, realRow] = within(list).getAllByRole('listitem');
    expect(within(demoRow).getByText('DEMO')).toBeInTheDocument();
    expect(demoRow).toHaveTextContent('Glucosa del dispositivo 114 mg/dL (DEMO (prueba))');
    expect(realRow).toHaveTextContent('Sin calibrar');
    expect(within(realRow).queryByText('DEMO')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Origen de los datos'), 'DEMO');
    await waitFor(() => {
      const last = new URL(api.calls.filter((call) => call.key === 'GET /measurements').at(-1).url);
      expect(last.searchParams.get('origen')).toBe('DEMO');
    });
    await user.selectOptions(screen.getByLabelText('Origen de los datos'), '');

    await user.click(await screen.findByRole('button', { name: /Eliminar mis datos de prueba/ }));
    expect(api.calls.some((call) => call.key === 'DELETE /measurements/demo')).toBe(false); // pide confirmación
    await user.click(screen.getByRole('button', { name: 'Confirmar eliminación' }));
    expect(await screen.findByText(/Se eliminaron 1 mediciones de prueba/)).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Mediciones' })).getAllByRole('listitem')).toHaveLength(1));
    expect(screen.queryByRole('button', { name: /Eliminar mis datos de prueba/ })).not.toBeInTheDocument();
  });

  it('elimina una medición de prueba desde su detalle', async () => {
    const api = routes(SIN_PUENTE, {
      [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, SAVED_DEMO),
      [`DELETE /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, { eliminadas: 1 }),
    });
    const user = userEvent.setup();
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText(/Datos de prueba \(DEMO\)/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Eliminar medición de prueba/ }));
    await user.click(screen.getByRole('button', { name: 'Confirmar eliminación' }));
    expect(await screen.findByText(/La medición de prueba se eliminó/)).toBeInTheDocument();
    expect(api.calls.some((call) => call.key === `DELETE /measurements/${MEASUREMENT_ID}`)).toBe(true);
  });

  it('una medición real no ofrece eliminar', async () => {
    routes(SIN_PUENTE, {
      [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, { ...SAVED_DEMO, origenGlucosa: 'SIN_CALIBRAR', glucosaDispositivo: null, esDemo: false, puedeEliminar: false, unidadGlucosa: null }),
    });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText('Sin calibrar')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Eliminar medición de prueba/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Datos de prueba \(DEMO\)/)).not.toBeInTheDocument();
  });
});
