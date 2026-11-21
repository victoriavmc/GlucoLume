import { useEffect } from "react";

// La app es una SPA: index.html trae una descripción base. Cada página pública fija la suya (y su título) para que los buscadores y las
// vistas previas de los enlaces muestren el contenido correcto. La descripción base se restaura al salir. El título lo decide la ruta
// (utils/titulos.js): al salir de la página, el de la ruta siguiente lo pone useTituloDeRuta.
// La canónica y el robots no se fijan acá: los decide la política por ruta de utils/indexacion.js (useIndexacion).
const BASE_DESCRIPTION =
  typeof document === "undefined" ? "" : document.querySelector('meta[name="description"]')?.getAttribute("content") ?? "";

export function usePageMeta(title, description) {
  useEffect(() => {
    document.title = title;
    const meta = document.querySelector('meta[name="description"]');
    if (meta && description) meta.setAttribute("content", description);
    return () => {
      if (meta) meta.setAttribute("content", BASE_DESCRIPTION);
    };
  }, [title, description]);
}
