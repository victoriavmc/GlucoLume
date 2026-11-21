// Títulos de página, jerarquía de encabezados y reglas de accesibilidad (axe-core) de las páginas públicas y de acceso (A-9, auditoría 2).
// El contraste de color se excluye: jsdom no calcula estilos reales. Se verifica en el navegador.
import { waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { beforeEach, describe, expect, it } from 'vitest';

import { jsonResponse, mockApi } from '../test/helpers.js';
import { renderAt } from '../test/renderApp.jsx';

const ESTADO_NO_AUTENTICADO = {
  'GET /auth/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
  'POST /auth/refresh': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
  'GET /platform/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
};

// Título esperado por ruta (la ruta define el título, no el shell genérico de index.html).
const TITULOS = [
  ['/', 'GlucoLume · Medición no invasiva de glucosa (experimental)'],
  ['/login', 'Iniciar sesión · GlucoLume'],
  ['/registro', 'Crear cuenta · GlucoLume'],
  ['/recuperar-contrasena', 'Recuperar contraseña · GlucoLume'],
  ['/ayuda', 'Ayuda · GlucoLume'],
  ['/consejos', 'Consejos para diabéticos · GlucoLume'],
  ['/privacidad', 'Política de privacidad · GlucoLume'],
  ['/caracteristicas', 'Características y privacidad · GlucoLume'],
  ['/plataforma/login', 'Acceso administrativo · GlucoLume'],
  ['/administracion/login', 'Acceso administrativo · GlucoLume'],
  ['/plataforma/recuperar', 'Recuperar contraseña administrativa · GlucoLume'],
  ['/plataforma/restablecer?token=x', 'Nueva contraseña administrativa · GlucoLume'],
  ['/administracion/activar', 'Activar cuenta administrativa · GlucoLume'],
];

// Páginas que deben tener su propio encabezado de primer nivel (h1), tanto en el formulario como en el estado de error.
const RUTAS_CON_ENCABEZADOS = [
  '/plataforma/login', '/plataforma/recuperar', '/plataforma/restablecer', '/administracion/activar',
  '/restablecer-contrasena', '/recuperar-contrasena', '/login', '/registro', '/ayuda', '/consejos', '/privacidad', '/caracteristicas',
];

beforeEach(() => {
  mockApi(ESTADO_NO_AUTENTICADO);
});

function encabezados() {
  return [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) => ({ nivel: Number(h.tagName[1]), texto: h.textContent.trim() }));
}

describe('título de página por ruta', () => {
  it.each(TITULOS)('%s tiene un título descriptivo', async (ruta, titulo) => {
    renderAt(ruta);
    await waitFor(() => expect(document.title).toBe(titulo));
  });

  it('una página sin título propio no hereda el título genérico de otra ruta', async () => {
    renderAt('/plataforma/login');
    await waitFor(() => expect(document.title).toBe('Acceso administrativo · GlucoLume'));
    const { unmount } = renderAt('/ayuda');
    await waitFor(() => expect(document.title).toBe('Ayuda · GlucoLume'));
    unmount();
  });
});

describe('jerarquía semántica de encabezados', () => {
  it.each(RUTAS_CON_ENCABEZADOS)('%s empieza con un único h1 y no salta niveles', async (ruta) => {
    renderAt(ruta);
    await waitFor(() => expect(encabezados().length).toBeGreaterThan(0));
    const hs = encabezados();
    expect(hs[0].nivel, `primer encabezado de ${ruta}: ${JSON.stringify(hs[0])}`).toBe(1);
    expect(document.querySelectorAll('h1').length, `h1 en ${ruta}`).toBe(1);
    for (let i = 1; i < hs.length; i += 1) {
      expect(hs[i].nivel <= hs[i - 1].nivel + 1, `salto de nivel en ${ruta}: ${JSON.stringify(hs[i - 1])} -> ${JSON.stringify(hs[i])}`).toBe(true);
    }
  });

  it('el estado de enlace inválido (restablecer sin token) es un h2 bajo el único h1 de la página', async () => {
    renderAt('/plataforma/restablecer');
    await waitFor(() => expect(encabezados()).toContainEqual({ nivel: 2, texto: 'No pudimos usar este enlace' }));
    expect(encabezados()).toEqual([{ nivel: 1, texto: 'Nueva contraseña' }, { nivel: 2, texto: 'No pudimos usar este enlace' }]);
    expect(document.querySelectorAll('h1')).toHaveLength(1);
  });

  it('el estado de enlace inválido general (recuperación sin token) no salta de h1 a h3', async () => {
    renderAt('/restablecer-contrasena');
    await waitFor(() => expect(encabezados().length).toBeGreaterThan(0));
    const hs = encabezados();
    for (let i = 1; i < hs.length; i += 1) expect(hs[i].nivel <= hs[i - 1].nivel + 1).toBe(true);
  });
});

describe('reglas de accesibilidad (axe-core, sin contraste de color)', () => {
  const REGLAS = { 'color-contrast': { enabled: false } };

  it.each(['/plataforma/login', '/plataforma/recuperar', '/plataforma/restablecer', '/administracion/activar',
    '/login', '/registro', '/ayuda', '/privacidad', '/caracteristicas'])('%s sin violaciones de axe de gravedad seria o crítica', async (ruta) => {
    renderAt(ruta);
    await waitFor(() => expect(encabezados().length).toBeGreaterThan(0));
    const resultado = await axe.run(document.body, { rules: REGLAS });
    const graves = resultado.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
    expect(graves.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
