// /app/ayuda: guía de uso separada por tipo de cuenta (cliente e institucional). Abre en la pestaña de la cuenta vigente.
// Los textos viven en helpContent.js; aquí solo se muestran.

import { Building2, UserRound } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useAuth } from '../../../auth/AuthContext.jsx';
import { Navbar } from '../../../components/Navbar.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { SiteFooter } from '../../../components/SiteFooter.jsx';
import { SkipLink } from '../../../components/SkipLink.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';
import { AYUDA_AVISO, AYUDA_CLIENTE, AYUDA_INSTITUCIONAL } from './helpContent.js';
import { PasoBoton, PasoImagen, PasoMenu } from './GuiaVisual.jsx';
import './Help.css';

const TAB_BASE = 'ayuda-tipo';
const PESTANAS = [
  { key: 'CLIENTE', label: 'Cliente', icon: UserRound, temas: AYUDA_CLIENTE, descripcion: 'Para cuentas individuales: medir, ver tus mediciones, el grupo familiar y tu seguridad.' },
  { key: 'INSTITUCIONAL', label: 'Institucional', icon: Building2, temas: AYUDA_INSTITUCIONAL, descripcion: 'Para cuentas de instituciones: equipo, pacientes, dispositivos y auditoría según tu rol.' },
];

function Tema({ prefijo, tipo, tema }) {
  const id = `${prefijo}-${tema.id}`;
  const headingId = `${id}-titulo`;
  return (
    <section className="panel help-topic" id={id} aria-labelledby={headingId}>
      <h2 id={headingId}>{tema.titulo}</h2>
      {tema.intro && <p className="help-intro">{tema.intro}</p>}

      {tema.pasos && (
        <>
          <h3>Cómo se usa</h3>
          <ol className="help-steps">
            {tema.pasos.map(({ texto, ir, boton, captura, pie }, index) => (
              <li key={`${index}-${texto}`}>
                <div className={ir || boton || captura ? 'help-paso' : undefined}>
                  <div>
                    {texto}
                    {ir && <Link to={ir.to} className="help-go">{ir.label} →</Link>}
                  </div>
                  {(ir || boton || captura) && (
                    <div className="help-paso-visual">
                      {ir && <PasoMenu tipo={tipo} destino={ir.to} />}
                      {boton && <PasoBoton texto={boton} captura={captura} pie={pie} />}
                      {captura && !boton && <PasoImagen captura={captura} pie={pie} alt={texto} />}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}

      {tema.detalles && (
        <>
          <h3>Qué es cada cosa</h3>
          <dl className="help-defs">
            {tema.detalles.map(({ titulo, texto, captura }) => (
              <div key={titulo}>
                <dt>{titulo}</dt>
                <dd>{texto}</dd>
                {captura && <PasoImagen captura={captura} alt={titulo} />}
              </div>
            ))}
          </dl>
        </>
      )}

      {tema.casos && (
        <>
          <h3>Casos</h3>
          <dl className="help-defs help-casos">
            {tema.casos.map(({ titulo, texto, captura }, index) => (
              <div key={`${index}-${titulo}`}>
                <dt>{titulo}</dt>
                <dd>{texto}</dd>
                {captura && <PasoImagen captura={captura} alt={titulo} />}
              </div>
            ))}
          </dl>
        </>
      )}

      {tema.tabla && (
        <div className="help-table-wrap" role="region" aria-label={`Tabla: ${tema.titulo}`} tabIndex={0}>
          <table className="help-table">
            <thead>
              <tr>{tema.tabla.encabezados.map((encabezado) => <th key={encabezado} scope="col">{encabezado}</th>)}</tr>
            </thead>
            <tbody>
              {tema.tabla.filas.map((fila) => (
                <tr key={fila[0]}>
                  {fila.map((celda, index) => (index === 0 ? <th key={celda} scope="row">{celda}</th> : <td key={`${fila[0]}-${index}`}>{celda}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function HelpPage() {
  const { account } = useAuth();
  const cuentaInstitucional = account?.usuario?.tipoCuenta === 'USUARIO_INSTITUCIONAL';
  const [eleccion, setEleccion] = useState(null);
  const tipo = eleccion ?? (cuentaInstitucional ? 'INSTITUCIONAL' : 'CLIENTE');
  const pestana = PESTANAS.find((item) => item.key === tipo) ?? PESTANAS[0];
  const prefijo = `ayuda-${pestana.key.toLowerCase()}`;

  return (
    <div className="page help-page">
      <PageHeader title="Ayuda" description={`${AYUDA_AVISO} Elegí la guía de tu tipo de cuenta.`} />

      <Tabs label="Tipo de cuenta" idBase={TAB_BASE} variant="pill" value={pestana.key} onChange={setEleccion}
        items={PESTANAS.map(({ key, label, icon }) => ({ key, label, icon }))} />

      <TabPanel idBase={TAB_BASE} value={pestana.key} focusable className="help-tabpanel">
        <p className="help-tipo-descripcion">{pestana.descripcion}</p>

        <nav className="panel help-index" aria-label={`Temas de la guía ${pestana.label.toLowerCase()}`}>
          <h2>Temas</h2>
          <ol>
            {pestana.temas.map((tema) => (
              <li key={tema.id}><a href={`#${prefijo}-${tema.id}`}>{tema.titulo}</a></li>
            ))}
          </ol>
        </nav>

        {pestana.temas.map((tema) => <Tema key={tema.id} prefijo={prefijo} tipo={pestana.key} tema={tema} />)}
      </TabPanel>
    </div>
  );
}

/** Pública (/ayuda): sin iniciar sesión, con el navbar y el pie de la portada. */
export function PublicHelpPage() {
  return (
    <div className="landing">
      <SkipLink />
      <Navbar />
      <main className="section" id="contenido" tabIndex={-1}>
        <div className="container">
          <HelpPage />
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
