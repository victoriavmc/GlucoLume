import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { POLL_INTERVAL_MS } from '../../../notifications/useIncomingNotifications.js';
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
    const tarjeta = screen.getByRole('button', { name: /^Aviso a/ });
    expect(within(tarjeta).getByText('Texto a')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Seguridad')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Sin leer')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /^Aviso b/ })).getByText('Leída')).toBeInTheDocument();
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

    expect(await screen.findByText('No tenés notificaciones')).toBeInTheDocument();
    expect(screen.getByText('No tenés avisos sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar todas como leídas' })).toBeDisabled();
  });

  it('muestra el estado de carga y, si falla, el error con la opción de reintentar', async () => {
    let attempt = 0;
    withInbox({
      'GET /notificaciones': async (options, url) => {
        // El cartel de avisos nuevos (layout) consulta aparte, solo no leídos: no cuenta como intento de la bandeja.
        if (new URL(url).searchParams.get('soloNoLeidas')) return bandeja([]);
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, 60)); // deja ver el estado de carga
        return attempt === 1 ? jsonResponse(500, { detail: 'boom' }) : bandeja([aviso('a')]);
      },
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    expect(await screen.findByText('Cargando tus notificaciones…')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(await screen.findByRole('button', { name: /^Aviso a/ })).toBeInTheDocument();
    expect(attempt).toBe(2);
  });

  it('se actualiza sola: un aviso nuevo aparece en la bandeja sin recargar la página', async () => {
    let primeraPagina = true;
    withInbox({
      'GET /notificaciones': (options, url) => {
        if (new URL(url).searchParams.get('soloNoLeidas')) return bandeja([]);
        const respuesta = primeraPagina ? bandeja([aviso('a')]) : bandeja([aviso('b'), aviso('a')]);
        primeraPagina = false;
        return respuesta;
      },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderAt('/app/notificaciones');
      await screen.findByRole('button', { name: /^Aviso a/ });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
      });

      expect(await screen.findByRole('button', { name: /^Aviso b/ })).toBeInTheDocument();
      expect(screen.getByText('Tenés 2 sin leer.')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('los filtros piden al backend la categoría o los no leídos', async () => {
    const { calls } = withInbox({ 'GET /notificaciones': () => bandeja([aviso('a')]) });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    await screen.findByRole('button', { name: /^Aviso a/ });

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
    await screen.findByRole('button', { name: /^Aviso a/ });

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Todas', 'No leídas', 'Seguridad', 'Institución']);
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

    await user.click(await screen.findByRole('button', { name: /^Aviso a/ }));

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

    await user.click(await screen.findByRole('button', { name: /^Aviso a/ }));

    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /^Aviso a/ })).getByText('Leída')).toBeInTheDocument();
  });

  it('marcar como leído es optimista y vuelve atrás si el backend lo rechaza', async () => {
    withInbox({
      'GET /notificaciones': bandeja([aviso('a', { url: null })]),
      'POST /notificaciones/a/leer': jsonResponse(500, { detail: 'boom' }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    await user.click(await screen.findByRole('button', { name: /^Aviso a/ }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /^Aviso a/ })).getByText('Sin leer')).toBeInTheDocument();
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

  describe('eliminar de la bandeja', () => {
    // Un backend simulado con estado: lo eliminado deja de venir en el siguiente GET (como la eliminación lógica de SQL Server).
    function statefulInbox(initial) {
      const state = { items: initial, deleted: [] };
      const visible = () => state.items.filter((item) => !state.deleted.includes(item.idNotificacion));
      const unread = () => visible().filter((item) => !item.leida).length;
      const routes = {
        'GET /notificaciones': (options, url) => {
          const params = new URL(url).searchParams;
          const list = params.get('soloNoLeidas') ? visible().filter((item) => !item.leida) : visible();
          return jsonResponse(200, { noLeidas: unread(), total: list.length, hayMas: false, notificaciones: list });
        },
      };
      for (const item of initial) {
        routes[`DELETE /notificaciones/${item.idNotificacion}`] = () => {
          state.deleted.push(item.idNotificacion);
          return jsonResponse(200, { noLeidas: unread(), eliminadas: 1 });
        };
        routes[`POST /notificaciones/${item.idNotificacion}/leer`] = () => {
          item.leida = true;
          return jsonResponse(200, { noLeidas: unread(), marcadas: 1 });
        };
      }
      routes['DELETE /notificaciones'] = (options, url) => {
        const alcance = new URL(url).searchParams.get('alcance');
        const removed = visible().filter((item) => alcance === 'todas' || item.leida);
        removed.forEach((item) => state.deleted.push(item.idNotificacion));
        return jsonResponse(200, { noLeidas: unread(), eliminadas: removed.length });
      };
      return { state, routes };
    }

    const menuOf = (titulo) => screen.getByRole('button', { name: new RegExp(`^Acciones de «${titulo}»`) });

    it('el menú de la tarjeta separa leer y abrir de eliminar y se maneja con el teclado', async () => {
      const { routes } = statefulInbox([aviso('a'), aviso('b', { leida: true, url: null })]);
      withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByRole('button', { name: /^Aviso a/ });

      await user.click(menuOf('Aviso a'));
      expect(menuOf('Aviso a')).toHaveAttribute('aria-expanded', 'true');
      expect(within(screen.getByRole('menu')).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['Abrir', 'Marcar como leída', 'Eliminar de la bandeja']);
      expect(screen.getByRole('menuitem', { name: 'Eliminar de la bandeja' }).closest('li')).toHaveClass('action-menu-group');
      expect(screen.getByRole('menuitem', { name: 'Abrir' })).toHaveFocus();

      await user.keyboard('{ArrowDown}');
      expect(screen.getByRole('menuitem', { name: 'Marcar como leída' })).toHaveFocus();
      await user.keyboard('{Escape}');
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
      expect(menuOf('Aviso a')).toHaveFocus();

      // Un aviso leído y sin destino solo ofrece eliminar.
      await user.click(menuOf('Aviso b'));
      expect(within(screen.getByRole('menu')).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['Eliminar de la bandeja']);
    });

    it('eliminar un aviso lo quita al instante, baja el contador y no vuelve al recargar', async () => {
      const { state, routes } = statefulInbox([aviso('a'), aviso('b')]);
      const { calls } = withInbox(routes);
      const user = userEvent.setup();
      const first = renderAt('/app/notificaciones');
      await screen.findByText('Tenés 2 sin leer.');

      await user.click(menuOf('Aviso a'));
      await user.click(screen.getByRole('menuitem', { name: 'Eliminar de la bandeja' }));

      expect(screen.queryByRole('button', { name: /^Aviso a/ })).not.toBeInTheDocument();
      expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
      expect(screen.getByText('Mostrando 1 de 1')).toBeInTheDocument();
      expect(calls.some((call) => call.key === 'DELETE /notificaciones/a')).toBe(true);
      expect(state.deleted).toEqual(['a']);

      first.unmount(); // «actualizar la página»: se vuelve a pedir todo al backend
      renderAt('/app/notificaciones');
      expect(await screen.findByRole('button', { name: /^Aviso b/ })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Aviso a/ })).not.toBeInTheDocument();
    });

    it('eliminar un aviso leído no cambia el contador de no leídas', async () => {
      const { routes } = statefulInbox([aviso('a'), aviso('b', { leida: true })]);
      withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 1 sin leer.');

      await user.click(menuOf('Aviso b'));
      await user.click(screen.getByRole('menuitem', { name: 'Eliminar de la bandeja' }));

      expect(screen.queryByRole('button', { name: /^Aviso b/ })).not.toBeInTheDocument();
      expect(screen.getByText('Tenés 1 sin leer.')).toBeInTheDocument();
    });

    it('si el backend rechaza la eliminación, el aviso vuelve a su lugar y se informa', async () => {
      const { routes } = statefulInbox([aviso('a'), aviso('b')]);
      routes['DELETE /notificaciones/a'] = jsonResponse(500, { detail: 'boom' });
      withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 2 sin leer.');

      await user.click(menuOf('Aviso a'));
      await user.click(screen.getByRole('menuitem', { name: 'Eliminar de la bandeja' }));

      expect(await screen.findByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Tenés 2 sin leer.')).toBeInTheDocument();
      const titles = screen.getAllByRole('button', { name: /^Aviso/ }).map((button) => button.textContent);
      expect(titles).toHaveLength(2);
      expect(titles[0]).toMatch(/^Aviso a/); // en su lugar original
    });

    it('«Marcar como leída» del menú lee sin abrir el destino ni eliminar', async () => {
      const { routes } = statefulInbox([aviso('a')]);
      const { calls } = withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 1 sin leer.');

      await user.click(menuOf('Aviso a'));
      await user.click(screen.getByRole('menuitem', { name: 'Marcar como leída' }));

      expect(await screen.findByText('No tenés avisos sin leer.')).toBeInTheDocument();
      expect(within(screen.getByRole('button', { name: /^Aviso a/ })).getByText('Leída')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument(); // no navegó
      expect(calls.some((call) => call.key.startsWith('DELETE'))).toBe(false);
    });

    it('«Eliminar las leídas» quita solo las leídas y conserva las sin leer', async () => {
      const { routes } = statefulInbox([aviso('a'), aviso('b', { leida: true }), aviso('c', { leida: true })]);
      const { calls } = withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 1 sin leer.');

      await user.click(screen.getByRole('button', { name: 'Eliminar notificaciones' }));
      await user.click(screen.getByRole('menuitem', { name: 'Eliminar las leídas' }));

      expect(screen.queryByRole('button', { name: /^Aviso b/ })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Aviso c/ })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^Aviso a/ })).toBeInTheDocument();
      expect(screen.getByText('Tenés 1 sin leer.')).toBeInTheDocument();
      expect(calls.find((call) => call.key === 'DELETE /notificaciones').url).toContain('alcance=leidas');
    });

    it('vaciar la bandeja pide confirmación, no hace nada si se cancela y deja el estado vacío si se confirma', async () => {
      const { state, routes } = statefulInbox([aviso('a'), aviso('b', { leida: true })]);
      const { calls } = withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 1 sin leer.');

      await user.click(screen.getByRole('button', { name: 'Eliminar notificaciones' }));
      await user.click(screen.getByRole('menuitem', { name: 'Vaciar la bandeja…' }));
      const dialog = screen.getByRole('alertdialog', { name: '¿Vaciar la bandeja?' });
      expect(dialog).toHaveTextContent('también las que todavía no leíste');
      await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      expect(calls.some((call) => call.key === 'DELETE /notificaciones')).toBe(false);
      expect(screen.getByRole('button', { name: /^Aviso a/ })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Eliminar notificaciones' }));
      await user.click(screen.getByRole('menuitem', { name: 'Vaciar la bandeja…' }));
      await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Vaciar bandeja' }));

      expect(await screen.findByText('No tenés notificaciones')).toBeInTheDocument();
      expect(screen.getByText('No tenés avisos sin leer.')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Aviso/ })).not.toBeInTheDocument();
      expect(calls.find((call) => call.key === 'DELETE /notificaciones').url).toContain('alcance=todas');
      expect([...state.deleted].sort()).toEqual(['a', 'b']);
    });

    it('si falla el vaciado, la bandeja vuelve como estaba', async () => {
      const { routes } = statefulInbox([aviso('a'), aviso('b')]);
      routes['DELETE /notificaciones'] = jsonResponse(500, { detail: 'boom' });
      withInbox(routes);
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('Tenés 2 sin leer.');

      await user.click(screen.getByRole('button', { name: 'Eliminar notificaciones' }));
      await user.click(screen.getByRole('menuitem', { name: 'Vaciar la bandeja…' }));
      await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Vaciar bandeja' }));

      expect(await screen.findByRole('alert')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /^Aviso/ })).toHaveLength(2);
      expect(screen.getByText('Tenés 2 sin leer.')).toBeInTheDocument();
    });

    it('con la bandeja vacía las acciones de eliminar están deshabilitadas', async () => {
      withInbox({ 'GET /notificaciones': bandeja([]) });
      const user = userEvent.setup();
      renderAt('/app/notificaciones');
      await screen.findByText('No tenés notificaciones');

      await user.click(screen.getByRole('button', { name: 'Eliminar notificaciones' }));

      expect(screen.getByRole('menuitem', { name: 'Eliminar las leídas' })).toBeDisabled();
      expect(screen.getByRole('menuitem', { name: 'Vaciar la bandeja…' })).toBeDisabled();
    });
  });
});
