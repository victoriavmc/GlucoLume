import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';
import { AYUDA_CLIENTE, AYUDA_INSTITUCIONAL } from './helpContent.js';

const EVOLUTION = { origen: 'TODOS', desde: null, hasta: null, puntos: [], truncado: false, estadisticas: { experimental: null, demo: null } };
const INSTITUCIONAL = { ...ACCOUNT, usuario: { ...ACCOUNT.usuario, tipoCuenta: 'USUARIO_INSTITUCIONAL' } };

function mockRoutes(account) {
  mockApi({
    'GET /auth/me': jsonResponse(200, account),
    'GET /measurements/evolution': jsonResponse(200, EVOLUTION),
    'GET /notificaciones': jsonResponse(200, { noLeidas: 0, total: 0, hayMas: false, notificaciones: [] }),
    'GET /instituciones': jsonResponse(200, { instituciones: [] }),
  });
}

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
});

describe('Ayuda: guía separada por tipo de cuenta', () => {
  it('una cuenta individual abre la guía de cliente, con sus temas', async () => {
    mockRoutes(ACCOUNT);
    renderAt('/app/ayuda');

    expect(await screen.findByRole('heading', { name: 'Ayuda' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cliente' })).toHaveAttribute('aria-selected', 'true');
    const temas = within(screen.getByRole('navigation', { name: /Temas de la guía cliente/ }));
    for (const tema of ['Primeros pasos', 'Perfil', 'Seguridad', 'Notificaciones', 'Conectar dispositivo', 'Mediciones', 'Grupo familiar']) {
      expect(temas.getByRole('link', { name: tema })).toBeInTheDocument();
    }
    expect(screen.queryByRole('region', { name: 'Tabla: Roles y secciones' })).toBeNull();
  });

  it('al pasar a Institucional muestra la tabla de roles por sección', async () => {
    mockRoutes(ACCOUNT);
    const user = userEvent.setup();
    renderAt('/app/ayuda');

    await user.click(await screen.findByRole('tab', { name: 'Institucional' }));

    expect(screen.getByRole('tab', { name: 'Institucional' })).toHaveAttribute('aria-selected', 'true');
    const tabla = screen.getByRole('region', { name: 'Tabla: Roles y secciones' });
    expect(within(tabla).getByRole('columnheader', { name: 'Propietario' })).toBeInTheDocument();
    expect(within(tabla).getByRole('rowheader', { name: 'Auditoría' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Roles y secciones' })).toBeInTheDocument();
  });

  it('una cuenta institucional abre directamente la guía institucional', async () => {
    mockRoutes(INSTITUCIONAL);
    renderAt('/app/ayuda');

    expect(await screen.findByRole('tab', { name: 'Institucional' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: 'Personal' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Grupo familiar' })).toBeNull();
  });

  it('el botón Ayuda de la barra lateral lleva a la guía, según el tipo de cuenta', async () => {
    mockRoutes(ACCOUNT);
    renderAt('/app/inicio');

    const menu = await screen.findByRole('navigation', { name: 'Secciones de la cuenta' });
    const ayuda = within(menu).getByRole('link', { name: 'Ayuda' });
    expect(ayuda).toHaveAttribute('href', '/app/ayuda');
  });
});

describe('Ayuda: capturas ampliables', () => {
  it('tocar una captura abre la imagen ampliada y Escape la cierra', async () => {
    mockRoutes(ACCOUNT);
    const user = userEvent.setup();
    renderAt('/app/ayuda');

    const captura = (await screen.findAllByRole('button', { name: /Ampliar imagen: Menú lateral con «Perfil»/ }))[0];
    await user.click(captura);

    const ampliada = await screen.findByRole('dialog', { name: 'Menú lateral: tocá «Perfil».' });
    expect(within(ampliada).getByRole('img', { name: 'Menú lateral con «Perfil» marcado' })).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('la X de cerrar del visor está arriba y cierra la imagen ampliada', async () => {
    mockRoutes(ACCOUNT);
    const user = userEvent.setup();
    renderAt('/app/ayuda');

    await user.click((await screen.findAllByRole('button', { name: /Ampliar imagen: Menú lateral con «Perfil»/ }))[0]);
    await screen.findByRole('dialog', { name: 'Menú lateral: tocá «Perfil».' });
    await user.click(screen.getByRole('button', { name: 'Cerrar' }));

    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('Ayuda: una imagen por paso', () => {
  it('el menú de una sección aparece una sola vez por tema, y un paso con pantalla propia no repite el menú', async () => {
    mockRoutes(ACCOUNT);
    renderAt('/app/ayuda');
    await screen.findByRole('heading', { name: 'Ayuda' });

    const mediciones = document.getElementById('ayuda-cliente-mediciones');
    expect(within(mediciones).getAllByRole('button', { name: /Ampliar imagen: Menú lateral con «Mediciones»/ })).toHaveLength(1);

    const perfil = document.getElementById('ayuda-cliente-perfil');
    expect(within(perfil).queryByRole('button', { name: /Ampliar imagen: Menú lateral/ })).toBeNull();
    expect(within(perfil).getByRole('button', { name: /Ampliar imagen: Pantalla donde está el botón «Editar perfil»/ })).toBeInTheDocument();
  });
});

describe('Ayuda: contenido', () => {
  it('cada tema tiene id único por guía y los enlaces apuntan al espacio privado', () => {
    for (const guia of [AYUDA_CLIENTE, AYUDA_INSTITUCIONAL]) {
      const ids = guia.map((tema) => tema.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const tema of guia) {
        for (const paso of tema.pasos ?? []) {
          if (paso.ir) expect(paso.ir.to.startsWith('/app/')).toBe(true);
        }
      }
    }
  });

  it('muestra los casos de registro e inicio de sesión de la guía de cliente', async () => {
    mockRoutes(ACCOUNT);
    renderAt('/app/ayuda');
    expect(await screen.findByText('CASO 3 · Sincronizar ambos')).toBeInTheDocument();
    expect(screen.getByText('CASO 6 · Perdiste la app y los códigos')).toBeInTheDocument();
  });
});
