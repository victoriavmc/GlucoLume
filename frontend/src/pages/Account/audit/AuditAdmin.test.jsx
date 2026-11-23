import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const account = (tipoCuenta) => ({ ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta } });
const ADMIN = account('ADMINISTRADOR_PLATAFORMA');
const INSTITUTIONAL = account('USUARIO_INSTITUCIONAL');
const INSTITUTION_ID = '9a000000-0000-4000-8000-000000000001';
const USER_ID = '7b000000-0000-4000-8000-0000000000aa';
const BASE = `/institutions/${INSTITUTION_ID}`;

function event(overrides = {}) {
  return {
    idAuditoria: 'e-1', fechaHora: '2026-10-09T14:32:16-03:00', usuario: 'Ana Paz', modulo: 'CUENTA', accion: 'LOGIN_LOCAL', accionEtiqueta: 'Inicio de sesión',
    tipoEntidad: null, idEntidad: null, idInstitucion: INSTITUTION_ID, nombreInstitucion: 'Hospital X', resultado: 'FALLO', descripcion: 'Contraseña inválida',
    critica: false, rechazado: false, entidadEtiqueta: null, severidad: 'ADVERTENCIA', clasificacion: 'OPERATIVO', origenActor: 'USUARIO',
    motivo: 'PASSWORD_INCORRECTA', motivoEtiqueta: 'Contraseña incorrecta', ipOrigen: '203.0.113.7', agenteUsuario: 'Chrome · Windows · Computadora',
    idCorrelacion: 'corr-abc-123', referenciaIdentificador: null, ...overrides,
  };
}

const SUMMARY = {
  total: 6, exitosos: 1, fallidos: 5, criticas: 1, accesosFallidos: 4, sospechosos: 1, confirmados: 1,
  porModulo: [{ clave: 'CUENTA', nombre: null, total: 5 }], porInstitucion: [{ clave: INSTITUTION_ID, nombre: 'Hospital X', total: 5 }],
};
const SIGNALS = {
  desde: '2026-10-08', hasta: '2026-10-09', contextoDisponible: true, truncado: false,
  umbrales: { ventanaMinutos: 15, fallosPorCuenta: 5, cuentasPorOrigen: 5, historialOrigenInusual: 5 },
  indicadores: { intentosFallidos: 9, cuentasAfectadas: 3, origenesDistintos: 2, bloqueos: 1, limitesExcedidos: 0, rafagasRechazos: 0 },
  senales: [
    { tipo: 'FALLOS_REPETIDOS_CUENTA', clasificacion: 'SOSPECHOSO', titulo: 'Accesos fallidos repetidos contra una cuenta', descripcion: '6 accesos fallidos en 15 minutos.',
      cantidad: 6, umbral: 5, desde: '2026-10-09T10:00:00-03:00', hasta: '2026-10-09T10:09:00-03:00', ipOrigen: null, cuenta: 'Ana Paz',
      filtros: { idCuenta: USER_ID, categoria: 'ACCESOS_FALLIDOS' } },
    { tipo: 'BLOQUEOS_CUENTA', clasificacion: 'CONFIRMADO', titulo: 'Cuentas bloqueadas temporalmente', descripcion: 'El sistema aplicó el control 1 vez/veces.',
      cantidad: 1, umbral: null, desde: '2026-10-09T10:09:00-03:00', hasta: '2026-10-09T10:09:00-03:00', ipOrigen: null, cuenta: null,
      filtros: { accion: 'BLOQUEO_TEMPORAL_CUENTA' } },
  ],
};
const EMPTY_SIGNALS = { ...SIGNALS, senales: [], indicadores: { ...SIGNALS.indicadores, intentosFallidos: 1, bloqueos: 0 } };
const page = (items, total = items.length) => jsonResponse(200, { items, total, pagina: 1, tamanioPagina: 20 });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

const routes = (me, extra = {}) => mockApi({ 'GET /auth/me': jsonResponse(200, me), ...extra });
const lastParams = (calls, key) => Object.fromEntries(new URL(calls.filter((call) => call.key === key).at(-1).url).searchParams);

describe('Auditoría de la administración: tres ámbitos', () => {
  it('muestra una sola auditoría general, sin pestañas de ámbito, y pide los eventos sin parámetros de ámbito', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    renderAt('/app/auditoria');
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
    expect(screen.queryByRole('tablist', { name: 'Ámbito de la auditoría' })).not.toBeInTheDocument();
    expect(lastParams(calls, 'GET /audit')).toEqual({ pagina: '1', tamanioPagina: '20' });
  });

  it('pide los eventos por página y nunca más de veinte a la vez', async () => {
    const { calls } = routes(ADMIN, {
      'GET /audit': () => page([event()], 4500), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS),
    });
    renderAt('/app/auditoria');
    expect(await screen.findByText('Página 1 de 225 · 4500 eventos')).toBeInTheDocument();
    expect(calls.filter((call) => call.key === 'GET /audit').every((call) => new URL(call.url).searchParams.get('tamanioPagina') === '20')).toBe(true);
  });

  it('los eventos llevan color semántico y texto: advertencia, crítico, sospechoso y control activado', async () => {
    routes(ADMIN, {
      'GET /audit': page([
        event({ idAuditoria: 'a', severidad: 'EXITO', resultado: 'EXITO', accion: 'LOGIN_PWD', accionEtiqueta: 'Inicio de sesión', motivo: null, motivoEtiqueta: null }),
        event({ idAuditoria: 'b' }),
        event({ idAuditoria: 'c', severidad: 'CRITICO', clasificacion: 'CONFIRMADO', accion: 'BLOQUEO_TEMPORAL_CUENTA', accionEtiqueta: 'Bloqueo temporal por intentos fallidos' }),
        event({ idAuditoria: 'd', severidad: 'ADVERTENCIA', clasificacion: 'SOSPECHOSO', accion: 'RAFAGA_RECHAZOS_HTTP', accionEtiqueta: 'Ráfaga de solicitudes rechazadas (401/403)' }),
        event({ idAuditoria: 'e', severidad: 'INFO', resultado: 'EXITO', accion: 'CONSULTAR_PACIENTE', accionEtiqueta: 'Consulta de un paciente', motivo: null, motivoEtiqueta: null }),
      ]),
      'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS),
    });
    renderAt('/app/auditoria');
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    const rows = table.getAllByRole('row').slice(1);
    expect(rows.map((row) => ['is-exito', 'is-advertencia', 'is-critico', 'is-info'].find((name) => row.classList.contains(name)))).toEqual(
      ['is-exito', 'is-advertencia', 'is-critico', 'is-advertencia', 'is-info']);
    expect(table.getByText('Control activado')).toBeInTheDocument();
    expect(table.getByText('Actividad sospechosa')).toBeInTheDocument();
    expect(table.getAllByText('Contraseña incorrecta').length).toBeGreaterThan(0);
    expect(table.queryByText('Error operativo')).not.toBeInTheDocument(); // un fallo aislado no se rotula como ataque ni como sospechoso
  });

  it('muestra la IP y marca lo hecho por la administración de GlucoLume', async () => {
    routes(ADMIN, {
      'GET /audit': page([event({ idAuditoria: 'a', usuario: 'Victoria Cortés', origenActor: 'PLATAFORMA', ipOrigen: null }), event({ idAuditoria: 'b' })]),
      'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS),
    });
    renderAt('/app/auditoria');
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Administración')).toBeInTheDocument();
    expect(table.getByText('IP 203.0.113.7')).toBeInTheDocument();
  });

  it('la auditoría general no muestra el resumen de seguridad (el listado sigue disponible)', async () => {
    routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    renderAt('/app/auditoria');
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
    expect(screen.queryByRole('list', { name: 'Seguridad según los filtros' })).not.toBeInTheDocument();
  });
  it('los filtros nuevos (tipo de evento, clasificación, autor, correlación, IP y correo consultado) viajan al backend', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': () => page([]), 'GET /audit/summary': () => jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await screen.findByText('Todavía no hay eventos registrados.');
    await user.selectOptions(screen.getByLabelText('Tipo de evento'), 'ACCESOS_FALLIDOS');
    await user.selectOptions(screen.getByLabelText('Clasificación'), 'SOSPECHOSO');
    await user.type(screen.getByLabelText('IP de origen'), '203.0.113.*');
    await waitFor(() => {
      expect(lastParams(calls, 'GET /audit')).toEqual({
        categoria: 'ACCESOS_FALLIDOS', clasificacion: 'SOSPECHOSO', ip: '203.0.113.*', pagina: '1', tamanioPagina: '20',
      });
      expect(lastParams(calls, 'GET /audit/summary')).toMatchObject({ categoria: 'ACCESOS_FALLIDOS', ip: '203.0.113.*' });
    }, { timeout: 5000 });
  });
});

describe('Eventos críticos de seguridad', () => {
  it('muestra las señales que requieren revisión, cada una con «Ver evento»', async () => {
    routes(ADMIN, {
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS),
    });
    renderAt('/app/auditoria');
    const list = within(await screen.findByRole('list', { name: 'Eventos críticos de seguridad' }));
    expect(list.getAllByRole('listitem')).toHaveLength(SIGNALS.senales.length);
    expect(screen.getAllByRole('button', { name: /Ver evento:/ })).toHaveLength(SIGNALS.senales.length);
    expect(screen.getByText(SIGNALS.senales[0].titulo)).toBeInTheDocument();
  });

  it('sin señales que revisar muestra 0 y ninguna tarjeta', async () => {
    routes(ADMIN, {
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, EMPTY_SIGNALS),
    });
    renderAt('/app/auditoria');
    expect(await screen.findByText('0 eventos críticos en los últimos 7 días.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Eventos críticos de seguridad' })).not.toBeInTheDocument();
  });
});

describe('Detalle del evento y acceso', () => {
  it('el detalle del administrador muestra el origen de la solicitud y el motivo', async () => {
    routes(ADMIN, {
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, EMPTY_SIGNALS),
      'GET /audit/events/e-1': jsonResponse(200, { ...event(), tipoEvento: 'LOGIN', tablaRelacionada: null, idRelacionado: null, valoresPrevios: null, valoresNuevos: null, referencias: [] }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await user.click(await screen.findByRole('link', { name: /Ver detalle/ }));
    const origin = within((await screen.findByRole('heading', { name: 'Origen de la solicitud' })).closest('section'));
    expect(origin.getByText('203.0.113.7')).toBeInTheDocument();
    expect(origin.getByText('corr-abc-123')).toBeInTheDocument();
    expect(origin.getByText('Chrome · Windows · Computadora')).toBeInTheDocument();
    expect(origin.getByText(/nunca se guardan contraseñas, tokens ni códigos/)).toBeInTheDocument();
    expect(screen.getAllByText('Contraseña incorrecta').length).toBeGreaterThan(0);
    expect(screen.getByText('Error operativo')).toBeInTheDocument();
    expect(screen.getByText(/No es un ataque por sí solo/)).toBeInTheDocument();
  });

  it('un propietario no ve IP, cliente ni correlación, ni los filtros de red, ni las pestañas de la administración', async () => {
    const OWN = event({ ipOrigen: null, agenteUsuario: null, idCorrelacion: null });
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, {
        idInstitucion: INSTITUTION_ID, nombre: 'Hospital X', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: 'PROPIETARIO', estadoRelacion: 'ACTIVO',
        permisos: ['CONSULTAR_INSTITUCION', 'CONSULTAR_AUDITORIA'], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null,
        fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' },
        cantidadModeradores: 0, cantidadOperadores: 0, cantidadPacientes: 0,
      }),
      [`GET ${BASE}/audit`]: page([OWN, event({ idAuditoria: 'e-2', usuario: 'Victoria Cortés', origenActor: 'PLATAFORMA', ipOrigen: null, resultado: 'EXITO', severidad: 'EXITO',
        accion: 'MODIFICAR_INSTITUCION', accionEtiqueta: 'Modificación de datos de la institución', motivo: null, motivoEtiqueta: null })]),
      [`GET ${BASE}/audit/summary`]: jsonResponse(200, { ...SUMMARY, porInstitucion: [] }),
      [`GET ${BASE}/audit/events/e-1`]: jsonResponse(200, { ...OWN, tipoEvento: 'LOGIN', tablaRelacionada: null, idRelacionado: null, valoresPrevios: null, valoresNuevos: null, referencias: [] }),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${INSTITUTION_ID}/auditoria`);
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Administración')).toBeInTheDocument(); // distingue lo hecho por la administración de GlucoLume
    expect(table.getAllByText('Contraseña incorrecta').length).toBeGreaterThan(0);
    expect(screen.queryByText(/IP 203/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('IP de origen')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('IP de origen')).not.toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: 'Ámbito de la auditoría' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Seguridad y accesos fallidos/ })).not.toBeInTheDocument();
    await user.click(screen.getAllByRole('link', { name: /Ver detalle/ })[0]);
    await screen.findByRole('heading', { name: 'Detalle del evento' });
    expect(screen.queryByRole('heading', { name: 'Origen de la solicitud' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('203.0.113.7');
  });

  it('una cuenta que no es administradora no consulta nada de seguridad', async () => {
    const { calls } = routes(ACCOUNT, { 'GET /groups/mine': jsonResponse(200, { grupo: null }), 'GET /groups/invitations': jsonResponse(200, []) });
    renderAt('/app/auditoria');
    await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(screen.queryByRole('tablist', { name: 'Ámbito de la auditoría' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith('GET /audit'))).toBe(false);
  });
});
