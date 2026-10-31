// Medición de un paciente institucional: UNA sola pantalla (datos del paciente → configuración → estado del dispositivo →
// señal en vivo → resultado). Reutiliza el DeviceMonitor de la cuenta individual. No hay Arduino: el stream SSE lo controla la prueba.

import { act, configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';
import { ageFromBirthDate } from './PatientMeasurementCard.jsx';

const stream = vi.hoisted(() => ({ emit: null }));
vi.mock('../../../../api/acquisitionApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  openStream: vi.fn(() => () => {}),
  openTelemetryStream: vi.fn(({ onEvent }) => {
    stream.emit = onEvent;
    return () => {};
  }),
}));

configure({ asyncUtilTimeout: 5000 });

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PATIENT_URL = `${BASE}/patients/p-1`;
const OPERADOR = ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'];
const DEVICE = { idDispositivo: 'd-1', codigoDispositivo: 'ARD-001', nombre: 'Arduino MAX30100', modelo: 'HC-06', modeloSensor: 'MAX30100', versionFirmware: '1.0.0' };
const BRIDGE = { puerto: 'COM4', medio: 'BLUETOOTH', baudios: 9600, codigoDispositivo: 'ARD-001', estadoEnlace: 'CONECTADO', reintento: 0, ultimoError: null };
const READING = {
  bpm: 76.4, spo2: 98.2, glucosa: 117, unidadGlucosa: 'mg/dL', origen: 'DEMO', esDemo: true, indiceOptico: 2.41, senalValida: true, dedo: true,
  muestras: 58, instante: '2026-10-08T09:00:00Z', edadSegundos: 0.4,
};
const status = (overrides = {}) => ({
  estado: 'CONECTADO', ocupado: false, puente: BRIDGE, lectura: READING, avisoDispositivo: null, lineasInvalidas: 0, lecturasRecibidas: 30, sesion: null, ...overrides,
});
const session = (lecturasValidas, estable, modo = 'OXIMETRIA') => ({
  idMedicion: 'm-1', iniciada: '2026-10-08T09:00:00Z', enlacePerdido: false, modo,
  estabilidad: { estable, motivo: estable ? null : 'LECTURAS_INSUFICIENTES', mensaje: null, lecturasValidas, lecturasRequeridas: 8 },
});
const SAVED = { idMedicion: 'm-1', idPerfilMedicion: 'p-1', modoMedicion: 'OXIMETRIA', estadoMedicion: 'COMPLETADA', esDemo: true, puedeOperar: false };

function patient(overrides = {}) {
  return {
    idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: '20111222',
    fechaNacimiento: '1980-01-02', edad: 10, sexoModelo: 'MASCULINO', estado: 'ACTIVO', fechaCreacion: '2026-10-03T09:00:00',
    fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
    responsable: { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz', activo: true },
    puedeModificar: true, esMio: true, medicionesAutorizadas: true, ...overrides,
  };
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  stream.emit = null;
});

function routes(person, telemetry = status(), extra = {}) {
  let current = telemetry;
  const api = mockApi({
    'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
    [`GET ${BASE}`]: jsonResponse(200, {
      idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: 'OPERADOR',
      estadoRelacion: 'ACTIVO', permisos: OPERADOR, propietario: { nombre: 'Victoria', apellido: 'Cortés' },
    }),
    [`GET ${PATIENT_URL}`]: jsonResponse(200, person),
    'GET /measurements/devices': jsonResponse(200, [DEVICE]),
    'GET /acquisition/telemetry/status': () => jsonResponse(200, current),
    'GET /acquisition/status': jsonResponse(200, { conectado: false }),
    ...extra,
  });
  return { ...api, set: (next) => { current = next; } };
}

const open = () => renderAt(`/app/instituciones/${ID}/pacientes/p-1/medir`);
const form = async () => {
  const start = await screen.findByRole('form', { name: 'Iniciar sesión de medición con el dispositivo' });
  await within(start).findByRole('button', { name: 'Iniciar medición' }); // ya cargó la lista de dispositivos
  return start;
};
const START = 'POST /acquisition/telemetry/session';
const pushStatus = (next) => act(() => stream.emit({ tipo: 'estado', ...next }));

describe('Medición institucional: datos del paciente y formulario único', () => {
  it('abre con los datos registrados (edad calculada hoy, sexo del perfil) y un solo formulario de medición', async () => {
    const { calls } = routes(patient());
    open();
    const card = (await screen.findByRole('heading', { name: /Datos del paciente/ })).closest('section');
    expect(within(card).getByRole('heading', { name: /Juan Pérez/ })).toBeInTheDocument();
    expect(within(card).getByText('Paciente activo')).toBeInTheDocument();
    // Fecha de nacimiento y edad calculada hoy (no usa la edad guardada: 10).
    expect(within(card).getByText(`02/01/1980 (${ageFromBirthDate('1980-01-02')} años)`, { exact: false })).toBeInTheDocument();
    expect(within(card).getByText('Masculino')).toBeInTheDocument();
    expect(within(card).getByText(/Centro Médico San José/)).toBeInTheDocument();
    const start = await form();
    // Una sola configuración: sin la sección «Medir con el dispositivo» ni un segundo formulario «Nueva medición».
    expect(screen.queryByRole('heading', { name: 'Medir con el dispositivo' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Medición en tiempo real/)).not.toBeInTheDocument(); // el monitor aparece recién al iniciar la sesión
    expect(screen.queryByLabelText('Vista previa del sensor')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Iniciar medición' })).toHaveLength(1);
    expect(screen.getAllByLabelText('Alimentación')).toHaveLength(1);
    expect(screen.getAllByLabelText(/^Edad en años/)).toHaveLength(1);
    expect(screen.getAllByLabelText(/^Sexo \(opcional\)/)).toHaveLength(1);
    // Los datos del perfil se sugieren sin pedirlos de nuevo.
    expect(within(start).getByLabelText('Edad en años (opcional)')).toHaveValue(ageFromBirthDate('1980-01-02'));
    expect(within(start).getByLabelText('Sexo (opcional)')).toHaveValue('MASCULINO');
    expect(within(start).getByText(/no modifican el perfil del paciente/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('PATCH') || call.key.startsWith('PUT') || call.key === 'POST /measurements')).toBe(false);
  });

  it('con datos incompletos muestra «Sin informar», no inventa valores y permite medir sin completarlos', async () => {
    const { calls } = routes(patient({ fechaNacimiento: null, edad: null, sexoModelo: null }));
    const user = userEvent.setup();
    open();
    const card = (await screen.findByRole('heading', { name: /Datos del paciente/ })).closest('section');
    expect(within(card).getByText('Fecha de nacimiento sin informar')).toBeInTheDocument();
    expect(within(card).getByText('Sexo sin informar')).toBeInTheDocument();
    expect(await screen.findByText(/no tiene fecha de nacimiento ni sexo registrado/)).toBeInTheDocument();
    const start = await form();
    expect(within(start).getByLabelText('Edad en años (opcional)')).toHaveValue(null);
    expect(within(start).getByLabelText('Sexo (opcional)')).toHaveValue('');
    await user.click(within(start).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(calls.some((call) => call.key === START)).toBe(true));
    expect(calls.find((call) => call.key === START).body).toEqual({
      idPerfilMedicion: 'p-1', idDispositivo: 'd-1', condicionComida: 'NO_INFORMADA', modoMedicion: 'OXIMETRIA',
    });
  });

  it('los datos opcionales valen solo para esta medición: se envían y no modifican al paciente', async () => {
    const { calls } = routes(patient({ fechaNacimiento: null, edad: null, sexoModelo: null }));
    const user = userEvent.setup();
    open();
    const start = await form();
    await user.type(within(start).getByLabelText('Edad en años (opcional)'), '47');
    await user.selectOptions(within(start).getByLabelText('Sexo (opcional)'), 'FEMENINO');
    await user.click(within(start).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(calls.some((call) => call.key === START)).toBe(true));
    expect(calls.find((call) => call.key === START).body).toMatchObject({ idPerfilMedicion: 'p-1', edadAlMomento: 47, sexoModelo: 'FEMENINO' });
    expect(calls.some((call) => call.key.startsWith('PATCH') || call.key.startsWith('PUT'))).toBe(false);
  });

  it('cambia entre oximetría y glucosa experimental: solo la glucosa muestra «Inicio de la última comida (opcional)» y la matriz, y nunca es obligatoria', async () => {
    const { calls } = routes(patient(), status(), {
      'GET /measurements/matrix': jsonResponse(200, { idMatriz: 'g', nombre: 'Matriz San José', version: '2', ambito: 'INSTITUCION', estado: 'ACTIVA' }),
    });
    const user = userEvent.setup();
    open();
    const start = await form();
    expect(within(start).queryByLabelText('Inicio de la última comida (opcional)')).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /measurements/matrix')).toBe(false);
    await user.selectOptions(within(start).getByLabelText('Modo de medición'), 'GLUCOSA_EXPERIMENTAL');
    expect(await within(start).findByText(/Matriz San José, versión 2/)).toBeInTheDocument();
    expect(within(start).getByLabelText('Inicio de la última comida (opcional)')).toBeInTheDocument(); // sigue visible como opcional
    await user.selectOptions(within(start).getByLabelText('Alimentación'), 'POSTPRANDIAL');
    expect(within(start).getByText(/no se puede comparar con la matriz «después de comer»/)).toBeInTheDocument(); // se avisa, no se bloquea
    // Vacía: «Después de comer» + Glucosa experimental INICIA igual, sin enviar fecha (queda NULL).
    await user.click(within(start).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(calls.some((call) => call.key === START)).toBe(true));
    expect(within(start).queryByText(/Indicá cuándo fue la última comida/)).not.toBeInTheDocument();
    const sent = calls.find((call) => call.key === START).body;
    expect(sent).toMatchObject({ modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'POSTPRANDIAL' });
    expect(sent.fechaHoraUltimaComida).toBeUndefined();
  });

  it('si se informa la última comida se envía con su fecha y hora', async () => {
    const { calls } = routes(patient(), status(), {
      'GET /measurements/matrix': jsonResponse(200, { idMatriz: 'g', nombre: 'Matriz San José', version: '2', ambito: 'INSTITUCION', estado: 'ACTIVA' }),
    });
    const user = userEvent.setup();
    open();
    const start = await form();
    await user.selectOptions(within(start).getByLabelText('Modo de medición'), 'GLUCOSA_EXPERIMENTAL');
    await user.selectOptions(within(start).getByLabelText('Alimentación'), 'POSTPRANDIAL');
    await user.type(within(start).getByLabelText('Inicio de la última comida (opcional)'), '2026-10-08T07:30');
    await user.click(within(start).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(calls.some((call) => call.key === START)).toBe(true));
    expect(calls.find((call) => call.key === START).body).toMatchObject({
      modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'POSTPRANDIAL', fechaHoraUltimaComida: '2026-10-08T07:30:00',
    });
  });

  it('sin dispositivo conectado no deja iniciar y lo explica', async () => {
    const { calls } = routes(patient(), status({ estado: 'SIN_PUENTE', puente: null, lectura: null }));
    open();
    const start = await form();
    expect(within(start).getByRole('button', { name: 'Iniciar medición' })).toBeDisabled();
    expect(calls.some((call) => call.key === START)).toBe(false);
  });
});

describe('Medición institucional: permisos', () => {
  it('un operador que no es el responsable ve los datos permitidos pero no puede medir', async () => {
    const { calls } = routes(patient({ puedeModificar: false, esMio: false, medicionesAutorizadas: false }));
    open();
    expect(await screen.findByText(/Solo el operador responsable del paciente puede iniciar mediciones/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar medición' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /measurements/devices')).toBe(false);
  });

  it('un paciente dado de baja no se puede medir', async () => {
    routes(patient({ estado: 'BAJA' }));
    open();
    expect(await screen.findByText(/dado de baja: no se pueden iniciar mediciones/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Iniciar medición' })).not.toBeInTheDocument();
  });
});

describe('Medición institucional: señal en vivo y guardado', () => {
  it('sigue mostrando al paciente durante la sesión, refleja dedo/señal reales y guarda una sola vez en el paciente', async () => {
    const api = routes(patient(), status(), {
      [START]: () => jsonResponse(201, { ...SAVED, estadoMedicion: 'ADQUIRIENDO' }),
      'POST /acquisition/telemetry/session/save': jsonResponse(200, SAVED),
    });
    const user = userEvent.setup();
    open();
    await user.click(within(await form()).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === START)).toBe(true));

    api.set(status({ sesion: session(2, false), lectura: { ...READING, dedo: false, bpm: null, spo2: null, glucosa: null, senalValida: false } }));
    await pushStatus(status({ sesion: session(2, false), lectura: { ...READING, dedo: false, bpm: null, spo2: null, glucosa: null, senalValida: false } }));
    const live = await screen.findByRole('region', { name: 'Sesión de medición con el dispositivo' });
    expect(screen.getByRole('heading', { name: /Datos del paciente/ })).toBeInTheDocument(); // el contexto del paciente no desaparece
    expect(within(live).getByLabelText('Datos de la medición en curso')).toHaveTextContent('PAC-ABC123');
    expect(within(live).getByLabelText('Indicadores de la adquisición')).toHaveTextContent('Dedo: no colocado');
    expect(within(live).getByText('Esperando dedo')).toBeInTheDocument();
    expect(within(live).getByRole('button', { name: 'Guardar medición' })).toBeDisabled();

    // Dedo colocado pero señal inválida: «señal insuficiente», sin valores inventados.
    await pushStatus(status({ sesion: session(0, false), lectura: { ...READING, dedo: true, bpm: null, spo2: null, glucosa: null, senalValida: false } }));
    expect(within(live).getByText('Señal insuficiente')).toBeInTheDocument();
    expect(within(live).getByLabelText('Indicador de latidos detectados')).toHaveTextContent('0 latidos detectados'); // sin muestras reales no hay latidos

    // Lectura estable con valores reales: se habilita guardar; dos clics rápidos guardan una sola vez.
    await pushStatus(status({ sesion: session(8, true) }));
    expect(within(live).getByText('Lectura estable. Podés guardar la medición.')).toBeInTheDocument();
    const save = within(live).getByRole('button', { name: 'Guardar medición' });
    await user.dblClick(save);
    expect(await screen.findByRole('heading', { name: 'Medición guardada' })).toBeInTheDocument();
    expect(screen.getByText(/asociada al paciente PAC-ABC123/)).toBeInTheDocument();
    expect(screen.getByText(/no suma a los indicadores de salud/)).toBeInTheDocument(); // DEMO
    expect(api.calls.filter((call) => call.key === 'POST /acquisition/telemetry/session/save')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Ver medición' })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/p-1/mediciones/m-1`);
  });
});

describe('Medición institucional: correo del paciente para sus resultados', () => {
  const EMAIL_URL = `${PATIENT_URL}/result-email`;
  const withEmail = (overrides = {}) => patient({ correoResultados: 'pa***@example.com', correoResultadosVence: '2027-10-17T10:00:00', ...overrides });

  it('es opcional: se carga con la autorización del paciente, queda pendiente de su confirmación, enmascarado, y no inicia la medición', async () => {
    const api = routes(patient(), status(), { [`PUT ${EMAIL_URL}`]: jsonResponse(200, patient({ correoResultadosPendiente: 'pa***@example.com' })) });
    const user = userEvent.setup();
    open();
    const box = (await screen.findByText(/Resultados por correo \(opcional\)/)).closest('fieldset');
    expect(within(box).getByText(/sin esa confirmación no recibe nada/)).toBeInTheDocument();
    expect(within(box).getByText(/también las pruebas DEMO/)).toBeInTheDocument();
    await user.type(within(box).getByLabelText('Correo del paciente'), 'paciente@example.com');
    await user.keyboard('{Enter}'); // Enter guarda el correo: no inicia la medición
    expect(await within(box).findByText(/Ingresá el correo del paciente y confirmá que autorizó/)).toBeInTheDocument();
    expect(api.calls.some((call) => call.key === `PUT ${EMAIL_URL}`)).toBe(false);
    await user.click(within(box).getByRole('checkbox', { name: /El paciente autorizó recibir sus resultados/ }));
    await user.click(within(box).getByRole('button', { name: 'Enviar confirmación al paciente' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === `PUT ${EMAIL_URL}`)).toBe(true));
    expect(api.calls.find((call) => call.key === `PUT ${EMAIL_URL}`).body).toEqual({ correo: 'paciente@example.com', pacienteAutoriza: true });
    expect(await within(box).findByText(/Enviamos un correo a pa\*\*\*@example.com para que el paciente la confirme/)).toBeInTheDocument();
    expect(within(box).queryByText(/paciente@example.com/)).not.toBeInTheDocument(); // solo se muestra enmascarado
    expect(api.calls.some((call) => call.key === START)).toBe(false);
  });

  it('se puede cambiar (renueva el plazo) y quitar con confirmación', async () => {
    const api = routes(withEmail(), status(), {
      [`PUT ${EMAIL_URL}`]: jsonResponse(200, withEmail({ correoResultadosPendiente: 'ro***@example.com' })),
      [`DELETE ${EMAIL_URL}`]: jsonResponse(200, patient()),
    });
    const user = userEvent.setup();
    open();
    const box = (await screen.findByText(/Resultados por correo \(opcional\)/)).closest('fieldset');
    expect(within(box).getByText(/pa\*\*\*@example.com/)).toBeInTheDocument();
    await user.click(within(box).getByRole('button', { name: /Cambiar correo/ }));
    await user.type(within(box).getByLabelText('Nuevo correo del paciente'), 'rosa.nueva@example.com');
    await user.click(within(box).getByRole('checkbox', { name: /El paciente autorizó/ }));
    await user.click(within(box).getByRole('button', { name: 'Enviar confirmación al paciente' }));
    expect(await within(box).findByText(/Hasta entonces sigue vigente el correo anterior/)).toBeInTheDocument();
    expect(within(box).getByText(/vence el 17\/10\/2027/)).toBeInTheDocument(); // el anterior sigue con su vencimiento
    expect(api.calls.find((call) => call.key === `PUT ${EMAIL_URL}`).body.correo).toBe('rosa.nueva@example.com');
    await user.click(within(box).getByRole('button', { name: /Quitar correo/ }));
    expect(api.calls.some((call) => call.key === `DELETE ${EMAIL_URL}`)).toBe(false); // pide confirmación
    await user.click(within(box).getByRole('button', { name: 'Confirmar' }));
    expect(await within(box).findByText(/ya no recibirá resultados automáticos/)).toBeInTheDocument();
    expect(within(box).getByLabelText('Correo del paciente')).toBeInTheDocument();
  });

  it('al guardar la medición informa si el resultado se envió solo al correo del paciente', async () => {
    const api = routes(withEmail(), status(), {
      [START]: () => jsonResponse(201, { ...SAVED, estadoEnlace: 'ADQUIRIENDO' }),
      'POST /acquisition/telemetry/session/save': jsonResponse(200, { ...SAVED, esDemo: false, envioAutomatico: 'ENVIADO' }),
    });
    const user = userEvent.setup();
    open();
    await user.click(within(await form()).getByRole('button', { name: 'Iniciar medición' }));
    await waitFor(() => expect(api.calls.some((call) => call.key === START)).toBe(true));
    api.set(status({ sesion: session(8, true) }));
    await pushStatus(status({ sesion: session(8, true) }));
    await user.click(await screen.findByRole('button', { name: 'Guardar medición' }));
    expect(await screen.findByText(/Enviamos el resultado por correo al paciente \(pa\*\*\*@example.com\)/)).toBeInTheDocument();
  });
});
