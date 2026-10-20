import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { clearTokens, saveTokens } from '../../auth/tokenStore.js';
import { ARTICLES, CATEGORIES, DISCLAIMER, featuredArticles, filterArticles } from '../../data/diabetesTips.js';
import { ACCOUNT, TOKENS, jsonResponse, mockApi } from '../../test/helpers.js';
import { renderAt } from '../../test/renderApp.jsx';

beforeEach(() => {
  clearTokens();
  saveTokens(TOKENS, false);
  mockApi({ 'GET /auth/me': jsonResponse(200, ACCOUNT) });
});

describe('Contenido estático de los consejos', () => {
  it('cada categoría tiene al menos 5 artículos, con ids únicos y sin artículos de una sola oración', () => {
    expect(new Set(ARTICLES.map((article) => article.id)).size).toBe(ARTICLES.length);
    for (const category of CATEGORIES) {
      expect(ARTICLES.filter((article) => article.category === category.id).length).toBeGreaterThanOrEqual(5);
    }
    for (const article of ARTICLES) {
      const text = article.content.flatMap((block) => (block.items ? block.items : [block.text])).join(' ');
      expect(text.split(/[.!?]/).filter(Boolean).length, article.id).toBeGreaterThan(3);
      expect(article.title && article.summary && article.icon, article.id).toBeTruthy();
    }
  });

  it('todos los artículos tienen fuente con institución, publicación, fecha y enlace https directo', () => {
    for (const article of ARTICLES) {
      expect(article.sources.length, article.id).toBeGreaterThanOrEqual(1);
      for (const source of article.sources) {
        expect(source.institution && source.title && source.dateNote, article.id).toBeTruthy();
        expect(source.url, article.id).toMatch(/^https:\/\/[^\s]+$/);
      }
    }
  });

  it('en Inicio hay 2 destacados por categoría y, con «Todos», de categorías distintas', () => {
    for (const category of CATEGORIES) expect(featuredArticles(category.id)).toHaveLength(2);
    const all = featuredArticles('todos');
    expect(all).toHaveLength(2);
    expect(new Set(all.map((article) => article.category)).size).toBe(2);
  });

  it('el buscador ignora tildes y mayúsculas y exige todas las palabras', () => {
    expect(filterArticles({ query: 'HIDRATACION' }).length).toBeGreaterThan(0);
    expect(filterArticles({ query: 'calzado medias' }).map((article) => article.id)).toContain('calzado-y-medias');
    expect(filterArticles({ query: 'xyzxyz' })).toHaveLength(0);
    expect(filterArticles({ category: 'pies', query: '' }).every((article) => article.category === 'pies')).toBe(true);
  });
});

describe('Consejos en Inicio', () => {
  it('muestra el título, las 6 etiquetas, solo 2 artículos, el aviso educativo y el botón para explorar', async () => {
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Consejos para diabéticos' }));
    const tags = within(section.getByRole('group', { name: 'Filtrar consejos por categoría' }));
    expect(tags.getAllByRole('button').map((button) => button.textContent)).toEqual(['Todos', 'Alimentación', 'Hidratación', 'Actividad física', 'Control', 'Pies']);
    expect(tags.getByRole('button', { name: 'Todos' })).toHaveAttribute('aria-pressed', 'true');
    expect(section.getAllByRole('article')).toHaveLength(2);
    expect(section.getByText(DISCLAIMER)).toBeInTheDocument();
    expect(section.getByRole('link', { name: /Explorar todos los consejos/ })).toHaveAttribute('href', '/app/consejos');
  });

  it('al elegir una etiqueta aparecen solo artículos de esa categoría, sin recargar', async () => {
    const user = userEvent.setup();
    renderAt('/app/inicio');
    const section = within(await screen.findByRole('region', { name: 'Consejos para diabéticos' }));
    await user.click(section.getByRole('button', { name: 'Pies' }));
    const cards = section.getAllByRole('article');
    expect(cards).toHaveLength(2);
    for (const card of cards) expect(within(card).getByText('Cuidado de los pies')).toBeInTheDocument();
    expect(section.getByRole('button', { name: 'Pies' })).toHaveAttribute('aria-pressed', 'true');
    expect(section.getByRole('link', { name: /Explorar todos los consejos/ })).toHaveAttribute('href', '/app/consejos?categoria=pies');
  });
});

describe('Página de consejos', () => {
  it('con «Todos» lista toda la colección y las etiquetas filtran por categoría', async () => {
    const user = userEvent.setup();
    renderAt('/app/consejos');
    expect(await screen.findByRole('heading', { name: 'Consejos para diabéticos', level: 1 })).toBeInTheDocument();
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
    expect(screen.getAllByRole('article')).toHaveLength(ARTICLES.length);
    expect(screen.getByRole('heading', { name: 'Artículos', level: 2 })).toBeInTheDocument(); // sin salto h1 → h3 en los títulos de las tarjetas
    await user.click(screen.getByRole('button', { name: 'Hidratación' }));
    const expected = ARTICLES.filter((article) => article.category === 'hidratacion').length;
    expect(screen.getAllByRole('article')).toHaveLength(expected);
    expect(screen.getByRole('status')).toHaveTextContent(`${expected} artículos en «Hidratación»`);
    await user.click(screen.getByRole('button', { name: 'Todos' }));
    expect(screen.getAllByRole('article')).toHaveLength(ARTICLES.length);
  });

  it('el buscador filtra por título o palabras clave y avisa cuando no hay resultados', async () => {
    const user = userEvent.setup();
    renderAt('/app/consejos');
    const input = await screen.findByLabelText('Buscar por título o palabra clave');
    await user.type(input, 'caminata');
    expect(screen.getAllByRole('article').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('article').length).toBeLessThan(ARTICLES.length);
    await user.clear(input);
    await user.type(input, 'xyzxyz');
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    expect(screen.getByText('No encontramos consejos con esa búsqueda.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ver todos los consejos' }));
    expect(screen.getAllByRole('article')).toHaveLength(ARTICLES.length);
  });

  it('abre un artículo dentro de la app con sus fuentes y vuelve conservando el filtro', async () => {
    const user = userEvent.setup();
    renderAt('/app/consejos?categoria=pies');
    await user.click(await screen.findByRole('link', { name: 'Leer artículo: Revisá tus pies todos los días' }));
    expect(await screen.findByRole('heading', { name: 'Revisá tus pies todos los días', level: 1 })).toBeInTheDocument();
    const sources = within(screen.getByRole('region', { name: 'Fuentes consultadas' }));
    expect(sources.getAllByText(/^Fuente:/).length).toBeGreaterThanOrEqual(1);
    expect(sources.getAllByText(/^Referencia:/).length).toBeGreaterThanOrEqual(1);
    const link = sources.getAllByRole('link', { name: /Consultar fuente original/ })[0];
    expect(link).toHaveAttribute('href', expect.stringMatching(/^https:\/\//));
    expect(link).toHaveAttribute('target', '_blank'); // el enlace externo abre una pestaña nueva
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /Volver a consejos/ }));
    expect(await screen.findByRole('heading', { name: 'Consejos para diabéticos', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pies' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('article').length).toBe(ARTICLES.filter((article) => article.category === 'pies').length);
  });

  it('un artículo inexistente muestra un aviso y permite volver', async () => {
    renderAt('/app/consejos/no-existe');
    expect(await screen.findByText('No encontramos ese consejo.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Volver a consejos' })).toHaveAttribute('href', '/app/consejos');
  });
});
