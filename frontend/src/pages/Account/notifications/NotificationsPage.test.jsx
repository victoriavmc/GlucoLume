import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

const PROFILE = {
  ...ACCOUNT,
  usuario: { ...ACCOUNT.usuario, fechaNacimiento: '1990-05-17', sexo: 'FEMENINO' },
};

const SETTINGS = {
  preferencias: [
    { evento: 'INICIO_SESION', enPagina: true, porCorreo: true },
    { evento: 'AGREGADO_GRUPO', enPagina: true, porCorreo: true },
    { evento: 'RECORDATORIO_MEDICION', enPagina: true, porCorreo: false },
    { evento: 'NUEVA_ACCION_GRUPO', enPagina: true, porCorreo: true },
  ],
  recordatorio: { modo: 'NINGUNO', intervaloHoras: null, horarios: [] },
};

const INBOX = {
  noLeidas: 1,
  notificaciones: [{
    idNotificacion: 'n1', evento: 'INICIO_SESION', titulo: 'Nuevo inicio de sesión',
    mensaje: 'Se inició sesión en tu cuenta.', url: '/app/seguridad', fechaCreacion: '2026-10-29T10:15:00-03:00', leida: false,
  }],
};

function withNotifications(routes = {}, account = PROFILE) {
  saveTokens(TOKENS, false);
  return mockApi({
    'GET /auth/me': jsonResponse(200, account),
    'GET /notificaciones/preferencias': jsonResponse(200, SETTINGS),
    'GET /notificaciones': jsonResponse(200, INBOX),
    ...routes,
  });
}

beforeEach(() => clearTokens());

describe('Notificaciones', () => {
  it('muestra la bandeja, los canales de cada aviso y el horario de una cuenta individual', async () => {
    withNotifications();
    renderAt('/app/notificaciones');

    expect(await screen.findByText('Tenés 1 sin leer.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Notificaciones' })).toBeInTheDocument();
    expect(screen.getByText('Nuevo inicio de sesión')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'En la página: Inicio de sesión' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: 'Por correo: Inicio de sesión' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: 'Por correo: Recordatorio para medirme' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('region', { name: 'Horario para medirme' })).toBeInTheDocument();
  });

  it('una cuenta institucional solo ve el aviso de inicio de sesión y no el horario de medición', async () => {
    const institucional = { ...PROFILE, usuario: { ...PROFILE.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    withNotifications({}, institucional);
    renderAt('/app/notificaciones');

    expect(await screen.findByRole('heading', { name: 'Qué avisos recibir' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Por correo: Inicio de sesión' })).toBeInTheDocument();
    expect(screen.queryByText('Me agregan a un grupo')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Horario para medirme' })).not.toBeInTheDocument();
  });

  it('cambiar un canal lo guarda en el backend', async () => {
    const { calls } = withNotifications({
      'PUT /notificaciones/preferencias/RECORDATORIO_MEDICION': jsonResponse(200, {
        ...SETTINGS,
        preferencias: SETTINGS.preferencias.map((p) => (p.evento === 'RECORDATORIO_MEDICION' ? { ...p, porCorreo: true } : p)),
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    const toggle = await screen.findByRole('switch', { name: 'Por correo: Recordatorio para medirme' });
    await user.click(toggle);

    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(calls.find((c) => c.key === 'PUT /notificaciones/preferencias/RECORDATORIO_MEDICION').body).toEqual({ porCorreo: true });
  });

  it('guarda un horario a horas específicas', async () => {
    const { calls } = withNotifications({
      'PUT /notificaciones/recordatorio': jsonResponse(200, {
        ...SETTINGS, recordatorio: { modo: 'HORARIOS', intervaloHoras: null, horarios: ['07:30', '21:00'] },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('radio', { name: 'A horas específicas' }));
    fireEvent.change(within(schedule).getByLabelText('Horario 1'), { target: { value: '07:30' } });
    await user.click(within(schedule).getByRole('button', { name: 'Agregar horario' }));
    fireEvent.change(within(schedule).getByLabelText('Horario 2'), { target: { value: '21:00' } });
    await user.click(within(schedule).getByRole('button', { name: 'Guardar horario' }));

    expect(await within(schedule).findByText('Guardamos tu horario.')).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio').body).toEqual({
      modo: 'HORARIOS', horarios: ['07:30', '21:00'],
    });
  });

  it('un horario repetido se avisa antes de enviar', async () => {
    const { calls } = withNotifications();
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('radio', { name: 'A horas específicas' }));
    await user.click(within(schedule).getByRole('button', { name: 'Agregar horario' }));
    await user.click(within(schedule).getByRole('button', { name: 'Guardar horario' }));

    expect(await within(schedule).findByText('Hay horarios repetidos. Dejá uno solo por horario.')).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio')).toBeUndefined();
  });

  it('cada cuántas horas: guarda el intervalo elegido', async () => {
    const { calls } = withNotifications({
      'PUT /notificaciones/recordatorio': jsonResponse(200, {
        ...SETTINGS, recordatorio: { modo: 'INTERVALO', intervaloHoras: 6, horarios: [] },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('radio', { name: 'Cada cierto tiempo' }));
    await user.selectOptions(within(schedule).getByLabelText('Cada cuántas horas'), '6');
    await user.click(within(schedule).getByRole('button', { name: 'Guardar horario' }));

    await within(schedule).findByText('Guardamos tu horario.');
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio').body).toEqual({ modo: 'INTERVALO', intervaloHoras: 6 });
  });

  it('marcar un aviso como leído actualiza la bandeja', async () => {
    const { calls } = withNotifications({
      'POST /notificaciones/n1/leer': jsonResponse(200, {
        noLeidas: 0, notificaciones: [{ ...INBOX.notificaciones[0], leida: true }],
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones');

    await user.click(await screen.findByRole('button', { name: 'Marcar como leído' }));

    expect(await screen.findByText('No tenés avisos sin leer.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /notificaciones/n1/leer')).toBe(true);
  });
});
