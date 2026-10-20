import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PpgChart, buildPpgFrame, hasPpgSignal } from './PpgChart.jsx';

const ppgOf = (valores, latidos = [], extra = {}) => ({ hz: 25, inicio: 0, valores, latidos, edadSegundos: 0.2, ...extra });

describe('buildPpgFrame', () => {
  it('traza solo las muestras reales de la ventana y marca los latidos detectados', () => {
    const ppg = ppgOf(Array.from({ length: 100 }, (_, i) => (i % 10) * 5), [9, 19, 29]);
    const frame = buildPpgFrame(ppg, 99, 200);
    expect(frame.samples).toBe(100);
    expect(frame.path.startsWith('M')).toBe(true);
    expect(frame.path.match(/M/g)).toHaveLength(1);
    expect(frame.beats.map((beat) => beat.index)).toEqual([9, 19, 29]);
  });

  it('un hueco sin señal corta la línea: no se interpola', () => {
    const ppg = ppgOf([1, 2, 3, null, null, null, 7, 8, 9]);
    const frame = buildPpgFrame(ppg, 8, 200);
    expect(frame.path.match(/M/g)).toHaveLength(2);
    expect(frame.path).not.toMatch(/NaN/);
    expect(frame.samples).toBe(6);
  });

  it('solo dibuja hasta el borde derecho: lo que todavía no llegó a «ahora» no se adelanta', () => {
    const ppg = ppgOf(Array.from({ length: 100 }, (_, i) => i), [90]);
    const frame = buildPpgFrame(ppg, 60, 200);
    expect(frame.samples).toBe(61);
    expect(frame.beats).toEqual([]);
  });

  it('sin muestras reales no hay trazo', () => {
    expect(buildPpgFrame(ppgOf([null, null]), 1, 200)).toMatchObject({ path: '', samples: 0 });
  });

  it('una serie plana no inventa variación ni produce NaN', () => {
    expect(buildPpgFrame(ppgOf([5, 5, 5, 5]), 3, 200).path).not.toMatch(/NaN|Infinity/);
  });
});

describe('PpgChart', () => {
  it('sin datos, con datos viejos o solo huecos muestra «Esperando señal»', () => {
    for (const ppg of [null, ppgOf([1, 2, 3], [], { edadSegundos: 5 }), ppgOf([null, null])]) {
      expect(hasPpgSignal(ppg)).toBe(false);
      const { getByText, unmount } = render(<PpgChart ppg={ppg} />);
      expect(getByText('Esperando señal')).toBeInTheDocument();
      unmount();
    }
  });

  it('dibuja la onda y avisa cada latido detectado cuando cruza el «ahora» del gráfico (no con un temporizador propio)', async () => {
    const onBeat = vi.fn();
    const values = Array.from({ length: 120 }, (_, i) => Math.round(50 * Math.sin(i / 4)));
    // Un latido ya mostrado al montar (no debe disparar) y otro 12 muestras por delante del borde (≈ 0,5 s).
    const { container } = render(<PpgChart ppg={ppgOf(values, [20, 119 - 28])} onBeat={onBeat} />);
    const svg = container.querySelector('svg');
    expect(Number(svg.getAttribute('data-muestras'))).toBeGreaterThan(50);
    expect(svg.querySelector('.ppg-line').getAttribute('d')).toMatch(/^M/);
    expect(onBeat).not.toHaveBeenCalled();
    await waitFor(() => expect(onBeat).toHaveBeenCalledTimes(1), { timeout: 4000 });
    expect(onBeat).toHaveBeenCalledWith(91);
  });
});
