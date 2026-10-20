// Las pestañas de variable de Inicio y del dashboard de mediciones son el componente compartido `Tabs`:
// teclado completo (flechas, Inicio y Fin) y panel enlazado a la pestaña activa.
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const point = (id, fecha, extra = {}) => ({
  idMedicion: id, fecha, modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'EXPERIMENTAL', esDemo: false, frecuenciaCardiaca: 72, spo2: 98, glucosa: 102,
  indiceOptico: 0.4, ...extra,
});
const stat = (cantidad = 0, ultimo = null, promedio = null, minimo = null, maximo = null) => ({ cantidad, ultimo, promedio, minimo, maximo });
const EVOLUTION = {
  origen: 'TODOS', desde: '2026-10-08T00:00:00', hasta: null, truncado: false,
  puntos: [point('a', '2026-10-14T09:00:00'), point('b', '2026-10-15T09:00:00', { glucosa: 110 })],
  estadisticas: { experimental: { mediciones: 2, frecuenciaCardiaca: stat(2, { valor: 72, fecha: '2026-10-15T09:00:00' }, 72, 72, 72), spo2: stat(2, { valor: 98, fecha: '2026-10-15T09:00:00' }, 98, 98, 98),
    glucosa: stat(2, { valor: 110, fecha: '2026-10-15T09:00:00' }, 106, 102, 110), indiceOptico: stat(2, { valor: 0.4, fecha: '2026-10-15T09:00:00' }, 0.4, 0.4, 0.4) }, demo: null },
};
const DASHBOARD = {
  perfilDisponible: true, datosFaltantes: [], periodo: { dias: 30, desde: null, hasta: null },
  resumen: { total: 2, completadas: 2, enPeriodo: 2, ultimaMedicion: null, ultimaGlucosa: null, ultimaSpo2: null, ultimaFrecuencia: null },
  estadisticas: { dias: 30, cantidadMediciones: 0, serieDiaria: [] }, recientes: [], ultimaGuardada: null, pruebasDemo: 0,
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function open() {
  mockApi({
    'GET /auth/me': jsonResponse(200, ACCOUNT),
    'GET /measurements/evolution': jsonResponse(200, EVOLUTION),
    'GET /measurements/dashboard': jsonResponse(200, DASHBOARD),
    'GET /measurements/profile': jsonResponse(200, { perfilDisponible: true, datosFaltantes: [], idPerfilMedicion: 'p', nombre: 'Victoria', apellido: 'Cortés' }),
  });
}

describe('Pestañas de variable (componente compartido)', () => {
  it('Inicio: las flechas cambian de variable, solo la pestaña activa entra en el orden de Tab y el panel queda nombrado por ella', async () => {
    open();
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Evolución reciente' }));
    const tabs = section.getAllByRole('tab');
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1, -1, -1]);
    expect(section.getByRole('tabpanel', { name: 'Glucosa experimental' })).toBeInTheDocument();
    tabs[0].focus();
    await user.keyboard('{ArrowRight}');
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(section.getByRole('tabpanel', { name: 'Frecuencia cardíaca' })).toBeInTheDocument();
    await user.keyboard('{End}');
    expect(section.getByRole('tabpanel', { name: 'Vista general' })).toBeInTheDocument();
    await user.keyboard('{ArrowRight}'); // vuelve a la primera
    expect(tabs[0]).toHaveFocus();
  });

  it('Dashboard de mediciones: las pestañas de variable y su panel funcionan con el teclado', async () => {
    open();
    const user = userEvent.setup();
    renderAt('/app/mediciones');
    const panel = await screen.findByRole('region', { name: 'Evolución de mis mediciones' });
    const tabs = within(within(panel).getByRole('tablist', { name: 'Variable' })).getAllByRole('tab');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    tabs[0].focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    expect(tabs[2]).toHaveFocus();
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true');
    expect(within(panel).getByRole('tabpanel', { name: 'Saturación de oxígeno (SpO₂)' })).toBeInTheDocument();
  });
});
