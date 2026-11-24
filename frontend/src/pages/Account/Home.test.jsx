import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';
import { latestValues } from './home/useHomeData.js';
import { whenText } from './home/HomeParts.jsx';

const point = (id, fecha, extra = {}) => ({
  idMedicion: id, fecha, modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: null, esDemo: false, frecuenciaCardiaca: null, spo2: null, glucosa: null,
  indiceOptico: null, ...extra,
});
const evolution = (puntos) => ({ origen: 'TODOS', desde: '2026-10-08T00:00:00', hasta: null, puntos, truncado: false, estadisticas: { experimental: null, demo: null } });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

describe('Últimos valores de Inicio', () => {
  it('el último valor es el experimental más reciente; si solo hay pruebas, el de la última prueba DEMO identificado como tal', () => {
    const points = [
      point('a', '2026-10-10T09:00:00', { glucosa: 100, spo2: 97, frecuenciaCardiaca: 70 }),
      point('b', '2026-10-12T09:00:00', { glucosa: 110, esDemo: true, origen: 'DEMO', spo2: 99 }),
      point('c', '2026-10-13T09:00:00', { esDemo: true, origen: 'DEMO', frecuenciaCardiaca: 91, indiceOptico: 2.3 }),
    ];
    const latest = latestValues(points);
    expect(latest.glucosa).toEqual({ value: 100, when: '2026-10-10T09:00:00', demo: false }); // la experimental, aunque la DEMO sea más nueva
    expect(latest.spo2.demo).toBe(false);
    expect(latest.frecuenciaCardiaca).toEqual({ value: 70, when: '2026-10-10T09:00:00', demo: false });
    expect(latest.indiceOptico).toEqual({ value: 2.3, when: '2026-10-13T09:00:00', demo: true }); // solo hay prueba: se marca DEMO
    expect(latestValues([]).glucosa).toBeNull();
  });

  it('«Hoy», «Ayer» o la fecha completa según el día de la medición', () => {
    const now = new Date(2026, 9, 15, 12, 0);
    expect(whenText('2026-10-15T15:28:00', now)).toBe('Hoy, 15:28');
    expect(whenText('2026-10-14T09:10:00', now)).toBe('Ayer, 09:10');
    expect(whenText('2026-10-01T09:10:00', now)).toBe('01/10/2026 09:10');
  });
});

describe('Inicio de una cuenta individual', () => {
  function open(latestPoints, chartPoints = latestPoints) {
    return mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'GET /measurements/evolution': [jsonResponse(200, evolution(latestPoints)), jsonResponse(200, evolution(chartPoints)), jsonResponse(200, evolution(chartPoints))],
    });
  }

  it('muestra saludo, fecha, aviso, los cuatro últimos valores con su origen, accesos rápidos', async () => {
    open([point('a', '2026-10-13T09:00:00', { glucosa: 102, spo2: 98.2, frecuenciaCardiaca: 72, indiceOptico: 0.4231 }),
      point('b', '2026-10-14T10:00:00', { glucosa: 113, esDemo: true, origen: 'DEMO' })]);
    renderAt('/app/inicio');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.getByText('Nos alegra verte de nuevo en GlucoLume.')).toBeInTheDocument();
    expect(screen.getByLabelText('Fecha y hora actuales')).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Tu bienestar nos importa' })).toBeInTheDocument();
    const kpis = within(await screen.findByRole('list', { name: 'Últimos valores medidos' }));
    await waitFor(() => expect(kpis.getByText('Última glucosa').closest('li')).toHaveTextContent('102 mg/dL'));
    expect(kpis.getByText('Última glucosa').closest('li')).toHaveTextContent('Experimental'); // la DEMO más nueva no pisa la experimental
    expect(kpis.getByText('Última frecuencia cardíaca').closest('li')).toHaveTextContent('72 lpm');
    expect(kpis.getByText('Última SpO₂').closest('li')).toHaveTextContent('98,2 %');
    expect(kpis.queryByText('Último índice óptico')).not.toBeInTheDocument(); // la tarjeta de índice óptico ya no se muestra
    expect(screen.queryByRole('list', { name: 'Accesos rápidos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Consejos para diabéticos' })).not.toBeInTheDocument();
  });

  it('sin mediciones no muestra ceros: dice «Sin datos» y ofrece hacer una medición', async () => {
    open([]);
    renderAt('/app/inicio');
    const kpis = within(await screen.findByRole('list', { name: 'Últimos valores medidos' }));
    await waitFor(() => expect(kpis.getAllByText('Sin datos')).toHaveLength(3)); // glucosa, frecuencia y SpO₂
    expect(kpis.queryByText(/^0\b/)).not.toBeInTheDocument();
    // Dos secciones vacías: la evolución y «Cómo fueron tus mediciones».
    expect(await screen.findAllByText('No hay mediciones en este período.')).toHaveLength(2);
  });

  it('la glucosa experimental de Inicio muestra el semáforo (resumen por color y zona del intervalo)', async () => {
    const referencia = { referenciaMinima: 70, referenciaMaxima: 140 };
    open([point('a', '2026-10-14T09:00:00', { glucosa: 102, semaforo: 'VERDE', ...referencia }),
      point('b', '2026-10-14T13:00:00', { glucosa: 150, semaforo: 'ROJO', ...referencia })]);
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    const legend = await section.findByRole('list', { name: 'Resumen del semáforo' });
    expect(legend).toHaveTextContent('Está bien 1');
    expect(legend).toHaveTextContent('Muy alto 1');
    expect(legend).toHaveTextContent('Revisar 0');
    expect(section.getByText(/Intervalo recomendado: 70–140 mg\/dL/)).toBeInTheDocument();
  });

  it('«Cómo fueron tus mediciones» muestra el semáforo en dona y el promedio de glucosa experimental del período', async () => {
    const referencia = { referenciaMinima: 70, referenciaMaxima: 140 };
    open([point('a', '2026-10-14T09:00:00', { glucosa: 100, semaforo: 'VERDE', ...referencia }),
      point('b', '2026-10-14T13:00:00', { glucosa: 110, semaforo: 'AMARILLO', ...referencia }),
      point('c', '2026-10-14T20:00:00', { glucosa: 150, esDemo: true, origen: 'DEMO', semaforo: 'ROJO', ...referencia })]);
    renderAt('/app/inicio');
    const mix = within(await screen.findByRole('region', { name: 'Cómo fueron tus mediciones' }));
    expect(await mix.findByRole('img', { name: 'Semáforo de glucosa: 3 en total' })).toBeInTheDocument();
    expect(mix.getByRole('article', { name: 'Promedio de glucosa del período' })).toHaveTextContent('120 mg/dL'); // todas las mediciones, DEMO incluida
  });

  it('«Cómo fueron tus mediciones» también muestra el promedio de frecuencia cardíaca y de SpO₂ del período', async () => {
    open([point('a', '2026-10-14T09:00:00', { frecuenciaCardiaca: 70, spo2: 97 }),
      point('b', '2026-10-14T13:00:00', { frecuenciaCardiaca: 80, spo2: 99 })]);
    renderAt('/app/inicio');
    const mix = within(await screen.findByRole('region', { name: 'Cómo fueron tus mediciones' }));
    await waitFor(() => expect(mix.getByRole('article', { name: 'Promedio de frecuencia cardíaca del período' })).toHaveTextContent('75 lpm'));
    expect(mix.getByRole('article', { name: 'Promedio de frecuencia cardíaca del período' })).toHaveTextContent('Promedio de frecuencia cardíaca');
    expect(mix.getByRole('article', { name: 'Promedio de SpO₂ del período' })).toHaveTextContent('98 %');
  });

  it('el gráfico de glucosa se puede acercar y volver a la vista completa', async () => {
    open([point('a', '2026-10-14T09:00:00', { glucosa: 100 }), point('b', '2026-10-14T13:00:00', { glucosa: 104 })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    await user.click(await section.findByRole('button', { name: 'Acercar gráfico' }));
    expect(section.getByText('Zoom 2×')).toBeInTheDocument();
    await user.click(section.getByRole('button', { name: 'Ver todo' }));
    expect(section.getByText('Vista completa')).toBeInTheDocument();
  });

  it('al elegir un punto del gráfico muestra su detalle (valor, fecha, hora y origen) y permite volver', async () => {
    open([point('a', '2026-10-14T09:00:00', { glucosa: 100 }), point('b', '2026-10-14T13:00:00', { glucosa: 104, esDemo: true, origen: 'DEMO', frecuenciaCardiaca: 75 })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    await user.click(await section.findByRole('button', { name: /: 104 mg\/dL \(DEMO\)$/ }));
    const detail = within(section.getByRole('region', { name: 'Medición seleccionada' }));
    expect(detail.getByText('Glucosa DEMO (simulada)')).toBeInTheDocument();
    expect(detail.getByText('104 mg/dL')).toBeInTheDocument();
    expect(detail.getByText('DEMO (prueba)')).toBeInTheDocument();
    expect(detail.getByText('Frecuencia cardíaca')).toBeInTheDocument(); // los demás valores de la misma medición
    await user.click(section.getByRole('button', { name: 'Volver a la evolución del período' }));
    expect(section.queryByRole('region', { name: 'Medición seleccionada' })).not.toBeInTheDocument();
  });

  it('una prueba DEMO también muestra el semáforo de la matriz vigente', async () => {
    open([point('d', '2026-10-14T09:00:00', { glucosa: 150, esDemo: true, origen: 'DEMO', semaforo: 'ROJO', referenciaMinima: 70, referenciaMaxima: 140 })]);
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    expect(await section.findByRole('list', { name: 'Resumen del semáforo' })).toHaveTextContent('Muy alto 1');
  });

  it('Inicio arriba muestra agrupación y período (sin filtro de origen) y consulta el período elegido', async () => {
    const { calls } = open([point('a', '2026-10-14T09:00:00', { glucosa: 102 })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const filters = within(await screen.findByRole('region', { name: 'Filtros del gráfico' }));
    expect(filters.queryByLabelText('Origen de los datos de la evolución')).not.toBeInTheDocument();
    expect(filters.getByLabelText('Período de la evolución')).toHaveValue('7');
    await user.selectOptions(filters.getByLabelText('Período de la evolución'), '30');
    await waitFor(() => expect(calls.some((call) => new URL(call.url).searchParams.get('dias') === '30')).toBe(true));
  });

  it('permite elegir la variable del gráfico (glucosa, frecuencia, SpO₂) y una vista general', async () => {
    open([point('a', '2026-10-14T09:00:00', { glucosa: 102, frecuenciaCardiaca: 72, spo2: 98, indiceOptico: 0.42 }),
      point('b', '2026-10-14T11:00:00', { frecuenciaCardiaca: 80, esDemo: true, origen: 'DEMO' })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    const tabs = within(section.getByRole('tablist', { name: 'Variable a graficar' }));
    expect(tabs.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Glucosa experimental', 'Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)']); // sin índice óptico ni vista general
    expect(tabs.getByRole('tab', { name: 'Glucosa experimental' })).toHaveAttribute('aria-selected', 'true');
    await user.click(tabs.getByRole('tab', { name: 'Frecuencia cardíaca' }));
    expect(await section.findByRole('group', { name: /Frecuencia cardíaca: 2 puntos/ })).toBeInTheDocument(); // una experimental y una prueba DEMO
  });

  it('cuenta las mediciones por oximetría o glucosa y por condición de comida, por bloque de tiempo', async () => {
    open([
      point('a', '2026-10-14T09:00:00', { modoMedicion: 'OXIMETRIA', condicionComida: 'AYUNO', spo2: 98 }),
      point('b', '2026-10-14T13:00:00', { modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'POSTPRANDIAL', glucosa: 130 }),
      point('c', '2026-10-15T08:00:00', { modoMedicion: 'GLUCOSA_EXPERIMENTAL', condicionComida: 'NO_INFORMADA', glucosa: 95 }),
      point('d', '2026-10-15T20:00:00', { modoMedicion: 'OXIMETRIA', esDemo: true, origen: 'DEMO', spo2: 99 }),
    ]);
    renderAt('/app/inicio');
    const mix = within(await screen.findByRole('region', { name: 'Cómo fueron tus mediciones' }));
    // Tendencia por día (7D): cada medición cuenta una vez; la DEMO también.
    const device = await mix.findByRole('img', { name: 'Oximetría y glucosa: 4 mediciones' });
    expect(device).toBeInTheDocument();
    const legend = device.closest('figure');
    expect(legend).toHaveTextContent('Oximetría: 2');
    expect(legend).toHaveTextContent('Glucosa (experimental): 2');
    const meals = mix.getByRole('img', { name: 'Condición de comida: 4 mediciones' }).closest('figure');
    expect(meals).toHaveTextContent('En ayunas: 1');
    expect(meals).toHaveTextContent('Después de comer: 1');
    expect(meals).toHaveTextContent('Sin informar: 2');
  });

  it('el aviso de bienestar se puede cerrar', async () => {
    open([]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    await user.click(await screen.findByRole('button', { name: 'Cerrar el aviso' }));
    expect(screen.queryByRole('complementary', { name: 'Tu bienestar nos importa' })).not.toBeInTheDocument();
  });
});

describe('Inicio de una cuenta institucional', () => {
  it('no muestra accesos rápidos (están en el menú lateral) ni consulta mediciones propias', async () => {
    const institutional = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    const { calls } = mockApi({ 'GET /auth/me': jsonResponse(200, institutional) });
    renderAt('/app/inicio');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Accesos rápidos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Últimos valores medidos' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /measurements/evolution')).toBe(false);
  });
});
