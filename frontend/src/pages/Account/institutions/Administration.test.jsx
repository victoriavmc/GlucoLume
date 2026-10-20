import { configure, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'CONSULTAR_AUDITORIA'],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO', 'CONSULTAR_PACIENTES'],
};

const institution = (rol, extra = {}) => ({
  idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
  estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
  descripcion: 'Atención ambulatoria', fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-02T11:30:00',
  propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0,
  cantidadReaperturas: 0, ...extra,
});

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

const open = (rol, path, extra) => {
  mockApi({ 'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET /institutions/${ID}`]: jsonResponse(200, institution(rol, extra)) });
  renderAt(`/app/instituciones/${ID}/administracion/${path}`);
};

describe('Administración → Datos', () => {
  it('organiza los datos en tres secciones, con el CUIT legible y sin identificadores internos', async () => {
    open('PROPIETARIO', 'datos');
    const general = within((await screen.findByRole('heading', { name: 'Información general' })).closest('section'));
    expect(general.getByText('Centro Médico San José')).toBeInTheDocument();
    expect(general.getByText('Clínica')).toBeInTheDocument();
    expect(general.getByText('Atención ambulatoria')).toBeInTheDocument();
    const legal = within(screen.getByRole('heading', { name: 'Identificación legal' }).closest('section'));
    expect(legal.getByText('30-71234567-1')).toBeInTheDocument();
    expect(legal.getByText(/No se puede modificar/)).toBeInTheDocument();
    const state = within(screen.getByRole('heading', { name: 'Estado y registro' }).closest('section'));
    for (const label of ['Estado actual', 'Propietario/a', 'Fecha de creación', 'Última actualización', 'Cantidad de reaperturas']) {
      expect(state.getByText(label, { selector: 'dt' })).toBeInTheDocument();
    }
    expect(state.getByText('Victoria Cortés')).toBeInTheDocument();
    expect(state.queryByText('Fecha de última reapertura')).not.toBeInTheDocument(); // no hubo reaperturas
    expect(screen.queryByText(new RegExp(ID))).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Editar datos/ })).toBeInTheDocument();
  });

  it('con reaperturas muestra la fecha de la última; quien no es propietario no ve «Editar datos»', async () => {
    open('MODERADOR', 'datos', { cantidadReaperturas: 2, fechaUltimaReapertura: '2026-10-05T09:00:00' });
    const state = within((await screen.findByRole('heading', { name: 'Estado y registro' })).closest('section'));
    expect(state.getByText('Fecha de última reapertura')).toBeInTheDocument();
    expect(state.getByText('05/10/2026 09:00')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Editar datos/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Solo el propietario de la institución puede modificar/)).toBeInTheDocument();
  });
});

describe('Datos institucionales: zona de riesgo', () => {
  it('muestra el título de la página, la zona de riesgo con la eliminación y ninguna pestaña', async () => {
    open('PROPIETARIO', 'datos');
    expect(await screen.findByRole('heading', { name: 'Datos institucionales' })).toBeInTheDocument();
    expect(screen.getByText(/Última actualización: 02\/10\/2026 11:30/)).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Secciones de administración' })).not.toBeInTheDocument();
    const risk = within(screen.getByRole('heading', { name: 'Zona de riesgo' }).closest('div'));
    expect(risk.getByRole('heading', { name: 'Eliminar institución' })).toBeInTheDocument();
    expect(risk.getByText(/escribir el nombre exacto de la institución/)).toBeInTheDocument();
    expect(risk.getByRole('button', { name: 'Eliminar institución' })).toBeInTheDocument();
  });

  it('el moderador ve los datos pero no la zona de riesgo', async () => {
    open('MODERADOR', 'datos');
    expect(await screen.findByRole('heading', { name: 'Datos institucionales' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Zona de riesgo' })).not.toBeInTheDocument();
  });
});

describe('Actividad reciente del panel', () => {
  const dashboard = {
    periodo: { dias: 30, desde: null, hasta: null }, pacientesActivos: 0, moderadoresActivos: 0, operadoresActivos: 0, dispositivosRegistrados: 0,
    dispositivosOperativos: 0, medicionesTotal: 0, medicionesHoy: 0, medicionesUltimos7Dias: 0, medicionesUltimos30Dias: 0, medicionesEnPeriodo: 0,
    porEstado: {}, porModo: {}, ultimaActividad: null, serie: [], porOperador: [],
    estadisticas: { dias: 30, cantidadMediciones: 0, serieDiaria: [] },
  };
  const item = (extra) => ({
    titulo: 'Moderador incorporado', categoria: 'MODERADORES', entidad: 'Victoria Valentina Collins', usuario: 'Victoriavmc',
    fechaHora: '2026-10-15T16:15:00-03:00', resultado: 'EXITO', critica: false, rechazado: false, ruta: 'personal/moderadores', idAuditoria: 'a-1', ...extra,
  });
  const open = (rol, items) => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET /institutions/${ID}`]: jsonResponse(200, institution(rol)),
      [`GET /institutions/${ID}/dashboard`]: jsonResponse(200, dashboard), [`GET /institutions/${ID}/activity`]: jsonResponse(200, { items }),
    });
    renderAt(`/app/instituciones/${ID}`);
  };

  it('resume la actividad con nombre, entidad, responsable, día y hora, criticidad y enlace a su pantalla', async () => {
    open('PROPIETARIO', [
      item(),
      item({ titulo: 'Dispositivo descomisionado', categoria: 'DISPOSITIVOS', entidad: 'Dispositivo GL-0001', usuario: 'Victoriavmc', critica: true,
        ruta: 'dispositivos/d-1' }),
      item({ titulo: 'Operación rechazada: Consulta de la auditoría', categoria: 'SEGURIDAD', entidad: null, usuario: null, rechazado: true, critica: true,
        ruta: 'auditoria/a-3', idAuditoria: 'a-3' }),
    ]);
    const list = within(await screen.findByRole('list', { name: 'Actividad reciente' }));
    const rows = list.getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('Moderador incorporado');
    expect(rows[0]).toHaveTextContent('Victoria Valentina Collins');
    expect(rows[0]).toHaveTextContent('Realizado por Victoriavmc');
    expect(rows[0]).toHaveTextContent(/\d{2}\/\d{2}\/\d{4} — \d{2}:\d{2}/);
    // El propietario abre el evento de auditoría puntual de cada actividad (no la pantalla del módulo).
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/auditoria/a-1`);
    expect(rows[1]).toHaveTextContent('Dispositivo GL-0001');
    expect(rows[1]).toHaveTextContent('Crítica');
    expect(within(rows[1]).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/auditoria/a-1`);
    expect(rows[2]).toHaveTextContent('Rechazado');
    expect(rows[2]).toHaveTextContent('Realizado por el sistema');
    expect(within(rows[2]).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/auditoria/a-3`);
    expect(screen.getByRole('link', { name: /Ver toda la actividad/ })).toHaveAttribute('href', `/app/instituciones/${ID}/actividad`);
    expect(screen.queryByRole('link', { name: /Ver auditoría/ })).not.toBeInTheDocument(); // Actividad no es Auditoría
  });

  it('un integrante sin acceso a la auditoría ve la actividad y «Ver toda la actividad»; una actividad sin ruta no es un enlace', async () => {
    open('MODERADOR', [item({ titulo: 'Operador incorporado', categoria: 'OPERADORES', ruta: null, idAuditoria: null })]);
    const list = within(await screen.findByRole('list', { name: 'Actividad reciente' }));
    expect(list.getByText('Operador incorporado')).toBeInTheDocument();
    expect(list.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Ver auditoría/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ver toda la actividad/ })).toHaveAttribute('href', `/app/instituciones/${ID}/actividad`);
  });

  it('la página Actividad muestra la actividad (hasta 20) para cualquier integrante, sin ser Auditoría', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET /institutions/${ID}`]: jsonResponse(200, institution('MODERADOR')),
      [`GET /institutions/${ID}/activity`]: jsonResponse(200, { items: [item({ ruta: null, idAuditoria: null })] }),
    });
    renderAt(`/app/instituciones/${ID}/actividad`);
    expect(await screen.findByRole('heading', { name: 'Actividad' })).toBeInTheDocument();
    expect(await screen.findByText('Moderador incorporado')).toBeInTheDocument(); // la lista llega después del encabezado
    expect(screen.queryByRole('link', { name: /Ver toda la actividad/ })).not.toBeInTheDocument();
    expect(calls.find((call) => call.key === `GET /institutions/${ID}/activity`).url).toContain('limite=20');
    expect(calls.some((call) => call.key.includes('/audit'))).toBe(false);
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Actividad')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Volver al panel' })).toHaveAttribute('href', `/app/instituciones/${ID}`);
  });

  it('quien no puede auditar abre la pantalla relacionada de cada actividad', async () => {
    open('MODERADOR', [item({ idAuditoria: null }), item({ titulo: 'Dispositivo descomisionado', categoria: 'DISPOSITIVOS', ruta: 'dispositivos/d-1', idAuditoria: null })]);
    const rows = within(await screen.findByRole('list', { name: 'Actividad reciente' })).getAllByRole('listitem');
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/personal/moderadores`);
    expect(within(rows[1]).getByRole('link')).toHaveAttribute('href', `/app/instituciones/${ID}/dispositivos/d-1`);
  });

  it('sin actividad muestra un estado vacío', async () => {
    open('PROPIETARIO', []);
    expect(await screen.findByText('Todavía no hay actividad registrada.')).toBeInTheDocument();
  });
});

describe('Panel institucional: administración, accesos y resumen', () => {
  const dashboard = {
    periodo: { dias: 30, desde: null, hasta: null }, pacientesActivos: 0, moderadoresActivos: 1, operadoresActivos: 0, dispositivosRegistrados: 0,
    dispositivosOperativos: 0, medicionesTotal: 0, medicionesHoy: 0, medicionesUltimos7Dias: 0, medicionesUltimos30Dias: 0, medicionesEnPeriodo: 0,
    porEstado: {}, porModo: {}, ultimaActividad: null, serie: [], porOperador: [], estadisticas: { dias: 30, cantidadMediciones: 0, serieDiaria: [] },
  };
  const openPanel = (rol, extra = {}) => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET /institutions/${ID}`]: jsonResponse(200, institution(rol, { cantidadModeradores: 1, ...extra })),
      [`GET /institutions/${ID}/dashboard`]: jsonResponse(200, dashboard), [`GET /institutions/${ID}/activity`]: jsonResponse(200, { items: [] }),
    });
    renderAt(`/app/instituciones/${ID}`);
  };

  it('el propietario ve la administración institucional con sus accesos y el resumen en el orden del diseño', async () => {
    openPanel('PROPIETARIO');
    const admin = within((await screen.findByRole('heading', { name: 'Administración institucional' })).closest('section'));
    expect(admin.getByRole('link', { name: /Datos institucionales/ })).toHaveAttribute('href', `/app/instituciones/${ID}/administracion/datos`);
    expect(admin.getByRole('link', { name: /Moderadores/ })).toHaveAttribute('href', `/app/instituciones/${ID}/personal/moderadores`);
    expect(admin.getByRole('link', { name: /Operadores/ })).toHaveAttribute('href', `/app/instituciones/${ID}/personal/operadores`);
    expect(admin.getByRole('link', { name: /Auditoría/ })).toHaveAttribute('href', `/app/instituciones/${ID}/auditoria`);
    expect(admin.getByText(/Última actualización/)).toBeInTheDocument();
    const summary = within(screen.getByRole('region', { name: 'Resumen de la institución' }));
    const labels = summary.getAllByText(/^(Pacientes|Moderadores|Operadores|Dispositivos)$/).map((e) => e.textContent);
    expect(labels).toEqual(['Pacientes', 'Operadores', 'Moderadores']); // Dispositivos llega con la consulta de dispositivos
    expect(summary.getByRole('link', { name: 'Moderadores: 1 activo' })).toHaveAttribute('href', `/app/instituciones/${ID}/personal/moderadores`);
    expect(screen.queryByText('Tu rol')).not.toBeInTheDocument(); // el rol y el estado ya están en el encabezado
  });

  it('el moderador ve solo los accesos que le corresponden: datos y operadores, sin moderadores ni auditoría', async () => {
    openPanel('MODERADOR');
    const admin = within((await screen.findByRole('heading', { name: 'Administración institucional' })).closest('section'));
    expect(admin.getByRole('link', { name: /Datos institucionales/ })).toBeInTheDocument();
    expect(admin.getByRole('link', { name: /Operadores/ })).toBeInTheDocument();
    expect(admin.queryByRole('link', { name: /Moderadores/ })).not.toBeInTheDocument();
    expect(admin.queryByRole('link', { name: /Auditoría/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Moderadores: / })).not.toBeInTheDocument();
  });
});
