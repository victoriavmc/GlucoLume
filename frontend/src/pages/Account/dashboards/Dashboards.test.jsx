import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const metric = (cantidad = 0, promedio = null, minimo = null, maximo = null) => ({ cantidad, promedio, minimo, maximo });
const STATS = {
  dias: 30, cantidadMediciones: 4, glucosa: metric(), spo2: metric(4, 96.5, 94, 99), frecuenciaCardiaca: metric(4, 72, 65, 80),
  serieDiaria: [
    { fecha: '2026-10-06', mediciones: 2, glucosaPromedio: null, spo2Promedio: 95, frecuenciaPromedio: 70 },
    { fecha: '2026-10-08', mediciones: 2, glucosaPromedio: null, spo2Promedio: 98, frecuenciaPromedio: 74 },
  ],
};
const EMPTY_STATS = { dias: 30, cantidadMediciones: 0, glucosa: metric(), spo2: metric(), frecuenciaCardiaca: metric(), serieDiaria: [] };
const PERIOD = { dias: 30, desde: null, hasta: null };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

// --- Grupo ---------------------------------------------------------------------------------------------------

const GID = '7b000000-0000-4000-8000-000000000001';
const GBASE = `/groups/${GID}`;
const NONE = { compartePerfil: false, comparteUltimaMedicion: false, comparteHistorial: false };
const GROUP = {
  idGrupo: GID, nombre: 'Familia Pérez', descripcion: null, estado: 'ACTIVO', fechaCreacion: '2026-10-01T10:00:00',
  administrador: 'Ana Gómez', cantidadIntegrantes: 3, miRol: 'MIEMBRO', idGrupoUsuario: 'gu-me', fechaIncorporacion: '2026-10-01T10:00:00',
};
const member = (id, nombre, rol, flags = {}, extra = {}) => ({
  idGrupoUsuario: id, nombre, apellido: 'X', rol, estado: 'ACTIVO', fechaIncorporacion: '2026-10-02T10:00:00', esVos: false,
  ...NONE, tienePerfil: true, ...flags, ...extra,
});
const GROUP_DASHBOARD = {
  grupo: GROUP, periodo: PERIOD, integrantesActivos: 3, administradores: 1, miembros: 2, comparteUltimaMedicion: 1, comparteHistorial: 1,
  integrantes: [
    member('gu-me', 'Yo', 'MIEMBRO', {}, { esVos: true }),
    member('gu-juan', 'Juan', 'ADMINISTRADOR', { compartePerfil: true }),
    member('gu-pepe', 'Pepe', 'MIEMBRO', { comparteUltimaMedicion: true, comparteHistorial: true }),
  ],
  actividadReciente: [{
    idGrupoUsuario: 'gu-pepe', nombre: 'Pepe', apellido: 'X',
    medicion: { idMedicion: 'm-1', fechaHoraInicio: '2026-10-08T09:00:00', modoMedicion: 'OXIMETRIA', condicionComida: 'AYUNO', glucosaEstimada: null, spo2: 98, frecuenciaCardiaca: 70 },
  }],
  agregado: null, motivoSinAgregado: 'Se necesitan al menos 2 integrantes que compartan su historial para mostrar estadísticas del grupo sin exponer a una sola persona.',
};

function groupRoutes(extra = {}) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, ACCOUNT), [`GET ${GBASE}`]: jsonResponse(200, GROUP), ...extra });
}

describe('Dashboard del grupo', () => {
  it('muestra roles, quién comparte qué y solo la actividad autorizada; sin estadística grupal con una sola persona', async () => {
    groupRoutes({ [`GET ${GBASE}/dashboard`]: jsonResponse(200, GROUP_DASHBOARD) });
    renderAt(`/app/grupo/${GID}`);
    const summary = within(await screen.findByRole('list', { name: 'Resumen del grupo' }));
    expect(summary.getByText('Integrantes activos').closest('li')).toHaveTextContent('3');
    expect(summary.getByText('Comparten el historial').closest('li')).toHaveTextContent('1');
    const juan = within(screen.getByRole('list', { name: 'Qué comparte Juan X' }));
    expect(juan.getByText(/Datos básicos del perfil/)).toHaveTextContent('Compartido');
    expect(juan.getByText(/Historial de mediciones/)).toHaveTextContent('No compartido');
    const activity = within(screen.getByRole('list', { name: 'Actividad compartida reciente' }));
    expect(activity.getByText(/Pepe X/)).toBeInTheDocument();
    expect(activity.queryByText(/Juan/)).not.toBeInTheDocument(); // Juan no comparte mediciones
    expect(screen.getByText(/Se necesitan al menos 2 integrantes/)).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'SpO₂' })).not.toBeInTheDocument();
  });

  it('la evolución grupal grafica a quienes compartieron su historial, con tooltip completo, pruebas DEMO identificadas, y no consulta a los demás', async () => {
    const dashboard = { ...GROUP_DASHBOARD, comparteHistorial: 2, integrantes: [
      member('gu-me', 'Yo', 'MIEMBRO', { comparteHistorial: true }, { esVos: true }),
      member('gu-juan', 'Juan', 'ADMINISTRADOR', { compartePerfil: true }),
      member('gu-pepe', 'Pepe', 'MIEMBRO', { comparteHistorial: true }),
      member('gu-ana', 'Ana', 'MIEMBRO', { comparteUltimaMedicion: true, notificaMedicion: true }), // sin historial: no figura
    ] };
    const demoPoint = { idMedicion: 'd-1', fecha: '2026-10-09T10:05:00', frecuenciaCardiaca: 91, spo2: 99, glucosa: 120 };
    const expPoint = { idMedicion: 'e-1', fecha: '2026-10-08T16:12:30', modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'EXPERIMENTAL',
      frecuenciaCardiaca: 80, spo2: 97.5, glucosa: 130 };
    const { calls } = groupRoutes({
      [`GET ${GBASE}/dashboard`]: jsonResponse(200, dashboard),
      // Pepe solo tiene pruebas DEMO (sin serie experimental): deben verse igual.
      [`GET ${GBASE}/shared/gu-pepe/statistics`]: jsonResponse(200, { ...EMPTY_STATS, pruebasDemo: 1, puntosDemo: [demoPoint], puntos: [] }),
      'GET /measurements/evolution': jsonResponse(200, { origen: 'TODOS', desde: null, hasta: null, truncado: false, estadisticas: {},
        puntos: [
          { ...expPoint, origen: 'EXPERIMENTAL', esDemo: false, indiceOptico: null },
          { ...demoPoint, idMedicion: 'd-2', modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'DEMO', esDemo: true, indiceOptico: null },
        ] }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${GID}`);
    expect(await screen.findByRole('heading', { name: 'Evolución grupal de mediciones' })).toBeInTheDocument();
    const legend = within(await screen.findByRole('list', { name: 'Series graficadas' }));
    expect(legend.getByText('Pepe X · DEMO (prueba)')).toBeInTheDocument();
    expect(legend.getByText('Yo X (vos)')).toBeInTheDocument();
    expect(legend.getByText('Yo X (vos) · DEMO (prueba)')).toBeInTheDocument();
    expect(legend.queryByText(/Juan|Ana/)).not.toBeInTheDocument();
    expect(calls.some((call) => /\/shared\/gu-(juan|ana)\//.test(call.key))).toBe(false); // no compartieron el historial
    expect(calls.some((call) => call.key.includes('/shared/gu-me/'))).toBe(false);
    // Tooltip de una medición experimental propia: integrante, variable, valor, fecha y hora, origen.
    await user.hover(screen.getByRole('button', { name: /Yo X \(vos\) · 08\/10\/2026 16:12: 130 mg\/dL/ }));
    const tip = within(screen.getByRole('tooltip'));
    expect(tip.getByText('Yo X (vos)')).toBeInTheDocument();
    expect(tip.getByText('Glucosa experimental')).toBeInTheDocument();
    expect(tip.getByText('130 mg/dL')).toBeInTheDocument();
    expect(tip.getByText('08/10/2026 16:12')).toBeInTheDocument();
    expect(tip.getByText('Experimental')).toBeInTheDocument();
    // Tooltip de una prueba DEMO de otro integrante: queda identificada como DEMO y no como experimental.
    await user.hover(screen.getByRole('button', { name: /Pepe X · DEMO \(prueba\) · 09\/10\/2026 10:05: 120 mg\/dL/ }));
    const demoTip = within(screen.getByRole('tooltip'));
    expect(demoTip.getByText('Pepe X')).toBeInTheDocument();
    expect(demoTip.getByText('Glucosa DEMO (simulada)')).toBeInTheDocument();
    expect(demoTip.getByText('DEMO (prueba)')).toBeInTheDocument();
    expect(demoTip.queryByText('Experimental')).not.toBeInTheDocument();
  });

  it('la actividad reciente muestra siempre día, fecha y hora; con solo el aviso aparece el hecho sin ningún valor', async () => {
    const dashboard = { ...GROUP_DASHBOARD, actividadReciente: [
      { idGrupoUsuario: 'gu-pepe', nombre: 'Pepe', apellido: 'X', tipo: 'MEDICION', fechaHoraInicio: '2026-10-14T00:49:58',
        medicion: { idMedicion: 'm-1', fechaHoraInicio: '2026-10-14T00:49:58', modoMedicion: 'OXIMETRIA', condicionComida: 'AYUNO', glucosaEstimada: null, spo2: 98, frecuenciaCardiaca: 70 } },
      { idGrupoUsuario: 'gu-juan', nombre: 'Juan', apellido: 'X', tipo: 'AVISO', fechaHoraInicio: '2026-10-13T18:27:10', medicion: null },
    ] };
    groupRoutes({ [`GET ${GBASE}/dashboard`]: jsonResponse(200, dashboard) });
    renderAt(`/app/grupo/${GID}`);
    const feed = within(await screen.findByRole('list', { name: 'Actividad compartida reciente' }));
    const [valores, aviso] = feed.getAllByRole('listitem');
    expect(valores).toHaveTextContent('Mié, 14/10/2026 00:49');
    expect(valores).toHaveTextContent('SpO₂ 98 %');
    expect(aviso).toHaveTextContent('Juan X');
    expect(aviso).toHaveTextContent('Mar, 13/10/2026 18:27'); // día, fecha y hora también sin valores
    expect(aviso).toHaveTextContent('Aviso de medición compartido');
    expect(aviso).toHaveTextContent('Realizó una medición');
    expect(aviso).not.toHaveTextContent(/SpO₂|Frecuencia|Glucosa|lpm|mg\/dL|%/); // ningún valor
  });

  describe('evolución grupal: vista general, filtros y clic', () => {
    const exp = (id, fecha, extra = {}) => ({ idMedicion: id, fecha, modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'EXPERIMENTAL',
      frecuenciaCardiaca: 80, spo2: 97, glucosa: 120, indiceOptico: 2.4, ...extra });
    const dashboard = { ...GROUP_DASHBOARD, comparteHistorial: 2, integrantes: [
      member('gu-me', 'Yo', 'MIEMBRO', { comparteHistorial: true }, { esVos: true }),
      member('gu-pepe', 'Pepe', 'MIEMBRO', { comparteHistorial: true }),
    ] };
    const pepeStats = { ...EMPTY_STATS, pruebasDemo: 1,
      puntos: [exp('p-1', '2026-10-14T16:12:00', { glucosa: 120, frecuenciaCardiaca: 80 }), exp('p-2', '2026-10-14T16:40:00', { glucosa: 130, frecuenciaCardiaca: 90 })],
      puntosDemo: [{ idMedicion: 'p-d', fecha: '2026-10-14T18:00:00', frecuenciaCardiaca: 91, spo2: 99, glucosa: 114, indiceOptico: 2.1 }] };
    const own = { origen: 'TODOS', desde: null, hasta: null, truncado: false, estadisticas: {}, puntos: [
      { ...exp('y-1', '2026-10-14T10:00:00', { glucosa: 100 }), esDemo: false } ] };

    async function open() {
      groupRoutes({
        [`GET ${GBASE}/dashboard`]: jsonResponse(200, dashboard),
        [`GET ${GBASE}/shared/gu-pepe/statistics`]: jsonResponse(200, pepeStats),
        'GET /measurements/evolution': jsonResponse(200, own),
      });
      const user = userEvent.setup();
      renderAt(`/app/grupo/${GID}`);
      const section = within(await screen.findByRole('region', { name: 'Evolución grupal de mediciones' }));
      await section.findByRole('list', { name: 'Series graficadas' });
      return { user, section };
    }

    it('la vista general muestra una grilla con un gráfico por variable, respetando origen y agrupación', async () => {
      const { user, section } = await open();
      const tabs = section.getAllByRole('tab');
      expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1, -1, -1]); // una sola parada de Tab; las flechas recorren las pestañas
      tabs[0].focus();
      await user.keyboard('{End}');
      expect(section.getByRole('tab', { name: 'Vista general' })).toHaveAttribute('aria-selected', 'true');
      expect(section.getByRole('tabpanel', { name: 'Vista general' })).toBeInTheDocument();
      for (const title of ['Frecuencia cardíaca', 'Saturación de oxígeno (SpO₂)', 'Glucosa experimental', 'Índice óptico']) {
        expect(section.getByRole('article', { name: title })).toBeInTheDocument();
      }
      // Origen DEMO: solo la prueba de Pepe; ninguna serie experimental.
      await user.selectOptions(section.getByLabelText('Origen de los datos de la evolución'), 'DEMO');
      const legend = within(section.getByRole('list', { name: 'Series graficadas' }));
      expect(legend.getByText('Pepe X · DEMO (prueba)')).toBeInTheDocument();
      expect(legend.queryByText('Pepe X')).not.toBeInTheDocument();
      // Origen experimental + promedio por hora: las dos mediciones de Pepe de las 16 h se promedian en un solo punto.
      await user.selectOptions(section.getByLabelText('Origen de los datos de la evolución'), 'EXPERIMENTAL');
      await user.selectOptions(section.getByLabelText('Agrupación de la evolución'), 'HORA');
      const glucose = within(section.getByRole('article', { name: 'Glucosa experimental' }));
      expect(glucose.getByRole('button', { name: /Pepe X · 14\/10\/2026 16:00–17:00: 125 mg\/dL/ })).toBeInTheDocument(); // (120 + 130) / 2
      expect(glucose.getAllByRole('button')).toHaveLength(2); // Pepe (1 bloque) + vos (1 medición)
    });

    it('un clic deja el punto seleccionado y muestra su detalle en la misma vista', async () => {
      const { user, section } = await open();
      const target = section.getByRole('button', { name: /Pepe X · 14\/10\/2026 16:12: 120 mg\/dL/ });
      await user.click(target);
      expect(target).toHaveAttribute('aria-pressed', 'true');
      const detail = within(section.getByRole('region', { name: 'Medición seleccionada' }));
      expect(detail.getByText('Pepe X')).toBeInTheDocument();
      expect(detail.getByText('Glucosa experimental')).toBeInTheDocument();
      expect(detail.getByText('120 mg/dL')).toBeInTheDocument();
      expect(detail.getByText('14/10/2026')).toBeInTheDocument();
      expect(detail.getByText('16:12')).toBeInTheDocument();
      expect(detail.getByText('Experimental')).toBeInTheDocument();
      expect(detail.getByRole('link', { name: 'Ver detalle completo' })).toHaveAttribute('href', `/app/grupo/${GID}/compartidos/gu-pepe/mediciones/p-1`);
      // Una prueba DEMO se identifica como tal en el detalle.
      await user.click(section.getByRole('button', { name: /Pepe X · DEMO \(prueba\) · 14\/10\/2026 18:00: 114 mg\/dL/ }));
      const demo = within(section.getByRole('region', { name: 'Medición seleccionada' }));
      expect(demo.getByText('Glucosa DEMO (simulada)')).toBeInTheDocument();
      expect(demo.getByText('DEMO (prueba)')).toBeInTheDocument();
    });
  });

  it('con 2 o más integrantes que comparten historial muestra el período, quiénes participan y gráficos por variable', async () => {
    const { calls } = groupRoutes({
      [`GET ${GBASE}/dashboard`]: jsonResponse(200, { ...GROUP_DASHBOARD, comparteHistorial: 2,
        agregado: { participantes: ['Beto X', 'Pepe X'], estadisticas: STATS }, motivoSinAgregado: null }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${GID}`);
    expect(await screen.findByText(/Incluye a: Beto X, Pepe X/)).toBeInTheDocument();
    expect(screen.getByText(/Período: últimos 30 días/)).toBeInTheDocument();
    expect(within(screen.getByRole('article', { name: 'SpO₂' })).getByText('96,5 %')).toBeInTheDocument();
    expect(within(screen.getByRole('article', { name: 'Glucosa experimental' })).getByText('Sin datos disponibles')).toBeInTheDocument();
    await user.selectOptions(within(screen.getByRole('region', { name: 'Estadísticas del grupo' })).getByLabelText('Período'), '7');
    await screen.findByText(/Incluye a:/);
    const last = new URL(calls.filter((call) => call.key === `GET ${GBASE}/dashboard`).at(-1).url);
    expect(last.searchParams.get('dias')).toBe('7');
  });

  it('el integrante que no comparte no se consulta y se muestra el aviso', async () => {
    const { calls } = groupRoutes({ [`GET ${GBASE}/shared`]: jsonResponse(200, [member('gu-pepe', 'Pepe', 'MIEMBRO')]) });
    renderAt(`/app/grupo/${GID}/integrantes/gu-pepe`);
    expect(await screen.findByRole('heading', { name: 'Pepe X' })).toBeInTheDocument();
    expect(screen.getByText('Este integrante no habilitó la visualización de sus datos de medición.')).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/shared/gu-pepe/'))).toBe(false); // no se consulta lo restringido

  });

  it('vista de un integrante con historial compartido: gráfico de evolución con tooltip completo y las DEMO identificadas', async () => {
    const members = [member('gu-beto', 'Beto', 'MIEMBRO', { comparteHistorial: true })];
    const exp = { idMedicion: 'e-1', fecha: '2026-10-14T16:12:00', modoMedicion: 'GLUCOSA_EXPERIMENTAL', origen: 'EXPERIMENTAL',
      frecuenciaCardiaca: 80, spo2: 97.5, glucosa: 120 };
    const demo = { idMedicion: 'd-1', fecha: '2026-10-13T23:38:00', frecuenciaCardiaca: 91, spo2: 99, glucosa: 114 };
    groupRoutes({
      [`GET ${GBASE}/shared`]: jsonResponse(200, members),
      [`GET ${GBASE}/shared/gu-beto/history`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 20 }),
      [`GET ${GBASE}/shared/gu-beto/statistics`]: jsonResponse(200, { ...STATS, pruebasDemo: 1, puntos: [exp], puntosDemo: [demo] }),
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${GID}/integrantes/gu-beto`);
    expect(await screen.findByRole('heading', { name: 'Evolución de Beto X' })).toBeInTheDocument();
    await user.hover(await screen.findByRole('button', { name: 'Beto X · 14/10/2026 16:12: 120 mg/dL' }));
    const tip = within(screen.getByRole('tooltip'));
    expect(tip.getByText('Glucosa experimental')).toBeInTheDocument();
    expect(tip.getByText('120 mg/dL')).toBeInTheDocument();
    expect(tip.getByText('14/10/2026 16:12')).toBeInTheDocument();
    expect(tip.getByText('Experimental')).toBeInTheDocument();
    await user.hover(screen.getByRole('button', { name: 'Beto X · DEMO (prueba) · 13/10/2026 23:38: 114 mg/dL' }));
    const demoTip = within(screen.getByRole('tooltip'));
    expect(demoTip.getByText('Glucosa DEMO (simulada)')).toBeInTheDocument();
    expect(demoTip.getByText('DEMO (prueba)')).toBeInTheDocument();
  });

  it('el historial y los avisos de un integrante muestran solo los últimos 5 y un botón al costado abre todos', async () => {
    const members = [member('gu-beto', 'Beto', 'MIEMBRO', { comparteHistorial: true, notificaMedicion: true })];
    const item = (n) => ({ idMedicion: `h-${n}`, fechaHoraInicio: `2026-10-${String(20 - n).padStart(2, '0')}T10:00:00`, modoMedicion: 'OXIMETRIA',
      condicionComida: 'AYUNO', glucosaEstimada: null, spo2: 97, frecuenciaCardiaca: 70, esDemo: false, estadoMedicion: 'COMPLETADA' });
    const all = Array.from({ length: 8 }, (_, n) => item(n + 1));
    const notice = (n) => ({ fechaHoraInicio: `2026-10-${String(20 - n).padStart(2, '0')}T10:00:00` });
    const notices = Array.from({ length: 8 }, (_, n) => notice(n + 1));
    const { calls } = groupRoutes({
      [`GET ${GBASE}/shared`]: jsonResponse(200, members),
      [`GET ${GBASE}/shared/gu-beto/history`]: [
        jsonResponse(200, { items: all.slice(0, 5), total: 8, pagina: 1, tamanioPagina: 5 }),
        jsonResponse(200, { items: all, total: 8, pagina: 1, tamanioPagina: 10 }),
        jsonResponse(200, { items: all.slice(0, 5), total: 8, pagina: 1, tamanioPagina: 5 }),
      ],
      [`GET ${GBASE}/shared/gu-beto/statistics`]: jsonResponse(200, STATS),
      [`GET ${GBASE}/shared/gu-beto/notices`]: [
        jsonResponse(200, { items: notices.slice(0, 5), total: 8 }),
        jsonResponse(200, { items: notices, total: 8 }),
      ],
    });
    const user = userEvent.setup();
    renderAt(`/app/grupo/${GID}/integrantes/gu-beto`);
    const history = within(await screen.findByRole('region', { name: 'Historial de mediciones' }));
    expect(await history.findAllByRole('listitem')).toHaveLength(5); // solo los últimos 5
    expect(history.getByText(/Se muestran las últimas 5 de 8/)).toBeInTheDocument();
    expect(calls.find((call) => call.key === `GET ${GBASE}/shared/gu-beto/history`).url).toContain('tamanioPagina=5');
    await user.click(history.getByRole('button', { name: 'Ver historial' }));
    expect(await history.findAllByRole('listitem')).toHaveLength(8); // todos los de esa persona
    await user.click(history.getByRole('button', { name: 'Ver solo los últimos 5' }));
    expect(await history.findAllByRole('listitem')).toHaveLength(5);
    // Avisos: misma lógica.
    const avisos = within(await screen.findByRole('region', { name: 'Avisos de medición' }));
    expect(await avisos.findAllByRole('listitem')).toHaveLength(5);
    await user.click(avisos.getByRole('button', { name: 'Ver todos los avisos' }));
    expect(await avisos.findAllByRole('listitem')).toHaveLength(8);
    expect(avisos.getByText(/8 avisos en total/)).toBeInTheDocument();
  });

  it('vista de un integrante sin historial compartido (solo última medición y aviso): no hay gráfico y se explica por qué', async () => {
    const members = [member('gu-pepe', 'Pepe', 'MIEMBRO', { comparteUltimaMedicion: true, notificaMedicion: true })];
    const { calls } = groupRoutes({
      [`GET ${GBASE}/shared`]: jsonResponse(200, members),
      [`GET ${GBASE}/shared/gu-pepe/latest`]: jsonResponse(200, { medicion: null }),
      [`GET ${GBASE}/shared/gu-pepe/notices`]: jsonResponse(200, { items: [], total: 0 }),
    });
    renderAt(`/app/grupo/${GID}/integrantes/gu-pepe`);
    expect(await screen.findByText(/no habilitó compartir su historial de mediciones, por lo que no se puede mostrar su evolución/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Evolución de/ })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.endsWith('/statistics') || call.key.endsWith('/history'))).toBe(false);
  });

  it('quien comparte historial muestra sus datos y gráficos, sin migas de pan ni enlace de regreso', async () => {
    const members = [member('gu-beto', 'Beto', 'MIEMBRO', { comparteUltimaMedicion: true, comparteHistorial: true })];
    const { calls } = groupRoutes({
      [`GET ${GBASE}/shared`]: jsonResponse(200, members),
      [`GET ${GBASE}/shared/gu-beto/latest`]: jsonResponse(200, { medicion: null }),
      [`GET ${GBASE}/shared/gu-beto/history`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 20 }),
      [`GET ${GBASE}/shared/gu-beto/statistics`]: jsonResponse(200, STATS),
    });
    renderAt(`/app/grupo/${GID}/integrantes/gu-beto`);
    expect(await screen.findByRole('heading', { name: 'Evolución de Beto X' })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((call) => call.key === `GET ${GBASE}/shared/gu-beto/statistics`)).toBe(true));
    expect(screen.queryByRole('navigation', { name: 'Ruta de navegación' })).not.toBeInTheDocument();
    expect(document.querySelector('.back-link')).toBeNull();
  });
});

// --- Institución ------------------------------------------------------------------------------------------------------

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const IID = '9a000000-0000-4000-8000-000000000001';
const IBASE = `/institutions/${IID}`;
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'CONSULTAR_EQUIPO', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_EQUIPO', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
};
const institution = (rol) => ({
  idInstitucion: IID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
  estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null,
  fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' },
  cantidadModeradores: 1, cantidadOperadores: 2, cantidadPacientes: 3,
});
const INSTITUTION_DASHBOARD = {
  periodo: PERIOD, pacientesActivos: 3, moderadoresActivos: 1, operadoresActivos: 2, dispositivosRegistrados: 4, dispositivosOperativos: 3,
  medicionesTotal: 25, medicionesHoy: 2, medicionesUltimos7Dias: 9, medicionesUltimos30Dias: 20, medicionesEnPeriodo: 20,
  porEstado: { COMPLETADA: 20, CANCELADA: 3, INVALIDA: 2 }, porModo: { OXIMETRIA: 22, GLUCOSA_EXPERIMENTAL: 3 },
  ultimaActividad: '2026-10-08T11:00:00',
  serie: [{ fecha: '2026-10-07', total: 4, completadas: 3 }, { fecha: '2026-10-08', total: 6, completadas: 5 }],
  estadisticas: STATS,
  porOperador: [
    { idInstitucionUsuario: 'op-1', nombre: 'Victoria', apellido: 'Corti', activo: true, pacientesAsignados: 2, mediciones: 14 },
    { idInstitucionUsuario: 'op-2', nombre: 'Nueva', apellido: 'Prueba', activo: false, pacientesAsignados: 0, mediciones: 6 },
  ],
};
const person = (id, nombre, apellido, activo = true) => ({ idInstitucionUsuario: id, nombre, apellido, rolInstitucion: 'OPERADOR', activo });

function instRoutes(rol, extra = {}) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET ${IBASE}`]: jsonResponse(200, institution(rol)), ...extra });
}

const counts = (total, completadas, canceladas, invalidas, enCurso, experimentales, demo) => (
  { total, completadas, canceladas, invalidas, enCurso, experimentales, demo, sinResultado: canceladas + invalidas + enCurso });
const ADMIN = {
  filtros: { operador: null, modo: null, estado: null, origen: 'TODOS' },
  operadores: [{ idInstitucionUsuario: 'op-1', nombre: 'Victoria', apellido: 'Corti', rolInstitucion: 'OPERADOR', activo: true },
    { idInstitucionUsuario: 'op-2', nombre: 'Nueva', apellido: 'Prueba', rolInstitucion: 'OPERADOR', activo: false }],
  kpis: { ...counts(25, 20, 3, 2, 0, 15, 5), pacientesRegistrados: 4, pacientesActivos: 3, pacientesConMediciones: 3, pacientesSinOperador: 1, pacientesAsignadosOperador: null,
    operadoresActivos: 2, moderadoresActivos: 1, transferenciasPendientes: 2, transferenciasTotal: 5, dispositivosDisponibles: 3, dispositivosRegistrados: 4 },
  serie: [{ fecha: '2026-10-07', completadas: 3, canceladas: 1, invalidas: 0, enCurso: 0, experimentales: 3, demo: 1 },
    { fecha: '2026-10-08', completadas: 5, canceladas: 0, invalidas: 1, enCurso: 0, experimentales: 4, demo: 2 }],
  porModo: [{ modo: 'OXIMETRIA', ...counts(22, 18, 2, 2, 0, 14, 4) }, { modo: 'GLUCOSA_EXPERIMENTAL', ...counts(3, 2, 1, 0, 0, 1, 1) }],
  porEstado: [{ estado: 'PENDIENTE', total: 0, experimentales: 0, demo: 0, sinResultado: 0 }, { estado: 'ADQUIRIENDO', total: 0, experimentales: 0, demo: 0, sinResultado: 0 },
    { estado: 'PROCESANDO', total: 0, experimentales: 0, demo: 0, sinResultado: 0 }, { estado: 'COMPLETADA', total: 20, experimentales: 15, demo: 5, sinResultado: 0 },
    { estado: 'INVALIDA', total: 2, experimentales: 0, demo: 0, sinResultado: 2 }, { estado: 'CANCELADA', total: 3, experimentales: 0, demo: 0, sinResultado: 3 }],
  // «Nueva Prueba» fue desvinculada pero tuvo actividad en el período: sigue en la tabla (el backend omite a los desvinculados sin actividad).
  porOperador: [{ idInstitucionUsuario: 'op-1', nombre: 'Victoria', apellido: 'Corti', activo: true, pacientesAsignados: 2, ...counts(14, 12, 1, 1, 0, 10, 4) },
    { idInstitucionUsuario: 'op-2', nombre: 'Nueva', apellido: 'Prueba', activo: false, pacientesAsignados: 0, ...counts(6, 4, 2, 0, 0, 5, 1) }],
  porAlimentacion: [{ condicion: 'AYUNO', total: 12 }, { condicion: 'POSTPRANDIAL', total: 5 }, { condicion: 'NO_INFORMADA', total: 8 }],
  pacientesPorCantidad: [{ desde: 0, hasta: 0, pacientes: 0 }, { desde: 1, hasta: 1, pacientes: 0 }, { desde: 2, hasta: 3, pacientes: 1 }, { desde: 4, hasta: 5, pacientes: 0 }, { desde: 6, hasta: null, pacientes: 2 }],
  truncado: false,
};
const day = (fecha, mediciones, glucosa, spo2, rate) => ({
  fecha, mediciones, glucosaPromedio: glucosa, glucosaN: glucosa === null ? 0 : mediciones, spo2Promedio: spo2, spo2N: spo2 === null ? 0 : mediciones,
  frecuenciaPromedio: rate, frecuenciaN: rate === null ? 0 : mediciones,
});
const group = (origen, overrides = {}) => ({
  origen, estado: 'DISPONIBLE', motivo: null, mediciones: 7, pacientes: 5,
  spo2: metric(7, 96.5, 94, 99), frecuenciaCardiaca: metric(7, 72, 65, 80), glucosa: metric(), calidadSenal: metric(),
  alimentacion: { AYUNO: 4, NO_INFORMADA: 3 }, porModo: { OXIMETRIA: 7 }, sinInformar: { spo2: 0, frecuenciaCardiaca: 0, glucosa: 7, calidadSenal: 7 },
  serieDiaria: [day('2026-10-08', 7, null, 96.5, 72)], puntos: [], ...overrides,
});
const withoutGroup = (origen, estado, motivo) => ({ origen, estado, motivo, mediciones: 0, pacientes: 0, spo2: null, frecuenciaCardiaca: null, glucosa: null, sinInformar: {}, serieDiaria: [], puntos: [] });
const DEMO_POINTS = [
  { fecha: '2026-10-17T10:00:00', glucosa: 100, spo2: 96, frecuenciaCardiaca: 70 }, { fecha: '2026-10-17T14:30:00', glucosa: 120, spo2: 97, frecuenciaCardiaca: 80 },
  { fecha: '2026-10-18T09:15:00', glucosa: 110, spo2: 95, frecuenciaCardiaca: 75 },
];
const DEMO_GROUP = group('DEMO', {
  mediciones: 3, pacientes: 2, glucosa: metric(3, 110, 100, 120), spo2: metric(3, 96, 95, 97), frecuenciaCardiaca: metric(3, 75, 70, 80),
  porModo: { OXIMETRIA: 2, GLUCOSA_EXPERIMENTAL: 1 }, alimentacion: { AYUNO: 2, POSTPRANDIAL: 1 }, calidadSenal: metric(2, 0.8, 0.7, 0.9),
  sinInformar: { spo2: 0, frecuenciaCardiaca: 0, glucosa: 0, calidadSenal: 1 },
  serieDiaria: [day('2026-10-17', 2, 110, 96.5, 75), day('2026-10-18', 1, 110, 95, 75)], puntos: DEMO_POINTS,
});
const HEALTH = {
  minimoPacientes: 5, filtros: { operador: null, modo: null, estado: null, origen: 'TODOS' },
  experimentales: group('EXPERIMENTAL'),
  demo: DEMO_GROUP,
};
const WITH_ADMIN = { ...INSTITUTION_DASHBOARD, administrativo: ADMIN, saludAgregada: HEALTH };

describe('Panel de supervisión institucional (moderador y propietario)', () => {
  it('muestra los indicadores administrativos, la actividad por fecha con canceladas, estados, modos y la carga por operador, sin pacientes', async () => {
    instRoutes('MODERADOR', { [`GET ${IBASE}/dashboard`]: jsonResponse(200, WITH_ADMIN), [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${IID}`);
    const kpis = within(await screen.findByRole('list', { name: 'Indicadores administrativos' }));
    expect(kpis.getByText('Pacientes activos').closest('li')).toHaveTextContent(/3.*4 registrados/);
    expect(kpis.getByText('Pacientes sin operador').closest('li')).toHaveTextContent('1');
    expect(kpis.getByText('Mediciones en el período').closest('li')).toHaveTextContent('25');
    expect(kpis.getByText('DEMO (sintéticas)').closest('li')).toHaveTextContent('5');
    expect(kpis.getByText('Experimentales').closest('li')).toHaveTextContent('15');
    expect(kpis.getByText('Canceladas o inválidas').closest('li')).toHaveTextContent(/5.*3 canceladas · 2 inválidas/);
    expect(kpis.getByText('Transferencias pendientes').closest('li')).toHaveTextContent('2');
    expect(kpis.getByText('Dispositivos disponibles').closest('li')).toHaveTextContent('3');
    expect(screen.queryByRole('list', { name: 'Indicadores de gestión del propietario' })).not.toBeInTheDocument(); // facultades del propietario
    const dates = screen.getByRole('heading', { name: 'Mediciones por fecha' }).closest('article');
    expect(within(dates).getByText(/las canceladas e inválidas también cuentan/)).toBeInTheDocument();
    expect(within(dates).getAllByText('Canceladas').length).toBeGreaterThan(0); // la actividad distingue estados, no solo las completadas
    const operators = within(screen.getByRole('table', { name: 'Distribución de trabajo por operador' }));
    expect(operators.getByText('Victoria Corti').closest('tr')).toHaveTextContent(/2.*14.*12.*2.*10.*4/);
    expect(operators.getByText('Nueva Prueba').closest('tr')).toHaveTextContent('Desvinculado/a'); // con actividad en el período sigue apareciendo…
    expect(screen.getByText(/se muestran solo si tuvieron actividad en el período/)).toBeInTheDocument(); // …y se explica por qué
    expect(screen.queryByText(/Rosa|PAC-/)).not.toBeInTheDocument(); // nada de pacientes
  });

  it('con una sola medición cancelada la actividad aparece y se explica que no hay resultados válidos', async () => {
    const one = {
      ...ADMIN, kpis: { ...ADMIN.kpis, ...counts(1, 0, 1, 0, 0, 0, 0), pacientesRegistrados: 1, pacientesActivos: 1 },
      serie: [{ fecha: '2026-10-08', completadas: 0, canceladas: 1, invalidas: 0, enCurso: 0, experimentales: 0, demo: 0 }],
      porModo: [{ modo: 'OXIMETRIA', ...counts(1, 0, 1, 0, 0, 0, 0) }, { modo: 'GLUCOSA_EXPERIMENTAL', ...counts(0, 0, 0, 0, 0, 0, 0) }],
      porOperador: [ADMIN.porOperador[0]],
    };
    instRoutes('PROPIETARIO', {
      [`GET ${IBASE}/dashboard`]: jsonResponse(200, { ...INSTITUTION_DASHBOARD, agregadosProtegidos: true, minimoPacientesAgregados: 5, administrativo: one,
        estadisticas: { ...INSTITUTION_DASHBOARD.estadisticas, cantidadMediciones: 0 },
        saludAgregada: { ...HEALTH, experimentales: withoutGroup('EXPERIMENTAL', 'PROTEGIDO', 'Los resultados experimentales se informan con al menos 5 pacientes distintos con mediciones en el conjunto elegido.'),
          demo: withoutGroup('DEMO', 'SIN_DATOS', 'No hay mediciones DEMO completadas con estos filtros.') } }),
      [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }),
    });
    renderAt(`/app/instituciones/${IID}`);
    const kpis = within(await screen.findByRole('list', { name: 'Indicadores administrativos' }));
    expect(kpis.getByText('Mediciones en el período').closest('li')).toHaveTextContent('1'); // N = 1: se muestra
    expect(kpis.getByText('Canceladas o inválidas').closest('li')).toHaveTextContent(/1.*1 canceladas/);
    const dates = screen.getByRole('heading', { name: 'Mediciones por fecha' }).closest('article');
    expect(within(dates).queryByText('No hay actividad con estos filtros.')).not.toBeInTheDocument(); // el gráfico NO queda vacío
    expect(within(dates).getByRole('img', { name: 'Mediciones por fecha' })).toBeInTheDocument();
    // Los resultados experimentales siguen protegidos (mensaje breve, sin tarjetas vacías) y no se inventan resultados DEMO.
    expect(screen.getByText(/al menos 5 pacientes distintos con/)).toBeInTheDocument();
    expect(screen.getByText(/No hay mediciones DEMO completadas con estos filtros/)).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'SpO₂' })).not.toBeInTheDocument();
    // El propietario suma su bloque de gestión.
    const owner = within(screen.getByRole('list', { name: 'Indicadores de gestión del propietario' }));
    expect(owner.getByText('Personal activo').closest('li')).toHaveTextContent(/3.*1 moderadores · 2 operadores/);
  });

  it('sin resultados válidos explica «No hay mediciones válidas para calcular resultados» sin ocultar la actividad', async () => {
    instRoutes('MODERADOR', {
      [`GET ${IBASE}/dashboard`]: jsonResponse(200, { ...WITH_ADMIN, estadisticas: EMPTY_STATS, agregadosProtegidos: false,
        saludAgregada: { ...HEALTH, experimentales: withoutGroup('EXPERIMENTAL', 'SIN_DATOS', 'No hay mediciones experimentales completadas con estos filtros.'), demo: null } }),
      [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }),
    });
    renderAt(`/app/instituciones/${IID}`);
    expect(await screen.findByText(/No hay mediciones experimentales completadas con estos filtros/)).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Indicadores administrativos' })).getByText('Mediciones en el período').closest('li')).toHaveTextContent('25');
  });

  it('los filtros se envían al backend y por defecto incluyen DEMO', async () => {
    const { calls } = instRoutes('MODERADOR', { [`GET ${IBASE}/dashboard`]: jsonResponse(200, WITH_ADMIN), [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${IID}`);
    await screen.findByRole('list', { name: 'Indicadores administrativos' });
    expect(new URL(calls.find((call) => call.key === `GET ${IBASE}/dashboard`).url).searchParams.get('origen')).toBe('TODOS');
    expect(screen.getByRole('heading', { name: 'Resultados de salud agregados' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Operador' }), 'op-1');
    // Cada cambio de filtro se pide al backend (nada se aplica en silencio): el operador viaja en la consulta.
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === `GET ${IBASE}/dashboard`).at(-1).url).searchParams.get('operador')).toBe('op-1'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Origen de los datos' }), 'DEMO');
    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === `GET ${IBASE}/dashboard`).at(-1).url).searchParams;
      expect([last.get('operador'), last.get('origen')]).toEqual(['op-1', 'DEMO']);
    });
  });
});

describe('Resultados de salud agregados (moderador y propietario)', () => {
  const open = (health, rol = 'MODERADOR') => {
    instRoutes(rol, { [`GET ${IBASE}/dashboard`]: jsonResponse(200, { ...WITH_ADMIN, saludAgregada: health }), [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${IID}`);
    return screen.findByRole('heading', { name: 'Resultados de salud agregados' });
  };

  it('muestra experimentales y DEMO por separado, con tres tarjetas por origen y los DEMO identificados como datos sintéticos', async () => {
    await open(HEALTH);
    const experimental = within(screen.getByRole('region', { name: 'Resultados experimentales' }));
    const demo = within(screen.getByRole('region', { name: 'Datos DEMO (sintéticos)' }));
    expect(demo.getByText(/no son mediciones clínicas/)).toBeInTheDocument();
    for (const title of ['Glucosa estimada — DEMO', 'SpO₂ — DEMO', 'Frecuencia cardíaca — DEMO']) expect(demo.getByRole('article', { name: title })).toBeInTheDocument();
    for (const title of ['SpO₂ — Experimental', 'Frecuencia cardíaca — Experimental']) expect(experimental.getByRole('article', { name: title })).toBeInTheDocument();
    const glucose = within(demo.getByRole('article', { name: 'Glucosa estimada — DEMO' }));
    expect(glucose.getByText('Promedio').nextSibling).toHaveTextContent('110');
    expect(glucose.getByText('Mínimo').nextSibling).toHaveTextContent('100');
    expect(glucose.getByText('Máximo').nextSibling).toHaveTextContent('120');
    expect(glucose.getByText('Observaciones', { selector: 'dt' }).nextSibling).toHaveTextContent('3');
    // El promedio DEMO de SpO₂ (96) no aparece en el bloque experimental (96,5), y viceversa.
    expect(within(experimental.getByRole('article', { name: 'SpO₂ — Experimental' })).getByText('Promedio').nextSibling).toHaveTextContent('96,5');
    expect(within(demo.getByRole('article', { name: 'SpO₂ — DEMO' })).getByText('Promedio').nextSibling).toHaveTextContent('96');
  });

  it('los DEMO se ven por medición (cada punto con su fecha y hora) y también por día con la cantidad de observaciones', async () => {
    await open(HEALTH);
    const demo = within(screen.getByRole('region', { name: 'Datos DEMO (sintéticos)' }));
    const chart = () => demo.getByRole('img', { name: /Glucosa estimada — DEMO: por medición/ });
    expect(chart()).toHaveAttribute('aria-label', expect.stringContaining('3 mediciones'));
    expect(demo.getAllByRole('img', { name: /Medición individual/ }).length).toBeGreaterThanOrEqual(3);
    await userEvent.click(demo.getByRole('button', { name: 'Por día' }));
    expect(demo.getByRole('img', { name: /Glucosa estimada — DEMO: promedio diario/ })).toHaveAttribute('aria-label', expect.stringContaining('2 promedios diarios'));
    expect(demo.getAllByRole('img', { name: /Promedio diario de 2 observaciones/ }).length).toBeGreaterThan(0); // el promedio dice de cuántas se compone
    expect(demo.queryByRole('img', { name: /Medición individual/ })).not.toBeInTheDocument(); // nunca un promedio rotulado como medición
  });

  it('los experimentales solo ofrecen promedios diarios: sin vista por medición', async () => {
    await open(HEALTH);
    const experimental = within(screen.getByRole('region', { name: 'Resultados experimentales' }));
    expect(experimental.queryByRole('button', { name: 'Por medición' })).not.toBeInTheDocument();
    expect(experimental.getByText(/el detalle por medición no se expone/)).toBeInTheDocument();
    expect(experimental.queryByRole('img', { name: /Medición individual/ })).not.toBeInTheDocument();
  });

  it('el resumen compacto trae modos, pacientes únicos, alimentación, calidad de señal y datos faltantes', async () => {
    await open(HEALTH);
    const summary = within(within(screen.getByRole('region', { name: 'Datos DEMO (sintéticos)' })).getByLabelText('Resumen de las mediciones incluidas'));
    expect(summary.getByText(/3 de 2 pacientes únicos/)).toBeInTheDocument();
    expect(summary.getByText(/Oximetría 2 · Glucosa \(experimental\) 1/)).toBeInTheDocument();
    expect(summary.getByText(/En ayunas 2 · Después de comer 1/)).toBeInTheDocument();
    expect(summary.getByText(/promedio 0,8 · 2 lecturas/)).toBeInTheDocument();
    expect(summary.getByText(/calidad de señal en 1/)).toBeInTheDocument();
  });

  it('con solo datos DEMO no deja una tarjeta experimental vacía: un aviso compacto y los DEMO con su advertencia', async () => {
    await open({ ...HEALTH, experimentales: withoutGroup('EXPERIMENTAL', 'PROTEGIDO', 'Los resultados experimentales se informan con al menos 5 pacientes distintos.') });
    expect(screen.getByText(/al menos 5 pacientes distintos/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Resultados experimentales' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Datos DEMO (sintéticos)' })).getByText(/Son valores simulados/)).toBeInTheDocument();
  });

  it('con una sola medición DEMO muestra un punto y los valores ausentes como «Sin informar», nunca como cero', async () => {
    const one = group('DEMO', { mediciones: 1, pacientes: 1, glucosa: metric(1, 118, 118, 118), spo2: metric(), frecuenciaCardiaca: metric(1, 81, 81, 81),
      sinInformar: { spo2: 1, frecuenciaCardiaca: 0, glucosa: 0, calidadSenal: 1 }, serieDiaria: [day('2026-10-18', 1, 118, null, 81)],
      puntos: [{ fecha: '2026-10-18T10:00:00', glucosa: 118, spo2: null, frecuenciaCardiaca: 81 }] });
    await open({ ...HEALTH, experimentales: null, demo: one });
    const demo = within(screen.getByRole('region', { name: 'Datos DEMO (sintéticos)' }));
    expect(demo.getAllByRole('img', { name: /Medición individual/ })).toHaveLength(2); // glucosa y frecuencia; SpO₂ no se grafica
    expect(within(demo.getByRole('article', { name: 'SpO₂ — DEMO' })).getByText(/Sin informar en ninguna/)).toBeInTheDocument();
    expect(demo.getByText(/SpO₂ en 1/)).toBeInTheDocument();
  });

  it('un filtro que no se puede aplicar lo explica en lugar de ocultarlo', async () => {
    await open({ ...HEALTH, filtros: { ...HEALTH.filtros, estado: 'CANCELADA' },
      experimentales: withoutGroup('EXPERIMENTAL', 'NO_APLICA', 'Los resultados de salud se calculan solo con mediciones completadas.'),
      demo: withoutGroup('DEMO', 'NO_APLICA', 'Los resultados de salud se calculan solo con mediciones completadas.') });
    expect(screen.getAllByText(/se calculan solo con mediciones completadas/)).toHaveLength(2);
  });
});

describe('Varias mediciones por paciente en el dashboard institucional', () => {
  it('distingue pacientes únicos de mediciones y muestra origen, pacientes con mediciones y alimentación', async () => {
    instRoutes('MODERADOR', { [`GET ${IBASE}/dashboard`]: jsonResponse(200, WITH_ADMIN), [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }) });
    renderAt(`/app/instituciones/${IID}`);
    const kpis = within(await screen.findByRole('list', { name: 'Indicadores administrativos' }));
    expect(kpis.getByText('Pacientes con mediciones').closest('li')).toHaveTextContent(/3.*pacientes distintos · 25 mediciones/); // 3 personas, 25 mediciones
    expect(kpis.getByText('Mediciones en el período').closest('li')).toHaveTextContent('25');
    expect(screen.getByRole('img', { name: 'Mediciones por origen: 25 en total' })).toBeInTheDocument();
    expect(screen.getByText(/3 pacientes distintos aportaron 25 mediciones/)).toBeInTheDocument();
    expect(screen.getByText(/Un paciente puede medirse varias veces el mismo día/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Pacientes según su cantidad de mediciones' })).toBeInTheDocument();
    const food = screen.getByRole('img', { name: 'Mediciones por alimentación' });
    expect(food).toBeInTheDocument();
    expect(food.textContent).toMatch(/Sin informar/);
    expect(screen.queryByText(/Rosa|PAC-/)).not.toBeInTheDocument();
  });
});

describe('Dashboard institucional general', () => {
  it('el moderador lo ve; el operador no lo pide', async () => {
    const { calls } = instRoutes('OPERADOR', {
      [`GET ${IBASE}/operators/me/dashboard`]: jsonResponse(200, {
        periodo: PERIOD, operador: person('op-1', 'Victoria', 'Corti'), pacientesAsignados: 0, pacientes: [], medicionesRealizadas: 0,
        medicionesEnPeriodo: 0, medicionesPorEstado: {}, ultimaActividad: null, realizadas: [], ultimasDePacientes: [],
        transferencias: { recibidas: 0, recibidasPendientes: 0, enviadas: 0, enviadasPendientes: 0 }, dispositivosDisponibles: 0, dispositivos: [], esPropio: true,
      }),
    });
    renderAt(`/app/instituciones/${IID}`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(calls.some((call) => call.key === `GET ${IBASE}/dashboard`)).toBe(false);
  });
});

const OPERATOR_DASHBOARD = {
  periodo: PERIOD, operador: person('op-1', 'Victoria', 'Corti'), pacientesAsignados: 2, medicionesRealizadas: 24, medicionesEnPeriodo: 10,
  medicionesPorEstado: { COMPLETADA: 20, CANCELADA: 4 }, ultimaActividad: '2026-10-08T11:00:00', esPropio: false,
  pacientes: [{ idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-AAA', nombre: 'Rosa', apellido: 'Díaz', datosIdentificativos: true,
    edad: 40, sexoModelo: 'FEMENINO', ultimaMedicion: '2026-10-08T10:00:00' }],
  realizadas: [{ idMedicion: 'm-1', idPerfilMedicion: 'p-9', paciente: 'PAC-ZZZ', fechaHoraInicio: '2026-10-05T09:00:00', modoMedicion: 'OXIMETRIA',
    estadoMedicion: 'COMPLETADA', glucosaEstimada: null, spo2: 97, frecuenciaCardiaca: 70, dispositivo: 'GL-0001' }],
  ultimasDePacientes: [],
  transferencias: { recibidas: 3, recibidasPendientes: 2, enviadas: 1, enviadasPendientes: 0 }, dispositivosDisponibles: 1,
  dispositivos: [{ idDispositivo: 'd-1', codigoDispositivo: 'GL-0001', nombre: 'Oxímetro', modeloSensor: 'MAX30102' }],
};

describe('Dashboard por operador', () => {
  it('el propietario ve la carga de trabajo de un operador, sin sus pacientes ni mediciones individuales', async () => {
    instRoutes('PROPIETARIO', { [`GET ${IBASE}/operators/op-1/dashboard`]: jsonResponse(200, { ...OPERATOR_DASHBOARD, pacientes: [], realizadas: [], ultimasDePacientes: [] }) });
    renderAt(`/app/instituciones/${IID}/personal/operadores/op-1`);
    expect(await screen.findByRole('heading', { name: 'Operador: Victoria Corti' })).toBeInTheDocument();
    const kpis = within(screen.getByRole('list', { name: 'Resumen del operador' }));
    expect(kpis.getByText('Pacientes asignados ahora').closest('li')).toHaveTextContent('2');
    expect(kpis.getByText('Mediciones realizadas (histórico)').closest('li')).toHaveTextContent('24');
    expect(kpis.getByText('Transferencias recibidas').closest('li')).toHaveTextContent('2 pendientes');
    expect(screen.getByText(/Como supervisión ves la carga de trabajo de este operador/)).toBeInTheDocument();
    for (const hidden of ['Pacientes asignados', 'Mediciones realizadas', 'Mediciones de sus pacientes']) {
      expect(screen.queryByRole('list', { name: hidden })).not.toBeInTheDocument();
    }
    expect(screen.queryByText('Rosa Díaz')).not.toBeInTheDocument(); // los pacientes del operador no se listan al supervisor
    expect(screen.queryByRole('link', { name: /Nueva medición/ })).not.toBeInTheDocument();
  });

  it('el operador consulta el suyo: sus pacientes, con acceso a medir, y nada administrativo', async () => {
    instRoutes('OPERADOR', { [`GET ${IBASE}/operators/me/dashboard`]: jsonResponse(200, { ...OPERATOR_DASHBOARD, esPropio: true }) });
    renderAt(`/app/instituciones/${IID}`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes?mios=1&medir=1`);
    expect(screen.queryByRole('link', { name: /Conectar dispositivo/ })).not.toBeInTheDocument(); // se conecta dentro del flujo de medición
    expect(within(screen.getByRole('list', { name: 'Pacientes asignados' })).getByRole('link', { name: 'Medir a Rosa Díaz' })).toBeInTheDocument();
  });

  it('el panel del operador muestra gráficos propios, la última medición DEMO de cada paciente y separa lo DEMO de lo experimental', async () => {
    instRoutes('OPERADOR', {
      [`GET ${IBASE}/operators/me/dashboard`]: jsonResponse(200, { ...OPERATOR_DASHBOARD, esPropio: true, medicionesRealizadas: 1, medicionesRealizadasDemo: 2,
        medicionesEnPeriodo: 1, medicionesEnPeriodoDemo: 2,
        pacientes: [{ ...OPERATOR_DASHBOARD.pacientes[0], ultimaMedicion: '2026-10-17T20:36:00', ultimaModo: 'GLUCOSA_EXPERIMENTAL', ultimaEsDemo: true }],
        realizadas: [{ ...OPERATOR_DASHBOARD.realizadas[0], idMedicion: 'm-d', idPerfilMedicion: 'p-1', esDemo: true }],
        graficos: {
          serie: [{ fecha: '2026-10-15', experimentales: 1, demo: 0 }, { fecha: '2026-10-17', experimentales: 0, demo: 2 }],
          porModo: [{ modo: 'OXIMETRIA', experimentales: 1, demo: 1 }, { modo: 'GLUCOSA_EXPERIMENTAL', experimentales: 0, demo: 1 }],
          calidadSenal: { conValor: 2, sinDato: 1, fueraDeAlcance: 0, minimo: 0.5, maximo: 0.9,
            rangos: [{ desde: 0.5, hasta: 0.7, experimentales: 1, demo: 0 }, { desde: 0.7, hasta: 0.9, experimentales: 0, demo: 1 }],
            conLecturas: 2, lecturas: [{ lecturas: 4, experimentales: 1, demo: 1 }] },
          demografia: [{ rango: '0-17', masculino: 0, femenino: 0, sinInformar: 0 }, { rango: '18-39', masculino: 0, femenino: 1, sinInformar: 0 },
            { rango: 'SIN_INFORMAR', masculino: 0, femenino: 0, sinInformar: 1 }], pacientesDemografia: 2, truncado: false,
        } }),
      [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }),
    });
    renderAt(`/app/instituciones/${IID}`);
    const kpis = within(await screen.findByRole('list', { name: 'Resumen del operador' }));
    // El total incluye lo DEMO, que se informa aparte: nada de mezclarlo en silencio.
    expect(kpis.getByText('Mediciones realizadas (histórico)').closest('li')).toHaveTextContent(/3.*1 experimentales · 2 DEMO/);
    expect(kpis.getByText('Mediciones en el período').closest('li')).toHaveTextContent(/3.*1 experimentales · 2 DEMO/);
    const charts = within(await screen.findByRole('region', { name: 'Gráficos de mi trabajo' }));
    // Distribución por modo: las cantidades salen de las mismas mediciones (2 de oximetría + 1 de glucosa = 3).
    expect(charts.getByRole('img', { name: 'Mediciones por modo: 3 en total' })).toBeInTheDocument();
    expect(within(charts.getByRole('list', { name: 'Detalle de Mediciones por modo' })).getByText(/Oximetría/)).toHaveTextContent(/1 DEMO/);
    expect(charts.getByRole('img', { name: 'Mediciones por rango de calidad de señal registrada' })).toBeInTheDocument();
    expect(charts.getByText(/2 con calidad.*1 sin dato.*no define umbrales/)).toBeInTheDocument(); // sin categorías clínicas inventadas
    expect(charts.getByRole('img', { name: 'Lecturas estabilizadas por medición' })).toBeInTheDocument(); // lo que sí registra el equipo, aparte de la calidad
    expect(charts.getByRole('img', { name: 'Pacientes por rango de edad y sexo' })).toBeInTheDocument();
    expect(charts.getAllByText(/Sin informar \(1\)/).length).toBeGreaterThan(0); // el paciente sin edad ni sexo cuenta como categoría, no desaparece
    expect(charts.getByRole('link', { name: /Análisis detallado de mediciones/ })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes/analisis?dias=30&origen=TODOS`); // mismo período y todas las fuentes
    // Un paciente con solo mediciones DEMO no figura «sin mediciones»: se muestra la última, identificada como DEMO.
    const patients = within(screen.getByRole('list', { name: 'Pacientes asignados' }));
    expect(patients.getByText(/17\/10\/2026/)).toBeInTheDocument();
    expect(patients.getByText('DEMO')).toBeInTheDocument();
    expect(patients.queryByText(/Sin mediciones/)).not.toBeInTheDocument();
    const performed = within(screen.getByRole('list', { name: 'Mediciones realizadas' }));
    expect(performed.getByText('DEMO')).toBeInTheDocument();
    expect(performed.getByRole('link', { name: 'PAC-ZZZ' })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes/p-1/mediciones/m-d`);
  });

  it('el panel del operador sigue el diseño: indicadores con ayuda, actividad, pacientes asignados y tres tarjetas de trabajo', async () => {
    const recent = new Date(Date.now() - 6 * 3600 * 1000).toISOString();
    instRoutes('OPERADOR', {
      [`GET ${IBASE}/operators/me/dashboard`]: jsonResponse(200, { ...OPERATOR_DASHBOARD, esPropio: true, ultimaActividad: recent, realizadas: [], ultimasDePacientes: [],
        dispositivos: [], dispositivosDisponibles: 0, transferencias: { recibidas: 0, recibidasPendientes: 0, enviadas: 2, enviadasPendientes: 1 },
        pacientes: [{ ...OPERATOR_DASHBOARD.pacientes[0], nombre: 'Samd', apellido: 'Fdsfdsdfs', ultimaMedicion: null, identificadorPseudonimo: 'PAC-ECC8' }] }),
      [`GET ${IBASE}/activity`]: jsonResponse(200, { items: [] }),
    });
    renderAt(`/app/instituciones/${IID}`);
    expect(await screen.findByRole('heading', { name: 'Mi dashboard de trabajo' })).toBeInTheDocument();
    expect(screen.getByText('Indicadores de tu actividad como operador.')).toBeInTheDocument();
    const kpis = within(screen.getByRole('list', { name: 'Resumen del operador' }));
    expect(kpis.getByText('Pacientes asignados ahora').closest('li')).toHaveTextContent('pacientes a tu cargo');
    expect(kpis.getByText('Mediciones realizadas (histórico)').closest('li')).toHaveTextContent('en total');
    expect(kpis.getByText('Mediciones en el período').closest('li')).toHaveTextContent('últimos 30 días');
    expect(kpis.getByText('Última actividad').closest('li')).toHaveTextContent('hace 6 horas');
    const work = within(screen.getByRole('list', { name: 'Transferencias y dispositivos' }));
    expect(work.getByText('Transferencias enviadas').closest('li')).toHaveTextContent('1 pendiente');
    expect(work.getByText('Dispositivos disponibles').closest('li')).toHaveTextContent('operativos');
    expect(screen.getByRole('combobox', { name: 'Período' })).toHaveValue('30'); // el filtro de período va en el encabezado

    // Orden: dashboard, actividad, pacientes asignados y tarjetas de trabajo.
    await screen.findByRole('heading', { name: 'Pacientes asignados' });
    const headings = screen.getAllByRole('heading').map((heading) => heading.textContent);
    const order = ['Mi dashboard de trabajo', 'Mi actividad reciente', 'Pacientes asignados', 'Últimas mediciones que realizó',
      'Últimas mediciones de tus pacientes', 'Dispositivos disponibles'];
    const positions = order.map((title) => headings.indexOf(title));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));

    const patients = within(screen.getByRole('list', { name: 'Pacientes asignados' }));
    expect(patients.getByText('Samd Fdsfdsdfs')).toBeInTheDocument();
    expect(patients.getByText('SF')).toBeInTheDocument(); // iniciales
    expect(patients.getByText('Identificador: PAC-ECC8')).toBeInTheDocument();
    expect(patients.getByText('Sin mediciones completadas')).toBeInTheDocument();
    expect(patients.getByRole('link', { name: /Ver ficha/ })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes/p-1`);
    expect(patients.queryByRole('link', { name: /Dashboard/ })).not.toBeInTheDocument(); // el dashboard del paciente se quitó
    expect(screen.getByRole('link', { name: /Ver todos mis pacientes/ })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes?mios=1`);
    // Estados vacíos de las tres tarjetas.
    expect(screen.getAllByText('Sin mediciones para mostrar')).toHaveLength(2);
    expect(screen.getByText('Todavía no realizaste mediciones.')).toBeInTheDocument();
    expect(screen.getByText('Tus pacientes aún no tienen mediciones registradas.')).toBeInTheDocument();
    expect(screen.getByText('No hay dispositivos operativos')).toBeInTheDocument();
    expect(screen.getByText('En este momento no hay dispositivos disponibles para realizar mediciones.')).toBeInTheDocument();
  });

  it('un operador inexistente o de otra institución se informa como no encontrado', async () => {
    instRoutes('MODERADOR', { [`GET ${IBASE}/operators/op-9/dashboard`]: jsonResponse(404, { codigo: 'MIEMBRO_NO_ENCONTRADO', detail: 'No encontramos a ese operador en la institución.' }) });
    renderAt(`/app/instituciones/${IID}/personal/operadores/op-9`);
    expect(await screen.findByText('No encontramos a ese operador en la institución.')).toBeInTheDocument();
  });
});

describe('Dashboard por paciente (quitado)', () => {
  it('el enlace viejo /pacientes/:id/dashboard lleva a la ficha, que reúne perfil, historial y estadísticas', async () => {
    instRoutes('OPERADOR', {
      [`GET ${IBASE}/patients/p-1`]: jsonResponse(200, { idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-AAA', nombre: 'Rosa', apellido: 'Díaz', dni: null,
        fechaNacimiento: null, edad: null, sexoModelo: null, estado: 'ACTIVO', fechaCreacion: '2026-10-03T09:00:00', fechaUltimaMedicion: null,
        fechaExpiracionDatosPersonales: null, responsable: person('op-1', 'Ana', 'Paz'), puedeModificar: true, esMio: true, medicionesAutorizadas: true }),
      [`GET ${IBASE}/patients/p-1/measurements`]: jsonResponse(200, { items: [], total: 0, pagina: 1, tamanioPagina: 10 }),
      [`GET ${IBASE}/patients/p-1/measurements/evolution`]: jsonResponse(200, { puntos: [], truncado: false, desde: null, hasta: null, estadisticas: { experimental: null, demo: null }, resumen: null }),
    });
    renderAt(`/app/instituciones/${IID}/pacientes/p-1/dashboard`);
    expect(await screen.findByRole('heading', { name: 'Díaz, Rosa' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Nueva medición/ })).toHaveAttribute('href', `/app/instituciones/${IID}/pacientes/p-1/medir`);
    expect(screen.queryByRole('heading', { name: 'Perfil del paciente' })).not.toBeInTheDocument();
  });
});
