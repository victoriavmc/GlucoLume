// Guarda estática de H-09: ningún archivo del frontend puede volver a guardar un refresh token en Web Storage ni leerlo del JSON de las respuestas.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = `${process.cwd()}/src/`;

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(jsx?|mjs)$/.test(name) && !/\.test\.jsx?$/.test(name) && !path.includes('/test/') ? [path] : [];
  });
}

describe('el refresh token no pasa por el JavaScript', () => {
  const files = sources(SRC);

  it('ningún archivo de producción usa «refreshToken» salvo para borrar el rastro del esquema anterior', () => {
    const offenders = files.filter((file) => !file.endsWith('auth/tokenStore.js') && /refreshToken/i.test(readFileSync(file, 'utf8')));
    expect(offenders.map((file) => file.replace(SRC, ''))).toEqual([]);
  });

  it('la única clave de refresh en Web Storage es la heredada, y solo se usa para borrarla', () => {
    const uses = files.flatMap((file) => readFileSync(file, 'utf8').split('\n')
      .filter((line) => line.includes('glucolume.refreshToken') || line.includes('LEGACY_REFRESH_KEY'))
      .map((line) => `${file.replace(SRC, '')}: ${line.trim()}`));
    expect(uses.every((line) => line.startsWith('auth/tokenStore.js'))).toBe(true);
    expect(uses.some((line) => /setItem\([^)]*LEGACY/.test(line))).toBe(false);
  });
});
