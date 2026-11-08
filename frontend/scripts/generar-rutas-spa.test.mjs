// Pruebas del generador del mapa de rutas de Nginx (B-2) y de su sincronía con el router.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { aExpresionNginx, extraerRutas, generarMapa } from './generar-rutas-spa.mjs';

const aqui = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(aqui, 'generar-rutas-spa.mjs');
const APP = join(aqui, '..', 'src', 'App.jsx');
const SNAPSHOT = join(aqui, '..', '..', 'docker', 'nginx', 'rutas-spa.generado.conf');

// Un router sintético con suficientes rutas literales para pasar la guarda de tamaño.
const rutasLiterales = Array.from({ length: 25 }, (_, i) => `<Route path="/r${i}" element={<X />} />`).join('\n');

describe('mapa de rutas de Nginx generado desde el router', () => {
  it('la copia versionada coincide con lo que genera el router actual (sin desincronía)', () => {
    const dir = mkdtempSync(join(tmpdir(), 'rutas-spa-'));
    try {
      const salida = join(dir, 'rutas-spa.conf');
      execFileSync(process.execPath, [SCRIPT, salida], { stdio: 'pipe' });
      expect(readFileSync(salida, 'utf8')).toBe(readFileSync(SNAPSHOT, 'utf8'));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('incluye las rutas anidadas, las de parámetros y las de las cuentas de plataforma', () => {
    const rutas = extraerRutas(readFileSync(APP, 'utf8'));
    expect(rutas).toEqual(expect.arrayContaining([
      '/app/mediciones/:idMedicion',
      '/app/grupo/:idGrupo/integrantes/:idGrupoUsuario',
      '/plataforma/auditoria/:idAuditoria',
      '/app/seguridad',
      '/plataforma/seguridad',
      '/cuenta/seguridad',
    ]));
  });

  it('no incluye el catch-all «*»: es lo que redirige lo desconocido, no una ruta', () => {
    const rutas = extraerRutas(readFileSync(APP, 'utf8'));
    expect(rutas.some((ruta) => ruta.includes('*'))).toBe(false);
  });

  it('traduce los parámetros a un segmento y escapa los puntos', () => {
    expect(aExpresionNginx('/consejos/:idConsejo')).toBe('^/consejos/[^/]+/?$');
    expect(aExpresionNginx('/a.b')).toBe('^/a\\.b/?$');
    expect(aExpresionNginx('/')).toBe('^/$');
  });

  it('la ruta index responde en la ruta de su padre', () => {
    const codigo = `<Routes>${rutasLiterales}
      <Route path="/padre" element={<L />}><Route index element={<X />} /><Route path="hijo" element={<X />} /></Route>
    </Routes>`;
    const rutas = extraerRutas(codigo);
    expect(rutas).toEqual(expect.arrayContaining(['/padre', '/padre/hijo']));
  });

  it('falla si una ruta no es un texto fijo (no se puede saber qué sirve sin ejecutar el código)', () => {
    const codigo = `<Routes>${rutasLiterales}<Route path={RUTA_DINAMICA} element={<X />} /></Routes>`;
    expect(() => extraerRutas(codigo)).toThrow(/no literal/);
  });

  it('falla si no encuentra un router reconocible (guarda contra un parseo que no lo vea)', () => {
    const codigo = '<Routes><Route path="/solo" element={<X />} /></Routes>';
    expect(() => extraerRutas(codigo)).toThrow(/se esperaban al menos/);
  });

  it('el mapa tiene la forma que espera la plantilla de Nginx', () => {
    const mapa = generarMapa(['/a', '/b/:id']);
    expect(mapa).toMatch(/^map \$uri \$ruta_spa \{\n {4}default 0;\n/m);
    expect(mapa).toContain('~*^/b/[^/]+/?$ 1;');
    expect(mapa.trimEnd().endsWith('}')).toBe(true);
  });
});
