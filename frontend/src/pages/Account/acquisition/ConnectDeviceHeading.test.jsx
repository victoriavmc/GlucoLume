// «Conectar dispositivo» dentro de una institución vive bajo el h1 del nombre de la institución: su título es un h2
// (una sola h1 por vista); la versión de la cuenta individual conserva su h1.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { ConnectDeviceView } from './ConnectDevicePage.jsx';

const STOPPED = { estado: 'SIN_PUENTE', ocupado: false, puente: null, lectura: null, avisoDispositivo: null, lineasInvalidas: 0, lecturasRecibidas: 0, sesion: null };
const READINESS = { listo: false, bloqueo: 'PUENTE', dispositivo: null, pasos: [{ id: 'PUENTE', titulo: 'Servicio puente', estado: 'ERROR', detalle: 'No se está ejecutando.', solucion: 'Iniciá el puente.' }] };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  mockApi({
    'GET /acquisition/telemetry/status': jsonResponse(200, STOPPED),
    'GET /acquisition/telemetry/readiness': jsonResponse(200, READINESS),
    'GET /measurements/profile': jsonResponse(200, { perfilDisponible: false }),
  });
});

describe('Título de «Conectar dispositivo»', () => {
  it('en una institución es un h2 bajo el h1 de la institución y ofrece volver al panel', async () => {
    render(
      <MemoryRouter>
        <h1>Centro Médico Aurora</h1>
        <ConnectDeviceView institution={{ idInstitucion: 'i-1', nombre: 'Centro Médico Aurora' }} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { level: 2, name: 'Conectar dispositivo' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('link', { name: /Panel de Centro Médico Aurora/ })).toHaveAttribute('href', '/app/instituciones/i-1');
  });

  it('en la cuenta individual es el h1 de la pantalla', async () => {
    render(<MemoryRouter><ConnectDeviceView /></MemoryRouter>);
    expect(await screen.findByRole('heading', { level: 1, name: 'Conectar dispositivo' })).toBeInTheDocument();
  });
});
