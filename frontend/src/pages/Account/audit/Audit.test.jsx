import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

// Con todos los archivos en paralelo, 1 s por defecto no siempre alcanza para que las pantallas carguen.
configure({ asyncUtilTimeout: 5000 });

const account = (tipoCuenta) => ({ ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta } });
const ADMIN = account('ADMINISTRADOR_PLATAFORMA');
const PLATFORM_MODERATOR = account('MODERADOR_PLATAFORMA');
const INSTITUTIONAL = account('USUARIO_INSTITUCIONAL');
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const PERMISOS = {
  PROPIETARIO: ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'ADMINISTRAR_OPERADORES',
    'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES',
    'GESTIONAR_MATRICES', 'CONSULTAR_MATRIZ', 'CONSULTAR_AUDITORIA'],
  MODERADOR: ['CONSULTAR_INSTITUCION', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES', 'CONSULTAR_EQUIPO',
    'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'BAJA_PACIENTES', 'GESTIONAR_MATRICES', 'CONSULTAR_MATRIZ'],
  OPERADOR: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'CONSULTAR_MATRIZ'],
};

function institution(rol) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos: PERMISOS[rol], tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671',
    descripcion: null, fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0,
  };
}

function event(overrides = {}) {
  return {
    idAuditoria: 'e-1', fechaHora: '2026-10-09T14:32:16', usuario: 'Victoria Cortés', modulo: 'MATRICES', accion: 'ACTIVAR_MATRIZ',
    tipoEntidad: 'Matriz', idEntidad: 'mx-1', idInstitucion: ID, nombreInstitucion: 'Centro Médico San José', resultado: 'EXITO',
    descripcion: null, critica: true, ...overrides,
  };
}

const SUMMARY = {
  total: 12, exitosos: 10, fallidos: 2, criticas: 3,
  porModulo: [{ clave: 'MATRICES', nombre: null, total: 7 }, { clave: 'INSTITUCIONES', nombre: null, total: 5 }],
  porInstitucion: [{ clave: ID, nombre: 'Centro Médico San José', total: 9 }, { clave: 'i-2', nombre: 'Clínica Norte', total: 3 }],
};
const page = (items) => jsonResponse(200, { items, total: items.length, pagina: 1, tamanioPagina: 20 });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(me, extra = {}) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, me), ...extra });
}

describe('Auditoría general (administrador del sistema)', () => {
  it('muestra el resumen, la actividad por módulo e institución y la tabla de eventos', async () => {
    routes(ADMIN, {
      'GET /audit': page([event(), event({ idAuditoria: 'e-2', accion: 'LOGIN_LOCAL', modulo: 'CUENTA', idInstitucion: null, nombreInstitucion: null, resultado: 'FALLO', critica: false })]),
      'GET /audit/summary': jsonResponse(200, SUMMARY),
    });
    renderAt('/app/auditoria');
    expect(await screen.findByRole('heading', { name: 'Auditoría general' })).toBeInTheDocument();
    const cards = within(await screen.findByRole('list', { name: 'Resumen de la auditoría' }));
    expect(cards.getByText('Total de eventos').closest('li')).toHaveTextContent('12');
    expect(cards.getByText('Fallidos').closest('li')).toHaveTextContent('2');
    expect(cards.getByText('Operaciones críticas').closest('li')).toHaveTextContent('3');
    expect(within(screen.getByRole('list', { name: 'Actividad por módulo' })).getByText('Matrices y reglas')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Actividad por institución' })).getByText('Clínica Norte')).toBeInTheDocument();
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Activar matriz')).toBeInTheDocument();
    expect(table.getByText('Crítica')).toBeInTheDocument();
    expect(table.getAllByText('09/10/2026 14:32')).toHaveLength(2);
    expect(table.getByText('Fallido')).toBeInTheDocument();
    expect(table.getByRole('columnheader', { name: 'Institución' })).toBeInTheDocument();
  });

  it('el menú ofrece Auditoría solo al administrador del sistema', async () => {
    routes(ADMIN, { 'GET /audit': page([]), 'GET /audit/summary': jsonResponse(200, SUMMARY) });
    renderAt('/app/auditoria');
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).getByRole('link', { name: 'Auditoría' })).toHaveAttribute('href', '/app/auditoria');
  });

  it.each([['moderador de plataforma', PLATFORM_MODERATOR], ['usuario individual', ACCOUNT]])(
    '%s no ve la opción ni consulta la auditoría',
    async (_, me) => {
      const { calls } = routes(me, {
        'GET /groups/mine': jsonResponse(200, { grupo: null }), 'GET /groups/invitations': jsonResponse(200, []),
        'GET /matrices/global': jsonResponse(200, []),
      });
      renderAt('/app/auditoria');
      const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
      expect(within(nav).queryByRole('link', { name: 'Auditoría' })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Auditoría general' })).not.toBeInTheDocument();
      expect(calls.some((call) => call.key.startsWith('GET /audit'))).toBe(false);
    },
  );

  it('los filtros se envían al backend (institución, usuario, módulo, acción, resultado y período)', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': () => page([]), 'GET /audit/summary': () => jsonResponse(200, SUMMARY) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await screen.findByText('Todavía no hay eventos registrados.');
    await user.selectOptions(await screen.findByLabelText('Institución'), ID);
    await user.type(screen.getByLabelText('Usuario'), 'duenia');
    await user.selectOptions(screen.getByLabelText('Módulo'), 'MATRICES');
    await user.type(screen.getByLabelText('Acción'), 'activar');
    await user.selectOptions(screen.getByLabelText('Resultado'), 'FALLO');
    await user.type(screen.getByLabelText('Desde'), '2026-10-01');
    await user.type(screen.getByLabelText('Hasta'), '2026-10-09');
    await user.click(screen.getByRole('checkbox', { name: /operaciones críticas/ }));
    await waitFor(() => {
      const last = new URL(calls.filter((call) => call.key === 'GET /audit').at(-1).url);
      expect(Object.fromEntries(last.searchParams)).toEqual({
        idInstitucion: ID, usuario: 'duenia', modulo: 'MATRICES', accion: 'activar', resultado: 'FALLO',
        desde: '2026-10-01', hasta: '2026-10-09', critica: 'true', pagina: '1', tamanioPagina: '20',
      });
    }, { timeout: 5000 });
    expect(await screen.findByText('No hay eventos que coincidan con los filtros.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Limpiar filtros/ }));
    expect(screen.getByLabelText('Módulo')).toHaveValue('');
  });

  it('abre el detalle de un evento con sus valores previos y nuevos', async () => {
    routes(ADMIN, {
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, {
        ...event({ entidadEtiqueta: 'Matriz Principal' }), tipoEvento: 'CRUD', tablaRelacionada: 'Institucion', idRelacionado: ID,
        valoresPrevios: { estado: 'INACTIVA' }, valoresNuevos: { estado: 'ACTIVA', version: '2' },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await user.click(await screen.findByRole('link', { name: /Ver detalle: Activar matriz/ }));
    await screen.findByRole('heading', { name: 'Detalle del evento' });
    const detail = screen;
    expect(detail.getByText('Matriz Principal')).toBeInTheDocument();
    expect(detail.getAllByText('Exitoso').length).toBeGreaterThan(0); // en la cabecera y en el resumen
    expect(detail.getByText('Realizado por')).toBeInTheDocument();
    expect(detail.getByLabelText('Valores nuevos')).toHaveTextContent('"version": "2"');
    expect(detail.getByLabelText('Valores previos')).toHaveTextContent('"estado": "INACTIVA"');
    await user.click(screen.getByRole('link', { name: /Volver a auditoría/ }));
    expect(await screen.findByRole('table', { name: 'Eventos de auditoría' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Detalle del evento' })).not.toBeInTheDocument();
  });

  it('muestra los cambios con nombres y deja los UUID en los detalles técnicos', async () => {
    const OLD = '11111111-1111-4111-8111-111111111111';
    const NEW = '22222222-2222-4222-8222-222222222222';
    routes(ADMIN, {
      'GET /audit': page([event({ accion: 'CAMBIAR_RESPONSABLE_PERFIL', modulo: 'PERFILES', entidadEtiqueta: 'Paciente PAC-0001' })]),
      'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, {
        ...event({ accion: 'CAMBIAR_RESPONSABLE_PERFIL', modulo: 'PERFILES', entidadEtiqueta: 'Paciente PAC-0001' }), tipoEvento: 'CRUD',
        valoresPrevios: { idInstitucionUsuarioResponsable: OLD }, valoresNuevos: { idInstitucionUsuarioResponsable: NEW },
        cambios: [{
          campo: 'idInstitucionUsuarioResponsable', etiqueta: 'Responsable institucional', tipo: 'PERSONA',
          anterior: { id: OLD, texto: 'Juan Pérez', rol: 'OPERADOR', disponible: true },
          nuevo: { id: NEW, texto: 'Usuario institucional no disponible', rol: null, disponible: false },
        }],
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    const table = await screen.findByRole('table', { name: 'Eventos de auditoría' });
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(expect.arrayContaining(
      ['Fecha y hora', 'Módulo', 'Acción', 'Usuario responsable', 'Entidad afectada', 'Resultado']));
    expect(within(table).getByText('Paciente PAC-0001')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: /Ver detalle/ }));
    await screen.findByRole('heading', { name: 'Detalle del evento' });
    const detail = screen;
    const changes = within(detail.getByRole('table', { name: 'Cambios del evento' }));
    expect(changes.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Campo', 'Antes', 'Después']);
    const row = changes.getByText('Responsable institucional').closest('tr');
    expect(row).toHaveTextContent('Juan Pérez (operador/a)');
    expect(row).toHaveTextContent('Usuario institucional no disponible');
    expect(changes.queryByText(/idInstitucionUsuarioResponsable/)).not.toBeInTheDocument(); // sin nombres técnicos en la tabla de cambios
    expect(detail.getByText('Detalles técnicos').closest('details')).not.toHaveAttribute('open');
    expect(detail.getByLabelText('Valores previos')).toHaveTextContent(OLD);
    expect(detail.getByLabelText('Valores nuevos')).toHaveTextContent(NEW);
  });

  it('si el resumen falla lo informa y no muestra ceros mientras el listado tiene eventos', async () => {
    routes(ADMIN, {
      'GET /audit': page([event(), event({ idAuditoria: 'e-2' })]),
      'GET /audit/summary': jsonResponse(500, { codigo: 'ERROR_SERVIDOR', detail: 'Error' }),
    });
    renderAt('/app/auditoria');
    expect(await screen.findByText(/No pudimos cargar el resumen de actividad/)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Resumen de la auditoría' })).not.toBeInTheDocument();
    expect(within(await screen.findByRole('table', { name: 'Eventos de auditoría' })).getAllByRole('row')).toHaveLength(3);
  });

  it('el resumen y el listado piden lo mismo: mismos filtros y mismo período', async () => {
    const { calls } = routes(ADMIN, { 'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY) });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await screen.findByRole('table', { name: 'Eventos de auditoría' });
    await user.selectOptions(screen.getByLabelText('Módulo'), 'MATRICES');
    await user.selectOptions(screen.getByLabelText('Resultado'), 'FALLO');
    await waitFor(() => {
      const withFilters = (path) => calls.some((call) => call.url.includes(path) && call.url.includes('modulo=MATRICES') && call.url.includes('resultado=FALLO'));
      expect(withFilters('/audit?')).toBe(true);
      expect(withFilters('/audit/summary?')).toBe(true);
    });
  });

  it('muestra el resumen con cuatro indicadores y la actividad por módulo, y marca un evento rechazado', async () => {
    routes(ADMIN, {
      'GET /audit': page([event({ idAuditoria: 'e-3', resultado: 'FALLO', rechazado: true, accion: 'CONSULTAR_AUDITORIA' }), event()]),
      'GET /audit/summary': jsonResponse(200, SUMMARY),
    });
    renderAt('/app/auditoria');
    const cards = within(await screen.findByRole('list', { name: 'Resumen de la auditoría' }));
    expect(cards.getAllByRole('listitem')).toHaveLength(4);
    expect(cards.getByText('Total de eventos').closest('li')).toHaveTextContent('12');
    expect(within(screen.getByRole('list', { name: 'Actividad por módulo' })).getByText('Matrices y reglas').closest('li')).toHaveTextContent('7');
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Rechazado')).toBeInTheDocument();
    expect(table.getByText('Exitoso')).toBeInTheDocument();
  });

  it('«Aceptar invitación» muestra Campo / Antes / Después con etiquetas y distingue «sin valor»', async () => {
    const base = event({ accion: 'ACEPTAR_INVITACION_INSTITUCION', accionEtiqueta: 'Aceptar invitación institucional', modulo: 'INSTITUCIONES' });
    routes(ADMIN, {
      'GET /audit': page([base]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, { ...base, tipoEvento: 'PERMISO', valoresPrevios: null,
        valoresNuevos: { rolInstitucion: 'MODERADOR', estadoRelacion: 'ACTIVO' },
        cambios: [
          { campo: 'rolInstitucion', etiqueta: 'Rol institucional', tipo: 'VALOR', anterior: { texto: 'Sin rol', ausente: true }, nuevo: { texto: 'Moderador/a' } },
          { campo: 'estadoRelacion', etiqueta: 'Estado de la relación', tipo: 'VALOR', anterior: { texto: 'Sin estado', ausente: true }, nuevo: { texto: 'Activo' } },
        ] }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await user.click(await screen.findByRole('link', { name: /Ver detalle/ }));
    const table = within(await screen.findByRole('table', { name: 'Cambios del evento' }));
    expect(table.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Campo', 'Antes', 'Después']);
    const role = table.getByText('Rol institucional').closest('tr');
    expect(within(role).getByText('Sin rol')).toHaveClass('is-empty'); // sin valor: se ve apagado
    expect(within(role).getByText('Moderador/a')).not.toHaveClass('is-empty');
    const state = table.getByText('Estado de la relación').closest('tr');
    expect(state).toHaveTextContent('Sin estado');
    expect(state).toHaveTextContent('Activo');
    expect(table.queryByText('MODERADOR')).not.toBeInTheDocument(); // el código interno solo en «Detalles técnicos»
    expect(table.queryByText('ACTIVO')).not.toBeInTheDocument();
  });

  it('el detalle nombra la entidad, su rol y la institución, y los UUID quedan en «Detalles técnicos» junto al nombre', async () => {
    const EVENT = '33333333-3333-4333-8333-333333333333';
    const REL = '44444444-4444-4444-8444-444444444444';
    const base = event({ accion: 'ACEPTAR_INVITACION_INSTITUCION', accionEtiqueta: 'Aceptar invitación institucional', modulo: 'INSTITUCIONES',
      usuario: 'Victoria Valentina Collins' });
    routes(ADMIN, {
      'GET /audit': page([base]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, { ...base, idAuditoria: EVENT, tipoEvento: 'PERMISO', tipoEntidad: 'InstitucionUsuario',
        entidad: { id: REL, texto: 'Victoria Valentina Collins', tipo: 'Integrante de la institución', rol: 'MODERADOR', disponible: true, origen: 'EVENTO',
          atributos: [{ etiqueta: 'Rol asignado', texto: 'Moderador/a', origen: 'EVENTO' }, { etiqueta: 'Estado de la relación (actual)', texto: 'Activo', origen: 'ACTUAL' }] },
        referencias: [
          { etiqueta: 'Identificador del evento', id: EVENT, nombre: null, origen: null, disponible: true },
          { etiqueta: 'Institución (identificador interno)', id: ID, nombre: 'Centro Médico San José', origen: 'ACTUAL', disponible: true },
          { etiqueta: 'Entidad afectada', id: REL, nombre: 'Victoria Valentina Collins', origen: 'EVENTO', disponible: true },
        ] }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await user.click(await screen.findByRole('link', { name: /Ver detalle/ }));
    const summary = within((await screen.findByRole('heading', { name: 'Detalle del evento' })).closest('section'));
    expect(summary.getByText('Realizado por').closest('div')).toHaveTextContent('Victoria Valentina Collins');
    const entity = summary.getByText('Entidad afectada').closest('div');
    expect(entity).toHaveTextContent('Victoria Valentina Collins');
    expect(entity).toHaveTextContent('Integrante de la institución');
    expect(summary.getByText('Rol asignado').closest('div')).toHaveTextContent('Moderador/a');
    expect(summary.getByText('Estado de la relación (actual)').closest('div')).toHaveTextContent('dato actual'); // puede haber cambiado desde el evento
    // Los UUID no están en el resumen principal; sí en «Detalles técnicos» (contraído), con el nombre resuelto al lado y botón para copiar.
    expect(summary.queryByText(new RegExp(REL))).not.toBeInTheDocument();
    const details = screen.getByText('Detalles técnicos').closest('details');
    expect(details).not.toHaveAttribute('open');
    const technical = within(details);
    const ref = technical.getByText('Entidad afectada').closest('div');
    expect(ref).toHaveTextContent('Victoria Valentina Collins');
    expect(ref).toHaveTextContent(REL);
    expect(within(ref).getByRole('button', { name: 'Copiar entidad afectada' })).toBeInTheDocument();
    expect(technical.getByRole('button', { name: 'Copiar identificador del evento' })).toBeInTheDocument();
    expect(technical.getByText('Institución (identificador interno)').closest('div')).toHaveTextContent('Centro Médico San José');
    expect(technical.getByText('Tipo de evento').closest('div')).toHaveTextContent('PERMISO');
  });

  it('copiar funciona también en http (sin navigator.clipboard) y avisa si no se pudo', async () => {
    const EVENT = '33333333-3333-4333-8333-333333333333';
    routes(ADMIN, {
      'GET /audit': page([event()]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, { ...event(), idAuditoria: EVENT, tipoEvento: 'CRUD',
        referencias: [{ etiqueta: 'Identificador del evento', id: EVENT, nombre: null, origen: null, disponible: true }] }),
    });
    Object.defineProperty(window.navigator, 'clipboard', { value: undefined, configurable: true }); // contexto no seguro
    const exec = vi.fn(() => true);
    document.execCommand = exec;
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    await user.click(await screen.findByRole('link', { name: /Ver detalle/ }));
    await screen.findByRole('heading', { name: 'Detalle del evento' });
    const button = screen.getByRole('button', { name: 'Copiar identificador del evento' });
    await user.click(button);
    expect(exec).toHaveBeenCalledWith('copy');
    expect(await within(button).findByText('Copiado')).toBeInTheDocument();
    exec.mockReturnValue(false); // el navegador no permite copiar
    await user.click(button);
    expect(await within(button).findByText('No se pudo copiar')).toBeInTheDocument();
  });

  it('el detalle de una transferencia dice qué paciente, de qué operador y a cuál', async () => {
    const base = event({ accion: 'ACEPTAR_TRANSFERENCIA_PERFIL', modulo: 'PERFILES', tipoEntidad: 'TransferenciaPerfil',
      entidadEtiqueta: 'Paciente PAC-0001' });
    routes(ADMIN, {
      'GET /audit': page([base]), 'GET /audit/summary': jsonResponse(200, SUMMARY),
      'GET /audit/events/e-1': jsonResponse(200, { ...base, tipoEvento: 'CRUD', transferencia: {
        paciente: { id: 'p-1', identificador: 'PAC-0001', nombreCompleto: 'Rosa Díaz', datosIdentificativos: true },
        origen: { id: 'r-1', texto: 'Juan Pérez', rol: 'OPERADOR', disponible: true },
        destino: { id: 'r-2', texto: 'María González', rol: 'OPERADOR', disponible: true },
      } }),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    expect(await screen.findByText('Paciente PAC-0001')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: /Ver detalle/ }));
    await screen.findByRole('heading', { name: 'Detalle del evento' });
    const detail = screen;
    expect(detail.getByText('Rosa Díaz')).toBeInTheDocument();
    expect(detail.getByText('PAC-0001')).toBeInTheDocument();
    expect(detail.getByText('Juan Pérez (operador/a)')).toBeInTheDocument();
    expect(detail.getByText('María González (operador/a)')).toBeInTheDocument();
  });

  it('pagina desde el backend', async () => {
    const { calls } = routes(ADMIN, {
      'GET /audit': () => jsonResponse(200, { items: [event()], total: 45, pagina: 1, tamanioPagina: 20 }),
      'GET /audit/summary': jsonResponse(200, SUMMARY),
    });
    const user = userEvent.setup();
    renderAt('/app/auditoria');
    expect(await screen.findByText('Página 1 de 3 · 45 eventos')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Siguiente/ }));
    await waitFor(() => expect(new URL(calls.filter((call) => call.key === 'GET /audit').at(-1).url).searchParams.get('pagina')).toBe('2'));
  });
});

describe('Auditoría institucional (propietario)', () => {
  it('el propietario ve Auditoría en el menú lateral y la auditoría de su institución, sin pestañas ni selector de institución', async () => {
    const { calls } = routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/audit`]: page([
        event({ nombreInstitucion: null }),
        event({ idAuditoria: 'e-3', accion: 'SOLICITAR_TRANSFERENCIA_PERFIL', modulo: 'PERFILES', usuario: 'Ana Paz', critica: false, nombreInstitucion: null }),
      ]),
      [`GET ${BASE}/audit/summary`]: jsonResponse(200, { ...SUMMARY, porInstitucion: [] }),
    });
    renderAt(`/app/instituciones/${ID}/auditoria`);
    const menu = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(menu).getAllByRole('link').map((link) => link.textContent).slice(-2)).toEqual(['Administración', 'Auditoría']); // Auditoría va al final
    expect(within(menu).getByRole('link', { name: 'Auditoría' })).toHaveAttribute('href', `/app/instituciones/${ID}/auditoria`);
    expect(within(menu).getByRole('link', { name: 'Auditoría' })).toHaveClass('is-active');
    // Sin la barra Datos/Auditoría: el contenido empieza con el título «Auditoría institucional».
    expect(screen.queryByRole('navigation', { name: 'Secciones de administración' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Auditoría institucional' })).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Auditoría')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Volver al panel' })).toHaveAttribute('href', `/app/instituciones/${ID}`);
    const table = within(await screen.findByRole('table', { name: 'Eventos de auditoría' }));
    expect(table.getByText('Solicitar transferencia perfil')).toBeInTheDocument();
    expect(table.getByText('Ana Paz')).toBeInTheDocument();
    expect(table.queryByRole('columnheader', { name: 'Institución' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Institución')).not.toBeInTheDocument(); // sin selector para ver otras instituciones
    expect(screen.queryByRole('list', { name: 'Actividad por institución' })).not.toBeInTheDocument();
    const url = new URL(calls.find((call) => call.key === `GET ${BASE}/audit`).url);
    expect(url.searchParams.has('idInstitucion')).toBe(false);
  });

  it.each([['MODERADOR'], ['OPERADOR']])('el %s no ve Auditoría en el menú lateral', async (rol) => {
    routes(INSTITUTIONAL, { [`GET ${BASE}`]: jsonResponse(200, institution(rol)) });
    renderAt(`/app/instituciones/${ID}`);
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la institución' });
    expect(within(nav).queryByRole('link', { name: 'Auditoría' })).not.toBeInTheDocument();
  });

  it('la ruta anterior administracion/auditoria redirige a Auditoría conservando los filtros', async () => {
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/audit`]: page([event({ nombreInstitucion: null })]),
      [`GET ${BASE}/audit/summary`]: jsonResponse(200, { ...SUMMARY, porInstitucion: [] }),
    });
    renderAt(`/app/instituciones/${ID}/administracion/auditoria?modulo=PERFILES`);
    expect(await screen.findByRole('heading', { name: 'Auditoría institucional' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Módulo')).toHaveValue('PERFILES');
  });

  it('si un moderador abre la ruta a mano, no consulta nada y se le informa', async () => {
    const { calls } = routes(INSTITUTIONAL, { [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR')) });
    renderAt(`/app/instituciones/${ID}/auditoria`);
    expect(await screen.findByText('Solo el propietario de la institución puede consultar la auditoría.')).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/audit'))).toBe(false);
  });

  it('si el backend responde 403, se informa sin mostrar eventos', async () => {
    const denied = jsonResponse(403, { codigo: 'PERMISO_INSUFICIENTE', detail: 'No tenés permiso para consultar la auditoría.' });
    routes(INSTITUTIONAL, {
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO')),
      [`GET ${BASE}/audit`]: denied,
      [`GET ${BASE}/audit/summary`]: denied,
    });
    renderAt(`/app/instituciones/${ID}/auditoria`);
    expect((await screen.findAllByText(/No tenés permiso para consultar la auditoría/)).length).toBeGreaterThan(0);
    expect(screen.queryByRole('table', { name: 'Eventos de auditoría' })).not.toBeInTheDocument();
  });
});
