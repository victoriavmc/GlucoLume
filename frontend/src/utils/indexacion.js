import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

// Política de indexación por tipo de ruta (A-6, auditoría 2). Debe coincidir con docker/nginx/default.conf.template ($robots_tag):
// la prueba de sincronía (indexacion.test.jsx) lo verifica. Esto no es un control de acceso: solo indica a los buscadores qué indexar.

// Dirección pública del sitio: base de las URL canónicas. Sin barra final.
export const SITE_ORIGIN = 'https://glucolume-server.tailb27487.ts.net';

// Prefijos de primer nivel que son privados o de autenticación: se listan igual que en el mapa de Nginx.
export const PREFIJOS_PRIVADOS = [
  'app', 'plataforma', 'administracion', 'auth', 'cuenta', 'login', 'registro', 'verificar-correo', 'activar-cuenta',
  'recuperar-contrasena', 'restablecer-contrasena', 'confirmar-correo-resultados',
];
const RUTA_PRIVADA = new RegExp(`^/(${PREFIJOS_PRIVADOS.join('|')})(/|$)`, 'i');

export function esRutaPrivada(pathname) {
  return RUTA_PRIVADA.test(pathname);
}

/** Robots y canónica que corresponden a una ruta. Las privadas nunca se canonicalizan (ni a la home ni a sí mismas). */
export function politicaIndexacion(pathname) {
  if (esRutaPrivada(pathname)) return { robots: 'noindex, nofollow', canonical: null };
  return { robots: 'index, follow', canonical: `${SITE_ORIGIN}${pathname}` };
}

function setMeta(attribute, name, content) {
  let meta = document.head.querySelector(`meta[${attribute}="${name}"]`);
  if (content === null) {
    meta?.remove();
    return;
  }
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute(attribute, name);
    document.head.append(meta);
  }
  meta.setAttribute('content', content);
}

function setCanonical(href) {
  let link = document.head.querySelector('link[rel="canonical"]');
  if (href === null) {
    link?.remove();
    return;
  }
  if (!link) {
    link = document.createElement('link');
    link.rel = 'canonical';
    document.head.append(link);
  }
  link.href = href;
}

/**
 * Aplica la política de la ruta actual al <head>: robots, canonical y og:url. Va una sola vez en el router, así cubre todas las
 * rutas (también las que no llaman a usePageMeta). El HTML estático de index.html no fija ninguno de estos valores.
 */
export function useIndexacion() {
  const { pathname } = useLocation();
  useEffect(() => {
    const politica = politicaIndexacion(pathname);
    setMeta('name', 'robots', politica.robots);
    setCanonical(politica.canonical);
    setMeta('property', 'og:url', politica.canonical);
  }, [pathname]);
}
