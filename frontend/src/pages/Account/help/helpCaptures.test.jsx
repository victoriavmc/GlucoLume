// Capturas de la guía: cada referencia existe, cada PNG original tiene su miniatura WebP, la guía muestra la miniatura y el visor
// amplía el original (sin reducir calidad). Ver frontend/scripts/generar-miniaturas-ayuda.sh.
import { fireEvent, render, screen, within } from '@testing-library/react';
import { readdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { AYUDA_CLIENTE, AYUDA_INSTITUCIONAL } from './helpContent.js';
import { PasoImagen } from './GuiaVisual.jsx';

const AYUDA_DIR = join(dirname(fileURLToPath(import.meta.url)), '../../../../public/ayuda');
const MINIATURAS_DIR = join(AYUDA_DIR, 'miniaturas');

// Recorre el contenido de la guía y devuelve todos los valores `captura` que referencia.
function capturasReferenciadas(valor, acumulado = new Set()) {
  if (Array.isArray(valor)) valor.forEach((item) => capturasReferenciadas(item, acumulado));
  else if (valor && typeof valor === 'object') {
    for (const [clave, contenido] of Object.entries(valor)) {
      if (clave === 'captura' && typeof contenido === 'string') acumulado.add(contenido);
      else capturasReferenciadas(contenido, acumulado);
    }
  }
  return acumulado;
}

describe('Capturas de Ayuda: referencias y miniaturas', () => {
  const originales = readdirSync(AYUDA_DIR).filter((nombre) => nombre.endsWith('.png'));

  it('toda captura citada en la guía existe como PNG original', () => {
    const citadas = capturasReferenciadas([AYUDA_CLIENTE, AYUDA_INSTITUCIONAL]);
    expect(citadas.size).toBeGreaterThan(100);
    for (const captura of citadas) {
      expect(existsSync(join(AYUDA_DIR, captura)), `falta el original ${captura}`).toBe(true);
    }
  });

  it('cada PNG original tiene su miniatura WebP con el mismo nombre', () => {
    expect(originales.length).toBeGreaterThan(100);
    for (const original of originales) {
      const miniatura = original.replace(/\.png$/, '.webp');
      expect(existsSync(join(MINIATURAS_DIR, miniatura)), `falta la miniatura ${miniatura}`).toBe(true);
    }
  });

  it('no quedan miniaturas huérfanas (sin original)', () => {
    const miniaturas = readdirSync(MINIATURAS_DIR).filter((nombre) => nombre.endsWith('.webp'));
    for (const miniatura of miniaturas) {
      expect(existsSync(join(AYUDA_DIR, miniatura.replace(/\.webp$/, '.png'))), `miniatura sin original: ${miniatura}`).toBe(true);
    }
  });
});

describe('PasoImagen: miniatura en la guía, original en el visor', () => {
  it('muestra la miniatura WebP y guarda el PNG original para ampliar', () => {
    const { container } = render(<PasoImagen captura="grupo-creado.png" alt="Grupo creado" pie="Creaste el grupo." />);

    const imagen = container.querySelector('img');
    expect(imagen).toHaveAttribute('src', '/ayuda/miniaturas/grupo-creado.webp');
    expect(imagen).toHaveAttribute('alt', '');
    expect(imagen).toHaveAttribute('loading', 'lazy');

    const figura = container.querySelector('figure.help-captura');
    expect(figura).toHaveAttribute('data-src', '/ayuda/grupo-creado.png');
    expect(figura).toHaveAttribute('data-miniatura', '/ayuda/miniaturas/grupo-creado.webp');
    expect(screen.getByRole('button', { name: 'Ampliar imagen: Grupo creado' })).toBeInTheDocument();
    expect(screen.getByText('Creaste el grupo.')).toBeInTheDocument();
  });

  it('al ampliar, el visor usa el original y mantiene la navegación con flechas', () => {
    const { container } = render(
      <>
        <PasoImagen captura="grupo-creado.png" alt="Grupo creado" />
        <PasoImagen captura="grupo-privacidad.png" alt="Privacidad del grupo" />
      </>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Ampliar imagen: Grupo creado' }));

    const dialogo = screen.getByRole('dialog');
    const visor = dialogo.querySelector('.help-visor-img');
    expect(visor).toHaveAttribute('src', '/ayuda/grupo-creado.png');
    expect(visor.style.backgroundImage).toContain('/ayuda/miniaturas/grupo-creado.webp');
    expect(within(dialogo).getByText('1 de 2')).toBeInTheDocument();

    fireEvent.click(within(dialogo).getByRole('button', { name: 'Captura siguiente' }));
    expect(dialogo.querySelector('.help-visor-img')).toHaveAttribute('src', '/ayuda/grupo-privacidad.png');
    expect(within(dialogo).getByText('2 de 2')).toBeInTheDocument();
  });
});
