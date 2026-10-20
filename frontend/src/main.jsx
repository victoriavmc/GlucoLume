import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App.jsx';
import { OriginGuard } from './auth/OriginGuard.jsx';
import './styles/global.css';
import './styles/components.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <OriginGuard>
        <App />
      </OriginGuard>
    </BrowserRouter>
  </StrictMode>,
);
