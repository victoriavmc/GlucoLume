// Semáforo de glucosa: solo se enciende la luz del color que informa el backend, con su rótulo; sin color no se muestra nada.

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Semaforo } from './Semaforo.jsx';

function litLights(container) {
  return [...container.querySelectorAll('.semaforo-luz.is-on')].map((light) => light.className);
}

describe('Semaforo', () => {
  it.each([
    ['ROJO', 'Muy alto', 'is-rojo'],
    ['AMARILLO', 'Revisar', 'is-amarillo'],
    ['VERDE', 'Está bien', 'is-verde'],
  ])('enciende solo la luz %s y muestra «%s»', (color, label, lightClass) => {
    const { container } = render(<Semaforo color={color} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(litLights(container)).toHaveLength(1);
    expect(litLights(container)[0]).toContain(lightClass);
    expect(container.querySelector('.semaforo')).toHaveClass(`is-${color.toLowerCase()}`);
  });

  it('no muestra nada sin color (sin regla o sin valor)', () => {
    const { container } = render(<Semaforo color={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
