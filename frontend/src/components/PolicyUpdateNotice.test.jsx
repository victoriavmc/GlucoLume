// Aviso no bloqueante de la versión vigente de la Política: aparece si la versión no está aceptada, se acepta desde el aviso y se puede ocultar.
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { acceptPolicy, getConsents } from '../api/authApi.js';
import { PolicyUpdateNotice } from './PolicyUpdateNotice.jsx';

vi.mock('../api/authApi.js', () => ({
  getConsents: vi.fn(),
  acceptPolicy: vi.fn(),
}));

function renderNotice() {
  return render(<MemoryRouter><PolicyUpdateNotice /></MemoryRouter>);
}

describe('PolicyUpdateNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('se muestra cuando la versión vigente de la política no está aceptada y no bloquea nada', async () => {
    getConsents.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: false, versionAceptada: '1.1', versionVigente: '1.2' } });
    renderNotice();
    expect(await screen.findByRole('heading', { name: 'Actualizamos la Política de Privacidad' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Leer la política' })).toHaveAttribute('href', '/privacidad');
    expect(screen.getByText(/Tu acceso no cambia/)).toBeInTheDocument();
  });

  it('no se muestra si la versión vigente ya está aceptada', async () => {
    getConsents.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: true, versionAceptada: '1.2', versionVigente: '1.2' } });
    const { container } = renderNotice();
    await waitFor(() => expect(getConsents).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('si la consulta falla, no muestra nada', async () => {
    getConsents.mockRejectedValue(new Error('sin red'));
    const { container } = renderNotice();
    await waitFor(() => expect(getConsents).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('aceptar registra la versión y oculta el aviso', async () => {
    getConsents.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: false } });
    acceptPolicy.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: true } });
    const { container } = renderNotice();
    fireEvent.click(await screen.findByRole('button', { name: 'Acepto la versión 1.2' }));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(acceptPolicy).toHaveBeenCalledTimes(1);
  });

  it('si la aceptación falla, avisa y mantiene el aviso', async () => {
    getConsents.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: false } });
    acceptPolicy.mockRejectedValue(new Error('caído'));
    renderNotice();
    fireEvent.click(await screen.findByRole('button', { name: 'Acepto la versión 1.2' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos registrar tu aceptación');
    expect(screen.getByRole('button', { name: 'Acepto la versión 1.2' })).toBeEnabled();
  });

  it('«Ahora no» oculta el aviso sin registrar nada', async () => {
    getConsents.mockResolvedValue({ POLITICA_PRIVACIDAD: { aceptado: false } });
    const { container } = renderNotice();
    fireEvent.click(await screen.findByRole('button', { name: 'Ahora no' }));
    expect(container).toBeEmptyDOMElement();
    expect(acceptPolicy).not.toHaveBeenCalled();
  });
});
