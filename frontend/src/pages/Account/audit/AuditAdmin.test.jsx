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
  it('ofrece Plataforma general, Instituciones y Cuentas individuales, y empieza en la plataforma sin parámetros de ámbito', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    renderAt('/app/auditoria');
    const tabs = within(await screen.findByRole('tablist', { name: 'Ámbito de la auditoría' }));
    expect(tabs.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Plataforma general', 'Instituciones', 'Cuentas individuales']);
    expect(tabs.getByRole('tab', { name: 'Plataforma general' })).toHaveAttribute('aria-selected', 'true');
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
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

  it('el resumen incluye accesos fallidos, eventos sospechosos y controles activados', async () => {
    routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    renderAt('/app/auditoria');
    const security = within(await screen.findByRole('list', { name: 'Seguridad según los filtros' }));
    expect(security.getByText('Accesos fallidos').closest('li')).toHaveTextContent('4');
    expect(security.getByText('Eventos sospechosos').closest('li')).toHaveTextContent('1');
    expect(security.getByText('Controles activados').closest('li')).toHaveTextContent('1');
  });

  it('los filtros nuevos (tipo de evento, clasificación, autor, correlación, IP y correo consultado) viajan al backend', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': () => page([]), 'GET /audit/summary': () => jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await screen.findByText('Todavía no hay eventos registrados.');
    await user.selectOptions(screen.getByLabelText('Tipo de evento'), 'ACCESOS_FALLIDOS');
    await user.selectOptions(screen.getByLabelText('Clasificación'), 'SOSPECHOSO');
    await user.selectOptions(screen.getByLabelText('Autor del evento'), 'PLATAFORMA');
    await user.type(screen.getByLabelText('Identificador de correlación'), 'corr-abc-123');
    await user.type(screen.getByLabelText('IP de origen'), '203.0.113.*');
    await user.type(screen.getByLabelText('Correo o usuario consultado'), 'fantasma@example.com');
    await waitFor(() => {
      expect(lastParams(calls, 'GET /audit')).toEqual({
        categoria: 'ACCESOS_FALLIDOS', clasificacion: 'SOSPECHOSO', origenActor: 'PLATAFORMA', idCorrelacion: 'corr-abc-123', ip: '203.0.113.*',
        identificador: 'fantasma@example.com', pagina: '1', tamanioPagina: '20',
      });
      expect(lastParams(calls, 'GET /audit/summary')).toMatchObject({ categoria: 'ACCESOS_FALLIDOS', ip: '203.0.113.*' });
    }, { timeout: 5000 });
  });
});

describe('Seguridad y accesos fallidos', () => {
  it('muestra indicadores, señales sospechosas y controles activados, y «Ver eventos» filtra el listado', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': () => page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, SIGNALS) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    const panel = within(await screen.findByRole('region', { name: 'Seguridad y accesos fallidos' }));
    const indicators = within(await panel.findByRole('list', { name: 'Indicadores de seguridad del período' }));
    expect(indicators.getByText('Intentos fallidos').closest('li')).toHaveTextContent('9');
    const signals = within(panel.getByRole('list', { name: 'Señales de seguridad' }));
    expect(signals.getByText('Actividad sospechosa')).toBeInTheDocument();
    expect(signals.getByText('Control activado')).toBeInTheDocument();
    expect(signals.getByText('6 accesos fallidos en 15 minutos.')).toBeInTheDocument();
    await user.click(signals.getByRole('button', { name: /Ver los eventos de: Accesos fallidos repetidos/ }));
    await waitFor(() => expect(lastParams(calls, 'GET /audit')).toMatchObject({ idCuenta: USER_ID, categoria: 'ACCESOS_FALLIDOS' }));
    expect(await screen.findByText('Solo los eventos de la cuenta elegida')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Quitar' }));
    await waitFor(() => expect(lastParams(calls, 'GET /audit')).not.toHaveProperty('idCuenta'));
  });

  it('sin patrones no inventa nada: lo dice y aclara que los fallos aislados siguen en la lista', async () => {
    routes(ADMIN, { 'GET /audit': page([]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, EMPTY_SIGNALS) });
    renderAt('/app/auditoria');
    expect(await screen.findByText('No se detectaron patrones sospechosos ni controles activados en el período.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Señales de seguridad' })).not.toBeInTheDocument();
    expect(screen.getByText(/Eso no significa que no haya habido intentos fallidos/)).toBeInTheDocument();
  });

  it('los umbrales se ajustan solo para la consulta y viajan acotados', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': page([]), 'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': () => jsonResponse(200, SIGNALS) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await screen.findByRole('list', { name: 'Señales de seguridad' });
    await user.click(screen.getByText(/Umbrales de detección/));
    const field = screen.getByLabelText('Fallos por cuenta');
    await user.clear(field);
    await user.type(field, '3');
    await user.click(screen.getByRole('button', { name: 'Aplicar a esta consulta' }));
    await waitFor(() => expect(lastParams(calls, 'GET /audit/security/signals')).toMatchObject({ fallosPorCuenta: '3' }));
    expect(screen.getByText(/Solo valen para esta consulta/)).toBeInTheDocument();
  });

  it('avisa si falta la actualización de la base y si el análisis se truncó', async () => {
    routes(ADMIN, { 'GET /audit': page([]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/security/signals': jsonResponse(200, { ...EMPTY_SIGNALS, contextoDisponible: false, truncado: true }) });
    renderAt('/app/auditoria');
    expect(await screen.findByText(/La base de datos instalada todavía no registra el origen de los eventos/)).toBeInTheDocument();
    expect(screen.getByText(/Se analizaron los 5000 intentos más recientes/)).toBeInTheDocument();
  });

  it('si el análisis falla lo informa y la tabla de eventos sigue disponible', async () => {
    routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/security/signals': jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'No pudimos analizar.' }) });
    renderAt('/app/auditoria');
    expect(await screen.findByRole('table', { name: 'Eventos de auditoría' })).toBeInTheDocument();
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('list', { name: 'Señales de seguridad' })).not.toBeInTheDocument();
  });
});

describe('Ámbito Instituciones', () => {
  const institutions = [{ clave: INSTITUTION_ID, nombre: 'Hospital X', total: 0 }, { clave: 'i-2', nombre: 'Clínica Norte', total: 0 }];

  it('pide elegir una institución y no consulta eventos hasta entonces', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit/institutions': jsonResponse(200, institutions) });
    renderAt('/app/auditoria?ambito=instituciones');
    expect(await screen.findByText('Elegí una institución para ver su auditoría.')).toBeInTheDocument();
    expect(calls.some((call) => call.key === 'GET /audit' || call.key === 'GET /audit/summary')).toBe(false);
  });

  it('elegida una institución, pide solo sus eventos, oculta el selector de otras y distingue a la administración', async () => {
    const { calls } = routes(ADMIN, {
      'GET /audit/institutions': jsonResponse(200, institutions),
      'GET /audit': page([event({ idAuditoria: 'a', usuario: 'Victoria Cortés', origenActor: 'PLATAFORMA', ipOrigen: null, accion: 'MODIFICAR_INSTITUCION', accionEtiqueta: 'Modificación de datos de la institución', resultado: 'EXITO', severidad: 'EXITO', clasificacion: 'INFORMATIVO', motivo: null, motivoEtiqueta: null }), event()]),
      'GET /audit/summary': jsonResponse(200, SUMMARY), 'GET /audit/security/signals': jsonResponse(200, EMPTY_SIGNALS),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria?ambito=instituciones');
    await user.click(await screen.findByRole('button', { name: 'Hospital X' }));
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Administración')).toBeInTheDocument();
    expect(table.getByText('Ana Paz')).toBeInTheDocument();
    expect(lastParams(calls, 'GET /audit')).toMatchObject({ idInstitucion: INSTITUTION_ID });
    expect(lastParams(calls, 'GET /audit/summary')).toMatchObject({ idInstitucion: INSTITUTION_ID });
    expect(lastParams(calls, 'GET /audit/security/signals')).toMatchObject({ idInstitucion: INSTITUTION_ID });
    expect(screen.queryByLabelText('Institución')).not.toBeInTheDocument(); // la institución ya está elegida: no hay selector para mezclar otra
    expect(screen.queryByRole('list', { name: 'Actividad por institución' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Seguridad de esta institución' })).toBeInTheDocument();
    expect(screen.getByText('Hospital X', { selector: 'b' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Elegir otra institución/ }));
    expect(await screen.findByText('Elegí una institución para ver su auditoría.')).toBeInTheDocument();
  });

  it('el filtro «Autor del evento» separa a la administración del personal', async () => {
    const { calls } = routes(ADMIN, {
      'GET /audit/institutions': jsonResponse(200, institutions), 'GET /audit': () => page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/security/signals': jsonResponse(200, EMPTY_SIGNALS),
    });
    const user = userEvent.setup();
    renderAt(`/app/auditoria?ambito=instituciones&institucion=${INSTITUTION_ID}`);
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
    await user.selectOptions(screen.getByLabelText('Autor del evento'), 'PLATAFORMA');
    await waitFor(() => expect(lastParams(calls, 'GET /audit')).toMatchObject({ idInstitucion: INSTITUTION_ID, origenActor: 'PLATAFORMA' }));
  });
});

describe('Ámbito Cuentas individuales', () => {
  const found = [{ idUsuario: USER_ID, nombre: 'Ana Paz', usuario: 'anapaz', correo: 'an******@example.com', tipoCuenta: 'USUARIO_INSTITUCIONAL', estado: 'ACTIVO' }];
  const header = { ...found[0], fechaCreacion: '2026-10-01T10:00:00-03:00', mfaHabilitado: true, bloqueadaHasta: null, fallosAcceso24h: 3,
    ultimoAccesoExitoso: '2026-10-08T09:00:00-03:00', instituciones: [{ idInstitucion: INSTITUTION_ID, institucion: 'Hospital X', rol: 'OPERADOR', estado: 'ACTIVO' }] };

  it('busca con tres o más caracteres, abre la ficha (con el correo enmascarado) y lista solo los eventos de esa cuenta', async () => {
    const { calls } = routes(ADMIN, {
      'GET /audit/accounts': jsonResponse(200, found), [`GET /audit/accounts/${USER_ID}`]: jsonResponse(200, header),
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria?ambito=cuentas');
    expect(await screen.findByText('Buscá una cuenta para ver su auditoría.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Buscar cuenta'), 'an');
    await new Promise((resolve) => setTimeout(resolve, 450));
    expect(calls.some((call) => call.key === 'GET /audit/accounts')).toBe(false); // menos de tres caracteres: no consulta
    await user.type(screen.getByLabelText('Buscar cuenta'), 'a');
    await user.click(await screen.findByRole('button', { name: /Ana Paz/ }));
    const card = within(await screen.findByRole('heading', { name: /Ana Paz/ }).then((heading) => heading.closest('section')));
    expect(card.getByText('an******@example.com')).toBeInTheDocument();
    expect(card.getByText('Usuario institucional')).toBeInTheDocument();
    expect(card.getByText('Activada')).toBeInTheDocument();
    expect(card.getByText(/Hospital X \(operador, activo\)/)).toBeInTheDocument();
    expect(card.getByText(/No incluye mediciones ni datos médicos/)).toBeInTheDocument();
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
    expect(lastParams(calls, 'GET /audit')).toMatchObject({ idCuenta: USER_ID });
    expect(lastParams(calls, 'GET /audit/summary')).toMatchObject({ idCuenta: USER_ID });
    expect(document.body.textContent).not.toMatch(/anapaz@|glucosa|contraseña:/i);
  });

  it('si la ficha no se puede abrir informa el error del backend', async () => {
    routes(ADMIN, {
      [`GET /audit/accounts/${USER_ID}`]: jsonResponse(404, { codigo: 'USUARIO_NO_ENCONTRADO', detail: 'No encontramos esa cuenta.' }),
      'GET /audit': page([]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
    });
    renderAt(`/app/auditoria?ambito=cuentas&cuenta=${USER_ID}`);
    expect(await screen.findByText(/No encontramos esa cuenta/)).toBeInTheDocument();
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
    expect(screen.queryByLabelText('Identificador de correlación')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Correo o usuario consultado')).not.toBeInTheDocument();
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
