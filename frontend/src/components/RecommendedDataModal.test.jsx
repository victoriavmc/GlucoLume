import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RecommendedDataModal } from './RecommendedDataModal.jsx';

let mockAccount;
vi.mock('../auth/AuthContext.jsx', () => ({ useAuth: () => ({ account: mockAccount }) }));

const KEY = 'glucolume.datosRecomendados.postergadoHasta.u-1';
const cuenta = (usuario) => ({ usuario: { idUsuario: 'u-1', tipoCuenta: 'CONSUMIDOR_FINAL', fechaNacimiento: null, sexo: null, ...usuario } });

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<RecommendedDataModal />} />
        <Route path="/app/perfil" element={<p>Pantalla de perfil</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  mockAccount = cuenta({});
});

describe('RecommendedDataModal', () => {
  it('aparece como alerta cuando falta la edad o el sexo, con «Más tarde» y «Completar datos»', () => {
    renderAt('/app/mediciones');
    const dialog = screen.getByRole('alertdialog', { name: 'Completá tu edad y sexo' });
    expect(dialog).toHaveTextContent(/Podés realizar mediciones sin completar tu edad o sexo/);
    expect(screen.getByRole('button', { name: 'Más tarde' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Completar datos' })).toHaveAttribute('href', '/app/perfil?editar=1');
  });

  it('no aparece si la cuenta ya tiene edad y sexo', () => {
    mockAccount = cuenta({ fechaNacimiento: '1990-05-17', sexo: 'FEMENINO' });
    renderAt('/app/inicio');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('no aparece en cuentas institucionales', () => {
    mockAccount = cuenta({ tipoCuenta: 'USUARIO_INSTITUCIONAL' });
    renderAt('/app/inicio');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('«Más tarde» lo oculta y no vuelve a mostrarse durante 7 días', async () => {
    const user = userEvent.setup();
    const { unmount } = renderAt('/app/mediciones');
    await user.click(screen.getByRole('button', { name: 'Más tarde' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(Number(window.localStorage.getItem(KEY))).toBeGreaterThan(Date.now() + 6 * 24 * 60 * 60 * 1000);
    unmount();

    renderAt('/app/inicio');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('vuelve a mostrarse cuando vence la postergación y los datos siguen faltando', () => {
    window.localStorage.setItem(KEY, String(Date.now() - 1000));
    renderAt('/app/inicio');
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('no se muestra en la propia pantalla de perfil', () => {
    renderAt('/app/perfil');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
