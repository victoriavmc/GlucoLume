import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App, { preloadForPath, warmPrivateHome } from './App.jsx';
import { OriginGuard } from './auth/OriginGuard.jsx';
import { ErrorBoundary } from './components/ErrorBoundary.jsx';
import './styles/global.css';
import './styles/components.css';

preloadForPath(window.location.pathname); // descarga la pantalla pedida mientras se recupera la sesión
if (['/', '/login'].includes(window.location.pathname)) warmPrivateHome();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <OriginGuard>
          <App />
        </OriginGuard>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);
