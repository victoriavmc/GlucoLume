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

  it('muestra saludo, fecha, aviso, los cuatro últimos valores con su origen, accesos rápidos y los consejos', async () => {
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
    expect(kpis.getByText('Último índice óptico').closest('li')).toHaveTextContent('0,4231');
    const shortcuts = within(screen.getByRole('list', { name: 'Accesos rápidos' }));
    expect(shortcuts.getByRole('link', { name: /Ver mis mediciones/ })).toHaveAttribute('href', '/app/mediciones');
    expect(shortcuts.getByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', '/app/mediciones/nueva');
    expect(shortcuts.getByRole('link', { name: /Ir a mi grupo/ })).toHaveAttribute('href', '/app/grupo');
    expect(shortcuts.getByRole('link', { name: /Configurar perfil/ })).toHaveAttribute('href', '/app/perfil');
    expect(screen.getByRole('region', { name: 'Consejos para diabéticos' })).toBeInTheDocument();
  });

  it('sin mediciones no muestra ceros: dice «Sin datos» y ofrece hacer una medición', async () => {
    open([]);
    renderAt('/app/inicio');
    const kpis = within(await screen.findByRole('list', { name: 'Últimos valores medidos' }));
    await waitFor(() => expect(kpis.getAllByText('Sin datos')).toHaveLength(4));
    expect(kpis.queryByText(/^0\b/)).not.toBeInTheDocument();
    expect(await screen.findByText('No hay mediciones en este período.')).toBeInTheDocument();
  });

  it('el gráfico de glucosa cambia de período (1D, 7D, 30D) consultando ese período', async () => {
    const { calls } = open([point('a', '2026-10-14T09:00:00', { glucosa: 102 })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    expect(await section.findByRole('group', { name: /Glucosa experimental: 1 punto/ })).toBeInTheDocument();
    expect(section.getByRole('button', { name: 'Últimos 7 días' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(section.getByRole('button', { name: 'Último día' }));
    expect(section.getByRole('button', { name: 'Último día' })).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(calls.filter((call) => call.key === 'GET /measurements/evolution').some((call) => new URL(call.url).searchParams.get('dias') === '1')).toBe(true));
  });

  it('permite elegir la variable del gráfico (glucosa, frecuencia, SpO₂, índice óptico) y una vista general', async () => {
    open([point('a', '2026-10-14T09:00:00', { glucosa: 102, frecuenciaCardiaca: 72, spo2: 98, indiceOptico: 0.42 }),
      point('b', '2026-10-14T11:00:00', { frecuenciaCardiaca: 80, esDemo: true, origen: 'DEMO' })]);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    const tabs = within(section.getByRole('tablist', { name: 'Variable a graficar' }));
    expect(tabs.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Glucosa experimental', 'Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)', 'Índice óptico', 'Vista general']);
    expect(tabs.getByRole('tab', { name: 'Glucosa experimental' })).toHaveAttribute('aria-selected', 'true');
    await user.click(tabs.getByRole('tab', { name: 'Frecuencia cardíaca' }));
    expect(await section.findByRole('group', { name: /Frecuencia cardíaca: 2 puntos/ })).toBeInTheDocument(); // una experimental y una prueba DEMO
    await user.click(tabs.getByRole('tab', { name: 'Índice óptico' }));
    expect(await section.findByRole('group', { name: /Índice óptico: 1 punto/ })).toBeInTheDocument();
    await user.click(tabs.getByRole('tab', { name: 'Vista general' }));
    const overview = within(section.getByRole('tabpanel', { name: 'Vista general' })); // el panel lo nombra su pestaña
    for (const title of ['Glucosa experimental', 'Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)', 'Índice óptico']) {
      expect(overview.getByRole('article', { name: title })).toBeInTheDocument();
    }
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
  it('muestra accesos a instituciones, perfil y seguridad, sin consultar mediciones propias', async () => {
    const institutional = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    const { calls } = mockApi({ 'GET /auth/me': jsonResponse(200, institutional) });
    renderAt('/app/inicio');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    const shortcuts = within(screen.getByRole('list', { name: 'Accesos rápidos' }));
    expect(shortcuts.getByRole('link', { name: /Mis instituciones/ })).toHaveAttribute('href', '/app/instituciones');
    expect(shortcuts.getByRole('link', { name: /Seguridad/ })).toHaveAttribute('href', '/app/seguridad');
    expect(screen.queryByRole('list', { name: 'Últimos valores medidos' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /measurements/evolution')).toBe(false);
  });
});
