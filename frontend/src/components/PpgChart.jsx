// Señal de pulso (PPG) en tiempo real. Dibuja las muestras ópticas REALES del canal IR del MAX30100 que el firmware transmite, pasan por
// el puente y el backend (ventana deslizante de la sesión). No genera ni suaviza datos: un corte de señal queda como hueco y no se
// interpola. Los latidos marcados son los que detectó el firmware (no un pico validado). No es un electrocardiograma.
//
// Desplazamiento continuo: los bloques llegan cada ~0,4 s (en ráfagas de ~1 s por el puente). La pantalla muestra la señal con un pequeño
// retardo (DELAY_SAMPLES) y avanza a velocidad constante (1 muestra cada 1/hz s) hasta donde haya datos, así la onda se desplaza sin saltos.
// El dibujo se hace directo sobre el SVG en cada cuadro (sin re-renderizar React) y solo avisa a React cuando pasa un latido.

import { Activity } from 'lucide-react';
import { useEffect, useRef } from 'react';

const WIDTH = 720;
const HEIGHT = 200;
const PAD = { top: 14, right: 14, bottom: 26, left: 14 };
const WINDOW_SECONDS = 8; // 5–10 s
const DELAY_SAMPLES = 40; // ≈ 1,6 s de retardo de visualización
const MAX_LAG_SAMPLES = 75; // si el retardo crece más que esto (ráfagas), se reengancha
const STALE_SECONDS = 2.5; // sin bloques nuevos por más que esto: «Esperando señal»
const SVG_NS = 'http://www.w3.org/2000/svg';

const innerW = WIDTH - PAD.left - PAD.right;
const innerH = HEIGHT - PAD.top - PAD.bottom;

/** ¿Hay una señal reciente con al menos una muestra real? */
export function hasPpgSignal(ppg) {
  return Boolean(ppg && ppg.edadSegundos <= STALE_SECONDS && ppg.valores.some((value) => value !== null));
}

/** Calcula el trazo para una ventana que termina en `edge` (índice absoluto, puede ser fraccionario). Función pura. */
export function buildPpgFrame(ppg, edge, windowSamples) {
  const left = edge - windowSamples;
  const first = Math.max(Math.ceil(left), ppg.inicio);
  const lastIndex = Math.min(Math.floor(edge), ppg.inicio + ppg.valores.length - 1);
  const visible = [];
  for (let index = first; index <= lastIndex; index += 1) visible.push([index, ppg.valores[index - ppg.inicio]]);
  const real = visible.filter(([, value]) => value !== null).map(([, value]) => value);
  if (real.length === 0) return { path: '', beats: [], min: 0, max: 0, samples: 0 };
  const lo = Math.min(...real);
  const hi = Math.max(...real);
  const margin = (hi - lo || 2) * 0.15;
  const yMin = lo - margin;
  const yMax = hi + margin;
  const x = (index) => PAD.left + ((index - left) / windowSamples) * innerW;
  const y = (value) => PAD.top + innerH - ((value - yMin) / (yMax - yMin)) * innerH;
  let path = '';
  let open = false;
  for (const [index, value] of visible) {
    if (value === null) {
      open = false; // hueco: la línea se corta, no se une con la muestra siguiente
    } else {
      path += `${open ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
      open = true;
    }
  }
  const beats = ppg.latidos
    .filter((index) => index >= first && index <= lastIndex && ppg.valores[index - ppg.inicio] !== null)
    .map((index) => ({ index, x: x(index), y: y(ppg.valores[index - ppg.inicio]) }));
  return { path, beats, min: Math.round(lo), max: Math.round(hi), samples: real.length };
}

export function PpgChart({ ppg, onBeat }) {
  const lineRef = useRef(null);
  const beatsRef = useRef(null);
  const frame = useRef({ ppg: null, edge: null, fired: -1, lastTime: null, onBeat });
  const live = hasPpgSignal(ppg);

  frame.current.onBeat = onBeat;

  function draw() {
    const state = frame.current;
    const data = state.ppg;
    if (!data || !lineRef.current || data.valores.length === 0) return;
    const last = data.inicio + data.valores.length - 1;
    const windowSamples = WINDOW_SECONDS * data.hz;
    if (state.edge === null || state.edge < data.inicio) {
      state.edge = Math.max(data.inicio, last - DELAY_SAMPLES);
      state.fired = Math.max(-1, ...data.latidos.filter((index) => index <= state.edge));
    }
    const result = buildPpgFrame(data, state.edge, windowSamples);
    lineRef.current.setAttribute('d', result.path);
    lineRef.current.parentNode.setAttribute('data-muestras', String(result.samples));
    lineRef.current.parentNode.setAttribute('data-latidos', String(result.beats.length));
    if (beatsRef.current) {
      beatsRef.current.replaceChildren(...result.beats.flatMap((beat) => {
        const mark = document.createElementNS(SVG_NS, 'line');
        mark.setAttribute('x1', beat.x); mark.setAttribute('x2', beat.x);
        mark.setAttribute('y1', PAD.top); mark.setAttribute('y2', PAD.top + innerH);
        mark.setAttribute('class', 'ppg-beat-line');
        const dot = document.createElementNS(SVG_NS, 'circle');
        dot.setAttribute('cx', beat.x); dot.setAttribute('cy', beat.y); dot.setAttribute('r', 5);
        dot.setAttribute('class', 'ppg-beat-dot');
        return [mark, dot];
      }));
    }
    // El corazón late cuando el latido DETECTADO cruza el borde derecho (el «ahora» de la pantalla), no con un temporizador propio.
    const crossed = data.latidos.filter((index) => index > state.fired && index <= state.edge);
    if (crossed.length) {
      state.fired = Math.max(...crossed);
      state.onBeat?.(state.fired);
    }
  }

  // Datos nuevos: la ventana vive en el backend; acá solo se guarda la última y se redibuja de inmediato.
  useEffect(() => {
    frame.current.ppg = ppg;
    draw();
  });

  // Avance continuo entre bloques.
  useEffect(() => {
    if (typeof requestAnimationFrame !== 'function') return undefined;
    let request = 0;
    function tick(time) {
      const state = frame.current;
      const data = state.ppg;
      if (data && state.edge !== null && state.lastTime !== null && hasPpgSignal(data)) {
        const last = data.inicio + data.valores.length - 1;
        state.edge = Math.min(state.edge + ((time - state.lastTime) / 1000) * data.hz, last);
        if (state.edge < last - MAX_LAG_SAMPLES) state.edge = last - DELAY_SAMPLES;
        draw();
      }
      state.lastTime = time;
      request = requestAnimationFrame(tick);
    }
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!live) {
    return (
      <div className="ppg-chart is-waiting" role="status" aria-label="Señal de pulso (PPG): esperando señal">
        <span className="ppg-wait-icon"><Activity size={24} aria-hidden="true" /></span>
        <p>Esperando señal</p>
        <small>Todavía no llegan muestras ópticas válidas del sensor.</small>
      </div>
    );
  }
  return (
    <figure className="ppg-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Señal de pulso (PPG) en tiempo real: muestras ópticas reales del sensor"
        data-muestras="0" data-latidos="0">
        <rect x={PAD.left} y={PAD.top} width={innerW} height={innerH} className="ppg-frame" />
        <path ref={lineRef} className="ppg-line" d="" />
        <g ref={beatsRef} />
        <line x1={WIDTH - PAD.right} x2={WIDTH - PAD.right} y1={PAD.top} y2={PAD.top + innerH} className="ppg-now" />
        <text x={PAD.left} y={HEIGHT - 8} className="trend-label">{`últimos ${WINDOW_SECONDS} s`}</text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 8} textAnchor="end" className="trend-label">ahora</text>
      </svg>
    </figure>
  );
}
