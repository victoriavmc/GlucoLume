// /app/consejos y /app/consejos/:idConsejo — colección completa de «Consejos para diabéticos».
// Lista con etiquetas, buscador y tarjetas; al abrir un artículo se lee dentro de GlucoLume (y «Volver a consejos» conserva el filtro).
// El filtro vive en la URL (?categoria=&q=), así el botón «atrás» del navegador y el enlace desde Inicio funcionan sin recargar.

import { Lightbulb, Search, X } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Link } from 'react-router-dom';

import { DiabetesArticle } from '../../components/DiabetesArticle.jsx';
import { CategoryTags, TipCard } from '../../components/DiabetesTipParts.jsx';
import { CATEGORIES, DISCLAIMER, articleById, categoryOf, filterArticles } from '../../data/diabetesTips.js';

function TipsList() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('categoria') ?? 'todos';
  const category = requested === 'todos' || categoryOf(requested) ? requested : 'todos';
  const query = params.get('q') ?? '';
  const articles = filterArticles({ category, query });
  const search = params.toString() ? `?${params.toString()}` : '';

  function update(next) {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value && value !== 'todos') merged.set(key, value);
      else merged.delete(key);
    }
    setParams(merged, { replace: true });
  }

  return (
    <div className="page is-wide dt-page">
      <header className="dt-page-head">
        <span className="dt-home-icon is-large"><Lightbulb size={34} aria-hidden="true" /></span>
        <div>
          <h1>Consejos para diabéticos</h1>
          <p className="dt-intro">
            Recomendaciones generales para cuidar tu bienestar todos los días: alimentación, hidratación, actividad física, controles y cuidado de los
            pies. Cada artículo está explicado en lenguaje simple e indica la institución de salud en la que se basa, con el enlace a la fuente.
          </p>
        </div>
      </header>

      <p className="dt-disclaimer is-strong">{DISCLAIMER}</p>

      <section className="dt-filters" aria-label="Buscar y filtrar consejos">
        <div className="dt-search">
          <label htmlFor="dt-search-input">Buscar por título o palabra clave</label>
          <div className="dt-search-box">
            <Search size={22} aria-hidden="true" />
            <input id="dt-search-input" type="search" value={query} placeholder="Ej.: agua, pies" autoComplete="off"
              onChange={(event) => update({ q: event.target.value })} />
            {query && (
              <button type="button" className="dt-clear" onClick={() => update({ q: '' })} aria-label="Borrar la búsqueda"><X size={20} aria-hidden="true" /></button>
            )}
          </div>
        </div>
        <CategoryTags value={category} onChange={(id) => update({ categoria: id })} idPrefix="dt-page" />
        {category !== 'todos' && <p className="dt-category-note">{categoryOf(category).description}</p>}
      </section>

      <p className="dt-count" role="status" aria-live="polite">
        {articles.length === 1 ? '1 artículo' : `${articles.length} artículos`}
        {category !== 'todos' ? ` en «${categoryOf(category).label}»` : ` en ${CATEGORIES.length} categorías`}
        {query ? ` para «${query}»` : ''}
      </p>

      {articles.length === 0 ? (
        <div className="dt-empty">
          <b>No encontramos consejos con esa búsqueda.</b>
          <p>Probá con otra palabra o elegí «Todos» para ver toda la colección.</p>
          <button type="button" className="btn btn-outline" onClick={() => setParams({}, { replace: true })}>Ver todos los consejos</button>
        </div>
      ) : (
        <div className="dt-grid">
          <h2 className="sr-only">Artículos</h2>
          {articles.map((article) => <TipCard key={article.id} article={article} search={search} />)}
        </div>
      )}
    </div>
  );
}

export default function DiabetesTipsPage() {
  const { idConsejo } = useParams();
  if (!idConsejo) return <TipsList />;
  const article = articleById(idConsejo);
  if (!article) {
    return (
      <div className="page dt-page">
        <div className="dt-empty">
          <b>No encontramos ese consejo.</b>
          <p>Puede que el enlace esté incompleto o que el artículo ya no exista.</p>
          <Link to="/app/consejos" className="btn btn-primary">Volver a consejos</Link>
        </div>
      </div>
    );
  }
  return <div className="page dt-page"><DiabetesArticle article={article} /></div>;
}
