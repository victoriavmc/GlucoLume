import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../auth/tokenStore.js';
import { TOKENS, jsonResponse, mockApi } from '../test/helpers.js';
import { NotificationToasts } from './NotificationToasts.jsx';
import { POLL_INTERVAL_MS } from './useIncomingNotifications.js';

vi.mock('./notificationSound.js', () => ({ playNotificationSound: vi.fn() }));
const { playNotificationSound } = await import('./notificationSound.js');

const aviso = (id, extra = {}) => ({
  idNotificacion: id, evento: 'AGREGADO_GRUPO', titulo: `Aviso ${id}`, mensaje: 'Te sumaron a un grupo.',
  url: '/app/grupo', fechaCreacion: '2026-10-29T10:00:00', leida: false, ...extra,
});
const inbox = (...items) => jsonResponse(200, { noLeidas: items.length, notificaciones: items });

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  vi.useFakeTimers({ shouldAdvanceTime: true });
  playNotificationSound.mockClear();
});

afterEach(() => vi.useRealTimers());

async function tick(ms) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('Avisos nuevos: cartel y sonido', () => {
  it('no anuncia los avisos que ya estaban y sí los nuevos, con sonido', async () => {
    mockApi({ 'GET /notificaciones': [inbox(aviso('a')), inbox(aviso('a'), aviso('b'))] });
    render(<MemoryRouter><NotificationToasts /></MemoryRouter>);
    await tick(0);
    expect(screen.queryByText('Aviso a')).not.toBeInTheDocument();
    expect(playNotificationSound).not.toHaveBeenCalled();

    await tick(POLL_INTERVAL_MS);
    expect(screen.getByText('Aviso b')).toBeInTheDocument();
    expect(screen.queryByText('Aviso a')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver' })).toHaveAttribute('href', '/app/grupo');
    expect(playNotificationSound).toHaveBeenCalledTimes(1);
  });

  it('el cartel se cierra solo y un error de red no rompe nada', async () => {
    mockApi({ 'GET /notificaciones': [inbox(), inbox(aviso('c')), new Error('sin red')] });
    render(<MemoryRouter><NotificationToasts /></MemoryRouter>);
    await tick(0);
    await tick(POLL_INTERVAL_MS);
    expect(screen.getByText('Aviso c')).toBeInTheDocument();
    await tick(8000);
    expect(screen.queryByText('Aviso c')).not.toBeInTheDocument();
    await tick(POLL_INTERVAL_MS);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
