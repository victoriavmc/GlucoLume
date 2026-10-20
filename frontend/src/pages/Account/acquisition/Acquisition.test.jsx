import { act, configure, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../../../auth/tokenStore.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../../test/helpers.js';
import { renderAt } from '../../../test/renderApp.jsx';

// El stream SSE se reemplaza por uno controlado por la prueba (no hay Arduino): se inyectan los eventos que enviaría el backend.
const stream = vi.hoisted(() => ({ emit: null, closed: false }));
vi.mock('../../../api/acquisitionApi.js', async (importOriginal) => ({
  ...(await importOriginal()),
  openStream: vi.fn(({ onEvent }) => {
    stream.emit = onEvent;
    stream.closed = false;
    return () => { stream.closed = true; };
  }),
}));

configure({ asyncUtilTimeout: 5000 });

const DOWN = {
  conectado: false, ocupado: false, puerto: null, medio: null, baudios: null, estadoDispositivo: null, ultimoError: null,
  lineasInvalidas: 0, dispositivo: null, adquisicion: null,
};
const DEVICE = { codigo: 'GL-0001', sensor: 'MAX30102', firmware: '1.0.0', frecuenciaMuestreo: 25 };
const CONNECTED = { ...DOWN, conectado: true, puerto: 'COM7', medio: 'BLUETOOTH', baudios: 9600, dispositivo: DEVICE, estadoDispositivo: 'LISTO' };

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  stream.emit = null;
});

// «Conectar dispositivo» (diseño con puente local) se prueba en ConnectDevice.test.jsx.

const MEASUREMENT = {
  idMedicion: 'm-1', idPerfilMedicion: 'p-own', modoMedicion: 'OXIMETRIA', estadoMedicion: 'PENDIENTE',
  fechaHoraInicio: '2026-10-08T09:00:00', fechaHoraFin: null, fechaHoraUltimaComida: null, condicionComida: 'NO_INFORMADA',
  minutosDesdeUltimaComida: null, duracionMs: null, edadAlMomento: 36, sexoModelo: 'FEMENINO', versionFirmwareAlMomento: '1.0.0',
  modeloSensorAlMomento: 'MAX30102', versionAlgoritmo: null, calidadSenal: null, spo2: null, frecuenciaCardiaca: null,
  glucosaEstimada: null, observacion: null, matriz: null, cantidadMuestras: 0, referenciaCapilar: null, puedeOperar: true,
  dispositivo: { idDispositivo: 'd-1', codigoDispositivo: 'GL-0001', nombre: 'Oxímetro', modelo: 'HC-06', modeloSensor: 'MAX30102', versionFirmware: '1.0.0' },
  aviso: 'Resultado experimental de GlucoLume: no es un diagnóstico ni reemplaza una medición clínica certificada.',
};

describe('Adquisición en tiempo real', () => {
  it('inicia con el Arduino conectado, grafica las muestras reales y procesa al finalizar', async () => {
    let link = CONNECTED;
    const done = { ...MEASUREMENT, estadoMedicion: 'COMPLETADA', spo2: 97.2, frecuenciaCardiaca: 72, calidadSenal: 0.98,
      cantidadMuestras: 60, versionAlgoritmo: 'oximetria-ppg-v1', fechaHoraFin: '2026-10-08T09:00:30', duracionMs: 30000 };
    const { calls } = mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT),
      'GET /measurements/m-1': jsonResponse(200, MEASUREMENT),
      'GET /acquisition/status': () => jsonResponse(200, link),
      'POST /acquisition/start': () => {
        link = { ...CONNECTED, estadoDispositivo: 'ADQUIRIENDO', adquisicion: {
          idMedicion: 'm-1', estado: 'ADQUIRIENDO', muestras: 0, guardadas: 0, segundos: 0, error: null, codigoError: null, indicadores: null } };
        return jsonResponse(200, link);
      },
      'POST /acquisition/finish': jsonResponse(200, done),
    });
    const user = userEvent.setup();
    renderAt('/app/mediciones/m-1');
    const start = await screen.findByRole('button', { name: /Iniciar adquisición/ });
    expect(screen.getByText(/GL-0001 · MAX30102 · firmware 1.0.0/)).toBeInTheDocument();
    await user.click(start);
    expect(calls.find((call) => call.key === 'POST /acquisition/start').body).toEqual({ idMedicion: 'm-1' });

    const live = within(await screen.findByLabelText('Estado de la adquisición'));
    await vi.waitFor(() => expect(stream.emit).not.toBeNull());
    expect(live.getAllByText('Sin datos disponibles')).toHaveLength(2); // aún sin SpO₂ ni frecuencia: nada de ceros
    act(() => {
      for (let n = 0; n < 40; n += 1) stream.emit({ tipo: 'muestra', n, t: n * 40, red: 100000 + n * 10, ir: 120000 + n * 12 });
      stream.emit({ tipo: 'indicadores', spo2: 97.1, frecuenciaCardiaca: 73, calidad: 0.9, motivo: null, provisorio: true });
    });
    expect(await live.findByText('40')).toBeInTheDocument(); // muestras recibidas
    expect(live.getByText('97,1 %')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Canal rojo \(RED\): 40 muestras recientes/ })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Canal infrarrojo \(IR\)/ })).toBeInTheDocument();
    expect(screen.getByText(/provisorios/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Finalizar y procesar/ }));
    expect(await screen.findByLabelText('Resultados')).toHaveTextContent('97,2 %');
    expect(calls.some((call) => call.key === 'POST /acquisition/finish')).toBe(true);
    expect(screen.queryByRole('button', { name: /Finalizar y procesar/ })).not.toBeInTheDocument();
  });

  it('sin Arduino conectado lleva a conectar el dispositivo y no ofrece iniciar', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/m-1': jsonResponse(200, MEASUREMENT),
      'GET /acquisition/status': jsonResponse(200, DOWN),
    });
    renderAt('/app/mediciones/m-1');
    expect(await screen.findByText(/No hay un Arduino conectado/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Conectar dispositivo/ }).some((l) => l.getAttribute('href') === '/app/conectar-dispositivo')).toBe(true);
    expect(screen.queryByRole('button', { name: /Iniciar adquisición/ })).not.toBeInTheDocument();
  });

  it('un Arduino distinto del dispositivo elegido bloquea el inicio', async () => {
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/m-1': jsonResponse(200, MEASUREMENT),
      'GET /acquisition/status': jsonResponse(200, { ...CONNECTED, dispositivo: { ...DEVICE, codigo: 'OTRO-9' } }),
    });
    renderAt('/app/mediciones/m-1');
    expect(await screen.findByText(/no es el dispositivo elegido para esta medición/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Iniciar adquisición/ })).toBeDisabled();
  });

  it('si el dispositivo informa un error durante la adquisición lo muestra y deja finalizar lo recibido', async () => {
    const live = { ...CONNECTED, estadoDispositivo: 'ERROR_SENSOR', adquisicion: {
      idMedicion: 'm-1', estado: 'ERROR', muestras: 80, guardadas: 80, segundos: 3.2,
      error: 'El dispositivo informó que perdió el sensor MAX30100/MAX30102.', codigoError: 'SENSOR_DESCONECTADO', indicadores: null } };
    mockApi({
      'GET /auth/me': jsonResponse(200, ACCOUNT), 'GET /measurements/m-1': jsonResponse(200, { ...MEASUREMENT, estadoMedicion: 'ADQUIRIENDO', cantidadMuestras: 80 }),
      'GET /acquisition/status': jsonResponse(200, live),
    });
    renderAt('/app/mediciones/m-1');
    expect(await screen.findByText(/perdió el sensor MAX30100\/MAX30102/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Finalizar y procesar/ })).toBeEnabled();
  });
});
