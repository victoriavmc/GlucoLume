import { configure, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../../test/helpers.js';
import { renderAt } from '../../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const BASE = `/institutions/${ID}`;
const INSTITUTION = {
  idInstitucion: ID, nombre: 'Centro Médico San José', tipoInstitucion: 'CLINICA', estado: 'ACTIVA', rolInstitucion: 'OPERADOR',
  estadoRelacion: 'ACTIVO', permisos: ['CONSULTAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES'],
  tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null, fechaCreacion: '2026-10-01T10:00:00',
  fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' },
  cantidadModeradores: 1, cantidadOperadores: 2, cantidadPacientes: 1,
};
const ANA = { idInstitucionUsuario: 'op-1', nombre: 'Ana', apellido: 'Paz', activo: false, rolInstitucion: 'OPERADOR', estadoRelacion: 'BAJA' };
const BRUNO = { idInstitucionUsuario: 'op-2', nombre: 'Bruno', apellido: 'Ríos', activo: true, rolInstitucion: 'OPERADOR', estadoRelacion: 'ACTIVO' };
const PATIENT = { idPerfilMedicion: 'p-1', identificadorPseudonimo: 'PAC-ABC123', edad: 46, sexoModelo: 'MASCULINO' };

const LIST_ITEM = {
  idTransferenciaPerfil: 't-1', estado: 'ACEPTADA', fechaPeticion: '2026-10-08T09:00:00', fechaTransferencia: '2026-10-08T12:00:00',
  observacion: 'Cambio de turno', paciente: PATIENT, origen: ANA, destino: BRUNO, esRecibida: true, esEnviada: false,
  puedeAceptar: false, puedeRechazar: false, puedeCancelar: false, tipo: 'TRANSFERENCIA',
};
const DETAIL = {
  ...LIST_ITEM, fechaPeticion: '2026-10-08T09:00:00-03:00', fechaTransferencia: '2026-10-08T12:00:00-03:00',
  fechaRespuesta: '2026-10-08T12:00:00-03:00', paciente: { ...PATIENT, puedeVerPerfil: true, nombre: 'Rosa', apellido: 'Díaz', datosIdentificativos: true },
  institucion: { idInstitucion: ID, nombre: 'Centro Médico San José' }, solicitante: { nombre: 'Ana', apellido: 'Paz', rolInstitucion: 'OPERADOR' },
  descripcion: 'El paciente PAC-ABC123 fue transferido de Ana Paz a Bruno Ríos.',
  historial: [
    { clave: 'SOLICITADA', etiqueta: 'Solicitada', fechaHora: '2026-10-08T09:00:00-03:00', usuario: 'Ana Paz' },
    { clave: 'ACEPTADA', etiqueta: 'Aceptada', fechaHora: '2026-10-08T12:00:00-03:00', usuario: 'Bruno Ríos' },
    { clave: 'RESPONSABLE_ACTUALIZADO', etiqueta: 'Responsable actualizado', fechaHora: '2026-10-08T12:00:00-03:00', usuario: null },
  ],
  tecnico: { idTransferenciaPerfil: 'tid-uuid-1', idPerfilMedicion: 'pid-uuid-1', idOperadorOrigen: 'op-1', idOperadorDestino: 'op-2',
    idInstitucion: ID, eventos: [{ accion: 'ACEPTAR_TRANSFERENCIA_PERFIL' }] },
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

function routes(extra) {
  return mockApi({ 'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET ${BASE}`]: jsonResponse(200, INSTITUTION), ...extra });
}

describe('Detalle de una transferencia', () => {
  it('abre en su propia página con origen, destino, historial y los UUID solo en detalles técnicos', async () => {
    routes({
      [`GET ${BASE}/transfers`]: jsonResponse(200, { items: [LIST_ITEM], total: 1, pagina: 1, tamanioPagina: 10 }),
      [`GET ${BASE}/transfers/t-1`]: jsonResponse(200, DETAIL),
    });
    const user = userEvent.setup();
    renderAt(`/app/instituciones/${ID}/pacientes/transferencias`);
    await user.click(await screen.findByRole('link', { name: /Ver detalle de la transferencia de PAC-ABC123/ }));

    const heading = await screen.findByRole('heading', { name: 'Transferencia de paciente' });
    expect(screen.queryByRole('list', { name: 'Transferencias respondidas' })).not.toBeInTheDocument(); // no se despliega bajo el listado
    expect(screen.getByText('El paciente PAC-ABC123 fue transferido de Ana Paz a Bruno Ríos.')).toBeInTheDocument();
    const origin = within(screen.getByLabelText('Operador de origen'));
    expect(origin.getByText('Ana Paz')).toBeInTheDocument();
    expect(origin.getByText(/Ya no está vinculado/)).toBeInTheDocument(); // operador desvinculado, aún identificado
    expect(within(screen.getByLabelText('Operador de destino')).getByText('Bruno Ríos')).toBeInTheDocument();
    const steps = within(screen.getByRole('list', { name: 'Historial de estados' })).getAllByRole('listitem');
    expect(steps.map((item) => item.querySelector('b').textContent)).toEqual(['Solicitada', 'Aceptada', 'Responsable actualizado']);
    expect(screen.getByText('Fecha de aceptación')).toBeInTheDocument();
    const patientCard = within(screen.getByLabelText('Paciente'));
    expect(patientCard.getByText('Rosa Díaz')).toBeInTheDocument();
    expect(patientCard.getByText('PAC-ABC123')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver perfil del paciente' })).toHaveAttribute('href', `/app/instituciones/${ID}/pacientes/p-1`);
    const crumbs = screen.getByRole('navigation', { name: 'Ruta de navegación' });
    expect(within(crumbs).getByText('Detalle de la transferencia')).toHaveAttribute('aria-current', 'page');

    const technical = screen.getByText('Detalles técnicos').closest('details');
    expect(technical).not.toHaveAttribute('open');
    expect(within(technical).getByText('tid-uuid-1')).toBeInTheDocument();
    expect(heading.closest('section')).not.toHaveTextContent('tid-uuid-1'); // la vista principal no muestra UUID

    await user.click(screen.getByRole('link', { name: /Volver a transferencias/ }));
    expect(await screen.findByRole('list', { name: 'Transferencias respondidas' })).toBeInTheDocument();
  });

  it('el operador no ve los detalles técnicos: el backend no los envía y la página no muestra el bloque', async () => {
    routes({ [`GET ${BASE}/transfers/t-1`]: jsonResponse(200, { ...DETAIL, tecnico: null }) });
    renderAt(`/app/instituciones/${ID}/pacientes/transferencias/t-1`);
    expect(await screen.findByRole('heading', { name: 'Transferencia de paciente' })).toBeInTheDocument();
    expect(screen.queryByText('Detalles técnicos')).not.toBeInTheDocument();
    expect(screen.queryByText('tid-uuid-1')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Eventos originales')).not.toBeInTheDocument();
  });

  it('funciona al abrir la URL directamente y informa si la transferencia no existe', async () => {
    routes({ [`GET ${BASE}/transfers/t-9`]: jsonResponse(404, { codigo: 'TRANSFERENCIA_NO_ENCONTRADA', detail: 'x' }) });
    renderAt(`/app/instituciones/${ID}/pacientes/transferencias/t-9`);
    expect(await screen.findByRole('link', { name: /Volver a transferencias/ })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('una reasignación directa se presenta como tal y no como transferencia entre operadores', async () => {
    routes({
      [`GET ${BASE}/transfers/t-1`]: jsonResponse(200, { ...DETAIL, tipo: 'REASIGNACION',
        descripcion: 'El paciente PAC-ABC123 fue reasignado de Ana Paz a Bruno Ríos.' }),
    });
    renderAt(`/app/instituciones/${ID}/pacientes/transferencias/t-1`);
    expect(await screen.findByRole('heading', { name: 'Reasignación de responsable' })).toBeInTheDocument();
    expect(screen.getByText('Realizada por')).toBeInTheDocument();
  });
});
