// Lectura de UN artículo dentro de GlucoLume: título, categoría, contenido en bloques cortos y, al final, la fuente (institución),
// la referencia (publicación consultada) y el enlace a la fuente original, que se abre en una pestaña nueva.

import { ArrowLeft, ExternalLink, Info, ShieldAlert } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

import { DISCLAIMER } from '../data/diabetesTips.js';
import { CategoryBadge, TipIcon } from './DiabetesTipParts.jsx';

function Block({ block }) {
  if (block.type === 'h') return <h2 className="dt-article-h">{block.text}</h2>;
  if (block.type === 'list') return <ul className="dt-article-list">{block.items.map((item) => <li key={item}>{item}</li>)}</ul>;
  if (block.type === 'note') {
    return (
      <aside className="dt-article-note" role="note">
        <Info size={22} aria-hidden="true" />
        <p>{block.text}</p>
      </aside>
    );
  }
  return <p className="dt-article-p">{block.text}</p>;
}

export function DiabetesArticle({ article, basePath = '/app/consejos' }) {
  const { state } = useLocation();
  const back = `${basePath}${state?.search ?? ''}`;

  return (
    <article className="dt-article" aria-labelledby="dt-article-title">
      <Link to={back} className="dt-back"><ArrowLeft size={22} aria-hidden="true" /> Volver a consejos</Link>

      <header className="dt-article-head">
        <span className={`dt-card-icon is-large is-${article.category}`}><TipIcon name={article.icon} size={46} /></span>
        <div>
          <CategoryBadge id={article.category} />
          <h1 id="dt-article-title">{article.title}</h1>
          <p className="dt-article-lead">{article.summary}</p>
        </div>
      </header>

      <div className="dt-article-body">
        {article.content.map((block, index) => <Block key={`${block.type}-${index}`} block={block} />)}
      </div>

      <section className="dt-sources" aria-labelledby="dt-sources-title">
        <h2 id="dt-sources-title">Fuentes consultadas</h2>
        <ul>
          {article.sources.map((source) => (
            <li key={source.url} className="dt-source">
              <p><b>Fuente:</b> {source.institution}</p>
              <p><b>Referencia:</b> {source.title}{source.language === 'en' ? ' (en inglés)' : ''}</p>
              <p className="dt-source-date">{source.dateNote}</p>
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="dt-source-link">
                Consultar fuente original <ExternalLink size={18} aria-hidden="true" />
                <span className="sr-only"> (se abre en una pestaña nueva)</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <p className="dt-disclaimer is-strong"><ShieldAlert size={20} aria-hidden="true" /> {DISCLAIMER}</p>
    </article>
  );
}
