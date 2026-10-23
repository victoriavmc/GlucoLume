import { vi } from 'vitest';

/** Respuesta JSON simulada de fetch. */
export function jsonResponse(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => {
      if (body === undefined) throw new SyntaxError('sin cuerpo');
      return body;
    },
  };
}

/** Reemplaza fetch con respuestas por "MÉTODO /ruta" (la primera coincidencia se consume si es una lista). */
export function mockApi(userRoutes) {
  // Por defecto la persona ya autorizó el almacenamiento de sus mediciones: los tests de consentimiento lo sobrescriben.
  const routes = { 'GET /auth/consents': jsonResponse(200, CONSENTS_ACCEPTED), ...userRoutes };
  const calls = [];
  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = new URL(url).pathname.replace('/api/v1', '');
    const key = `${options.method ?? 'GET'} ${path}`;
    calls.push({ key, url, options, body: options.body ? JSON.parse(options.body) : undefined });
    const route = routes[key];
    if (route === undefined) throw new Error(`Ruta no simulada: ${key}`);
    const next = Array.isArray(route) ? route.shift() : route;
    if (next instanceof Error) throw next;
    return typeof next === 'function' ? next(options, url) : next;
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

const consentStatus = (aceptado) => ({
  aceptado, versionVigente: '1.0', versionAceptada: aceptado ? '1.0' : null,
  estado: aceptado ? 'ACEPTADO' : null, fecha: aceptado ? '2026-10-13T10:00:00' : null,
});
export const CONSENTS_ACCEPTED = { POLITICA_PRIVACIDAD: consentStatus(true), DATOS_EXPERIMENTALES: consentStatus(true) };
export const CONSENTS_PENDING = { POLITICA_PRIVACIDAD: consentStatus(true), DATOS_EXPERIMENTALES: consentStatus(false) };

export const TOKENS = { accessToken: 'access-1', refreshToken: null, tokenType: 'bearer', expiresIn: 1800 };

export const ACCOUNT = {
  usuario: {
    idUsuario: '3f1c1e2a-0000-4000-8000-000000000001',
    nombre: 'Victoria',
    apellido: 'Cortés',
    usuario: 'victoria',
    correoElectronico: 'victoria@example.com',
    tipoCuenta: 'CONSUMIDOR_FINAL',
    estado: 'ACTIVO',
    fechaCreacion: '2026-10-01T10:00:00',
    fechaActualizacion: '2026-10-01T10:00:00',
  },
  tieneCredencialLocal: true,
  tieneGoogle: false,
  mfaHabilitado: false,
  notificarNuevoInicioSesion: true,
  requiereCompletarPerfil: false,
  camposFaltantes: [],
};
