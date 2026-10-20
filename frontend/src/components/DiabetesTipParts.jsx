// Piezas compartidas de «Consejos para diabéticos»: ícono de cada artículo, etiquetas de categoría y tarjeta de vista previa.
// El contenido sale de data/diabetesTips.js (estático): acá solo se presenta.

import {
  Activity, Apple, ArrowRight, BookOpen, CakeSlice, CalendarCheck, ClipboardList, CupSoda, Droplet, Dumbbell, Eye, Footprints, Gauge, GlassWater,
  NotebookPen, PersonStanding, Salad, Scissors, ShoppingCart, Stethoscope, Sunset, Thermometer, TriangleAlert, Utensils, UtensilsCrossed, Wheat, Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { CATEGORIES, categoryOf } from '../data/diabetesTips.js';
import './diabetesTips.css';

const ICONS = {
  apple: Apple, water: GlassWater, walk: PersonStanding, clipboard: ClipboardList, foot: Footprints, plate: Utensils, bread: Wheat, salad: Salad,
  restaurant: UtensilsCrossed, dessert: CakeSlice, cart: ShoppingCart, soda: CupSoda, bottle: GlassWater, thermometer: Thermometer, run: Activity,
  sunset: Sunset, strength: Dumbbell, meter: Gauge, alert: TriangleAlert, steps: Footprints, drop: Droplet, notebook: NotebookPen,
  stethoscope: Stethoscope, book: BookOpen, eye: Eye, soap: Droplet, shoe: Footprints, scissors: Scissors, nerve: Zap, calendar: CalendarCheck,
};

export function TipIcon({ name, size = 30 }) {
  const Icon = ICONS[name] ?? Apple;
  return <Icon size={size} aria-hidden="true" />;
}

/** Fila de etiquetas: «Todos» más una por categoría. `value` es el id elegido; `onChange` recibe el id. */
export function CategoryTags({ value, onChange, idPrefix = 'dt' }) {
  const options = [{ id: 'todos', shortLabel: 'Todos' }, ...CATEGORIES];
  return (
    <div className="dt-tags" role="group" aria-label="Filtrar consejos por categoría">
      {options.map((option) => (
        <button key={option.id} type="button" id={`${idPrefix}-${option.id}`} className={`dt-tag${value === option.id ? ' is-active' : ''}`}
          aria-pressed={value === option.id} onClick={() => onChange(option.id)}>
          {option.shortLabel}
        </button>
      ))}
    </div>
  );
}

export function CategoryBadge({ id }) {
  const category = categoryOf(id);
  return <span className={`dt-badge is-${id}`}>{category?.label ?? id}</span>;
}

/** Tarjeta de vista previa: ícono, categoría, título, resumen y «Leer artículo». `search` conserva el filtro para volver. */
export function TipCard({ article, search = '', compact = false }) {
  return (
    <article className={`dt-card${compact ? ' is-compact' : ''}`} aria-label={article.title}>
      <span className={`dt-card-icon is-${article.category}`}><TipIcon name={article.icon} size={compact ? 36 : 40} /></span>
      <div className="dt-card-body">
        <CategoryBadge id={article.category} />
        <h3>{article.title}</h3>
        <p>{article.summary}</p>
        <Link to={`/app/consejos/${article.id}`} state={{ search }} className="dt-link" aria-label={`Leer artículo: ${article.title}`}>
          Leer artículo <ArrowRight size={18} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}
