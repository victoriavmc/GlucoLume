// Señales de indexación del HTML que el navegador (y el rastreador que ejecuta JavaScript) ve en cada ruta (A-6, auditoría 2).
// Públicas: index, follow y canonical a su propia URL. Privadas y de autenticación: noindex, nofollow y sin canonical.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { jsonResponse, mockApi } from '../test/helpers.js';
import { renderAt } from '../test/renderApp.jsx';
import { PREFIJOS_PRIVADOS, SITE_ORIGIN, esRutaPrivada, politicaIndexacion } from './indexacion.js';

const PUBLICAS = ['/', '/privacidad', '/consejos', '/caracteristicas', '/ayuda'];
const PRIVADAS = ['/login', '/registro', '/recuperar-contrasena', '/plataforma/login', '/plataforma/dashboard', '/administracion/activar'];

// El navegador parte del HTML de index.html; jsdom no lo carga. Se copia su <head> para medir lo que de verdad ve el rastreador.
function cargarHeadDelShell() {
  const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');
  const shell = new DOMParser().parseFromString(html, 'text/html');
  document.head.innerHTML = shell.head.innerHTML;
}

beforeEach(() => {
  cargarHeadDelShell();
  mockApi({
    'GET /auth/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
    'POST /auth/refresh': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
    'GET /platform/me': jsonResponse(401, { codigo: 'NO_AUTENTICADO', detail: 'Sin sesión.' }),
  });
});

function robotsDelHead() {
  return document.head.querySelector('meta[name="robots"]')?.getAttribute('content') ?? null;
}

function canonicalDelHead() {
  return document.head.querySelector('link[rel="canonical"]')?.getAttribute('href') ?? null;
}

describe('política de indexación (función pura)', () => {
  it('distingue rutas públicas, privadas y de autenticación', () => {
    for (const path of PUBLICAS) expect(esRutaPrivada(path)).toBe(false);
    for (const path of PRIVADAS) expect(esRutaPrivada(path)).toBe(true);
    expect(esRutaPrivada('/app/inicio')).toBe(true);
    expect(esRutaPrivada('/cuenta/eliminar/confirmar')).toBe(true);
    expect(esRutaPrivada('/auth/google/callback')).toBe(true);
  });

  it('una ruta privada nunca se canonicaliza a la home ni queda indexable', () => {
    expect(politicaIndexacion('/app/inicio')).toEqual({ robots: 'noindex, nofollow', canonical: null });
    expect(politicaIndexacion('/plataforma/dashboard')).toEqual({ robots: 'noindex, nofollow', canonical: null });
  });

  it('una ruta pública se canonicaliza a sí misma', () => {
    expect(politicaIndexacion('/ayuda')).toEqual({ robots: 'index, follow', canonical: `${SITE_ORIGIN}/ayuda` });
    expect(politicaIndexacion('/')).toEqual({ robots: 'index, follow', canonical: `${SITE_ORIGIN}/` });
  });
});

describe('HTML resultante por ruta (el head real después de renderizar)', () => {
  it.each(PUBLICAS)('pública %s: index, follow y canonical propio', async (path) => {
    renderAt(path);
    await waitFor(() => expect(robotsDelHead()).toBe('index, follow'));
    expect(canonicalDelHead()).toBe(`${SITE_ORIGIN}${path}`);
  });

  it.each(PRIVADAS)('privada o de autenticación %s: noindex, nofollow y sin canonical', async (path) => {
    renderAt(path);
    await waitFor(() => expect(robotsDelHead()).toBe('noindex, nofollow'));
    expect(canonicalDelHead()).toBeNull();
  });

  it('al pasar de una ruta privada a una pública el canonical aparece y el noindex se quita', async () => {
    const { unmount } = renderAt('/login');
    await waitFor(() => expect(robotsDelHead()).toBe('noindex, nofollow'));
    unmount();
    renderAt('/ayuda');
    await waitFor(() => expect(robotsDelHead()).toBe('index, follow'));
    expect(canonicalDelHead()).toBe(`${SITE_ORIGIN}/ayuda`);
  });

  it('el HTML estático del shell no declara un canonical fijo a la home ni un robots fijo', () => {
    const shell = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');
    expect(shell).not.toMatch(/rel="canonical"/);
    expect(shell).not.toMatch(/name="robots"/);
  });
});

describe('sincronía con Nginx', () => {
  it('la lista de rutas privadas es la misma que el mapa $robots_tag de docker/nginx/default.conf.template', () => {
    const plantilla = readFileSync(resolve(process.cwd(), '../docker/nginx/default.conf.template'), 'utf8');
    const linea = plantilla.split('\n').find((l) => l.includes('"noindex, nofollow"') && l.includes('~*^/'));
    expect(linea).toBeTruthy();
    const prefijosNginx = linea.match(/~\*\^\/\(([^)]+)\)/)[1].split('|');
    expect([...PREFIJOS_PRIVADOS].sort()).toEqual([...prefijosNginx].sort());
  });
});
