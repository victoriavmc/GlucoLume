import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, CONSENTS_PENDING, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';
import { ageText } from './GlucoseReferencePanel.jsx';

const PROFILE_ID = 'p-own';
const MEASUREMENT_ID = 'm-1';
const DEVICE = {
  idDispositivo: 'd-1', codigoDispositivo: 'OXI-001', nombre: 'Oxímetro', modelo: 'HC-06', modeloSensor: 'MAX30102',
  versionFirmware: '1.0.0',
};
const OWN_PROFILE = {
  perfilDisponible: true, datosFaltantes: [], idPerfilMedicion: PROFILE_ID, nombre: 'Victoria', apellido: 'Cortés',
  fechaNacimiento: '1990-05-17', edad: 36, sexoModelo: 'FEMENINO', fechaCreacion: '2026-10-01T10:00:00',
  fechaUltimaMedicion: null,
};
const EMPTY = { items: [], total: 0, pagina: 1, tamanioPagina: 10 };
const NO_STATS = { dias: 30, cantidadMediciones: 0 };
const metric = (cantidad = 0, promedio = null, minimo = null, maximo = null) => ({ cantidad, promedio, minimo, maximo });
const DASHBOARD_EMPTY = {
  perfilDisponible: true, datosFaltantes: [], periodo: { dias: 30, desde: null, hasta: null },
  resumen: { total: 0, completadas: 0, enPeriodo: 0, ultimaMedicion: null, ultimaGlucosa: null, ultimaSpo2: null, ultimaFrecuencia: null },
  estadisticas: { dias: 30, cantidadMediciones: 0, glucosa: metric(), spo2: metric(), frecuenciaCardiaca: metric(), serieDiaria: [] },
  recientes: [],
};
const stat = (cantidad = 0, ultimo = null, promedio = null, minimo = null, maximo = null) => ({ cantidad, ultimo, promedio, minimo, maximo });
const STATS_EMPTY = { mediciones: 0, frecuenciaCardiaca: stat(), spo2: stat(), glucosa: stat(), indiceOptico: stat() };
const EVOLUTION_EMPTY = {
  origen: 'TODOS', desde: null, hasta: null, puntos: [], truncado: false, estadisticas: { experimental: STATS_EMPTY, demo: null },
};
const point = (id, fecha, extra = {}) => ({
  idMedicion: id, fecha, modoMedicion: 'OXIMETRIA', origen: null, esDemo: false, frecuenciaCardiaca: null, spo2: null, glucosa: null,
  indiceOptico: null, ...extra,
});
const LINK_DOWN = {
  conectado: false, ocupado: false, puerto: null, medio: null, baudios: null, estadoDispositivo: null, ultimoError: null,
  lineasInvalidas: 0, dispositivo: null, adquisicion: null,
};

function detail(overrides = {}) {
  return {
    idMedicion: MEASUREMENT_ID, idPerfilMedicion: PROFILE_ID, modoMedicion: 'OXIMETRIA', estadoMedicion: 'PENDIENTE',
    fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: null, fechaHoraUltimaComida: null, condicionComida: 'NO_INFORMADA',
    minutosDesdeUltimaComida: null, duracionMs: null, edadAlMomento: 36, sexoModelo: 'FEMENINO',
    versionFirmwareAlMomento: '1.0.0', modeloSensorAlMomento: 'MAX30102', versionAlgoritmo: null, calidadSenal: null,
    spo2: null, frecuenciaCardiaca: null, glucosaEstimada: null, observacion: null, dispositivo: DEVICE, matriz: null,
    cantidadMuestras: 0, referenciaCapilar: null, puedeOperar: true,
    aviso: 'Resultado experimental de GlucoLume: no es un diagnóstico ni reemplaza una medición clínica certificada.',
    ...overrides,
  };
}

// Con todos los archivos en paralelo, 1 s por defecto no siempre alcanza para que las pantallas carguen.
configure({ asyncUtilTimeout: 5000 });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(extra = {}, account = ACCOUNT) {
  return mockApi({
    'GET /auth/me': jsonResponse(200, account), 'GET /measurements/dashboard': jsonResponse(200, DASHBOARD_EMPTY),
    'GET /acquisition/status': jsonResponse(200, LINK_DOWN),
    'GET /measurements/evolution': jsonResponse(200, EVOLUTION_EMPTY), ...extra,
  });
}

const NOTICE = 'Podés realizar mediciones sin completar tu edad o sexo. Sin embargo, se recomienda informar estos datos para '
  + 'mejorar la contextualización de los resultados.';

describe('Mediciones: dashboard', () => {
  it('"Mediciones" aparece solo para cuentas individuales', async () => {
    const institutional = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    const { calls } = routes({ 'GET /institutions/mine': jsonResponse(200, []), 'GET /institutions/invitations': jsonResponse(200, []) }, institutional);
    renderAt('/app/mediciones');
    await waitFor(() => expect(calls.some((call) => call.key === 'GET /auth/me')).toBe(true));
    expect(calls.some((call) => call.key.startsWith('GET /measurements'))).toBe(false);
  });

  it('abre directamente el dashboard, con los tres botones principales y sin las demás secciones', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    renderAt('/app/mediciones');
    const dashboard = (await screen.findByRole('heading', { name: 'Mi dashboard' })).closest('section');
    expect(within(dashboard).getByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', '/app/mediciones/nueva');
    expect(within(dashboard).getByRole('link', { name: /Conectar dispositivo/ })).toHaveAttribute('href', '/app/conectar-dispositivo');
    // «Configuración de perfil» abre el apartado dentro de Mediciones, no la pantalla general «Mi perfil».
    expect(await within(dashboard).findByRole('link', { name: /Configuración de perfil/ })).toHaveAttribute('href', '/app/mediciones/perfil');
    // Nada de lo demás queda permanentemente en la pantalla principal.
    expect(screen.queryByRole('heading', { name: 'Mi perfil de medición' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Autorización para almacenar tus mediciones' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Revocar autorización' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: /Iniciar sesión de medición/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Estado')).not.toBeInTheDocument(); // sin los filtros del historial completo
  });

  it('sin ninguna medición guardada no dice que hay pruebas disponibles', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    renderAt('/app/mediciones');
    expect(await screen.findByText('Todavía no guardaste ninguna medición.')).toBeInTheDocument();
    expect(screen.getByText(/Todavía no hay mediciones experimentales/)).toBeInTheDocument();
    expect(screen.queryByText(/mediciones de prueba disponibles/)).not.toBeInTheDocument();
  });

  it('sin mediciones muestra estados vacíos claros y no fabrica ceros ni promedios', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    renderAt('/app/mediciones');
    const summary = await screen.findByRole('list', { name: 'Resumen personal' });
    for (const label of ['Última frecuencia cardíaca', 'Última SpO₂']) {
      expect(within(summary).getByText(label).closest('li')).toHaveTextContent('Sin datos disponibles');
    }
    expect(await screen.findByText(/No hay mediciones guardadas en este período/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Pruebas DEMO' })).not.toBeInTheDocument();
    expect(screen.getByText('Todavía no hay mediciones recientes.')).toBeInTheDocument();
  });

  const HISTORY = {
    ...EVOLUTION_EMPTY,
    puntos: [
      point('m-1', '2026-10-13T09:00:00', { frecuenciaCardiaca: 78, spo2: 97.5, origen: 'EXPERIMENTAL', glucosa: 98 }),
      point('m-2', '2026-10-13T14:30:00', { frecuenciaCardiaca: 86, spo2: 98, origen: 'SIN_CALIBRAR' }),
      point('m-3', '2026-10-13T22:00:00', { frecuenciaCardiaca: 108, spo2: 96, origen: 'EXPERIMENTAL', glucosa: 104, indiceOptico: 2.4149 }),
    ],
    estadisticas: {
      experimental: {
        mediciones: 3,
        frecuenciaCardiaca: stat(3, { valor: 108, fecha: '2026-10-13T22:00:00' }, 90.67, 78, 108),
        spo2: stat(3, { valor: 96, fecha: '2026-10-13T22:00:00' }, 97.17, 96, 98),
        glucosa: stat(2, { valor: 104, fecha: '2026-10-13T22:00:00' }, 101, 98, 104),
        indiceOptico: stat(1, { valor: 2.4149, fecha: '2026-10-13T22:00:00' }, 2.4149, 2.4149, 2.4149),
      },
      demo: null,
    },
  };

  it('las tarjetas y el gráfico usan las mediciones reales del período; cada variable tiene su unidad', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, HISTORY) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const summary = await screen.findByRole('list', { name: 'Resumen personal' });
    expect(within(summary).getByText('Última frecuencia cardíaca').closest('li')).toHaveTextContent('108 lpm');
    expect(within(summary).getByText('Última SpO₂').closest('li')).toHaveTextContent('96 %');
    const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
    // Se abre en la glucosa (hay valores): solo los puntos que existen y sus estadísticas del período.
    expect(await evolution.findByRole('group', { name: /Glucosa experimental: 2 puntos/ })).toBeInTheDocument();
    expect(evolution.getByRole('region', { name: 'Glucosa experimental: estadísticas experimentales' })).toHaveTextContent('101 mg/dL');
    // Frecuencia cardíaca: un punto por medición, con su valor exacto.
    await user.click(evolution.getByRole('tab', { name: 'Frecuencia cardíaca' }));
    expect(evolution.getByRole('region', { name: 'Frecuencia cardíaca: estadísticas experimentales' })).toHaveTextContent('90,7 lpm');
    const chart = evolution.getByRole('group', { name: /Frecuencia cardíaca: 3 puntos/ });
    expect(within(chart).getAllByRole('button').map((node) => node.getAttribute('aria-label'))).toEqual([
      '13/10/2026 09:00: 78 lpm', '13/10/2026 14:30: 86 lpm', '13/10/2026 22:00: 108 lpm',
    ]);
    expect(evolution.getByRole('region', { name: 'Frecuencia cardíaca: estadísticas experimentales' })).toHaveTextContent('78 lpm');
    // Cambiar la variable cambia datos, escala y unidad.
    await user.click(evolution.getByRole('tab', { name: 'Saturación de oxígeno (SpO₂)' }));
    expect(evolution.getByRole('group', { name: /Saturación de oxígeno \(SpO₂\): 3 puntos/ })).toBeInTheDocument();
    expect(evolution.getAllByRole('button', { name: /^13\/10\/2026/ }).map((node) => node.getAttribute('aria-label'))[0]).toBe('13/10/2026 09:00: 97,5 %');
    // Glucosa experimental: solo los valores que existen (la medición SIN_CALIBRAR no aporta ninguno).
    await user.click(evolution.getByRole('tab', { name: 'Glucosa experimental' }));
    expect(evolution.getByRole('group', { name: /Glucosa experimental: 2 puntos/ })).toBeInTheDocument();
    expect(evolution.getAllByRole('button').map((node) => node.getAttribute('aria-label'))).toEqual([
      '13/10/2026 09:00: 98 mg/dL', '13/10/2026 22:00: 104 mg/dL',
    ]);
  });

  it('al pasar sobre un punto muestra fecha, hora, valor, unidad, modo y origen; al elegirlo abre su detalle', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, HISTORY) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
    await user.click(await evolution.findByRole('tab', { name: 'Frecuencia cardíaca' }));
    const target = await evolution.findByRole('button', { name: '13/10/2026 22:00: 108 lpm' });
    await user.hover(target);
    const tip = within(evolution.getByRole('tooltip'));
    expect(tip.getByText('Frecuencia cardíaca')).toBeInTheDocument(); // variable
    expect(tip.getByText('108 lpm')).toBeInTheDocument(); // valor
    expect(tip.getByText('13/10/2026 22:00')).toBeInTheDocument(); // fecha y hora
    expect(tip.getByText('Experimental')).toBeInTheDocument(); // origen
    expect(tip.getByText('Oximetría')).toBeInTheDocument();
    await user.click(target);
    expect(target).toHaveAttribute('aria-pressed', 'true'); // el punto queda resaltado
    // El detalle sale en la misma vista: variable, valor, fecha, hora, origen y resumen; «Ver detalle completo» es secundario.
    const selected = within(evolution.getByRole('region', { name: 'Medición seleccionada' }));
    expect(selected.getByText('Frecuencia cardíaca')).toBeInTheDocument();
    expect(selected.getByText('108 lpm')).toBeInTheDocument();
    expect(selected.getByText('13/10/2026')).toBeInTheDocument();
    expect(selected.getByText('22:00')).toBeInTheDocument();
    expect(selected.getByText('Experimental')).toBeInTheDocument();
    expect(selected.getByText(/Medición experimental guardada en el historial/)).toBeInTheDocument();
    const others = within(selected.getByRole('list', { name: 'Otros valores de esta medición' }));
    expect(others.getByText('104 mg/dL')).toBeInTheDocument();
    expect(others.getByText('96 %')).toBeInTheDocument();
    // Abajo del gráfico queda solo el acceso al detalle completo; las estadísticas de la derecha se reemplazan por el detalle del punto.
    expect(evolution.getByRole('link', { name: 'Ver detalle completo' })).toHaveAttribute('href', '/app/mediciones/m-3');
    expect(within(selected.getByRole('list', { name: 'Otros valores de esta medición' })).getByText('104 mg/dL')).toBeInTheDocument();
    expect(evolution.queryByRole('region', { name: /estadísticas experimentales/ })).not.toBeInTheDocument();
    await user.click(evolution.getByRole('button', { name: 'Volver a las estadísticas del período' }));
    expect(evolution.getByRole('region', { name: /estadísticas experimentales/ })).toBeInTheDocument();
    expect(evolution.queryByRole('region', { name: 'Medición seleccionada' })).not.toBeInTheDocument();
  });

  it('en la vista general, un clic en un punto muestra su detalle sin salir de la vista y resalta la misma medición en los demás gráficos', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, HISTORY) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
    await user.click(await evolution.findByRole('tab', { name: 'Vista general' }));
    const glucose = within(evolution.getByRole('article', { name: 'Glucosa experimental' }));
    await user.click(glucose.getByRole('button', { name: '13/10/2026 22:00: 104 mg/dL' }));
    expect(evolution.getByRole('tab', { name: 'Vista general' })).toHaveAttribute('aria-selected', 'true'); // no cambia de pestaña
    const detail = within(evolution.getByRole('region', { name: 'Medición seleccionada' }));
    expect(detail.getByText('Glucosa experimental')).toBeInTheDocument();
    expect(detail.getByText('104 mg/dL')).toBeInTheDocument();
    expect(detail.getByText('22:00')).toBeInTheDocument();
    expect(detail.getByText('Experimental')).toBeInTheDocument();
    const heart = within(evolution.getByRole('article', { name: 'Frecuencia cardíaca' }));
    expect(heart.getByRole('button', { name: '13/10/2026 22:00: 108 lpm' })).toHaveAttribute('aria-pressed', 'true'); // misma medición
    expect(heart.getByRole('button', { name: '13/10/2026 09:00: 78 lpm' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('el período consulta al backend: 24 horas, 7, 14, 30, 90 días y personalizado', async () => {
    const { calls } = routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const select = await screen.findByLabelText('Período');
    expect([...select.options].map((option) => option.textContent)).toEqual([
      'Últimas 24 horas', 'Últimos 7 días', 'Últimos 14 días', 'Últimos 30 días', 'Últimos 90 días', 'Período personalizado',
    ]);
    const last = () => new URL(calls.filter((call) => call.key === 'GET /measurements/evolution').at(-1).url).searchParams;
    await user.selectOptions(select, '1');
    await waitFor(() => expect(last().get('dias')).toBe('1'));
    expect(last().get('origen')).toBe('TODOS');
    await user.selectOptions(select, '14');
    await waitFor(() => expect(last().get('dias')).toBe('14'));
    await user.selectOptions(select, 'rango');
    await user.type(await screen.findByLabelText('Desde'), '2026-10-01');
    await waitFor(() => expect(last().get('desde')).toBe('2026-10-01'));
  });

  it('la vista general muestra un gráfico propio por métrica y la agrupación por día promedia sin perder las mediciones', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, HISTORY) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
    await user.click(await evolution.findByRole('tab', { name: 'Vista general' }));
    for (const title of ['Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)', 'Glucosa experimental', 'Índice óptico']) {
      expect(evolution.getByRole('article', { name: title })).toBeInTheDocument();
    }
    await user.click(evolution.getByRole('tab', { name: 'Frecuencia cardíaca' }));
    await user.selectOptions(evolution.getByLabelText('Agrupación'), 'DIA');
    const day = await evolution.findByRole('button', { name: '13/10/2026 Día completo: 90,7 lpm' }); // promedio de las 3 del día
    await user.click(day);
    const selected = within(evolution.getByRole('region', { name: 'Medición seleccionada' }));
    expect(selected.getByText(/Promedio de 3 mediciones/)).toBeInTheDocument();
    expect(within(evolution.getByRole('list', { name: 'Mediciones promediadas' })).getAllByRole('link')).toHaveLength(3); // las mediciones individuales siguen accesibles
  });

  describe('«Promedio por hora»', () => {
    // Ventana pedida: últimas 24 h (el backend informa `desde` = ahora − 1 día). Tres pruebas DEMO caen en la hora 00:00-01:00 del 14/10,
    // una en la hora 23:00-24:00 del 13/10 y una experimental que NO debe entrar en el promedio de las DEMO.
    const HOURLY = {
      ...EVOLUTION_EMPTY, desde: '2026-10-13T12:50:00.123456',
      puntos: [
        point('d-1', '2026-10-13T23:38:44', { frecuenciaCardiaca: 99, spo2: 97.54, glucosa: 111, indiceOptico: 2.1, origen: 'DEMO', esDemo: true }),
        point('d-2', '2026-10-14T00:24:36', { frecuenciaCardiaca: 90, spo2: 98, glucosa: 114, indiceOptico: 2.2, origen: 'DEMO', esDemo: true }),
        point('e-1', '2026-10-14T00:30:00', { frecuenciaCardiaca: 60, spo2: 95, glucosa: 80, indiceOptico: 2.0, origen: 'EXPERIMENTAL' }),
        point('d-3', '2026-10-14T00:47:36', { frecuenciaCardiaca: 92, spo2: 98.5, glucosa: 118, indiceOptico: 2.3, origen: 'DEMO', esDemo: true }),
        point('d-4', '2026-10-14T00:49:58', { frecuenciaCardiaca: 94, spo2: 99, glucosa: 120, indiceOptico: 2.4, origen: 'DEMO', esDemo: true }),
      ],
    };

    async function open() {
      routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, HOURLY) });
      const user = userEvent.setup();
      renderAt('/app/mediciones');
      const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
      await user.selectOptions(evolution.getByLabelText('Período'), '1');
      await user.selectOptions(evolution.getByLabelText('Origen de los datos'), 'DEMO');
      await user.click(await evolution.findByRole('tab', { name: 'Frecuencia cardíaca' }));
      return { user, evolution };
    }

    it('agrupa las mediciones de la misma hora en un solo punto con su promedio (solo DEMO) y lo explica', async () => {
      const { user, evolution } = await open();
      // Cada medición: 4 puntos DEMO.
      expect(await evolution.findByRole('group', { name: /Frecuencia cardíaca: 4 puntos/ })).toBeInTheDocument();
      await user.selectOptions(evolution.getByLabelText('Agrupación'), 'HORA');
      // Por hora: 2 bloques (23:00 y 00:00). Sin duplicados y sin la medición experimental en el promedio: (90 + 92 + 94) / 3 = 92.
      expect(await evolution.findByRole('group', { name: /Frecuencia cardíaca: 2 puntos/ })).toBeInTheDocument();
      const block = await evolution.findByRole('button', { name: '14/10/2026 00:00–01:00: 92 lpm (DEMO)' });
      await user.hover(block);
      const tip = within(evolution.getByRole('tooltip'));
      expect(tip.getByText('92 lpm')).toBeInTheDocument();
      expect(tip.getByText('14/10/2026 00:00–01:00')).toBeInTheDocument(); // la hora que representa, no un instante inventado
      expect(tip.getByText('Promedio de 3 mediciones de esa hora')).toBeInTheDocument();
      expect(tip.getByText('DEMO (prueba)')).toBeInTheDocument();
      await user.click(block);
      const selected = within(evolution.getByRole('region', { name: 'Medición seleccionada' }));
      expect(selected.getByText(/Promedio de 3 mediciones/)).toBeInTheDocument();
      expect(within(evolution.getByRole('list', { name: 'Mediciones promediadas' })).getAllByRole('link')).toHaveLength(3); // las tres de esa hora siguen accesibles
      // El bloque con una sola medición también es un promedio horario identificado.
      expect(evolution.getByRole('button', { name: '13/10/2026 23:00–00:00: 99 lpm (DEMO)' })).toBeInTheDocument();
      // El eje representa las últimas 24 h pedidas y el pie dice que se promedia por hora.
      expect(evolution.getByText(/promedio de las mediciones de una hora/)).toBeInTheDocument();
      expect(evolution.getByText(/Eje: 13\/10\/2026 12:50 a 14\/10\/2026 12:50/)).toBeInTheDocument();
      // Volver a «Cada medición» devuelve los puntos individuales.
      await user.selectOptions(evolution.getByLabelText('Agrupación'), 'MEDICION');
      expect(await evolution.findByRole('group', { name: /Frecuencia cardíaca: 4 puntos/ })).toBeInTheDocument();
    });

    it('la vista general agrupa por hora las cuatro variables y el origen DEMO no mezcla experimentales', async () => {
      const { user, evolution } = await open();
      await user.selectOptions(evolution.getByLabelText('Agrupación'), 'HORA');
      await user.click(evolution.getByRole('tab', { name: 'Vista general' }));
      for (const title of ['Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)', 'Glucosa experimental', 'Índice óptico']) {
        const article = within(evolution.getByRole('article', { name: title }));
        expect(article.getByRole('group', { name: new RegExp(`${title.replace(/[()]/g, '\\$&')}: 2 puntos`) })).toBeInTheDocument();
      }
      // SpO₂ de la hora 00:00 solo con las DEMO: (98 + 98,5 + 99) / 3 = 98,5 (no 97,2 con la experimental de 95).
      const spo2 = within(evolution.getByRole('article', { name: 'Saturación de oxígeno (SpO₂)' }));
      expect(spo2.getByRole('button', { name: '14/10/2026 00:00–01:00: 98,5 % (DEMO)' })).toBeInTheDocument();
    });

    it('con origen experimental solo se agrupa lo experimental', async () => {
      const { user, evolution } = await open();
      await user.selectOptions(evolution.getByLabelText('Origen de los datos'), 'EXPERIMENTAL');
      await user.selectOptions(evolution.getByLabelText('Agrupación'), 'HORA');
      expect(await evolution.findByRole('button', { name: '14/10/2026 00:00–01:00: 60 lpm' })).toBeInTheDocument();
    });
  });

  it('las pruebas DEMO se identifican, van en una sección aparte y no se mezclan con los promedios experimentales', async () => {
    const mixed = {
      ...HISTORY,
      puntos: [...HISTORY.puntos, point('m-demo', '2026-10-13T23:00:00', { frecuenciaCardiaca: 70, spo2: 99, origen: 'DEMO', esDemo: true, glucosa: 117 })],
      estadisticas: { ...HISTORY.estadisticas, demo: {
        mediciones: 1, frecuenciaCardiaca: stat(1, { valor: 70, fecha: '2026-10-13T23:00:00' }, 70, 70, 70),
        spo2: stat(1, { valor: 99, fecha: '2026-10-13T23:00:00' }, 99, 99, 99), glucosa: stat(1, { valor: 117, fecha: '2026-10-13T23:00:00' }, 117, 117, 117),
        indiceOptico: stat(),
      } },
    };
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE), 'GET /measurements/evolution': jsonResponse(200, mixed),
      'GET /measurements/dashboard': jsonResponse(200, { ...DASHBOARD_EMPTY, pruebasDemo: 1 }) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const evolution = within(await screen.findByRole('region', { name: 'Evolución de mis mediciones' }));
    // Por defecto solo experimentales: la DEMO no aparece en el gráfico.
    await user.click(await evolution.findByRole('tab', { name: 'Frecuencia cardíaca' }));
    expect(await evolution.findByRole('group', { name: /Frecuencia cardíaca: 3 puntos/ })).toBeInTheDocument();
    // «Todos los registros»: se distingue visualmente y las estadísticas van separadas.
    await user.selectOptions(evolution.getByLabelText('Origen de los datos'), 'TODOS');
    expect(evolution.getByRole('group', { name: /Frecuencia cardíaca: 4 puntos/ })).toBeInTheDocument();
    expect(evolution.getByRole('button', { name: '13/10/2026 23:00: 70 lpm (DEMO)' })).toBeInTheDocument();
    expect(evolution.getByText('Prueba DEMO (simulada)')).toBeInTheDocument();
    expect(evolution.getByRole('region', { name: 'Frecuencia cardíaca: estadísticas experimentales' })).toHaveTextContent('90,7 lpm');
    expect(evolution.getByRole('region', { name: 'Frecuencia cardíaca: estadísticas de pruebas' })).toHaveTextContent('70 lpm');
    // Solo DEMO.
    await user.selectOptions(evolution.getByLabelText('Origen de los datos'), 'DEMO');
    expect(evolution.getByRole('group', { name: /Frecuencia cardíaca: 1 punto/ })).toBeInTheDocument();
    expect(evolution.queryByRole('region', { name: 'Frecuencia cardíaca: estadísticas experimentales' })).not.toBeInTheDocument();
    // Los indicadores superiores no incluyen la DEMO.
    const latestHeart = within(screen.getByRole('list', { name: 'Resumen personal' })).getByText('Última frecuencia cardíaca').closest('li');
    expect(latestHeart).toHaveTextContent('108 lpm');
    expect(latestHeart).not.toHaveTextContent('DEMO');
    expect(screen.queryByRole('region', { name: 'Pruebas DEMO' })).not.toBeInTheDocument();
  });

  it('muestra las pruebas DEMO entre las mediciones guardadas sin hacer pensar que nunca se midió', async () => {
    const demoItem = { idMedicion: 'm-demo', fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:00:12', modoMedicion: 'OXIMETRIA',
      estadoMedicion: 'COMPLETADA', condicionComida: 'AYUNO', edadAlMomento: null, glucosaEstimada: null, spo2: '99.65', frecuenciaCardiaca: 76,
      calidadSenal: null, observacion: null, dispositivo: 'ARD-001', origenGlucosa: 'DEMO', glucosaDispositivo: '114.00', indiceOptico: '2.41', esDemo: true };
    routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements/dashboard': jsonResponse(200, { ...DASHBOARD_EMPTY, ultimaGuardada: demoItem, recientes: [demoItem], pruebasDemo: 1 }),
    });
    renderAt('/app/mediciones');
    const last = within(await screen.findByRole('region', { name: 'Última medición registrada' }));
    expect(last.getByText('Medición de prueba (DEMO)')).toBeInTheDocument();
    expect(last.getByText(/Glucosa DEMO \(simulada\) 114 mg\/dL/)).toBeInTheDocument();
    expect(last.getByText(/no se cuentan como indicadores experimentales/)).toBeInTheDocument();
    expect(last.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/app/mediciones/m-demo');
    expect(screen.getByText(/Todavía no hay mediciones experimentales/)).toBeInTheDocument();
    expect(screen.getByText(/Tenés mediciones de prueba disponibles/)).toBeInTheDocument();
    const recent = within(screen.getByRole('table', { name: 'Mediciones recientes' }));
    expect(recent.getByText('DEMO')).toBeInTheDocument();
    expect(recent.getByText('114 mg/dL')).toBeInTheDocument();
    // Sin valores experimentales, los últimos valores salen de la última prueba y quedan identificados como DEMO.
    expect(within(screen.getByRole('list', { name: 'Resumen personal' })).getByText('Última frecuencia cardíaca').closest('li'))
      .toHaveTextContent(/76 lpm.*DEMO/);
    expect(screen.queryByText('Todavía no hay mediciones recientes.')).not.toBeInTheDocument();
  });

  it('sin ninguna medición guardada no dice que hay pruebas disponibles', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    renderAt('/app/mediciones');
    expect(await screen.findByText('Todavía no guardaste ninguna medición.')).toBeInTheDocument();
    expect(screen.getByText(/Todavía no hay mediciones experimentales/)).toBeInTheDocument();
    expect(screen.queryByText(/mediciones de prueba disponibles/)).not.toBeInTheDocument();
  });
});

describe('Mediciones: historial completo', () => {
  it('pide al backend los filtros elegidos', async () => {
    const { calls } = routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements': () => jsonResponse(200, EMPTY),
      'GET /measurements/statistics': () => jsonResponse(200, NO_STATS),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/historial');
    await screen.findByText('Todavía no hiciste ninguna medición.');
    expect(screen.getByRole('link', { name: /Mi dashboard/ })).toHaveAttribute('href', '/app/mediciones'); // regreso claro
    await user.selectOptions(screen.getByLabelText('Estado'), 'COMPLETADA');
    await user.selectOptions(screen.getByLabelText('Modo'), 'GLUCOSA_EXPERIMENTAL');
    await user.selectOptions(screen.getByLabelText('Orden'), 'asc');
    await user.type(screen.getByLabelText('Desde'), '2026-10-01');
    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === 'GET /measurements').at(-1).url);
      expect(Object.fromEntries(last.searchParams)).toMatchObject({
        estado: 'COMPLETADA', modo: 'GLUCOSA_EXPERIMENTAL', orden: 'asc', desde: '2026-10-01', pagina: '1',
      });
    }, { timeout: 5000 });
    expect(await screen.findByText('No hay mediciones que coincidan con los filtros.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Limpiar filtros/ }));
    expect(screen.getByLabelText('Estado')).toHaveValue('');
  });

  it('una respuesta lenta de un filtro anterior no pisa la del filtro actual (condición de carrera)', async () => {
    const base = { idMedicion: 'm-x', fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:00:12', modoMedicion: 'OXIMETRIA',
      condicionComida: 'AYUNO', edadAlMomento: 36, glucosaEstimada: null, spo2: '98.00', frecuenciaCardiaca: 70, calidadSenal: null, observacion: null,
      dispositivo: 'ARD-001', origenGlucosa: null, glucosaDispositivo: null, indiceOptico: null, esDemo: false };
    const all = { items: [{ ...base, idMedicion: 'm-todas', estadoMedicion: 'COMPLETADA', frecuenciaCardiaca: 71 }], total: 1, pagina: 1, tamanioPagina: 10 };
    const cancelled = { items: [{ ...base, idMedicion: 'm-cancelada', estadoMedicion: 'CANCELADA', frecuenciaCardiaca: 72 }], total: 1, pagina: 1, tamanioPagina: 10 };
    let release;
    const slow = new Promise((resolve) => { release = resolve; });
    let history = 0;
    routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements': (options, url) => {
        history += 1;
        const estado = new URL(url).searchParams.get('estado');
        if (estado === 'COMPLETADA') return slow.then(() => jsonResponse(200, all)); // la consulta ANTERIOR llega tarde
        return jsonResponse(200, estado === 'CANCELADA' ? cancelled : all);
      },
      'GET /measurements/statistics': () => jsonResponse(200, NO_STATS),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/historial');
    await screen.findByRole('list', { name: 'Mediciones' });
    await user.selectOptions(screen.getByLabelText('Estado'), 'COMPLETADA');   // consulta lenta
    await user.selectOptions(screen.getByLabelText('Estado'), 'CANCELADA');    // consulta nueva, rápida
    await waitFor(() => expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/app/mediciones/m-cancelada'));
    release();                                                                  // llega tarde la respuesta de COMPLETADA
    await new Promise((resolve) => { setTimeout(resolve, 100); });
    expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/app/mediciones/m-cancelada'); // no la pisa
    expect(history).toBeGreaterThanOrEqual(3);
  });

  it('cada medición es una tarjeta con su estado, valores y un «Ver detalle» separado de la eliminación de pruebas', async () => {
    const item = { idMedicion: 'm-5', fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:00:12', modoMedicion: 'OXIMETRIA',
      estadoMedicion: 'COMPLETADA', condicionComida: 'AYUNO', edadAlMomento: 36, glucosaEstimada: null, spo2: '98.00', frecuenciaCardiaca: 70,
      calidadSenal: null, observacion: null, dispositivo: 'ARD-001', origenGlucosa: 'EXPERIMENTAL', glucosaDispositivo: '101.00', indiceOptico: '2.1', esDemo: false };
    const demo = { ...item, idMedicion: 'm-6', origenGlucosa: 'DEMO', glucosaDispositivo: '114.00', esDemo: true };
    routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements': jsonResponse(200, { items: [item, demo], total: 2, pagina: 1, tamanioPagina: 10 }),
      'GET /measurements/statistics': jsonResponse(200, NO_STATS),
    });
    renderAt('/app/mediciones/historial');
    const rows = within(await screen.findByRole('list', { name: 'Mediciones' })).getAllByRole('listitem');
    expect(within(rows[0]).getByText('EXPERIMENTAL')).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent('Completada');
    expect(within(rows[0]).getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/app/mediciones/m-5');
    expect(within(rows[1]).getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/app/mediciones/m-6');
    expect(within(rows[1]).getByText('DEMO')).toBeInTheDocument();
    // La eliminación de pruebas es otra acción, fuera de las tarjetas.
    expect(within(rows[1]).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Eliminar mis datos de prueba/ })).toBeInTheDocument();
  });
});

describe('Mediciones: configuración de perfil', () => {
  it('sin fecha de nacimiento ni sexo muestra «Sin informar» y el aviso informativo, y permite volver al dashboard', async () => {
    routes({
      'GET /measurements/profile': jsonResponse(200, { ...OWN_PROFILE, fechaNacimiento: null, edad: null, sexoModelo: null,
        datosRecomendados: ['fechaNacimiento', 'sexo'] }),
    });
    renderAt('/app/mediciones/perfil');
    const profile = (await screen.findByRole('heading', { name: 'Mi perfil de medición' })).closest('section');
    expect(within(profile).getAllByText('Sin informar')).toHaveLength(4); // edad, fecha de nacimiento, sexo y última medición
    expect(within(profile).getByText('Sexo biológico')).toBeInTheDocument();
    const notice = document.getElementById('datos-recomendados');
    expect(notice).toHaveTextContent(NOTICE);
    expect(notice).toHaveAttribute('role', 'status'); // informativo, nunca un error
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Mi dashboard/ })).toHaveAttribute('href', '/app/mediciones');
  });

  it('con los datos completos muestra edad, fecha, sexo y última medición, sin recomendación', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, { ...OWN_PROFILE, fechaUltimaMedicion: '2026-10-07T08:30:00', datosRecomendados: [] }) });
    renderAt('/app/mediciones/perfil');
    const profile = (await screen.findByRole('heading', { name: 'Mi perfil de medición' })).closest('section');
    expect(within(profile).getByText('36 años')).toBeInTheDocument();
    expect(within(profile).getByText('17/05/1990')).toBeInTheDocument();
    expect(within(profile).getByText('Femenino')).toBeInTheDocument();
    expect(within(profile).getByText('07/10/2026 08:30')).toBeInTheDocument();
    expect(document.getElementById('datos-recomendados')).toBeNull();
  });

  it('«Editar datos» reutiliza el perfil de usuario y recarga el perfil de medición', async () => {
    let current = { ...OWN_PROFILE, fechaNacimiento: null, edad: null, sexoModelo: null, datosRecomendados: ['fechaNacimiento', 'sexo'] };
    const { calls } = routes({
      'GET /measurements/profile': () => jsonResponse(200, current),
      'PATCH /auth/me/profile': () => {
        current = { ...OWN_PROFILE, datosRecomendados: [] };
        return jsonResponse(200, { ...ACCOUNT, actualizado: true });
      },
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar datos' }));
    await user.type(await screen.findByLabelText('Fecha de nacimiento'), '1990-05-17');
    await user.selectOptions(screen.getByLabelText('Sexo'), 'FEMENINO');
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }));
    await waitFor(() => expect(calls.some((call) => call.key === 'PATCH /auth/me/profile')).toBe(true));
    expect(calls.find((call) => call.key === 'PATCH /auth/me/profile').body).toEqual({ fechaNacimiento: '1990-05-17', sexo: 'FEMENINO' });
    const profile = (await screen.findByRole('heading', { name: 'Mi perfil de medición' })).closest('section');
    expect(await within(profile).findByText('36 años')).toBeInTheDocument(); // la edad se recalcula desde la fecha
  });
});

describe('Detalle y estados de una medición', () => {
  function open(measurement, extra = {}) {
    return routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, measurement), ...extra });
  }

  it('una medición completada muestra datos generales y resultados, sin sección de contexto', async () => {
    open(detail({
      estadoMedicion: 'COMPLETADA', fechaHoraFin: '2026-10-08T09:01:00', duracionMs: 60000, spo2: '97.50',
      frecuenciaCardiaca: 72, calidadSenal: '0.900', versionAlgoritmo: 'oxi-1', cantidadMuestras: 120, puedeOperar: false,
    }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const results = within(await screen.findByLabelText('Resultados'));
    expect(results.getByText('97,5 %')).toBeInTheDocument();
    expect(results.getByText('72 lpm')).toBeInTheDocument();
    expect(results.queryByText('Glucosa estimada (experimental)')).not.toBeInTheDocument();
    expect(within(screen.getByLabelText('Datos generales de la medición')).getByText('Oxímetro · OXI-001')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Contexto de la medición' })).not.toBeInTheDocument(); // sin sección de contexto
    expect(screen.queryByRole('button', { name: /Cancelar medición/ })).not.toBeInTheDocument();
  });

  it('el detalle ocupa la pantalla con tarjetas grandes, identifica la glucosa DEMO como sintética y permite volver', async () => {
    open(detail({
      estadoMedicion: 'COMPLETADA', fechaHoraFin: '2026-10-08T09:00:12', duracionMs: 12000, spo2: '99.65', frecuenciaCardiaca: 76,
      versionAlgoritmo: 'firmware-v1', origenGlucosa: 'DEMO', glucosaDispositivo: '114.00', unidadGlucosa: 'mg/dL', indiceOptico: '2.41492',
      lecturasEstabilizadas: 8, esDemo: true, puedeEliminar: false, puedeOperar: false, edadAlMomento: null, sexoModelo: null,
      minutosDesdeUltimaComida: 95, fechaHoraUltimaComida: '2026-10-08T07:25:00', observacion: 'Después del desayuno',
    }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByRole('heading', { name: 'Detalle de medición' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Volver al historial/ })).toHaveAttribute('href', '/app/mediciones/historial');
    expect(screen.getByRole('link', { name: 'Volver a mi dashboard' })).toHaveAttribute('href', '/app/mediciones');
    const overview = within(await screen.findByLabelText('Datos generales de la medición'));
    expect(overview.getByText('Mi perfil')).toBeInTheDocument();
    expect(overview.getByText('Oxímetro · OXI-001')).toBeInTheDocument();
    const results = within(screen.getByLabelText('Resultados'));
    expect(results.getByText('76 lpm')).toBeInTheDocument();
    expect(results.getByText('99,7 %')).toBeInTheDocument();
    expect(results.getByText(/Glucosa \(valor DEMO, sintético\)/)).toBeInTheDocument();
    expect(results.getByText(/no es una glucemia real/)).toBeInTheDocument();
    expect(screen.getByText(/no hay una evolución temporal para graficar/)).toBeInTheDocument(); // sin series guardadas: no se inventa
    expect(screen.queryByLabelText('Contexto de la medición')).not.toBeInTheDocument();
  });

  it('la cuenta individual puede enviarse el resultado por correo con un botón', async () => {
    const { calls } = open(detail({ estadoMedicion: 'COMPLETADA', spo2: '97.50', puedeOperar: false, envioResultado: 'CUENTA_PROPIA' }), {
      [`POST /measurements/${MEASUREMENT_ID}/send-result`]: jsonResponse(200, { estadoEnvio: 'ENVIADO', correoEnmascarado: 'v***@example.com', mensaje: 'Enviamos el resultado por correo electrónico.' }),
    });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    await userEvent.click(await screen.findByRole('button', { name: /Enviarme el resultado por correo/ }));
    expect(await screen.findByText(/Enviamos el resultado por correo electrónico/)).toBeInTheDocument();
    expect(calls.find((call) => call.key.endsWith('/send-result')).body).toEqual({});
  });

  it('para un paciente se pide el correo y la autorización antes de enviar', async () => {
    const { calls } = open(detail({ estadoMedicion: 'COMPLETADA', spo2: '97.50', puedeOperar: false, envioResultado: 'PACIENTE' }), {
      [`POST /measurements/${MEASUREMENT_ID}/send-result`]: jsonResponse(200, { estadoEnvio: 'ENVIADO', correoEnmascarado: 'r***@example.com', mensaje: 'Enviamos el resultado por correo electrónico.' }),
    });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const send = await screen.findByRole('button', { name: /Enviar resultado al paciente/ });
    await userEvent.click(send);
    expect(await screen.findByText(/confirmá que autorizó/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.endsWith('/send-result'))).toBe(false);
    await userEvent.type(screen.getByLabelText('Correo del paciente'), 'rosa@example.com');
    await userEvent.click(screen.getByLabelText(/El paciente autorizó/));
    await userEvent.click(send);
    expect(await screen.findByText(/Enviamos el resultado/)).toBeInTheDocument();
    expect(calls.find((call) => call.key.endsWith('/send-result')).body).toEqual({ correoDestino: 'rosa@example.com', pacienteAutoriza: true });
  });

  it('sin permiso de envío no se ofrece el botón', async () => {
    open(detail({ estadoMedicion: 'COMPLETADA', spo2: '97.50', puedeOperar: false, envioResultado: null }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    await screen.findByLabelText('Resultados');
    expect(screen.queryByRole('button', { name: /resultado/i })).not.toBeInTheDocument();
  });

  it('una medición inválida no se presenta como resultado', async () => {
    open(detail({ estadoMedicion: 'INVALIDA', fechaHoraFin: '2026-10-08T09:01:00', observacion: 'El procesamiento no entregó SpO₂ y frecuencia cardíaca.', puedeOperar: false }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText(/La medición no es válida y no se usa como resultado/)).toBeInTheDocument();
    expect(screen.getByText(/no entregó SpO₂/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Resultados')).not.toBeInTheDocument();
  });

  it('el detalle muestra «Sin informar» cuando no hay última comida y la hora cuando sí se informó', async () => {
    open(detail({ modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'INVALIDA', fechaHoraFin: '2026-10-08T09:00:12', condicionComida: 'POSTPRANDIAL', fechaHoraUltimaComida: null,
      observacion: 'Estimación de glucosa no disponible por falta de información: no se indicó la hora de la última comida.', puedeOperar: false }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const overview = within(await screen.findByLabelText('Datos generales de la medición'));
    expect(overview.getByText('Última comida').closest('div')).toHaveTextContent('Sin informar');
    expect(overview.getByText('Alimentación').closest('div')).toHaveTextContent('Después de comer');
  });

  it('glucosa inválida por falta de algoritmo no muestra ningún valor estimado', async () => {
    open(detail({
      modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'INVALIDA', puedeOperar: false,
      observacion: 'El algoritmo de estimación de glucosa todavía no está disponible: no se generó ningún valor.',
      matriz: { idMatriz: 'mx', nombre: 'Matriz experimental', version: 'v1' },
    }));
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText(/no se generó ningún valor/)).toBeInTheDocument();
    expect(screen.queryByText(/Glucosa estimada \(experimental\)/)).not.toBeInTheDocument();
    expect(screen.getByText(/Matriz experimental, versión v1/)).toBeInTheDocument();
  });

  it('cancela una medición en curso con confirmación', async () => {
    const { calls } = open(detail(), {
      [`POST /measurements/${MEASUREMENT_ID}/cancel`]: jsonResponse(200, detail({ estadoMedicion: 'CANCELADA', fechaHoraFin: '2026-10-08T09:00:30' })),
    });
    const user = userEvent.setup();
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    await user.click(await screen.findByRole('button', { name: /Cancelar medición/ }));
    expect(calls.some((call) => call.key.endsWith('/cancel'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar cancelación' }));
    expect(await screen.findByText(/La medición se canceló: no tiene resultados/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancelar medición/ })).not.toBeInTheDocument();
  });

  it('una medición que no es de la cuenta se informa sin datos', async () => {
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(404, { codigo: 'MEDICION_NO_ENCONTRADA', detail: 'No encontramos esa medición.' }) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText('No encontramos esa medición.')).toBeInTheDocument();
  });

  it('registra la referencia capilar solo sobre una glucosa completada y la muestra separada', async () => {
    const completed = detail({
      modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'COMPLETADA', glucosaEstimada: '92.40', versionAlgoritmo: 'g-1',
      fechaHoraFin: '2026-10-08T09:01:00', puedeOperar: true,
    });
    const reference = {
      idMedicionReferencia: 'r-1', idMedicion: MEASUREMENT_ID, glucosaReferencia: '101.00',
      fechaHoraReferencia: '2026-10-08T09:05:00', marcaGlucometro: 'OneTouch', modeloGlucometro: null, observacion: null,
    };
    const { calls } = open(completed, {
      [`POST /measurements/${MEASUREMENT_ID}/capillary-reference`]: jsonResponse(201, { ...completed, referenciaCapilar: reference }),
    });
    const user = userEvent.setup();
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const form = await screen.findByRole('form', { name: 'Registrar referencia capilar' });
    expect(screen.getByText('92,4 mg/dL')).toBeInTheDocument(); // estimada, aparte de la referencia
    await user.click(within(form).getByRole('button', { name: 'Registrar referencia' }));
    expect(within(form).getByText(/Ingresá el valor medido con el glucómetro/)).toBeInTheDocument();
    await user.type(within(form).getByLabelText('Glucosa capilar (mg/dL)'), '101');
    await user.type(within(form).getByLabelText('Fecha y hora de la referencia'), '2026-10-08T09:05');
    await user.type(within(form).getByLabelText('Marca del glucómetro (opcional)'), 'OneTouch');
    await user.click(within(form).getByRole('button', { name: 'Registrar referencia' }));
    expect(await screen.findByLabelText('Referencia capilar')).toHaveTextContent('101 mg/dL');
    expect(calls.find((call) => call.key.endsWith('/capillary-reference')).body).toEqual({
      glucosaReferencia: '101', fechaHoraReferencia: '2026-10-08T09:05:00', marcaGlucometro: 'OneTouch',
    });
    expect(screen.getByText('92,4 mg/dL')).toBeInTheDocument(); // la estimación no cambió
  });
});

describe('Pacientes institucionales', () => {
  const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
  const ID = '9a000000-0000-4000-8000-000000000001';
  const BASE = `/institutions/${ID}`;
  const OPERADOR = ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'];
  const institution = (rol = 'OPERADOR') => ({
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: OPERADOR, tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 0, cantidadOperadores: 1, cantidadPacientes: 1,
  });
  const patient = (overrides = {}) => ({
    idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', nombre: 'Juan', apellido: 'Pérez', dni: null,
    fechaNacimiento: '1980-01-02', edad: 46, sexoModelo: 'MASCULINO', estado: 'ACTIVO', fechaCreacion: '2026-10-03T09:00:00',
    fechaUltimaMedicion: null, fechaExpiracionDatosPersonales: null,
    responsable: { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz', activo: true }, puedeModificar: true, esMio: true, medicionesAutorizadas: true,
    ...overrides,
  });

  // El flujo de medición institucional (datos del paciente, configuración, señal y guardado) se prueba en institutions/patients/PatientMeasure.test.jsx.

  it('quien no es el responsable no puede iniciar mediciones', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
      [`GET ${BASE}`]: jsonResponse(200, institution()),
      [`GET ${BASE}/patients/p-1`]: jsonResponse(200, patient({ puedeModificar: false })),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1/medir`);
    expect(await screen.findByText(/Solo el operador responsable del paciente puede iniciar mediciones/)).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('GET /measurements'))).toBe(false);
  });

  it('el detalle del paciente ofrece «Nueva medición» al responsable y el historial enlaza al detalle', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL),
      [`GET ${BASE}`]: jsonResponse(200, institution()),
      [`GET ${BASE}/patients/p-1`]: jsonResponse(200, patient()),
      [`GET ${BASE}/patients/assignable-operators`]: jsonResponse(200, []),
      [`GET ${BASE}/patients/p-1/measurements`]: jsonResponse(200, {
        items: [{ idMedicion: 'm-7', fechaHoraInicio: '2026-10-07T08:30:00', fechaHoraFin: null, modoMedicion: 'OXIMETRIA',
          estadoMedicion: 'CANCELADA', condicionComida: 'AYUNO', edadAlMomento: 46, glucosaEstimada: null, spo2: null,
          frecuenciaCardiaca: null, calidadSenal: null, observacion: null, dispositivo: 'OXI-001' }],
        total: 1, pagina: 1, tamanioPagina: 10,
      }),
      [`GET ${BASE}/patients/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/p-1`);
    expect(await screen.findByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/p-1/medir`);
    const row = within(await screen.findByRole('list', { name: 'Mediciones' })).getByRole('listitem');
    expect(row).toHaveTextContent('Sin resultado válido.'); // una cancelada no se muestra como resultado
    expect(within(row).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/p-1/mediciones/m-7`);
  });
});


describe('Autorización para almacenar mediciones experimentales', () => {
  function pending(extra = {}) {
    return routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements': jsonResponse(200, EMPTY),
      'GET /measurements/devices': jsonResponse(200, []),
      'GET /auth/consents': jsonResponse(200, CONSENTS_PENDING),
      ...extra,
    });
  }

  it('vive en Configuración de perfil: explica la finalidad y permite rechazar', async () => {
    const { calls } = pending();
    const user = userEvent.setup();
    renderAt('/app/mediciones/perfil');
    expect(await screen.findByRole('heading', { name: 'Autorización para almacenar tus mediciones' })).toBeInTheDocument();
    expect(screen.getByText(/exclusivamente académica y experimental/)).toBeInTheDocument();
    expect(screen.getByText(/No forman parte de\s+una historia clínica/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'No autorizo' }));
    expect(screen.getByText(/No autorizaste el almacenamiento: no se recolectará ninguna medición/)).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'PUT /auth/consents/datos-experimentales')).toBe(false);
  });

  it('sin autorización «Nueva medición» no ofrece medir y remite a la configuración', async () => {
    pending();
    renderAt('/app/mediciones/nueva');
    expect(await screen.findByText(/necesitamos tu autorización para almacenar mediciones experimentales/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configuración de perfil' })).toHaveAttribute('href', '/app/mediciones/perfil');
    expect(screen.queryByRole('button', { name: 'Iniciar medición' })).not.toBeInTheDocument();
    expect(screen.getByRole('note', { name: 'Aviso de uso experimental' })).toBeInTheDocument();
  });

  it('autorizar la registra en el backend; revocar vuelve a pedirla y explica qué pasa con lo medido', async () => {
    const accepted = { ...CONSENTS_PENDING, DATOS_EXPERIMENTALES: { ...CONSENTS_PENDING.DATOS_EXPERIMENTALES, aceptado: true, estado: 'ACEPTADO' } };
    const { calls } = pending({
      'PUT /auth/consents/datos-experimentales': [jsonResponse(200, accepted), jsonResponse(200, CONSENTS_PENDING)],
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/perfil');
    await user.click(await screen.findByRole('button', { name: 'Autorizo el almacenamiento' }));
    expect(calls.find((call) => call.key === 'PUT /auth/consents/datos-experimentales').body).toEqual({ acepta: true });
    expect(await screen.findByText(/no se iniciarán nuevas mediciones/)).toBeInTheDocument();
    expect(screen.getByText(/lo ya medido se conserva/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Revocar autorización' }));
    expect(await screen.findByRole('button', { name: 'Autorizo el almacenamiento' })).toBeInTheDocument();
    expect(calls.filter((call) => call.key === 'PUT /auth/consents/datos-experimentales').map((call) => call.body)).toEqual([
      { acepta: true }, { acepta: false },
    ]);
  });
});


describe('Información sobre tus mediciones y conservación', () => {
  it('es un apartado plegado que explica los seis estados, la conservación y mantiene el aviso experimental', async () => {
    routes({ 'GET /measurements/profile': jsonResponse(200, OWN_PROFILE) });
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const summary = await screen.findByText('Información sobre tus mediciones');
    const details = summary.closest('details');
    expect(details).not.toHaveAttribute('open'); // discreto: no sobrecarga el dashboard
    await user.click(summary);
    expect(details).toHaveAttribute('open');
    const table = within(details).getByRole('table');
    for (const [state, rule] of [['Pendiente', 'Temporal'], ['Adquiriendo', 'Temporal'], ['Procesando', 'Temporal'],
      ['Completada', 'Permanece en el historial'], ['Cancelada', 'Se oculta después de 30 minutos'], ['Inválida', 'Se oculta después de 30 minutos']]) {
      expect(within(table).getByRole('rowheader', { name: state }).closest('tr')).toHaveTextContent(rule);
    }
    expect(within(details).getByText(/Las mediciones completadas permanecen disponibles en tu historial\. Las mediciones canceladas, inválidas o interrumpidas se ocultan automáticamente después de 30 minutos\. El sistema conserva únicamente la información técnica necesaria para auditoría, sin identificar personalmente al usuario\./)).toBeInTheDocument();
    expect(within(details).getByRole('note', { name: 'Aviso de uso experimental' })).toBeInTheDocument();
  });

  it('una medición cancelada recién cerrada avisa hasta cuándo se ve y se vuelve a consultar sola', async () => {
    const cancelled = { idMedicion: 'm-c', fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: '2026-10-08T09:01:00', modoMedicion: 'OXIMETRIA',
      estadoMedicion: 'CANCELADA', condicionComida: 'AYUNO', edadAlMomento: null, glucosaEstimada: null, spo2: null, frecuenciaCardiaca: null,
      calidadSenal: null, observacion: null, dispositivo: 'ARD-001', visibleHasta: '2026-10-08T09:31:00' };
    routes({
      'GET /measurements/profile': jsonResponse(200, OWN_PROFILE),
      'GET /measurements': jsonResponse(200, { items: [cancelled], total: 1, pagina: 1, tamanioPagina: 10 }),
      'GET /measurements/statistics': jsonResponse(200, NO_STATS),
    });
    renderAt('/app/mediciones/historial');
    const row = within(await screen.findByRole('list', { name: 'Mediciones' })).getByRole('listitem');
    expect(row).toHaveTextContent('Cancelada');
    expect(row).toHaveTextContent('Temporal: se oculta del historial a las 09:31');
    expect(within(row).getByRole('link', { name: 'Ver detalle' })).toBeInTheDocument();
  });

  it('el detalle de una medición cancelada explica que es temporal', async () => {
    routes({
      [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, detail({ estadoMedicion: 'CANCELADA', puedeOperar: false, visibleHasta: '2026-10-08T09:31:00' })),
    });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText(/son temporales: esta se oculta de tu historial a las 09:31/)).toBeInTheDocument();
  });

  it('una medición oculta responde como inexistente (no se recupera por URL)', async () => {
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(404, { codigo: 'MEDICION_NO_ENCONTRADA', detail: 'No se encontró la medición.' }) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByLabelText('Resultados')).not.toBeInTheDocument();
  });
});


describe('Detalle de glucosa experimental: matriz de referencia', () => {
  const rule = (extra) => ({ idRegla: `r-${extra.sexoModelo}`, codigo: extra.sexoModelo === 'FEMENINO' ? 'F1' : 'M1', edadDesde: 18, edadHasta: 80,
    condicionComida: 'AYUNO', minutosComidaMin: null, minutosComidaMax: null, ...extra });
  const female = rule({ sexoModelo: 'FEMENINO', glucosaMinReferencia: 70, glucosaMaxReferencia: 105 });
  const male = rule({ sexoModelo: 'MASCULINO', glucosaMinReferencia: 75, glucosaMaxReferencia: 115 });
  const reference = (extra = {}) => ({
    estado: 'REFERENCIA', matriz: { idMatriz: 'mx', nombre: 'Matriz experimental', version: '1', ambito: 'GLOBAL' }, valor: 108, unidad: 'mg/dL',
    origen: 'EXPERIMENTAL', esDemo: false, sexoInformado: false, edadInformada: true, sexoModelo: null, edad: 40, condicionComida: 'AYUNO',
    minutosDesdeUltimaComida: null, avisoSexo: 'El sexo no fue informado. Se muestran ambas referencias únicamente para consulta. Ninguna se asigna automáticamente a tu perfil ni se utiliza como resultado personalizado.',
    grupos: [
      { sexoModelo: 'FEMENINO', titulo: 'Referencia femenina', reglas: [female], reglaSeleccionada: female, posicion: 'POR_ENCIMA', aplicada: false, motivoSinSeleccion: null },
      { sexoModelo: 'MASCULINO', titulo: 'Referencia masculina', reglas: [male], reglaSeleccionada: male, posicion: 'DENTRO', aplicada: false, motivoSinSeleccion: null },
    ], ...extra,
  });
  const glucoseDetail = (ref, extra = {}) => detail({
    modoMedicion: 'GLUCOSA_EXPERIMENTAL', estadoMedicion: 'COMPLETADA', fechaHoraFin: '2026-10-08T09:01:00', duracionMs: 60000, spo2: '97.50',
    frecuenciaCardiaca: 72, origenGlucosa: 'EXPERIMENTAL', glucosaDispositivo: '108.00', unidadGlucosa: 'mg/dL', indiceOptico: '2.1', lecturasEstabilizadas: 8,
    puedeOperar: false, referenciaGlucosa: ref, ...extra,
  });

  it('muestra primero los resultados y debajo la matriz con las dos referencias por sexo cuando el sexo no se informó', async () => {
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, glucoseDetail(reference())) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const results = await screen.findByLabelText('Resultados');
    const panel = within(await screen.findByRole('region', { name: 'Matriz de referencia de glucosa' }));
    expect(results.compareDocumentPosition(panel.getByRole('heading', { name: /Matriz de referencia de glucosa/ })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(results).getAllByRole('listitem')[0]).toHaveTextContent('Glucosa experimental del dispositivo'); // la glucosa va primero
    expect(panel.getByText('Matriz experimental, versión 1')).toBeInTheDocument(); // solo el nombre y la versión de la matriz
    expect(panel.queryByText('Global de GlucoLume')).not.toBeInTheDocument();
    // Los cuatro datos que se tienen en cuenta para elegir la regla.
    const facts = within(panel.getByRole('list', { name: 'Datos que se tienen en cuenta para las reglas' }));
    expect(facts.getByText('Glucosa obtenida').closest('li')).toHaveTextContent('108 mg/dL');
    expect(facts.getByText('Edad utilizada').closest('li')).toHaveTextContent('40 años');
    expect(facts.getByText('Sexo utilizado').closest('li')).toHaveTextContent('No informado');
    expect(facts.getByText('Alimentación').closest('li')).toHaveTextContent('En ayunas');
    expect(panel.getByText(/se consulta para comparar el resultado; no participó en ningún cálculo/)).toBeInTheDocument();
    expect(panel.getByText(/El sexo no fue informado\. Se muestran ambas referencias únicamente para consulta\. Ninguna se asigna automáticamente a tu perfil ni se utiliza como resultado personalizado\./)).toBeInTheDocument();
    // Botones para elegir qué referencia ver: una por vez.
    const user = userEvent.setup();
    expect(panel.getByRole('tab', { name: 'Referencia femenina' })).toHaveAttribute('aria-selected', 'true');
    const female = within(panel.getByRole('article', { name: 'Referencia femenina' }));
    expect(female.getByText('70–105 mg/dL')).toBeInTheDocument();
    expect(female.getByText('Por encima del intervalo configurado')).toBeInTheDocument();
    expect(female.getByRole('img', { name: /intervalo 70 a 105 mg\/dL/ })).toBeInTheDocument();
    expect(panel.queryByRole('article', { name: 'Referencia masculina' })).not.toBeInTheDocument();
    await user.click(panel.getByRole('tab', { name: 'Referencia masculina' }));
    const male = within(panel.getByRole('article', { name: 'Referencia masculina' }));
    expect(male.getByText('75–115 mg/dL')).toBeInTheDocument();
    expect(male.getByText('Dentro del intervalo configurado')).toBeInTheDocument();
    expect(panel.getAllByText(/no una clasificación clínica/).length).toBe(1);
    expect(panel.queryByText(/diabetes|hipoglucemia/i)).not.toBeInTheDocument();
  });

  it('sin edad no asigna un intervalo ficticio: lista las reglas disponibles con sus rangos', async () => {
    const noAge = reference({ edad: null, edadInformada: false, grupos: ['FEMENINO', 'MASCULINO'].map((sexo) => ({
      sexoModelo: sexo, titulo: sexo === 'FEMENINO' ? 'Referencia femenina' : 'Referencia masculina', reglas: [sexo === 'FEMENINO' ? female : male],
      reglaSeleccionada: null, posicion: null, aplicada: false,
      motivoSinSeleccion: 'La edad no fue informada: no puede seleccionarse una referencia personalizada. Se muestran las reglas disponibles con sus rangos de edad.',
    })) });
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, glucoseDetail(noAge)) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const panel = within(await screen.findByRole('region', { name: 'Matriz de referencia de glucosa' }));
    const femaleGroup = within(panel.getByRole('article', { name: 'Referencia femenina' }));
    expect(femaleGroup.getByText(/no puede seleccionarse una referencia personalizada/)).toBeInTheDocument();
    expect(femaleGroup.getByRole('list', { name: /Reglas disponibles/ })).toHaveTextContent('18–80 años · En ayunas · 70–105 mg/dL');
    expect(femaleGroup.queryByRole('status')).not.toBeInTheDocument(); // sin posición
    expect(panel.getByText('No informada')).toBeInTheDocument();
  });

  it('con el sexo informado muestra una sola referencia y destaca la regla aplicada', async () => {
    const applied = reference({ estado: 'APLICADA', sexoInformado: true, sexoModelo: 'FEMENINO', avisoSexo: null, grupos: [
      { sexoModelo: 'FEMENINO', titulo: 'Referencia femenina', reglas: [female], reglaSeleccionada: female, posicion: 'DENTRO', aplicada: true, motivoSinSeleccion: null }] });
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, glucoseDetail(applied, { glucosaEstimada: '100.00' })) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const panel = within(await screen.findByRole('region', { name: 'Matriz de referencia de glucosa' }));
    expect(panel.getByText(/Matriz aplicada: participó en el cálculo/)).toBeInTheDocument();
    expect(panel.getAllByRole('article')).toHaveLength(1);
    expect(panel.getByText('Regla aplicada')).toBeInTheDocument();
    expect(panel.queryByText(/El sexo no fue informado/)).not.toBeInTheDocument();
  });

  it('un valor DEMO se rotula como simulación y sin matriz dice que la referencia no está disponible', async () => {
    const demoRef = reference({ esDemo: true, origen: 'DEMO' });
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, glucoseDetail(demoRef, { origenGlucosa: 'DEMO', esDemo: true })) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    const panel = within(await screen.findByRole('region', { name: 'Matriz de referencia de glucosa' }));
    expect(panel.getByText(/El valor es DEMO: una simulación del firmware, no la glucosa real de la persona/)).toBeInTheDocument();
    expect(panel.getAllByText(/Comparación ilustrativa con un valor DEMO/).length).toBe(1);
  });

  it('sin matriz muestra «Referencia no disponible» y la oximetría no muestra ninguna matriz', async () => {
    const none = { ...reference(), estado: 'SIN_MATRIZ', matriz: null, grupos: [], avisoSexo: null };
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, glucoseDetail(none)) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    expect(await screen.findByText(/Referencia no disponible: no había una matriz vigente/)).toBeInTheDocument();
  });

  it('una medición de oximetría no muestra una matriz de glucosa aplicada artificialmente', async () => {
    routes({ [`GET /measurements/${MEASUREMENT_ID}`]: jsonResponse(200, detail({ estadoMedicion: 'COMPLETADA', spo2: '97.50', frecuenciaCardiaca: 72, puedeOperar: false })) });
    renderAt(`/app/mediciones/${MEASUREMENT_ID}`);
    await screen.findByLabelText('Resultados');
    expect(screen.queryByRole('region', { name: 'Matriz de referencia de glucosa' })).not.toBeInTheDocument();
  });
});


describe('Rango de edad de una regla de la matriz', () => {
  it('un límite vacío es «sin límite»: nunca se inventa un rango', () => {
    expect(ageText({ edadDesde: null, edadHasta: null })).toBe('Sin rango de edad (cualquier edad)');
    expect(ageText({ edadDesde: 65, edadHasta: null })).toBe('Desde 65 años');
    expect(ageText({ edadDesde: null, edadHasta: 17 })).toBe('Hasta 17 años');
    expect(ageText({ edadDesde: 18, edadHasta: 64 })).toBe('18–64 años');
  });
});
