// Genera el mapa de rutas de la SPA para Nginx a partir del router (src/App.jsx), que es la única fuente de verdad.
//
//   node scripts/generar-rutas-spa.mjs <salida.conf>
//
// Lee el árbol JSX de <Route> con el parser de Babel (anidadas, index y layouts incluidos) y escribe un bloque `map $uri $ruta_spa`:
// vale 1 para cada ruta que la SPA declara y 0 para el resto, que Nginx responde 404 (ver docker/nginx/default.conf.template).
// Falla si una ruta no es un literal (no se puede saber qué sirve sin ejecutar el código) o si no encuentra el router.
// Las rutas con parámetros (:id) se traducen a [^/]+. El catch-all «*» no es una ruta: es lo que redirige lo desconocido.

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from '@babel/parser';

const MINIMO_RUTAS = 20; // guarda contra un parseo que no encuentre el router real

export function extraerRutas(codigo) {
  const ast = parse(codigo, { sourceType: 'module', plugins: ['jsx'] });
  const raices = [];
  buscarRaices(ast, raices);
  const rutas = new Set();
  for (const raiz of raices) recorrer(raiz, '', rutas);
  if (rutas.size < MINIMO_RUTAS) {
    throw new Error(`Se encontraron ${rutas.size} rutas en App.jsx (se esperaban al menos ${MINIMO_RUTAS}): revisar el generador.`);
  }
  return [...rutas].sort();
}

function nombreDeElemento(nodo) {
  const nombre = nodo.openingElement?.name;
  return nombre?.type === 'JSXIdentifier' ? nombre.name : null;
}

function atributo(nodo, nombre) {
  return nodo.openingElement.attributes.find((a) => a.type === 'JSXAttribute' && a.name.name === nombre);
}

function buscarRaices(nodo, raices) {
  if (!nodo || typeof nodo.type !== 'string') return;
  if (nodo.type === 'JSXElement' && nombreDeElemento(nodo) === 'Route') {
    raices.push(nodo);
    return; // las rutas anidadas se recorren desde la raíz, no aquí
  }
  for (const valor of Object.values(nodo)) {
    if (Array.isArray(valor)) valor.forEach((hijo) => buscarRaices(hijo, raices));
    else if (valor && typeof valor === 'object') buscarRaices(valor, raices);
  }
}

function valorPath(nodo) {
  const attr = atributo(nodo, 'path');
  if (!attr) return null;
  const valor = attr.value?.type === 'JSXExpressionContainer' ? attr.value.expression : attr.value;
  if (valor?.type === 'StringLiteral') return valor.value;
  throw new Error(`Ruta no literal en App.jsx, línea ${attr.loc.start.line}: el generador necesita rutas escritas como texto.`);
}

function unir(base, relativa) {
  return `${base.replace(/\/$/, '')}/${relativa}`;
}

function recorrer(nodo, base, rutas) {
  if (nombreDeElemento(nodo) !== 'Route') return;
  const path = valorPath(nodo);
  const esIndice = atributo(nodo, 'index') !== undefined;
  let completa = base;
  if (esIndice) {
    completa = base || '/'; // la ruta index responde en la ruta de su padre
    rutas.add(completa);
  } else if (path !== null && path !== '*') {
    completa = path.startsWith('/') ? path : unir(base, path);
    rutas.add(completa);
  }
  for (const hijo of nodo.children) {
    if (hijo.type === 'JSXElement') recorrer(hijo, completa, rutas);
  }
}

const ESCAPABLES = /[.^$*+?()[\]{}|\\]/g;

export function aExpresionNginx(ruta) {
  if (ruta === '/') return '^/$';
  const partes = ruta.split('/').filter(Boolean);
  const cuerpo = partes.map((p) => (p.startsWith(':') ? '[^/]+' : p.replace(ESCAPABLES, '\\$&'))).join('/');
  return `^/${cuerpo}/?$`;
}

export function generarMapa(rutas) {
  const lineas = [
    '# GENERADO por frontend/scripts/generar-rutas-spa.mjs a partir de frontend/src/App.jsx. No editar a mano: cambiar el router y regenerar.',
    `# ${rutas.length} rutas de la SPA. $ruta_spa vale 1 para cada una; cualquier otra ruta que no es archivo responde 404 (B-2).`,
    'map $uri $ruta_spa {',
    '    default 0;',
    ...rutas.map((ruta) => `    ~*${aExpresionNginx(ruta)} 1;   # ${ruta}`),
    '}',
    '',
  ];
  return lineas.join('\n');
}

function principal() {
  const salida = process.argv[2];
  if (!salida) {
    console.error('Uso: node scripts/generar-rutas-spa.mjs <salida.conf>');
    process.exit(2);
  }
  const here = dirname(fileURLToPath(import.meta.url));
  const codigo = readFileSync(join(here, '..', 'src', 'App.jsx'), 'utf8');
  const rutas = extraerRutas(codigo);
  writeFileSync(salida, generarMapa(rutas));
  console.log(`${rutas.length} rutas escritas en ${salida}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) principal();
