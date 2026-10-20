import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App.jsx';
import { AuthProvider } from '../auth/AuthContext.jsx';

/** Renderiza la aplicación completa en una ruta (incluido el fragmento, para el callback de Google). */
export function renderAt(path) {
  window.history.replaceState(null, '', path);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}
