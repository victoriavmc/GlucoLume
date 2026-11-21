// Título del documento por ruta (A-9, auditoría 2). Antes, index.html fijaba un único título para todas las rutas que no llaman a
// usePageMeta. La ruta lo decide aquí; una página puede sobrescribirlo con usePageMeta mientras está montada.
import { useLayoutEffect } from 'react';
import { useLocation } from 'react-router-dom';

export const TITULO_BASE = 'GlucoLume · Medición no invasiva de glucosa (experimental)';

// Orden: la primera coincidencia gana. Las rutas de acceso administrativo van antes que el prefijo general de /plataforma.
const TITULOS = [
  [/^\/$/, TITULO_BASE],
  [/^\/login(\/|$)/, 'Iniciar sesión · GlucoLume'],
  [/^\/registro(\/|$)/, 'Crear cuenta · GlucoLume'],
  [/^\/recuperar-contrasena(\/|$)/, 'Recuperar contraseña · GlucoLume'],
  [/^\/restablecer-contrasena(\/|$)/, 'Nueva contraseña · GlucoLume'],
  [/^\/verificar-correo(\/|$)/, 'Verificar correo · GlucoLume'],
  [/^\/activar-cuenta(\/|$)/, 'Activar cuenta · GlucoLume'],
  [/^\/confirmar-correo-resultados(\/|$)/, 'Confirmar correo · GlucoLume'],
  [/^\/cuenta\/eliminar(\/|$)/, 'Eliminar cuenta · GlucoLume'],
  [/^\/auth\/google\/callback(\/|$)/, 'Acceso con Google · GlucoLume'],
  [/^\/plataforma\/login(\/|$)/, 'Acceso administrativo · GlucoLume'],
  [/^\/administracion\/login(\/|$)/, 'Acceso administrativo · GlucoLume'],
  [/^\/plataforma\/recuperar(\/|$)/, 'Recuperar contraseña administrativa · GlucoLume'],
  [/^\/plataforma\/restablecer(\/|$)/, 'Nueva contraseña administrativa · GlucoLume'],
  [/^\/(administracion|plataforma)\/activar(\/|$)/, 'Activar cuenta administrativa · GlucoLume'],
  [/^\/plataforma(\/|$)/, 'Administración · GlucoLume'],
  [/^\/app(\/|$)/, 'Mi cuenta · GlucoLume'],
  [/^\/privacidad(\/|$)/, 'Política de privacidad · GlucoLume'],
  [/^\/caracteristicas(\/|$)/, 'Características y privacidad · GlucoLume'],
  [/^\/consejos(\/|$)/, 'Consejos para diabéticos · GlucoLume'],
  [/^\/ayuda(\/|$)/, 'Ayuda · GlucoLume'],
];

export function tituloDeRuta(pathname) {
  return TITULOS.find(([patron]) => patron.test(pathname))?.[1] ?? TITULO_BASE;
}

/**
 * Pone el título de la ruta actual. Es un efecto de diseño (layout) para que una página que llama a usePageMeta (efecto normal, que
 * corre después) conserve su propio título.
 */
export function useTituloDeRuta() {
  const { pathname } = useLocation();
  useLayoutEffect(() => {
    document.title = tituloDeRuta(pathname);
  }, [pathname]);
}
