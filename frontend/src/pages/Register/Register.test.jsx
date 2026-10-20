import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens } from '../../auth/tokenStore.js';
import { jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

const PASSWORD = 'Glucolume#2026';

beforeEach(() => clearTokens());

async function fillCommon(user) {
  await user.type(screen.getByLabelText('Nombre'), 'Laura');
  await user.type(screen.getByLabelText('Apellido'), 'Díaz');
  await user.type(screen.getByLabelText('Correo electrónico'), 'laura@example.com');
  await user.type(screen.getByLabelText('Nombre de usuario'), 'lauradiaz');
  await user.type(screen.getByLabelText('Contraseña'), PASSWORD);
  await user.type(screen.getByLabelText('Repetir contraseña'), PASSWORD);
  await user.click(screen.getByRole('checkbox', { name: /Leí la Política de Privacidad/ }));
}

describe('Registro: selección del tipo de cuenta', () => {
  it('ofrece uso personal e institucional; el grupo no es un tipo de registro', () => {
    mockApi({});
    renderAt('/registro');
    expect(screen.getByText('¿Qué tipo de cuenta necesitás?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Uso personal/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Uso institucional/ })).toHaveTextContent(
      /Después podrás crear una institución o ser incorporado a una existente/,
    );
    expect(document.querySelectorAll('.type-option')).toHaveLength(2);
    expect(screen.getByText(/No es otro tipo de cuenta/)).toBeInTheDocument();
  });

  it('la elección se persiste en ?tipo= y el formulario no pide datos de institución', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderAt('/registro');
    await user.click(screen.getByRole('button', { name: /Uso institucional/ }));

    expect(screen.getByRole('group', { name: /Tus datos/ })).toBeInTheDocument();
    expect(screen.queryByLabelText(/institución/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('CUIT')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Crear cuenta institucional/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continuar con Google' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: /Cambiar/ }));
    await user.click(screen.getByRole('button', { name: /Uso personal/ }));
    expect(screen.getByRole('group', { name: /Tus datos/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Crear cuenta$/ })).toBeInTheDocument();
  });

  it('un tipo inválido vuelve a la selección', () => {
    mockApi({});
    renderAt('/registro?tipo=grupo');
    expect(screen.getByText('Elegí un tipo de cuenta para continuar.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Uso personal/ })).toBeInTheDocument();
  });
});

describe('Registro local', () => {
  it('valida los datos antes de llamar a la API', async () => {
    const { fetchMock } = mockApi({});
    const user = userEvent.setup();
    renderAt('/registro?tipo=usuario');
    await user.type(screen.getByLabelText('Nombre de usuario'), 'abc');
    await user.type(screen.getByLabelText('Contraseña'), 'corta');
    await user.type(screen.getByLabelText('Repetir contraseña'), 'otra');
    await user.click(screen.getByRole('button', { name: /Crear cuenta/ }));
    expect(screen.getByText('Ingresá tu nombre.')).toBeInTheDocument();
    expect(screen.getByText(/al menos 4 caracteres/)).toBeInTheDocument();
    expect(screen.getByText('La contraseña no cumple todos los requisitos.')).toBeInTheDocument();
    expect(screen.getByText('Las contraseñas no coinciden.')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('muestra en vivo los requisitos de la contraseña', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderAt('/registro?tipo=usuario');
    const rules = screen.getByRole('list', { name: 'Requisitos de la contraseña' });
    expect(within(rules).getAllByText(/\(pendiente\)/)).toHaveLength(5);
    await user.type(screen.getByLabelText('Contraseña'), PASSWORD);
    expect(within(rules).getAllByText(/\(cumplido\)/)).toHaveLength(5);
  });

  it.each([
    ['usuario', 'CONSUMIDOR_FINAL', /^Crear cuenta$/],
    ['institucion', 'USUARIO_INSTITUCIONAL', /Crear cuenta institucional/],
  ])('?tipo=%s crea solo la cuenta %s (sin institución)', async (tipo, tipoCuenta, button) => {
    const { calls } = mockApi({
      'POST /auth/register': jsonResponse(201, { idUsuario: 'x' }),
      'POST /auth/verify-email/resend': jsonResponse(202, { mensaje: 'ok' }),
    });
    const user = userEvent.setup();
    renderAt(`/registro?tipo=${tipo}`);
    await fillCommon(user);
    await user.click(screen.getByRole('button', { name: button }));

    expect(await screen.findByRole('heading', { name: 'Revisá tu correo' })).toBeInTheDocument();
    expect(calls[0].body).toEqual({
      nombre: 'Laura', apellido: 'Díaz', usuario: 'lauradiaz', correoElectronico: 'laura@example.com',
      password: PASSWORD, tipoCuenta, aceptaPoliticaPrivacidad: true,
    });

    await user.click(screen.getByRole('button', { name: 'Reenviar el correo' }));
    expect(await screen.findByText('Te enviamos un nuevo correo de verificación.')).toBeInTheDocument();
  });

  it('ubica en el campo los errores del backend', async () => {
    mockApi({
      'POST /auth/register': jsonResponse(409, { codigo: 'USUARIO_REGISTRADO', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt('/registro?tipo=institucion');
    await fillCommon(user);
    await user.click(screen.getByRole('button', { name: /Crear cuenta institucional/ }));
    expect(await screen.findByText('Ese nombre de usuario ya está en uso. Elegí otro.')).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre de usuario')).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('Registro con Google', () => {
  it.each([
    ['usuario', 'http://api.test/api/v1/auth/google/login?registro=usuario&acepta=true'],
    ['institucion', 'http://api.test/api/v1/auth/google/login?registro=institucion&acepta=true'],
  ])('?tipo=%s va directo al OAuth con la intención de registro', async (tipo, url) => {
    const { fetchMock } = mockApi({});
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const user = userEvent.setup();
    renderAt(`/registro?tipo=${tipo}`);
    await user.click(screen.getByRole('checkbox', { name: /Leí la Política de Privacidad/ }));
    await user.click(screen.getByRole('button', { name: 'Continuar con Google' }));
    // No exige ni guarda datos de institución en el navegador.
    expect(assign).toHaveBeenCalledWith(url);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(Object.keys(window.sessionStorage).filter((key) => /institu/i.test(key))).toEqual([]);
  });
});

describe('Registro con un correo que ya tiene cuenta', () => {
  it.each([
    ['usuario', /^Crear cuenta$/],
    ['institucion', /Crear cuenta institucional/],
  ])('?tipo=%s muestra un aviso: no se puede registrar, el correo ya existe con otra cuenta', async (tipo, button) => {
    const { calls } = mockApi({
      'POST /auth/register': jsonResponse(409, { codigo: 'CORREO_REGISTRADO', detail: 'x' }),
    });
    const user = userEvent.setup();
    renderAt(`/registro?tipo=${tipo}`);
    await fillCommon(user);
    await user.click(screen.getByRole('button', { name: button }));

    const dialog = await screen.findByRole('alertdialog', { name: 'Este correo ya está registrado' });
    expect(dialog).toHaveTextContent(/aunque la hayas creado con otro tipo \(personal o\s+institucional\)/);
    expect(within(dialog).getByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute('href', '/login');
    expect(calls.filter((call) => call.key === 'POST /auth/register')).toHaveLength(1);

    await user.click(within(dialog).getByRole('button', { name: 'Usar otro correo' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true');
  });

  it('con Google, el callback explica que ese correo ya existe con otro tipo de cuenta', async () => {
    mockApi({});
    renderAt('/auth/google/callback#error=CUENTA_OTRO_TIPO');
    expect(await screen.findByText(/ya está registrado con otro tipo de cuenta/)).toBeInTheDocument();
  });
});

describe('Registro: confirmación de la Política de Privacidad', () => {
  it('la casilla arranca sin marcar, enlaza a /privacidad y sin ella no se registra', async () => {
    const { fetchMock } = mockApi({});
    const user = userEvent.setup();
    renderAt('/registro?tipo=usuario');
    const checkbox = screen.getByRole('checkbox', { name: /Leí la Política de Privacidad/ });
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('link', { name: 'Política de Privacidad' })).toHaveAttribute('href', '/privacidad');

    await user.type(screen.getByLabelText('Nombre'), 'Laura');
    await user.type(screen.getByLabelText('Apellido'), 'Díaz');
    await user.type(screen.getByLabelText('Correo electrónico'), 'laura@example.com');
    await user.type(screen.getByLabelText('Nombre de usuario'), 'lauradiaz');
    await user.type(screen.getByLabelText('Contraseña'), PASSWORD);
    await user.type(screen.getByLabelText('Repetir contraseña'), PASSWORD);
    await user.click(screen.getByRole('button', { name: /^Crear cuenta$/ }));
    expect(screen.getByText('Para continuar tenés que confirmar que leíste la Política de Privacidad.')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('con Google tampoco se inicia OAuth sin confirmar la política', async () => {
    mockApi({});
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    const user = userEvent.setup();
    renderAt('/registro?tipo=usuario');
    await user.click(screen.getByRole('button', { name: 'Continuar con Google' }));
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByText(/confirmar que leíste la Política de Privacidad/)).toBeInTheDocument();
  });
});
