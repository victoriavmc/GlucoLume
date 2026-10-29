import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

const PROFILE = {
  ...ACCOUNT,
  usuario: { ...ACCOUNT.usuario, fechaNacimiento: '1990-05-17', sexo: 'FEMENINO' },
};

const hoy = new Date();
const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}T10:15:00-03:00`;
const diasAtras = (dias) => {
  const fecha = new Date(hoy);
  fecha.setDate(fecha.getDate() - dias);
  return iso(fecha);
};

const aviso = (id, extra = {}) => ({
  idNotificacion: id, evento: 'INICIO_SESION', categoria: 'SEGURIDAD', titulo: `Aviso ${id}`, mensaje: `Texto ${id}`,
  url: '/app/seguridad', fechaCreacion: diasAtras(0), leida: false, ...extra,
});

const bandeja = (items, extra = {}) => jsonResponse(200, {
  noLeidas: items.filter((item) => !item.leida).length, total: items.length, hayMas: false, notificaciones: items, ...extra,
});

function withInbox(routes = {}, account = PROFILE) {
  saveTokens(TOKENS, false);
  return mockApi({ 'GET /auth/me': jsonResponse(200, account), ...routes });
}

const queryOf = (call) => Object.fromEntries(new URL(call.url).searchParams);

beforeEach(() => clearTokens());

describe('Bandeja de notificaciones', () => {
  it('muestra el encabezado, los no leídos y los accesos a preferencias y a marcar todas', async () => {
    withInbox({ 'GET /notificaciones': bandeja([aviso('a'), aviso('b', { leida: true })]) });
    renderAt('/app/notificaciones');

    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Preferencias' })).toHaveAttribute('href', '/app/notificaciones/preferencias');
    expect(screen.getByRole('button', { name: 'Marcar todas como leídas' })).toBeEnabled();
    // Cada tarjeta muestra título, descripción, categoría, fecha y estado de lectura; sin enlaces «Ver».
    const tarjeta = screen.getByRole('button', { name: /Aviso a/ });
    expect(within(tarjeta).getByText('Texto a')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Seguridad')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Sin leer')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /Aviso b/ })).getByText('Leída')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Ver' })).not.toBeInTheDocument();
  });

  it('agrupa por Hoy, Ayer y Anteriores', async () => {
    withInbox({
      'GET /notificaciones': bandeja([
        aviso('h'), aviso('y', { fechaCreacion: diasAtras(1) }), aviso('v', { fechaCreacion: diasAtras(5) }),
      ]),
    });
    renderAt('/app/notificaciones');

    expect(await screen.findByRole('heading', { name: 'Hoy' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ayer' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Anteriores' })).toBeInTheDocument();
  });

  it('el estado vacío se muestra cuando no hay avisos', async () => {
    withInbox({ 'GET /notificaciones': bandeja([]) });
    renderAt('/app/notificaciones');

    expect(await screen.findByText('Todavía no tenés notificaciones')).toBeInTheDocument();
    expect(screen.getByText('No tenés avisos sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar todas como leídas' })).toBeDisabled();
  });

  it('muestra el estado de carga y, si falla, el error con la opción de reintentar', async () => {
    let attempt = 0;
    withInbox({
      'GET /notificaciones': (options, url) => {
        // El cartel de avisos nuevos (layout) consulta aparte, solo no leídos: no cuenta como intento de la bandeja.
        if (new URL(url).searchParams.get('soloNoLeidas')) return bandeja([]);
        attempt += 1;
        return attempt === 1 ? jsonResponse(500, { detail: 'boom' }) : bandeja([aviso('a')]);
      },
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    expect(await screen.findByText('Cargando tus notificaciones…')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(await screen.findByRole('button', { name: /Aviso a/ })).toBeInTheDocument();
    expect(attempt).toBe(2);
  });

  it('los filtros piden al backend la categoría o los no leídos', async () => {
    const { calls } = withInbox({ 'GET /notificaciones': () => bandeja([aviso('a')]) });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    await screen.findByRole('button', { name: /Aviso a/ });

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Todas', 'No leídas', 'Seguridad', 'Recordatorios', 'Grupo']);

    await user.click(screen.getByRole('tab', { name: 'No leídas' }));
    await waitFor(() => expect(calls.some((call) => queryOf(call).soloNoLeidas === 'true')).toBe(true));
    await user.click(screen.getByRole('tab', { name: 'Grupo' }));
    await waitFor(() => expect(calls.some((call) => queryOf(call).categoria === 'GRUPO')).toBe(true));
    await user.click(screen.getByRole('tab', { name: 'Recordatorios' }));
    await waitFor(() => expect(calls.some((call) => queryOf(call).categoria === 'RECORDATORIO')).toBe(true));
  });

  it('una cuenta institucional no ve los filtros de grupo ni de recordatorios', async () => {
    const institucional = { ...PROFILE, usuario: { ...PROFILE.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    withInbox({ 'GET /notificaciones': bandeja([aviso('a')]) }, institucional);
    renderAt('/app/notificaciones');
    await screen.findByRole('button', { name: /Aviso a/ });

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Todas', 'No leídas', 'Seguridad']);
  });

  it('carga más avisos con el desplazamiento y no repite los ya mostrados', async () => {
    const { calls } = withInbox({
      'GET /notificaciones': (options, url) => {
        const offset = Number(new URL(url).searchParams.get('desplazamiento') ?? 0);
        return offset === 0
          ? bandeja([aviso('a'), aviso('b')], { total: 3, hayMas: true })
          : bandeja([aviso('b'), aviso('c')], { total: 3, hayMas: false });
      },
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    await screen.findByText('Mostrando 2 de 3');

    await user.click(screen.getByRole('button', { name: 'Cargar más' }));

    expect(await screen.findByText('Mostrando 3 de 3')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Aviso/ })).toHaveLength(3);
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument();
    expect(calls.some((call) => queryOf(call).desplazamiento === '2')).toBe(true);
  });

  it('elegir una tarjeta la marca como leída y abre el destino autorizado', async () => {
    const { calls } = withInbox({
      'GET /notificaciones': bandeja([aviso('a', { url: '/app/seguridad' })]),
      'POST /notificaciones/a/leer': jsonResponse(200, { noLeidas: 0, marcadas: 1 }),
      'GET /auth/security': jsonResponse(200, {}),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    await user.click(await screen.findByRole('button', { name: /Aviso a/ }));

    await waitFor(() => expect(calls.some((call) => call.key === 'POST /notificaciones/a/leer')).toBe(true));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Notificaciones' })).not.toBeInTheDocument());
  });

  it('un aviso con un destino no autorizado se marca como leído pero no navega', async () => {
    withInbox({
      'GET /notificaciones': bandeja([aviso('a', { url: 'https://malo.example/robar' }), aviso('b', { url: '/app/ruta-inventada' })]),
      'POST /notificaciones/a/leer': jsonResponse(200, { noLeidas: 1, marcadas: 1 }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    await user.click(await screen.findByRole('button', { name: /Aviso a/ }));

    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /Aviso a/ })).getByText('Leída')).toBeInTheDocument();
  });

  it('marcar como leído es optimista y vuelve atrás si el backend lo rechaza', async () => {
    withInbox({
      'GET /notificaciones': bandeja([aviso('a', { url: null })]),
      'POST /notificaciones/a/leer': jsonResponse(500, { detail: 'boom' }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    await user.click(await screen.findByRole('button', { name: /Aviso a/ }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /Aviso a/ })).getByText('Sin leer')).toBeInTheDocument();
  });

  it('marcar todas como leídas actualiza la bandeja y se revierte si falla', async () => {
    const { calls } = withInbox({
      'GET /notificaciones': bandeja([aviso('a'), aviso('b')]),
      'POST /notificaciones/leer-todas': [jsonResponse(500, { detail: 'boom' }), jsonResponse(200, { noLeidas: 0, marcadas: 2 })],
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    await screen.findByText('Tenés 2 sin leer.');

    await user.click(screen.getByRole('button', { name: 'Marcar todas como leídas' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(await screen.findByText('Tenés 2 sin leer.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Marcar todas como leídas' }));
    expect(await screen.findByText('No tenés avisos sin leer.')).toBeInTheDocument();
    expect(calls.filter((call) => call.key === 'POST /notificaciones/leer-todas')).toHaveLength(2);
  });

  it('la bandeja y las preferencias son pantallas separadas', async () => {
    withInbox({
      'GET /notificaciones': bandeja([aviso('a')]),
      'GET /notificaciones/preferencias': jsonResponse(200, { preferencias: [], recordatorio: { modo: 'NINGUNO', intervaloHoras: null, horarios: [] } }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.click(await screen.findByRole('link', { name: 'Preferencias' }));

    expect(await screen.findByRole('heading', { name: 'Preferencias de notificaciones' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Volver a la bandeja' })).toHaveAttribute('href', '/app/notificaciones');
  });
});
