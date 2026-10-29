import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, getAccessToken, hasSessionHint, saveTokens } from '../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const PROFILE = {
  ...ACCOUNT,
  usuario: { ...ACCOUNT.usuario, fechaNacimiento: '1990-05-17', sexo: 'FEMENINO' },
};

function withSession(account = PROFILE, routes = {}) {
  saveTokens(TOKENS, false);
  return mockApi({ 'GET /auth/me': jsonResponse(200, account), ...routes });
}

const sidebar = () => screen.getByRole('complementary', { name: 'Menú principal' });

beforeEach(() => clearTokens());

describe('Layout autenticado', () => {
  it('login correcto lleva a Inicio con el sidebar y la opción activa', async () => {
    mockApi({
      'POST /auth/login': jsonResponse(200, { estado: 'AUTENTICADO', tokens: TOKENS }),
      'GET /auth/me': jsonResponse(200, PROFILE),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await user.type(screen.getByLabelText('Correo electrónico o usuario'), 'victoria');
    await user.type(screen.getByLabelText('Contraseña'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: /^Iniciar sesión/ }));

    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.getByText('Nos alegra verte de nuevo en GlucoLume.')).toBeInTheDocument();
    const nav = within(sidebar()).getByRole('navigation');
    // Cuenta individual: tiene Grupo y no Instituciones.
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['Inicio', 'Mediciones', 'Conectar dispositivo', 'Grupo', 'Consejos', 'Perfil', 'Seguridad']);
    expect(within(nav).getByRole('link', { name: 'Inicio' })).toHaveAttribute('aria-current', 'page');
    expect(within(sidebar()).getByText('Victoria Cortés')).toBeInTheDocument();
    expect(within(sidebar()).getByText('@victoria')).toBeInTheDocument();
  });

  it('la ruta activa se resalta y /app redirige a Inicio', async () => {
    withSession();
    renderAt('/app/perfil');
    const nav = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    expect(within(nav).getByRole('link', { name: 'Perfil' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Inicio' })).not.toHaveAttribute('aria-current');
  });

  it('rutas privadas sin sesión redirigen al login', async () => {
    mockApi({});
    for (const path of ['/app/inicio', '/app/perfil', '/app/seguridad']) {
      const { unmount } = renderAt(path);
      expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
      unmount();
    }
  });

  it('en pantallas chicas el menú se abre como drawer y se cierra con Escape', async () => {
    withSession();
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const toggle = await screen.findByRole('button', { name: 'Abrir menú' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('cerrar sesión desde el sidebar revoca la sesión y vuelve al login', async () => {
    const { calls } = withSession(PROFILE, { 'POST /auth/logout': { ok: true, status: 204, json: async () => null } });
    const user = userEvent.setup();
    renderAt('/app/inicio');
    await user.click(await within(await screen.findByRole('complementary', { name: 'Menú principal' }))
      .findByRole('button', { name: 'Cerrar sesión' }));
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /auth/logout')).toBe(true);
    expect(getAccessToken()).toBeNull();
    expect(hasSessionHint()).toBe(false);
  });

  it('si el refresh token es rechazado durante el uso, vuelve al login', async () => {
    saveTokens({ ...TOKENS, accessToken: 'vencido' }, false);
    mockApi({
      'GET /auth/me': [jsonResponse(200, PROFILE), jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' })],
      'POST /auth/mfa/setup': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }),
      'POST /auth/refresh': jsonResponse(401, { codigo: 'TOKEN_INVALIDO', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    await user.click(await screen.findByRole('button', { name: 'Activar verificación en dos pasos' }));
    await user.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
  });
});

describe('Perfil', () => {
  it('muestra los datos reales en modo lectura, sin datos técnicos', async () => {
    withSession();
    renderAt('/app/perfil');
    expect(await screen.findByRole('heading', { name: 'Mi perfil' })).toBeInTheDocument();
    for (const value of ['victoria', 'victoria@example.com', 'Victoria', 'Cortés', 'Femenino', 'Usuario individual']) {
      expect(screen.getAllByText(value).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(/17\/05\/1990 \(\d+ años\)/)).toBeInTheDocument();
    expect(screen.queryByText(PROFILE.usuario.idUsuario)).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('editar y guardar envía solo los cambios y actualiza el estado global', async () => {
    const updated = {
      ...PROFILE,
      usuario: { ...PROFILE.usuario, nombre: 'Vicky', usuario: 'vicky_2026', fechaNacimiento: '1991-02-03' },
      actualizado: true,
      detail: 'Se registraron los cambios.',
    };
    const { calls } = withSession(PROFILE, { 'PATCH /auth/me/profile': jsonResponse(200, updated) });
    const user = userEvent.setup();
    renderAt('/app/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));

    expect(screen.getByLabelText('Correo electrónico')).toBeDisabled();
    await user.clear(screen.getByLabelText('Nombre'));
    await user.type(screen.getByLabelText('Nombre'), 'Vicky');
    await user.clear(screen.getByLabelText('Nombre de usuario'));
    await user.type(screen.getByLabelText('Nombre de usuario'), 'vicky_2026');
    const date = screen.getByLabelText('Fecha de nacimiento');
    await user.clear(date);
    await user.type(date, '1991-02-03');
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }));

    expect(await screen.findByText('Se registraron los cambios.')).toBeInTheDocument();
    const patch = calls.find((c) => c.key === 'PATCH /auth/me/profile');
    expect(patch.body).toEqual({ nombre: 'Vicky', usuario: 'vicky_2026', fechaNacimiento: '1991-02-03' });
    expect(patch.options.headers.Authorization).toBe('Bearer access-1');
    // Vuelve a modo lectura y el sidebar refleja el cambio de inmediato.
    expect(screen.queryByRole('button', { name: /Guardar cambios/ })).not.toBeInTheDocument();
    expect(within(sidebar()).getByText('Vicky Cortés')).toBeInTheDocument();
    expect(within(sidebar()).getByText('@vicky_2026')).toBeInTheDocument();
  });

  it('cancelar restaura los valores y no llama al backend', async () => {
    const { calls } = withSession();
    const user = userEvent.setup();
    renderAt('/app/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));
    await user.clear(screen.getByLabelText('Nombre'));
    await user.type(screen.getByLabelText('Nombre'), 'Otra');
    await user.click(screen.getByRole('button', { name: /Cancelar/ }));
    expect(screen.queryByDisplayValue('Otra')).not.toBeInTheDocument();
    expect(screen.getAllByText('Victoria').length).toBeGreaterThan(0);
    expect(calls.some((c) => c.key === 'PATCH /auth/me/profile')).toBe(false);
  });

  it('username duplicado: error controlado en el campo', async () => {
    withSession(PROFILE, {
      'PATCH /auth/me/profile': jsonResponse(409, {
        codigo: 'USUARIO_NO_DISPONIBLE',
        detail: 'El nombre de usuario ya se encuentra en uso. Elegí otro.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));
    await user.clear(screen.getByLabelText('Nombre de usuario'));
    await user.type(screen.getByLabelText('Nombre de usuario'), 'ocupado');
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }));
    expect(await screen.findByText('Ese nombre de usuario ya está en uso.')).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre de usuario')).toHaveAttribute('aria-invalid', 'true');
  });

  it('fecha de nacimiento futura y datos vacíos se rechazan antes de enviar', async () => {
    const { calls } = withSession();
    const user = userEvent.setup();
    renderAt('/app/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));
    const date = screen.getByLabelText('Fecha de nacimiento');
    expect(date).toHaveAttribute('max');
    await user.clear(date);
    await user.type(date, '2999-01-01');
    await user.clear(screen.getByLabelText('Apellido'));
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }));
    expect(screen.getByText('La fecha de nacimiento no puede ser futura.')).toBeInTheDocument();
    expect(screen.getByText('Este dato no puede quedar vacío.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'PATCH /auth/me/profile')).toBe(false);
  });

  it('el sexo solo ofrece los valores admitidos por la base', async () => {
    withSession();
    const user = userEvent.setup();
    renderAt('/app/perfil');
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));
    const options = [...screen.getByLabelText('Sexo').options].map((option) => option.value);
    expect(options).toEqual(['FEMENINO', 'MASCULINO']);
  });

  it('cuenta de Google sin usuario: no hay aviso obligatorio y, al editar el perfil, se pide el usuario', async () => {
    const google = {
      ...ACCOUNT,
      tieneCredencialLocal: false,
      tieneGoogle: true,
      requiereCompletarPerfil: true,
      camposFaltantes: ['usuario', 'fechaNacimiento', 'sexo'],
      usuario: { ...ACCOUNT.usuario, usuario: null },
    };
    const { calls } = withSession(google);
    const user = userEvent.setup();
    renderAt('/app/inicio');
    expect(await screen.findByRole('heading', { name: 'Hola, Victoria' })).toBeInTheDocument();
    expect(screen.queryByText(/Completá tu perfil/)).not.toBeInTheDocument(); // completar el perfil no es obligatorio
    await user.click(await screen.findByRole('link', { name: /Configurar perfil/ }));
    await user.click(await screen.findByRole('button', { name: 'Editar perfil' }));
    await user.click(await screen.findByRole('button', { name: /Guardar cambios/ }));
    expect(screen.getByText('Elegí un nombre de usuario.')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'PATCH /auth/me/profile')).toBe(false);
  });
});

describe('Seguridad: MFA', () => {
  it('activar: QR, código incorrecto rechazado, código correcto activa y muestra los códigos de recuperación', async () => {
    const enabled = { ...PROFILE, mfaHabilitado: true };
    saveTokens(TOKENS, false);
    const { calls } = mockApi({
      'GET /auth/me': [jsonResponse(200, PROFILE), jsonResponse(200, enabled)],
      'POST /auth/mfa/setup': jsonResponse(200, {
        secreto: 'JBSWY3DPEHPK3PXP',
        otpauthUri: 'otpauth://totp/GlucoLume:victoria%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=GlucoLume',
      }),
      'POST /auth/mfa/enable': [
        jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'Código inválido.' }),
        jsonResponse(200, { codigosRecuperacion: ['AAAA-BBBB', 'CCCC-DDDD'] }),
      ],
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await screen.findByRole('region', { name: 'Verificación en dos pasos' });
    expect(within(mfa).getByText('Estado: Desactivada')).toBeInTheDocument();
    await user.click(within(mfa).getByRole('button', { name: 'Activar verificación en dos pasos' }));
    await user.click(within(mfa).getByRole('button', { name: 'Continuar' }));

    expect(await within(mfa).findByTitle('Código QR para la aplicación autenticadora')).toBeInTheDocument();
    expect(within(mfa).queryByText(/JBSW Y3DP/)).not.toBeInTheDocument();
    await user.click(within(mfa).getByRole('button', { name: /Ingresá la clave manualmente/ }));
    expect(within(mfa).getByText('JBSW Y3DP EHPK 3PXP')).toBeInTheDocument();

    await user.click(within(mfa).getByRole('button', { name: /Verificar y activar/ }));
    expect(within(mfa).getByText('Ingresá el código de 6 dígitos que muestra la aplicación.')).toBeInTheDocument();
    await user.type(within(mfa).getByLabelText('Código de verificación'), '000000');
    await user.click(within(mfa).getByRole('button', { name: /Verificar y activar/ }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('El código no es correcto');
    expect(within(mfa).getByText('Estado: Desactivada')).toBeInTheDocument();

    await user.type(within(mfa).getByLabelText('Código de verificación'), '123456');
    await user.click(within(mfa).getByRole('button', { name: /Verificar y activar/ }));
    expect(await within(mfa).findByText('AAAA-BBBB')).toBeInTheDocument();
    expect(await within(mfa).findByText('Estado: Activada')).toHaveClass('ui-badge', 'ui-badge--success');
    await user.click(within(mfa).getByRole('button', { name: 'Ya los guardé' }));
    expect(within(mfa).queryByText('AAAA-BBBB')).not.toBeInTheDocument();
    expect(within(mfa).getByRole('button', { name: 'Desactivar verificación' })).toBeInTheDocument();
    // Un código incorrecto (401 CODIGO_INVALIDO) no dispara renovación de sesión ni se reenvía.
    expect(calls.filter((c) => c.key === 'POST /auth/mfa/enable')).toHaveLength(2);
    expect(calls.some((c) => c.key === 'POST /auth/refresh')).toBe(false);
  });

  it('MFA no disponible en el servidor: mensaje claro', async () => {
    withSession(PROFILE, {
      'POST /auth/mfa/setup': jsonResponse(503, { codigo: 'MFA_NO_DISPONIBLE', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await screen.findByRole('region', { name: 'Verificación en dos pasos' });
    await user.click(within(mfa).getByRole('button', { name: 'Activar verificación en dos pasos' }));
    await user.click(within(mfa).getByRole('button', { name: 'Continuar' }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('no está disponible en este momento');
  });

  it('desactivar exige un código (o uno de recuperación)', async () => {
    const enabled = { ...PROFILE, mfaHabilitado: true };
    const { calls } = mockApi({
      'GET /auth/me': [jsonResponse(200, enabled), jsonResponse(200, PROFILE)],
      'POST /auth/mfa/disable': [
        jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'x' }),
        jsonResponse(200, { mensaje: 'MFA deshabilitado.' }),
      ],
    });
    saveTokens(TOKENS, false);
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await screen.findByRole('region', { name: 'Verificación en dos pasos' });
    await user.click(within(mfa).getByRole('button', { name: 'Desactivar verificación' }));
    await user.click(within(mfa).getByRole('button', { name: /^Desactivar verificación$/ }));
    expect(within(mfa).getByText('Ingresá el código de 6 dígitos.')).toBeInTheDocument();

    await user.type(within(mfa).getByLabelText('Código de verificación'), '111111');
    await user.click(within(mfa).getByRole('button', { name: /^Desactivar verificación$/ }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('El código no es correcto');

    await user.click(within(mfa).getByRole('button', { name: 'Usar un código de recuperación' }));
    await user.type(within(mfa).getByLabelText('Código de recuperación'), 'AAAA-BBBB');
    await user.click(within(mfa).getByRole('button', { name: /^Desactivar verificación$/ }));
    expect(await within(mfa).findByText('La verificación en dos pasos quedó desactivada.')).toBeInTheDocument();
    expect(within(mfa).getByText('Estado: Desactivada')).toBeInTheDocument();
    expect(calls.filter((c) => c.key === 'POST /auth/mfa/disable').map((c) => c.body)).toEqual([
      { codigo: '111111' },
      { codigoRecuperacion: 'AAAA-BBBB' },
    ]);
  });
});

describe('Seguridad: contraseña, avisos y baja', () => {
  it('cuenta con contraseña: la cambia con la actual y confirma con éxito', async () => {
    const { calls } = withSession(PROFILE, {
      'POST /auth/password/change': jsonResponse(200, { mensaje: 'Cambiaste tu contraseña. Cerramos tus otras sesiones.' }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const panel = await screen.findByRole('region', { name: 'Contraseña' });
    expect(within(panel).queryByText(/todavía no está disponible/)).not.toBeInTheDocument();
    await user.type(within(panel).getByLabelText('Contraseña actual'), 'Actual#2026');
    await user.type(within(panel).getByLabelText('Contraseña nueva'), 'Glucolume#2027');
    await user.type(within(panel).getByLabelText('Confirmar contraseña nueva'), 'Glucolume#2027');
    await user.click(within(panel).getByRole('button', { name: 'Cambiar contraseña' }));
    expect(await within(panel).findByText(/Cambiaste tu contraseña con éxito/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /auth/password/change').body).toEqual({ passwordActual: 'Actual#2026', passwordNueva: 'Glucolume#2027' });
  });

  it('cambiar la contraseña valida los datos antes de enviar', async () => {
    withSession();
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const panel = await screen.findByRole('region', { name: 'Contraseña' });
    await user.type(within(panel).getByLabelText('Contraseña nueva'), 'Glucolume#2027');
    await user.type(within(panel).getByLabelText('Confirmar contraseña nueva'), 'Otra#2027xx');
    await user.click(within(panel).getByRole('button', { name: 'Cambiar contraseña' }));
    expect(await within(panel).findByText('Ingresá tu contraseña actual.')).toBeInTheDocument();
    expect(within(panel).getByText('Las contraseñas no coinciden.')).toBeInTheDocument();
  });

  it('cuenta solo Google: crea una contraseña con POST /auth/password', async () => {
    const google = { ...PROFILE, tieneCredencialLocal: false, tieneGoogle: true };
    const { calls } = mockApi({
      'GET /auth/me': [jsonResponse(200, google), jsonResponse(200, { ...google, tieneCredencialLocal: true })],
      'POST /auth/password': jsonResponse(201, { mensaje: 'Contraseña local agregada.' }),
    });
    saveTokens(TOKENS, false);
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const panel = await screen.findByRole('region', { name: 'Contraseña' });
    await user.type(within(panel).getByLabelText('Nueva contraseña'), 'Glucolume#2026');
    await user.type(within(panel).getByLabelText('Confirmar contraseña'), 'Glucolume#2026');
    await user.click(within(panel).getByRole('button', { name: 'Crear contraseña' }));
    expect(await within(panel).findByText(/Contraseña creada con éxito/)).toBeInTheDocument();
    expect(calls.find((c) => c.key === 'POST /auth/password').body).toEqual({ password: 'Glucolume#2026' });
  });

  it('avisos de inicio de sesión se guardan en el backend', async () => {
    const { calls } = withSession(PROFILE, {
      'PUT /auth/me/notifications/new-login': jsonResponse(200, { ...PROFILE, notificarNuevoInicioSesion: false }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const toggle = await screen.findByRole('switch', { name: 'Avisos de inicio de sesión' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    await user.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'));
    expect(calls.find((c) => c.key === 'PUT /auth/me/notifications/new-login').body).toEqual({ habilitada: false });
  });

  it('eliminar cuenta solo solicita el enlace por correo', async () => {
    const { calls } = withSession(PROFILE, {
      'POST /auth/account-deletion/request': jsonResponse(202, {
        mensaje: 'ok', fechaExpiracion: '2026-10-07T18:30:00', vigenciaMinutos: 30,
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const danger = await screen.findByRole('region', { name: 'Zona de riesgo' });
    await user.click(within(danger).getByRole('button', { name: 'Eliminar cuenta' }));
    await user.click(within(danger).getByRole('button', { name: /Enviar enlace de confirmación/ }));
    expect(await within(danger).findByText(/07\/10\/2026 a las 18:30/)).toBeInTheDocument();
    const request = calls.find((c) => c.key === 'POST /auth/account-deletion/request');
    expect(request.body).toBeUndefined();
  });

  it('un bloqueo de Grupo/Institución se informa sin enviar nada', async () => {
    withSession(PROFILE, {
      'POST /auth/account-deletion/request': jsonResponse(409, {
        codigo: 'PROPIETARIO_GRUPO_ACTIVO',
        detail: 'No puede eliminar su cuenta mientras sea responsable de un grupo activo.',
      }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const danger = await screen.findByRole('region', { name: 'Zona de riesgo' });
    await user.click(within(danger).getByRole('button', { name: 'Eliminar cuenta' }));
    await user.click(within(danger).getByRole('button', { name: /Enviar enlace de confirmación/ }));
    expect(await within(danger).findByRole('alert')).toHaveTextContent('responsable de un grupo activo');
  });
});

describe('Confirmación de la eliminación (enlace del correo)', () => {
  it('sin sesión: pide contraseña, se adapta si el backend pide MFA y al confirmar limpia la sesión', async () => {
    const { calls } = mockApi({
      'POST /auth/account-deletion/confirm': [
        jsonResponse(422, { codigo: 'CODIGO_MFA_REQUERIDO', detail: 'x' }),
        jsonResponse(200, { mensaje: 'La cuenta fue eliminada.' }),
      ],
    });
    const user = userEvent.setup();
    renderAt('/cuenta/eliminar/confirmar?token=tok-123');
    await waitFor(() => expect(window.location.search).toBe('')); // la pantalla se carga de forma diferida y borra el token de la URL al montarse

    await user.type(await screen.findByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: /Eliminar mi cuenta definitivamente/ }));
    expect(await screen.findByText('Ingresá el código de verificación en dos pasos.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Código de verificación'), '123456');
    await user.click(screen.getByRole('button', { name: /Eliminar mi cuenta definitivamente/ }));

    expect(await screen.findByText(/Tu cuenta fue eliminada/)).toBeInTheDocument();
    expect(calls.map((c) => c.body)).toEqual([
      { token: 'tok-123', password: 'Clave#2026' },
      { token: 'tok-123', password: 'Clave#2026', codigo: '123456' },
    ]);
  });

  it('enlace vencido: no permite reintentar', async () => {
    mockApi({ 'POST /auth/account-deletion/confirm': jsonResponse(410, { codigo: 'TOKEN_VENCIDO', detail: 'x' }) });
    const user = userEvent.setup();
    renderAt('/cuenta/eliminar/confirmar?token=viejo');
    await user.type(await screen.findByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(screen.getByRole('button', { name: /Eliminar mi cuenta definitivamente/ }));
    expect(await screen.findByText(/El enlace venció/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Eliminar mi cuenta definitivamente/ })).not.toBeInTheDocument();
  });
});


describe('Seguridad: perdió la aplicación y los códigos de recuperación', () => {
  const MFA_ON = { ...PROFILE, mfaHabilitado: true };

  async function openRecovery(user) {
    const mfa = await screen.findByRole('region', { name: 'Verificación en dos pasos' });
    await user.click(within(mfa).getByRole('button', { name: 'Desactivar verificación' }));
    expect(within(mfa).getByText(/confirmá con un código de tu aplicación o un código de recuperación/)).toBeInTheDocument();
    await user.click(within(mfa).getByRole('button', { name: 'Recuperar acceso de otra manera' }));
    return mfa;
  }

  it('contraseña + código del correo desvinculan el MFA', async () => {
    const { calls } = withSession(MFA_ON, {
      'POST /auth/me/mfa/recovery/start': [
        jsonResponse(403, { codigo: 'PASSWORD_INCORRECTA', detail: 'La contraseña ingresada no es correcta.' }),
        jsonResponse(200, { correoEnmascarado: 'vi******@example.com', vigenciaMinutos: 10 }),
      ],
      'POST /auth/me/mfa/recovery/verify': [
        jsonResponse(401, { codigo: 'CODIGO_INVALIDO', detail: 'El código ingresado no es válido.' }),
        jsonResponse(200, PROFILE),
      ],
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await openRecovery(user);

    expect(within(mfa).getByText('Recuperar acceso a la verificación en dos pasos')).toBeInTheDocument();
    expect(within(mfa).queryByLabelText('Código de verificación')).not.toBeInTheDocument();
    await user.type(within(mfa).getByLabelText('Contraseña actual'), 'Mala#2026');
    await user.click(within(mfa).getByRole('button', { name: 'Continuar' }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('La contraseña ingresada no es correcta.');

    await user.clear(within(mfa).getByLabelText('Contraseña actual'));
    await user.type(within(mfa).getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(within(mfa).getByRole('button', { name: 'Continuar' }));
    expect(await within(mfa).findByText('vi******@example.com')).toBeInTheDocument();

    await user.type(within(mfa).getByLabelText('Código enviado a tu correo'), '000000');
    await user.click(within(mfa).getByRole('button', { name: /Verificar y desvincular MFA/ }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('El código ingresado no es válido.');
    expect(within(mfa).getByText('Estado: Activada')).toBeInTheDocument();

    await user.type(within(mfa).getByLabelText('Código enviado a tu correo'), '482913');
    await user.click(within(mfa).getByRole('button', { name: /Verificar y desvincular MFA/ }));
    expect(await within(mfa).findByText(/El método de autenticación anterior fue desvinculado/)).toBeInTheDocument();
    expect(within(mfa).getByText('Estado: Desactivada')).toBeInTheDocument();
    expect(within(mfa).getByRole('button', { name: 'Activar verificación en dos pasos' })).toBeInTheDocument();

    expect(calls.filter((c) => c.key === 'POST /auth/me/mfa/recovery/start').map((c) => c.body)).toEqual([
      { password: 'Mala#2026' }, { password: 'Clave#2026' },
    ]);
    expect(calls.filter((c) => c.key === 'POST /auth/me/mfa/recovery/verify').map((c) => c.body)).toEqual([
      { codigo: '000000' }, { codigo: '482913' },
    ]);
    expect(calls.some((c) => c.key === 'POST /auth/mfa/disable')).toBe(false);
  });

  it('reenviar código y código vencido', async () => {
    const { calls } = withSession(MFA_ON, {
      'POST /auth/me/mfa/recovery/start': [
        jsonResponse(200, { correoEnmascarado: 'vi******@example.com', vigenciaMinutos: 10 }),
        jsonResponse(429, { codigo: 'DEMASIADAS_SOLICITUDES', detail: 'Esperá un minuto antes de pedir un código nuevo.' }),
      ],
      'POST /auth/me/mfa/recovery/verify': jsonResponse(410, { codigo: 'CODIGO_VENCIDO', detail: 'El código venció. Solicitá uno nuevo.' }),
    });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await openRecovery(user);
    await user.type(within(mfa).getByLabelText('Contraseña actual'), 'Clave#2026');
    await user.click(within(mfa).getByRole('button', { name: 'Continuar' }));
    await user.type(await within(mfa).findByLabelText('Código enviado a tu correo'), '111111');
    await user.click(within(mfa).getByRole('button', { name: /Verificar y desvincular MFA/ }));
    expect(await within(mfa).findByRole('alert')).toHaveTextContent('El código venció. Solicitá uno nuevo.');
    await user.click(within(mfa).getByRole('button', { name: /Reenviar código/ }));
    expect(await within(mfa).findByText('Esperá un minuto antes de pedir un código nuevo.')).toBeInTheDocument();
    expect(calls.filter((c) => c.key === 'POST /auth/me/mfa/recovery/start')).toHaveLength(2);
  });

  it('cuenta solo Google: no pide contraseña y ofrece volver a ingresar con Google', async () => {
    const google = { ...MFA_ON, tieneCredencialLocal: false, tieneGoogle: true };
    const { calls } = withSession(google, { 'POST /auth/logout': { ok: true, status: 204, json: async () => null } });
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const user = userEvent.setup();
    renderAt('/app/seguridad');
    const mfa = await openRecovery(user);
    expect(within(mfa).queryByLabelText('Contraseña actual')).not.toBeInTheDocument();
    await user.click(within(mfa).getByRole('button', { name: /Volver a ingresar con Google/ }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('http://api.test/api/v1/auth/google/login'));
    expect(calls.some((c) => c.key === 'POST /auth/logout')).toBe(true);
    expect(calls.some((c) => c.key === 'POST /auth/me/mfa/recovery/start')).toBe(false);
  });
});
