// Capturas reales de dónde tocar, junto a cada paso de la guía (public/ayuda/). El texto del paso ya describe la acción,
// por eso la imagen va con texto alternativo corto y el pie repite solo dónde está.

import { useState } from 'react';

import { Modal } from '../../../components/Modal.jsx';

// Espejo del menú de layouts/Sidebar.jsx para cada tipo de cuenta: si cambia un nombre o una ruta, cambiarlo también aquí
// (y volver a capturar: scripts en public/ayuda/ se generan con la app local).
const MENU = {
  CLIENTE: [
    { to: '/app/inicio', label: 'Inicio' },
    { to: '/app/mediciones', label: 'Mediciones' },
    { to: '/app/conectar-dispositivo', label: 'Conectar dispositivo' },
    { to: '/app/grupo', label: 'Grupo' },
    { to: '/app/consejos', label: 'Consejos' },
    { to: '/app/notificaciones', label: 'Notificaciones' },
    { to: '/app/perfil', label: 'Perfil' },
    { to: '/app/seguridad', label: 'Seguridad' },
    { to: '/app/ayuda', label: 'Ayuda' },
  ],
  INSTITUCIONAL: [
    { to: '/app/inicio', label: 'Inicio' },
    { to: '/app/instituciones', label: 'Instituciones' },
    { to: '/app/consejos', label: 'Consejos' },
    { to: '/app/notificaciones', label: 'Notificaciones' },
    { to: '/app/perfil', label: 'Perfil' },
    { to: '/app/seguridad', label: 'Seguridad' },
    { to: '/app/ayuda', label: 'Ayuda' },
  ],
};

const PREFIJO = { CLIENTE: 'cliente', INSTITUCIONAL: 'institucional' };

// La sección del menú que contiene la ruta destino (p. ej. /app/mediciones/perfil cae en Mediciones).
function seccionDe(tipo, destino) {
  return MENU[tipo]
    .filter(({ to }) => destino === to || destino.startsWith(`${to}/`))
    .sort((a, b) => b.to.length - a.to.length)[0];
}

// Captura de la barra lateral de ese tipo de cuenta, con la sección del paso marcada.
export function PasoMenu({ tipo, destino }) {
  const seccion = seccionDe(tipo, destino);
  if (!seccion) return null;
  const archivo = `${PREFIJO[tipo]}-menu-${seccion.to.replace('/app/', '')}.png`;
  return <PasoImagen captura={archivo} alt={`Menú lateral con «${seccion.label}» marcado`} pie={`Menú lateral: tocá «${seccion.label}».`} />;
}

// Imagen de una pantalla de la app (`captura` es un archivo de public/ayuda/) con su pie. Al tocarla se abre ampliada
// en el modal de la app (Escape o clic afuera la cierran).
export function PasoImagen({ captura, alt, pie }) {
  const [ampliada, setAmpliada] = useState(false);
  const src = `/ayuda/${captura}`;
  return (
    <figure className="help-captura">
      <button type="button" className="help-captura-boton" aria-label={`Ampliar imagen: ${alt}`} onClick={() => setAmpliada(true)}>
        <img src={src} alt="" loading="lazy" />
      </button>
      {pie && <figcaption>{pie}</figcaption>}
      {ampliada && (
        <Modal role="dialog" visor title={pie ?? alt} onClose={() => setAmpliada(false)}>
          <img className="help-visor-img" src={src} alt={alt} />
        </Modal>
      )}
    </figure>
  );
}

// `pie` reemplaza el texto por defecto cuando la pantalla no muestra el botón en ese momento (p. ej. hace falta un
// dispositivo conectado).
export function PasoBoton({ texto, captura, pie }) {
  return <PasoImagen captura={captura} alt={`Pantalla donde está el botón «${texto}»`} pie={pie ?? `Tocá «${texto}».`} />;
}
