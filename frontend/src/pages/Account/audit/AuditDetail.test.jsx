import { configure, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const account = (tipoCuenta) => ({ ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta } });
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const owner = ['CONSULTAR_INSTITUCION', 'CONSULTAR_EQUIPO', 'CONSULTAR_PACIENTES', 'CONSULTAR_AUDITORIA', 'ELIMINAR_INSTITUCION'];

function institution(rol, permisos) {
  return {
    idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: rol,
    estadoRelacion: 'ACTIVO', permisos, tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null,
    fechaCreacion: '2026-10-01T10:00:00', fechaActualizacion: '2026-10-01T10:00:00',
    propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 1, cantidadPacientes: 0,
  };
}

const EVENT = {
  idAuditoria: 'e-1', fechaHora: '2026-10-09T14:32:16Z', usuario: 'Juan Pérez', modulo: 'PERFILES',
  accion: 'SOLICITAR_TRANSFERENCIA_PERFIL', accionEtiqueta: 'Solicitud de transferencia', tipoEntidad: 'TransferenciaPerfil', idEntidad: 't-1',
  idInstitucion: ID, nombreInstitucion: null, resultado: 'EXITO', descripcion: null, critica: false, entidadEtiqueta: 'Paciente PAC-1',
  resumen: 'Juan Pérez solicitó transferir el paciente PAC-1 al operador María González.',
};
const SUMMARY = { total: 1, exitosos: 1, fallidos: 0, criticas: 0, porModulo: [], porInstitucion: [] };
const DETAIL = {
  ...EVENT, nombreInstitucion: 'Centro Médico San José', tipoEvento: 'CRUD', cambios: [], relacionada: null,
  transferencia: {
    paciente: { identificador: 'PAC-1', nombreCompleto: 'Rosa Díaz', datosIdentificativos: true }, origen: { texto: 'Juan Pérez', rol: 'OPERADOR', disponible: true },
    destino: { texto: 'María González', rol: 'OPERADOR', disponible: true },
  },
  valoresNuevos: { idOperadorDestino: 'uuid-destino' },
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

describe('Detalle de auditoría en una página independiente', () => {
  it('abre en su ruta, vuelve conservando los filtros y no se despliega bajo el listado', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, account('USUARIO_INSTITUCIONAL')),
      [`GET ${BASE}`]: jsonResponse(200, institution('PROPIETARIO', owner)),
      [`GET ${BASE}/audit`]: jsonResponse(200, { items: [EVENT], total: 1, pagina: 1, tamanioPagina: 20 }),
      [`GET ${BASE}/audit/summary`]: jsonResponse(200, SUMMARY),
      [`GET ${BASE}/audit/events/e-1`]: jsonResponse(200, DETAIL),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/auditoria?modulo=PERFILES`);
    expect(await screen.findByLabelText('Módulo')).toHaveValue('PERFILES'); // los filtros salen de la URL
    await user.click(await screen.findByRole('link', { name: /Ver detalle: Solicitud de transferencia/ }));

    expect(await screen.findByRole('heading', { level: 2, name: 'Detalle del evento' })).toBeInTheDocument(); // el h1 es el de la institución
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole('table', { name: 'Eventos de auditoría' })).not.toBeInTheDocument();
    expect(screen.getByText('Juan Pérez solicitó transferir el paciente PAC-1 al operador María González.')).toBeInTheDocument();
    expect(screen.getByText('Centro Médico San José', { selector: 'dd' })).toBeInTheDocument(); // institución con nombre
    expect(screen.queryByText('Persona relacionada')).not.toBeInTheDocument();
    expect(screen.queryByText('Entidad afectada')).not.toBeInTheDocument(); // no se mezcla con la transferencia
    expect(within(screen.getByLabelText('Paciente')).getByText('Rosa Díaz')).toBeInTheDocument();
    expect(within(screen.getByLabelText('Paciente')).getByText('PAC-1')).toBeInTheDocument();
    expect(screen.getByLabelText('Operador de origen')).toHaveTextContent('Juan Pérez (operador/a)');
    expect(screen.getByLabelText('Operador de destino')).toHaveTextContent('María González (operador/a)');
    expect(screen.getByLabelText('Valores nuevos')).toHaveTextContent('uuid-destino');
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Detalle del evento')).toHaveAttribute('aria-current', 'page');

    await user.click(screen.getByRole('link', { name: /Volver a auditoría/ }));
    expect(await screen.findByRole('table', { name: 'Eventos de auditoría' })).toBeInTheDocument();
    expect(screen.getByLabelText('Módulo')).toHaveValue('PERFILES'); // vuelve con los mismos filtros
    expect(calls.filter((call) => call.key === `GET ${BASE}/audit/events/e-1`)).toHaveLength(1);
  });

  it('la fecha se muestra en hora local, sin rotularla como UTC', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, account('ADMINISTRADOR_PLATAFORMA')),
      'GET /audit/events/e-1': jsonResponse(200, DETAIL),
    });
    renderAt('/app/auditoria/e-1');
    // Sin layout de institución, el detalle global es la única pantalla con h1.
    expect(await screen.findByRole('heading', { level: 1, name: 'Detalle del evento' })).toBeInTheDocument();
    const expected = new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
      .format(new Date('2026-10-09T14:32:16Z')).replace(',', '');
    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(screen.queryByText(/UTC/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Volver a auditoría/ })).toHaveAttribute('href', '/app/auditoria');
  });

  it('un moderador que abre la URL a mano no consulta nada', async () => {
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, account('USUARIO_INSTITUCIONAL')),
      [`GET ${BASE}`]: jsonResponse(200, institution('MODERADOR', ['CONSULTAR_INSTITUCION', 'CONSULTAR_EQUIPO'])),
    });
    renderAt(`/app/instituciones/${ID}/auditoria/e-1`);
    expect(await screen.findByText('Solo el propietario de la institución puede consultar la auditoría.')).toBeInTheDocument();
    expect(calls.some((call) => call.key.includes('/audit'))).toBe(false);
  });
});
