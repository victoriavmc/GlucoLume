import { useEffect } from "react";

// La app es una SPA: index.html trae un único título y descripción. Cada página pública fija los suyos para que
// los buscadores y las vistas previas de los enlaces muestren el contenido correcto. Al salir se restaura el título base.
// La canónica y el robots no se fijan acá: los decide la política por ruta de utils/indexacion.js (useIndexacion).
const BASE_TITLE = typeof document === "undefined" ? "GlucoLume" : document.title;
const BASE_DESCRIPTION =
  typeof document === "undefined" ? "" : document.querySelector('meta[name="description"]')?.getAttribute("content") ?? "";

export function usePageMeta(title, description) {
  useEffect(() => {
    document.title = title;
    const meta = document.querySelector('meta[name="description"]');
    if (meta && description) meta.setAttribute("content", description);
    return () => {
      document.title = BASE_TITLE;
      if (meta) meta.setAttribute("content", BASE_DESCRIPTION);
    };
  }, [title, description]);
}
