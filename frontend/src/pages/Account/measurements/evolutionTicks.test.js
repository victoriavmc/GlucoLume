import { describe, expect, it } from 'vitest';

import { DAY, timeTicks } from './evolutionModel.js';

describe('marcas del eje de tiempo en rangos largos', () => {
  it('90 días caen en el primer día de cada mes, en hora local', () => {
    const t0 = new Date(2026, 7, 25).getTime(); // 25/08/2026
    const t1 = t0 + 90 * DAY;
    const { ticks } = timeTicks(t0, t1);
    expect(ticks.map((tick) => new Date(tick).getDate())).toEqual([1, 1, 1]);
    expect(ticks.map((tick) => new Date(tick).getMonth())).toEqual([8, 9, 10]); // sep, oct, nov
  });

  it('rangos cortos siguen con marcas regulares', () => {
    const t0 = new Date(2026, 10, 16).getTime();
    const t1 = t0 + 7 * DAY;
    expect(timeTicks(t0, t1).ticks.length).toBeGreaterThan(1);
  });
});
