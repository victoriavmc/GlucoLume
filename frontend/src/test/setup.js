import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// Las pantallas se cargan de forma diferida (React.lazy): la primera importación de cada módulo la transforma Vitest y, con los 50+ archivos en
// paralelo, puede pasar el segundo que esperan findBy*/waitFor por defecto.
configure({ asyncUtilTimeout: 6000 });

// jsdom no implementa el desplazamiento de la ventana.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
