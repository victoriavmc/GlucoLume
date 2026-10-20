import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const ROOT = import.meta.dirname;

// El backend admite por CORS solo el origen de FRONTEND_URL (http://localhost:5173 por defecto):
// strictPort evita que Vite cambie de puerto en silencio y las llamadas queden bloqueadas.
export default defineConfig(({ command, mode }) => {
  // Sin VITE_API_BASE_URL el build no sabe dónde está el backend: se corta al compilar, no con una página en
  // blanco al abrir la app. Se define en frontend/.env (ver .env.example) o como variable de entorno.
  const env = loadEnv(mode, ROOT, 'VITE_');
  if (command === 'build' && !env.VITE_API_BASE_URL) {
    throw new Error('Falta VITE_API_BASE_URL: copiá frontend/.env.example a frontend/.env y completala antes de compilar.');
  }
  // Solo "/" (mismo origen) o una URL http(s). Git Bash/MSYS convierte un "/" pasado por la línea de comandos en la ruta de Git
  // ("C:/Program Files/Git/"): el navegador terminaba pidiendo file:///C:/Program%20Files/Git/api/v1/... (19/10/2026).
  for (const name of ['VITE_API_BASE_URL', 'VITE_LOGIN_ORIGIN', 'VITE_APP_ORIGIN']) {
    const value = env[name];
    if (command === 'build' && value && !(name === 'VITE_API_BASE_URL' && value === '/') && !/^https?:\/\/[^\s/]+/.test(value)) {
      throw new Error(`${name} inválida («${value}»): debe ser "/" o una URL http(s). Si compilás desde Git Bash, usá MSYS_NO_PATHCONV=1 o PowerShell.`);
    }
  }

  return {
    root: ROOT,
    envDir: ROOT,
    plugins: [react()],
    server: { port: 5173, strictPort: true, host: 'localhost' },
    preview: { port: 5173, strictPort: true, host: 'localhost' },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.js'],
      env: { VITE_API_BASE_URL: 'http://api.test' },
      restoreMocks: true,
      unstubGlobals: true,
      // Los flujos completos tipean mucho con userEvent; con todos los archivos en paralelo superan los 5 s por defecto.
      testTimeout: 15000,
    },
  };
});
