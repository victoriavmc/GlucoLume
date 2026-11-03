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

const pref = (evento, categoria, enPagina, porCorreo) => ({ evento, categoria, enPagina, porCorreo });

const SETTINGS = {
  preferencias: [
    pref('INICIO_SESION', 'SEGURIDAD', true, true),
    pref('CAMBIO_CONTRASENA', 'SEGURIDAD', true, true),
    pref('CAMBIO_MFA', 'SEGURIDAD', true, true),
    pref('ACTIVIDAD_SOSPECHOSA', 'SEGURIDAD', true, true),
    { ...pref('INTENTO_INGRESO', 'SEGURIDAD', true, false), correoDisponible: false },
    pref('INVITACION_GRUPO', 'GRUPO', true, true),
    pref('AGREGADO_GRUPO', 'GRUPO', true, true),
    pref('NUEVA_ACCION_GRUPO', 'GRUPO', true, true),
    pref('MEDICION_GRUPO', 'GRUPO', true, true),
    pref('RECORDATORIO_MEDICION', 'RECORDATORIO', true, false),
  ],
  recordatorio: { modo: 'NINGUNO', intervaloHoras: null, horarios: [] },
};

function withPreferences(routes = {}, account = PROFILE) {
  saveTokens(TOKENS, false);
  return mockApi({
    'GET /auth/me': jsonResponse(200, account),
    'GET /notificaciones/preferencias': jsonResponse(200, SETTINGS),
    ...routes,
  });
}

beforeEach(() => clearTokens());

describe('Preferencias de notificaciones', () => {
  it('agrupa los avisos por categoría con los canales en la aplicación y por correo', async () => {
    withPreferences();
    renderAt('/app/notificaciones/preferencias');

    expect(await screen.findByRole('region', { name: 'Seguridad' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Grupo familiar' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Recordatorios de medición' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Horario para medirme' })).toBeInTheDocument();
    const correo = screen.getByRole('switch', { name: 'Por correo: Recordatorio para medirme' });
    const aplicacion = screen.getByRole('switch', { name: 'En la aplicación: Recordatorio para medirme' });
    expect(correo).toHaveAttribute('aria-checked', 'false');
    expect(aplicacion).toHaveAttribute('aria-checked', 'true');
  });

  it('las alertas de seguridad se pueden apagar en la aplicación y su correo también es opcional', async () => {
    const { calls } = withPreferences({
      'PUT /notificaciones/preferencias/CAMBIO_CONTRASENA': jsonResponse(200, {
        ...SETTINGS,
        preferencias: SETTINGS.preferencias.map((p) => (p.evento === 'CAMBIO_CONTRASENA' ? { ...p, porCorreo: false } : p)),
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');

    const seguridad = await screen.findByRole('region', { name: 'Seguridad' });
    expect(within(seguridad).getByRole('switch', { name: 'En la aplicación: Cambios de contraseña' })).toBeEnabled();
    expect(within(seguridad).queryByText('Siempre activa')).not.toBeInTheDocument();
    const correo = within(seguridad).getByRole('switch', { name: 'Por correo: Cambios de contraseña' });
    expect(correo).toHaveAttribute('aria-checked', 'true');
    await user.click(correo);

    await waitFor(() => expect(correo).toHaveAttribute('aria-checked', 'false'));
    expect(calls.find((c) => c.key === 'PUT /notificaciones/preferencias/CAMBIO_CONTRASENA').body).toEqual({ porCorreo: false });
  });

  it('cambiar un canal guarda solo ese canal en el backend y no toca el otro', async () => {
    const { calls } = withPreferences({
      'PUT /notificaciones/preferencias/RECORDATORIO_MEDICION': jsonResponse(200, {
        ...SETTINGS,
        preferencias: SETTINGS.preferencias.map((p) => (p.evento === 'RECORDATORIO_MEDICION' ? { ...p, porCorreo: true } : p)),
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');

    const toggle = await screen.findByRole('switch', { name: 'Por correo: Recordatorio para medirme' });
    await user.click(toggle);

    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(screen.getByRole('switch', { name: 'En la aplicación: Recordatorio para medirme' })).toHaveAttribute('aria-checked', 'true');
    expect(calls.find((c) => c.key === 'PUT /notificaciones/preferencias/RECORDATORIO_MEDICION').body).toEqual({ porCorreo: true });
  });

  it('si el backend rechaza el cambio, muestra el error y el interruptor no cambia', async () => {
    withPreferences({ 'PUT /notificaciones/preferencias/INICIO_SESION': jsonResponse(500, { detail: 'boom' }) });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');

    const toggle = await screen.findByRole('switch', { name: 'En la aplicación: Nuevos dispositivos o accesos desconocidos' });
    await user.click(toggle);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('una cuenta institucional solo ve la categoría de seguridad y no el horario de medición', async () => {
    const institucional = { ...PROFILE, usuario: { ...PROFILE.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    withPreferences({}, institucional);
    renderAt('/app/notificaciones/preferencias');

    expect(await screen.findByRole('region', { name: 'Seguridad' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Grupo familiar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Horario para medirme' })).not.toBeInTheDocument();
  });

  it('un aviso de institución ofrece el correo como opción, apagado por omisión', async () => {
    const institucional = { ...PROFILE, usuario: { ...PROFILE.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };
    const conInstitucion = {
      preferencias: [...SETTINGS.preferencias, {
        evento: 'INSTITUCION_PACIENTE_NUEVO', categoria: 'INSTITUCION', enPagina: true, porCorreo: false,
        correoDisponible: true,
      }],
      recordatorio: SETTINGS.recordatorio,
    };
    withPreferences({ 'GET /notificaciones/preferencias': jsonResponse(200, conInstitucion) }, institucional);
    renderAt('/app/notificaciones/preferencias');

    expect(await screen.findByRole('region', { name: 'Institución' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'En la aplicación: Pacientes nuevos' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: 'Por correo: Pacientes nuevos' })).toHaveAttribute('aria-checked', 'false');
  });

  it('el envío del resultado ofrece el correo como opción: por omisión no llega y se guarda aparte', async () => {
    const conResultado = {
      preferencias: [...SETTINGS.preferencias, {
        evento: 'RESULTADO_ENVIADO', categoria: 'MEDICION', enPagina: true, porCorreo: false, correoDisponible: true,
      }],
      recordatorio: SETTINGS.recordatorio,
    };
    const { calls } = withPreferences({
      'GET /notificaciones/preferencias': jsonResponse(200, conResultado),
      'PUT /notificaciones/preferencias/RESULTADO_ENVIADO': jsonResponse(200, {
        ...conResultado,
        preferencias: conResultado.preferencias.map((p) => (p.evento === 'RESULTADO_ENVIADO' ? { ...p, porCorreo: true } : p)),
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');

    const toggle = await screen.findByRole('switch', { name: 'Por correo: Envío del resultado' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.click(toggle);

    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(calls.find((c) => c.key === 'PUT /notificaciones/preferencias/RESULTADO_ENVIADO').body).toEqual({ porCorreo: true });
  });

  it('muestra el error de carga', async () => {
    withPreferences({ 'GET /notificaciones/preferencias': jsonResponse(500, { detail: 'boom' }) });
    renderAt('/app/notificaciones/preferencias');

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('guarda un horario a horas específicas', async () => {
    const { calls } = withPreferences({
      'PUT /notificaciones/recordatorio': jsonResponse(200, {
        ...SETTINGS, recordatorio: { modo: 'HORARIOS', intervaloHoras: null, horarios: ['07:30', '21:00'] },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');
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
    expect(within(schedule).getByText(/todos los días a las 07:30, 21:00/)).toBeInTheDocument();
  });

  it('un horario repetido se avisa antes de enviar', async () => {
    const { calls } = withPreferences();
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('radio', { name: 'A horas específicas' }));
    await user.click(within(schedule).getByRole('button', { name: 'Agregar horario' }));
    await user.click(within(schedule).getByRole('button', { name: 'Guardar horario' }));

    expect(await within(schedule).findByText('Hay horarios repetidos. Dejá uno solo por horario.')).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio')).toBeUndefined();
  });

  it('cada cuántas horas: guarda el intervalo elegido', async () => {
    const { calls } = withPreferences({
      'PUT /notificaciones/recordatorio': jsonResponse(200, {
        ...SETTINGS, recordatorio: { modo: 'INTERVALO', intervaloHoras: 6, horarios: [] },
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('radio', { name: 'Cada cierto tiempo' }));
    await user.selectOptions(within(schedule).getByLabelText('Cada cuántas horas'), '6');
    await user.click(within(schedule).getByRole('button', { name: 'Guardar horario' }));

    await within(schedule).findByText('Guardamos tu horario.');
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio').body).toEqual({ modo: 'INTERVALO', intervaloHoras: 6 });
  });

  it('elimina la programación guardada', async () => {
    const programado = { ...SETTINGS, recordatorio: { modo: 'HORARIOS', intervaloHoras: null, horarios: ['08:00'] } };
    const { calls } = withPreferences({
      'GET /notificaciones/preferencias': jsonResponse(200, programado),
      'PUT /notificaciones/recordatorio': jsonResponse(200, SETTINGS),
    });
    const user = userEvent.setup();
    renderAt('/app/notificaciones/preferencias');
    const schedule = await screen.findByRole('region', { name: 'Horario para medirme' });

    await user.click(within(schedule).getByRole('button', { name: 'Eliminar programación' }));

    expect(await within(schedule).findByText('Quitamos tu programación.')).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'PUT /notificaciones/recordatorio').body).toEqual({ modo: 'NINGUNO' });
    expect(within(schedule).queryByRole('button', { name: 'Eliminar programación' })).not.toBeInTheDocument();
  });
});
