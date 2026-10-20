// Navegación jerárquica de una institución: Instituciones → Panel → módulo → detalle. El botón de volver del encabezado y las migas
// salen de la ruta y del identificador real de la institución (no del historial del navegador), así que funcionan igual al
// ingresar por una URL directa.

import { configure, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });

const INSTITUTIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
const ID = '9a000000-0000-4000-8000-000000000001';
const PANEL = `/app/instituciones/${ID}`;
const OWNER = ['CONSULTAR_INSTITUCION', 'MODIFICAR_INSTITUCION', 'GESTIONAR_MODERADORES', 'INCORPORAR_OPERADORES', 'ADMINISTRAR_OPERADORES',
  'CONSULTAR_EQUIPO', 'ELIMINAR_INSTITUCION', 'CONSULTAR_PACIENTES', 'GESTIONAR_PACIENTES', 'CONSULTAR_AUDITORIA', 'CONSULTAR_DISPOSITIVOS',
  'GESTIONAR_DISPOSITIVOS', 'GESTIONAR_MATRICES', 'CONSULTAR_MATRIZ'];
const institution = {
  idInstitucion: ID, nombre: 'Prueba', tipoInstitucion: 'CONSULTORIO', estado: 'ACTIVA', rolInstitucion: 'PROPIETARIO', estadoRelacion: 'ACTIVO',
  permisos: OWNER, tipoIdentificadorLegal: 'CUIT', identificadorLegal: '30712345671', descripcion: null, fechaCreacion: '2026-10-01T10:00:00',
  fechaActualizacion: '2026-10-01T10:00:00', propietario: { nombre: 'Victoria', apellido: 'Cortés' }, cantidadModeradores: 1, cantidadOperadores: 0,
  cantidadPacientes: 0, cantidadReaperturas: 0,
};

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

// Las pantallas internas piden más datos: lo que no se simula falla en silencio y no afecta al encabezado que se prueba.
const open = (path) => {
  mockApi({ 'GET /auth/me': jsonResponse(200, INSTITUTIONAL), [`GET /institutions/${ID}`]: jsonResponse(200, institution) });
  renderAt(`${PANEL}${path}`);
};

describe('Botón de volver del encabezado institucional', () => {
  it.each([
    ['moderadores', '/personal/moderadores'], ['operadores', '/personal/operadores'], ['datos institucionales', '/administracion/datos'],
    ['auditoría', '/auditoria'], ['auditoría (ruta anterior)', '/administracion/auditoria'], ['actividad', '/actividad'], ['configuración (redirige a datos)', '/configuracion'], ['pacientes', '/pacientes'],
    ['dispositivos', '/dispositivos'], ['matrices', '/matrices'], ['detalle de un evento', '/auditoria/e-1'],
    ['detalle de un dispositivo', '/dispositivos/d-1'], ['detalle de un operador', '/personal/operadores/op-1'],
  ])('desde %s vuelve al panel de la misma institución (también con la URL directa)', async (_name, path) => {
    open(path);
    const back = await screen.findByRole('link', { name: 'Volver al panel' });
    expect(back).toHaveAttribute('href', PANEL);
    expect(screen.queryByRole('link', { name: 'Volver a instituciones' })).not.toBeInTheDocument();
  });

  it('desde el panel vuelve a la lista de instituciones', async () => {
    open('');
    expect(await screen.findByRole('link', { name: 'Volver a instituciones' })).toHaveAttribute('href', '/app/instituciones');
    expect(screen.queryByRole('link', { name: 'Volver al panel' })).not.toBeInTheDocument();
  });
});

describe('Migas de pan', () => {
  it('representan la jerarquía con enlaces a la lista, al panel y a la sección', async () => {
    open('/personal/moderadores');
    const crumbs = within(await screen.findByRole('navigation', { name: 'Ruta de navegación' }));
    expect(crumbs.getByRole('link', { name: 'Instituciones' })).toHaveAttribute('href', '/app/instituciones');
    expect(crumbs.getByRole('link', { name: 'Prueba' })).toHaveAttribute('href', PANEL);
    expect(crumbs.getByRole('link', { name: 'Personal' })).toHaveAttribute('href', `${PANEL}/personal`);
    expect(crumbs.getByText('Moderadores')).toHaveAttribute('aria-current', 'page');
  });

  it('un detalle suma su propio nivel con el nombre que le corresponde', async () => {
    open('/personal/operadores/op-1');
    let crumbs = within(await screen.findByRole('navigation', { name: 'Ruta de navegación' }));
    expect(crumbs.getByRole('link', { name: 'Operadores' })).toHaveAttribute('href', `${PANEL}/personal/operadores`);
    expect(crumbs.getByText('Detalle del operador')).toHaveAttribute('aria-current', 'page');
    expect(crumbs.queryByText('Detalle de la transferencia')).not.toBeInTheDocument();
  });

  it('el panel y los datos institucionales tienen su propia miga final', async () => {
    open('');
    expect(within(await screen.findByRole('navigation', { name: 'Ruta de navegación' })).getByText('Panel')).toHaveAttribute('aria-current', 'page');
  });
});

describe('Lista de instituciones', () => {
  it('muestra «Crear otra institución» arriba, junto al título, y cada tarjeta abre el panel de su institución', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, INSTITUTIONAL), 'GET /institutions/invitations': jsonResponse(200, []),
      'GET /institutions/mine': jsonResponse(200, [
        { idInstitucion: ID, nombre: 'Prueba', tipoInstitucion: 'CONSULTORIO', estado: 'ACTIVA', rolInstitucion: 'PROPIETARIO', estadoRelacion: 'ACTIVO', permisos: [] },
      ]),
    });
    renderAt('/app/instituciones');
    const head = within((await screen.findByRole('heading', { name: 'Instituciones', level: 1 })).closest('header'));
    expect(await head.findByRole('button', { name: /Crear otra institución/ })).toBeInTheDocument();
    const list = within(await screen.findByRole('list', { name: 'Tus instituciones' }));
    expect(list.getByRole('link', { name: /Prueba/ })).toHaveAttribute('href', PANEL);
    expect(list.getByText('Abrir panel')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Crear otra institución/ })).toHaveLength(1); // ya no está al final de la página
  });
});
