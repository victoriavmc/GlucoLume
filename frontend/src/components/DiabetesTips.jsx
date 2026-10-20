// «Consejos para diabéticos» en Inicio: vista RESUMIDA. Etiquetas por categoría y solo 2 artículos destacados de la categoría elegida; el botón
// «Explorar todos los consejos» abre la página con la colección completa. Contenido estático (data/diabetesTips.js): sin llamadas a la API.

import { ArrowRight, Lightbulb } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { DISCLAIMER, featuredArticles } from '../data/diabetesTips.js';
import { CategoryTags, TipCard } from './DiabetesTipParts.jsx';

export function DiabetesTips() {
  const [category, setCategory] = useState('todos');
  const featured = featuredArticles(category);
  const search = category === 'todos' ? '' : `?categoria=${category}`;

  return (
    <section className="dt-home" aria-labelledby="dt-home-title">
      <header className="dt-home-head">
        <span className="dt-home-icon"><Lightbulb size={28} aria-hidden="true" /></span>
        <div>
          <h2 id="dt-home-title">Consejos para diabéticos</h2>
          <p>Recomendaciones generales de instituciones de salud, explicadas en lenguaje simple.</p>
        </div>
      </header>

      <CategoryTags value={category} onChange={setCategory} idPrefix="dt-home" />

      <div className="dt-grid is-home" aria-live="polite">
        {featured.map((article) => <TipCard key={article.id} article={article} search={search} compact />)}
      </div>

      <Link to={`/app/consejos${search}`} className="dt-explore">
        Explorar todos los consejos <ArrowRight size={20} aria-hidden="true" />
      </Link>
      <p className="dt-disclaimer">{DISCLAIMER}</p>
    </section>
  );
}
