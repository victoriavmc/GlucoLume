import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { TimeSeriesChart, niceTicks } from './AnalyticsCharts.jsx';

const at = (day, hour, y, n = 1) => ({ t: new Date(2026, 9, day, hour, 0), y, n });

describe('TimeSeriesChart', () => {
  it('dibuja cada medición con su fecha y hora, incluso varias del mismo día, y muestra el tooltip con su origen', async () => {
    render(<TimeSeriesChart title="Glucosa" unit="mg/dL" kind="medicion" origin="DEMO — dato sintético de prueba" decimals={0}
      points={[at(17, 10, 100), at(17, 14, 120), at(17, 20, 110), at(18, 9, 105)]} />);
    const dots = screen.getAllByRole('img', { name: /Medición individual/ });
    expect(dots).toHaveLength(4); // tres el mismo día + una al siguiente: ninguna se pierde
    await userEvent.tab();
    expect(screen.getByRole('status')).toHaveTextContent(/100 mg\/dL/);
    expect(screen.getByRole('status')).toHaveTextContent(/17\/10\/2026 10:00/);
    expect(screen.getByRole('status')).toHaveTextContent(/DEMO — dato sintético de prueba/);
    expect(screen.getByRole('img', { name: /Glucosa \(mg\/dL\): 4 mediciones/ })).toBeInTheDocument();
  });

  it('por día rotula el promedio con la cantidad de observaciones y nunca como medición individual', async () => {
    render(<TimeSeriesChart title="SpO₂" unit="%" kind="dia" points={[at(17, 12, 96.5, 3), at(18, 12, 95, 1)]} />);
    expect(screen.queryByRole('img', { name: /Medición individual/ })).not.toBeInTheDocument();
    await userEvent.tab();
    expect(screen.getByRole('status')).toHaveTextContent(/Promedio diario de 3 observaciones/);
  });

  it('no grafica valores ausentes (ni como cero) y avisa cuando no queda ninguno', () => {
    const { rerender } = render(<TimeSeriesChart title="Frecuencia" unit="lpm" points={[at(17, 10, null), at(17, 11, 72)]} />);
    expect(screen.getAllByRole('img', { name: /Medición individual/ })).toHaveLength(1);
    rerender(<TimeSeriesChart title="Frecuencia" unit="lpm" points={[at(17, 10, null)]} />);
    expect(screen.getByText(/No hay observaciones con este dato/)).toBeInTheDocument();
  });

  it('una sola medición se grafica centrada y la escala sale de los datos', () => {
    render(<TimeSeriesChart title="SpO₂" unit="%" points={[at(18, 10, 97)]} />);
    expect(screen.getAllByRole('img', { name: /Medición individual/ })).toHaveLength(1);
  });

  it('las marcas del eje vertical son redondas y cubren el rango sin forzar el cero', () => {
    const ticks = niceTicks(93.2, 99.1);
    expect(ticks[0]).toBeLessThanOrEqual(93.2 + 1);
    expect(ticks.at(-1)).toBeGreaterThanOrEqual(99.1 - 1);
    expect(ticks.every((value) => value > 80)).toBe(true);
  });
});
