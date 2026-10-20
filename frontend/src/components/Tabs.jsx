// Pestañas accesibles (patrón WAI-ARIA «Tabs»). Dos componentes con el mismo aspecto:
//   · Tabs     – el estado vive en la pantalla (p. ej. la variable de un gráfico): role="tablist"/"tab"/"tabpanel",
//                un solo Tab entra a la lista (tabindex rotativo) y las flechas, Inicio y Fin mueven entre pestañas.
//   · NavTabs  – cada pestaña es una ruta: <nav> con enlaces y aria-current="page" (no usa role="tab").
// Variantes visuales: pill (botones grises, activo rojo), soft (texto con pastilla roja) y underline (subrayado).

import { useId, useRef } from 'react';
import { NavLink } from 'react-router-dom';

const VARIANTS = ['pill', 'soft', 'underline'];
const variantClass = (variant) => `ui-tabs ui-tabs--${VARIANTS.includes(variant) ? variant : 'pill'}`;

/**
 * items: [{ key, label, icon?, disabled? }]. `idBase` enlaza cada pestaña con su <TabPanel> (aria-controls / aria-labelledby).
 * activation="auto": al mover el foco con las flechas se selecciona (paneles livianos).
 * activation="manual": las flechas solo mueven el foco y Enter/Espacio selecciona (paneles que cargan datos).
 */
export function Tabs({ label, items, value, onChange, idBase, variant = 'pill', activation = 'auto', className = '' }) {
  const generated = useId();
  const base = idBase ?? generated;
  const refs = useRef({});
  const enabled = items.filter((item) => !item.disabled);
  const selected = enabled.find((item) => item.key === value) ?? enabled[0];

  function move(current, step) {
    const index = enabled.findIndex((item) => item.key === current);
    const next = step === 'first' ? enabled[0] : step === 'last' ? enabled.at(-1) : enabled[(index + step + enabled.length) % enabled.length];
    if (!next) return;
    refs.current[next.key]?.focus();
    if (activation === 'auto') onChange(next.key);
  }

  function handleKeyDown(event, key) {
    const keys = { ArrowRight: 1, ArrowLeft: -1, Home: 'first', End: 'last' };
    if (!(event.key in keys)) return;
    event.preventDefault();
    move(key, keys[event.key]);
  }

  return (
    <div role="tablist" aria-label={label} className={`${variantClass(variant)} ${className}`.trim()}>
      {items.map((item) => {
        const active = selected?.key === item.key;
        const Icon = item.icon;
        return (
          <button
            key={item.key}
            ref={(node) => { refs.current[item.key] = node; }}
            type="button"
            role="tab"
            id={`${base}-tab-${item.key}`}
            aria-selected={active}
            aria-controls={`${base}-panel`}
            tabIndex={active ? 0 : -1}
            disabled={item.disabled}
            className={`ui-tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(item.key)}
            onKeyDown={(event) => handleKeyDown(event, item.key)}
          >
            {Icon && <Icon size={18} aria-hidden="true" />}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

/** Panel de la pestaña activa. `focusable` lo hace alcanzable con Tab cuando no tiene controles propios. */
export function TabPanel({ idBase, value, focusable = false, className, children }) {
  return (
    <div role="tabpanel" id={`${idBase}-panel`} aria-labelledby={`${idBase}-tab-${value}`} tabIndex={focusable ? 0 : undefined} className={className}>
      {children}
    </div>
  );
}

/** items: [{ to, label, icon?, end? }]. `end` es true por defecto (coincidencia exacta). */
export function NavTabs({ label, items, variant = 'soft', className = '' }) {
  return (
    <nav aria-label={label} className={`${variantClass(variant)} ${className}`.trim()}>
      {items.map(({ to, label: text, icon: Icon, end = true }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => `ui-tab${isActive ? ' is-active' : ''}`}>
          {Icon && <Icon size={18} aria-hidden="true" />}
          {text}
        </NavLink>
      ))}
    </nav>
  );
}
