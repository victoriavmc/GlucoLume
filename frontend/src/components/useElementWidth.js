// Ancho real de un contenedor (en píxeles), para dibujar un gráfico a su medida en lugar de escalar un dibujo fijo: los textos mantienen su
// tamaño legible y la altura se adapta. Usa una «ref» por callback para seguir funcionando aunque el elemento aparezca después de montar.

import { useEffect, useState } from 'react';

export function useElementWidth(initial = 760) {
  const [node, setNode] = useState(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    if (!node || typeof ResizeObserver === 'undefined') return undefined;
    const update = () => {
      const next = Math.round(node.getBoundingClientRect().width);
      if (next > 0) setWidth(next);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, width];
}
