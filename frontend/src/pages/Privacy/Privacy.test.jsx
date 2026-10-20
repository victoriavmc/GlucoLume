import { configure, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { EXPERIMENTAL_NOTICE_TEXT } from '../../components/ExperimentalNotice.jsx';
import { clearTokens } from '../../auth/tokenStore.js';
import { mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

configure({ asyncUtilTimeout: 5000 });
beforeEach(() => clearTokens());

describe('Política de Privacidad y aviso experimental (páginas públicas)', () => {
  it('/privacidad se consulta sin iniciar sesión y no llama a la API', async () => {
    const { fetchMock } = mockApi({});
    renderAt('/privacidad');
    expect(await screen.findByRole('heading', { level: 1, name: 'Política de Privacidad' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Qué datos personales recopila/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Cuánto tiempo se conservan/ })).toBeInTheDocument();
    expect(screen.getByText(/no es un plazo impuesto por la Ley\s+25\.326/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('nombra los servicios externos reales y no promete lo que no hace', () => {
    mockApi({});
    renderAt('/privacidad');
    expect(screen.getByText(/Google \(inicio de sesión con Google\)/)).toBeInTheDocument();
    expect(screen.getByText(/Proveedor de correo \(SMTP\)/)).toBeInTheDocument();
    expect(screen.getByText(/no usa herramientas de analítica, publicidad ni píxeles/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/cumple con la Ley|certificad[oa] (por|conforme)|inteligencia artificial/i);
  });

  it('el aviso experimental aparece en la política, con el texto exacto', () => {
    mockApi({});
    renderAt('/privacidad');
    expect(screen.getByRole('note', { name: 'Aviso de uso experimental' })).toHaveTextContent(EXPERIMENTAL_NOTICE_TEXT);
    expect(EXPERIMENTAL_NOTICE_TEXT).toBe(
      'GlucoLume es un prototipo tecnológico desarrollado con fines exclusivamente académicos y experimentales. ' +
        'Las estimaciones obtenidas no constituyen resultados clínicos, no permiten establecer diagnósticos y no deben ' +
        'utilizarse para tomar decisiones médicas o modificar tratamientos.',
    );
  });

  it('la página de inicio muestra el aviso y el pie enlaza a Privacidad', () => {
    mockApi({});
    renderAt('/');
    expect(screen.getAllByRole('note', { name: 'Aviso de uso experimental' })).toHaveLength(1);
    expect(screen.getByRole('navigation', { name: 'Información legal' }).querySelector('a')).toHaveAttribute('href', '/privacidad');
  });
});

describe('Callback de Google sin confirmar la política', () => {
  it('muestra el motivo y no deja continuar', async () => {
    mockApi({});
    renderAt('/auth/google/callback#error=POLITICA_NO_ACEPTADA');
    expect(await screen.findByText(/confirmar que leíste la Política de Privacidad/)).toBeInTheDocument();
  });
});
