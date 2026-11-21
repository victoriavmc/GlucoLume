import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

import { postponeKey } from '../components/recommendedDataStorage.js';
import { clearQueryCache } from '../utils/queryCache.js';
import { ACCOUNT } from './helpers.js';

// Las pantallas se cargan de forma diferida (React.lazy): la primera importación de cada módulo la transforma Vitest y, con los 50+ archivos en
// paralelo, puede pasar el segundo que esperan findBy*/waitFor por defecto.
configure({ asyncUtilTimeout: 6000 });

// jsdom no implementa el desplazamiento de la ventana.
window.scrollTo = () => {};

// El aviso de «Completá tu edad y sexo» aparece en la cuenta de prueba (que no tiene esos datos) y taparía las pantallas de cada prueba.
// Se deja postergado; RecommendedDataModal.test.jsx prueba el aviso sin esta postergación.
beforeEach(() => {
  window.localStorage.setItem(postponeKey(ACCOUNT.usuario.idUsuario), String(Date.now() + 365 * 24 * 60 * 60 * 1000));
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearQueryCache();
});
