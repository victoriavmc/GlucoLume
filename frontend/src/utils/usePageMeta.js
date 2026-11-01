import { useEffect } from "react";

// Dirección pública del sitio: se usa para las URL canónicas. Sin barra final.
const SITE_ORIGIN = "https://glucolume-server.tailb27487.ts.net";

// La app es una SPA: index.html trae un único título y descripción. Cada página pública fija los suyos para que
// los buscadores y las vistas previas de los enlaces muestren el contenido correcto. Al salir se restaura el título base.
const BASE_TITLE = typeof document === "undefined" ? "GlucoLume" : document.title;
const BASE_DESCRIPTION =
  typeof document === "undefined" ? "" : document.querySelector('meta[name="description"]')?.getAttribute("content") ?? "";

function setCanonical(path) {
  let canonical = document.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    document.head.append(canonical);
  }
  canonical.href = `${SITE_ORIGIN}${path}`;
}

export function usePageMeta(title, description) {
  useEffect(() => {
    document.title = title;
    setCanonical(window.location.pathname);
    const meta = document.querySelector('meta[name="description"]');
    if (meta && description) meta.setAttribute("content", description);
    return () => {
      document.title = BASE_TITLE;
      if (meta) meta.setAttribute("content", BASE_DESCRIPTION);
    };
  }, [title, description]);
}
