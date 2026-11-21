// Barras apiladas por bloque de tiempo (hora, día, semana o mes): cada barra suma las mediciones del bloque y cada segmento es una categoría
// (por ejemplo oximetría o glucosa). Son cantidades reales: no se interpola ni se promedia, y un bloque sin mediciones queda vacío en el eje.

import { useElementWidth } from './useElementWidth.js';

const PAD = { top: 16, right: 12, bottom: 44, left: 40 };
const HEIGHT = 240;

/** Un tope de eje «redondo» (1, 2, 5, 10, 20, 50…) que contenga el máximo. */
function niceCeil(max) {
  if (max <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * magnitude >= max) return Math.ceil(step * magnitude);
  }
  return Math.ceil(max);
}

/**
 * @param categories  [{ key, label, color }] en el orden de apilado (de abajo hacia arriba).
 * @param blocks      [{ start, total, [categoría]: número }] en orden cronológico.
 * @param labelFor    (bloque) => texto corto del eje X.
 * @param describe    (bloque) => texto accesible del bloque («15/03: 3 mediciones: 2 oximetría, 1 glucosa»).
 */
export function StackedBarChart({ title, categories, blocks, labelFor, describe }) {
  const [setBox, WIDTH] = useElementWidth(); // dibujado con el ancho real del contenedor
  const innerW = Math.max(0, WIDTH - PAD.left - PAD.right);
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const peak = Math.max(0, ...blocks.map((block) => block.total));
  const yMax = niceCeil(peak);
  const yTicks = [0, 1, 2, 3, 4].map((index) => Math.round((yMax * index) / 4));
  const slot = blocks.length > 0 ? innerW / blocks.length : 0;
  const barW = Math.max(3, Math.min(40, slot * 0.7));
  // Se etiqueta cada bloque solo si cabe: si no, uno de cada N.
  const every = Math.max(1, Math.ceil(blocks.length / Math.max(1, Math.floor(innerW / 52))));
  const x = (index) => PAD.left + index * slot + slot / 2;
  const y = (value) => PAD.top + innerH - (value / yMax) * innerH;
  const totals = categories.map((category) => ({ ...category, sum: blocks.reduce((acc, block) => acc + (block[category.key] ?? 0), 0) }));

  return (
    <figure className="stacked-chart" ref={setBox}>
      <p className="stacked-title">{title}</p>
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}: ${blocks.reduce((acc, block) => acc + block.total, 0)} mediciones`}>
        {yTicks.map((tick) => (
          <g key={`y${tick}`}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="evo-grid" />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="trend-label">{tick}</text>
          </g>
        ))}
        <line x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH} className="trend-axis" />
        {blocks.map((block, index) => {
          let base = 0;
          return (
            <g key={block.start}>
              <title>{describe(block)}</title>
              {categories.map((category) => {
                const count = block[category.key] ?? 0;
                if (count === 0) return null;
                const top = y(base + count);
                const height = y(base) - top;
                base += count;
                return <rect key={category.key} x={x(index) - barW / 2} y={top} width={barW} height={height} rx={2} fill={category.color} />;
              })}
              {index % every === 0 && (
                <text x={x(index)} y={HEIGHT - 16} textAnchor="middle" className="trend-label">{labelFor(block)}</text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="stacked-legend">
        {totals.map((category) => (
          <span key={category.key}><i className="evo-swatch" style={{ background: category.color }} /> {category.label}: <b>{category.sum}</b></span>
        ))}
      </figcaption>
    </figure>
  );
}
