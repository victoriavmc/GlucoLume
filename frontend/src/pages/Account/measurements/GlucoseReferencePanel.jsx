// «Matriz de referencia de glucosa»: solo para mediciones GLUCOSA_EXPERIMENTAL. Muestra el valor, la matriz asociada y las reglas REALES de
// ReglaMatriz (sin intervalos inventados), con una escala donde se ubica el valor. «Dentro / por debajo / por encima» es una comparación
// matemática con el intervalo configurado: no es una clasificación clínica ni un diagnóstico.
//
// Distingue matriz APLICADA (participó de una estimación del servidor), de REFERENCIA (solo se consulta para comparar) y SIN_MATRIZ.
// Con el sexo sin informar muestra las dos referencias (femenina y masculina) solo para consulta: ninguna se asigna ni se usa como resultado.

import { BookOpen, Droplet, FlaskConical, User, Utensils, Venus } from 'lucide-react';
import { useState } from 'react';

import { Alert } from '../../../components/FormControls.jsx';
import { Badge } from '../../../components/Badge.jsx';
import { TabPanel, Tabs } from '../../../components/Tabs.jsx';
import { DemoBadge } from './DeviceReadout.jsx';
import { MEALS, ORIGINS, SEXO } from './measurementFormat.js';

const POSITIONS = {
  DENTRO: 'Dentro del intervalo configurado',
  POR_DEBAJO: 'Por debajo del intervalo configurado',
  POR_ENCIMA: 'Por encima del intervalo configurado',
};

const STATE_TEXT = {
  APLICADA: 'Matriz aplicada: participó en el cálculo de la estimación de este resultado.',
  REFERENCIA: 'Matriz de referencia: se consulta para comparar el resultado; no participó en ningún cálculo.',
  SIN_MATRIZ: 'Referencia no disponible: no había una matriz vigente asociada a esta medición.',
};

const SEX_LABELS = { FEMENINO: 'Femenino', MASCULINO: 'Masculino', NO_INFORMADO: 'Sexo no informado' };

/** Rango de edad de una regla: un límite vacío es «sin límite» (una regla sin rango vale para cualquier edad). */
export function ageText(rule) {
  if (rule.edadDesde === null && rule.edadHasta === null) return 'Sin rango de edad (cualquier edad)';
  if (rule.edadDesde === null) return `Hasta ${rule.edadHasta} años`;
  if (rule.edadHasta === null) return `Desde ${rule.edadDesde} años`;
  return `${rule.edadDesde}–${rule.edadHasta} años`;
}

const number = (value) => Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 });

/** Escala horizontal: límites inferior y superior de la regla y un marcador con el valor. */
export function RangeScale({ min, max, value, label }) {
  const span = max - min || 1;
  const lo = Math.min(min, value ?? min) - span * 0.35;
  const hi = Math.max(max, value ?? max) + span * 0.35;
  const at = (point) => `${(((point - lo) / (hi - lo)) * 100).toFixed(1)}%`;
  return (
    <div className="range-scale" role="img" aria-label={label}>
      <div className="range-track">
        <span className="range-band" style={{ left: at(min), width: `${(((max - min) / (hi - lo)) * 100).toFixed(1)}%` }} />
        {value !== null && value !== undefined && <span className="range-marker" style={{ left: at(value) }}><b>{number(value)}</b></span>}
      </div>
      <div className="range-limits">
        <span style={{ left: at(min) }}>{number(min)}</span>
        <span style={{ left: at(max) }}>{number(max)}</span>
      </div>
    </div>
  );
}

function ruleText(rule) {
  const minutes = rule.minutosComidaMin !== null || rule.minutosComidaMax !== null
    ? ` (${rule.minutosComidaMin ?? 0}–${rule.minutosComidaMax ?? '∞'} min desde la comida)` : '';
  return `${ageText(rule)} · ${MEALS[rule.condicionComida] ?? rule.condicionComida}${minutes} · ${number(rule.glucosaMinReferencia)}–${number(rule.glucosaMaxReferencia)} mg/dL`;
}

function Group({ group, value, demo }) {
  const rule = group.reglaSeleccionada;
  return (
    <article className="reference-group" aria-label={group.titulo}>
      <h4>{group.titulo} {group.aplicada && <Badge tone="success">Regla aplicada</Badge>}</h4>
      {rule ? (
        <>
          <dl className="data-list">
            <div><dt>Regla disponible para {SEX_LABELS[rule.sexoModelo] ?? rule.sexoModelo}</dt><dd>{rule.codigo}</dd></div>
            <div><dt>Rango de edad</dt><dd>{ageText(rule)}</dd></div>
            <div><dt>Condición de alimentación</dt><dd>{MEALS[rule.condicionComida] ?? rule.condicionComida}</dd></div>
            <div><dt>Intervalo configurado</dt><dd>{number(rule.glucosaMinReferencia)}–{number(rule.glucosaMaxReferencia)} mg/dL</dd></div>
          </dl>
          <RangeScale min={rule.glucosaMinReferencia} max={rule.glucosaMaxReferencia} value={value}
            label={`${group.titulo}: intervalo ${number(rule.glucosaMinReferencia)} a ${number(rule.glucosaMaxReferencia)} mg/dL`} />
          {group.posicion ? (
            <p className={`reference-position is-${group.posicion.toLowerCase()}`} role="status">
              <b>{POSITIONS[group.posicion]}</b>
              <small>{demo ? ' Comparación ilustrativa con un valor DEMO (sintético).' : ' Comparación matemática con la regla experimental, no una clasificación clínica.'}</small>
            </p>
          ) : <p className="field-hint">Sin valor de glucosa para comparar.</p>}
        </>
      ) : (
        <>
          <p className="field-hint">{group.motivoSinSeleccion}</p>
          {group.reglas.length > 0 && (
            <ul className="reference-rules" aria-label={`Reglas disponibles: ${group.titulo}`}>
              {group.reglas.map((candidate) => <li key={candidate.idRegla}>{ruleText(candidate)}</li>)}
            </ul>
          )}
        </>
      )}
    </article>
  );
}

/** Un dato que se tiene en cuenta para elegir la regla: ícono, nombre y valor. */
function Fact({ icon: Icon, label, children, empty }) {
  return (
    <li className="ref-fact">
      <span className="ref-fact-icon"><Icon size={22} aria-hidden="true" /></span>
      <small>{label}</small>
      <b className={empty ? 'is-empty' : undefined}>{children}</b>
    </li>
  );
}

export function GlucoseReferencePanel({ reference }) {
  const groups = reference.grupos ?? [];
  const firstApplied = groups.findIndex((group) => group.aplicada);
  const [chosen, setChosen] = useState(null);
  const active = Math.min(chosen ?? (firstApplied >= 0 ? firstApplied : 0), Math.max(groups.length - 1, 0));
  return (
    <section className="md-card reference-panel" aria-label="Matriz de referencia de glucosa">
      <header className="md-section-head">
        <div className="md-section-text">
          <h3 className="md-section-title"><FlaskConical size={22} aria-hidden="true" /> Matriz de referencia de glucosa</h3>
          <p className="field-hint">Las referencias pueden variar según la edad, el sexo utilizado por el modelo y el tipo de comida.</p>
        </div>
        <span className="md-matrix">
          <BookOpen size={20} aria-hidden="true" />
          <b>{reference.matriz ? `${reference.matriz.nombre}, versión ${reference.matriz.version}` : 'Sin matriz'}</b>
        </span>
      </header>
      <ul className="ref-facts" aria-label="Datos que se tienen en cuenta para las reglas">
        <Fact icon={Droplet} label="Glucosa obtenida" empty={reference.valor === null}>
          {reference.valor !== null ? <>{number(reference.valor)} {reference.unidad} {reference.esDemo && <DemoBadge />}</> : 'Sin dato'}
        </Fact>
        <Fact icon={User} label="Edad utilizada" empty={reference.edad === null}>{reference.edad !== null ? `${reference.edad} años` : 'No informada'}</Fact>
        <Fact icon={Venus} label="Sexo utilizado" empty={!reference.sexoModelo}>{reference.sexoModelo ? (SEXO[reference.sexoModelo] ?? reference.sexoModelo) : 'No informado'}</Fact>
        <Fact icon={Utensils} label="Alimentación">{MEALS[reference.condicionComida] ?? reference.condicionComida}</Fact>
      </ul>
      <p className="field-hint">{STATE_TEXT[reference.estado]}</p>
      {reference.esDemo && (
        <Alert kind="info">El valor es DEMO: una simulación del firmware, no la glucosa real de la persona. Las comparaciones son solo ilustrativas.</Alert>
      )}
      {reference.avisoSexo && <Alert kind="info">{reference.avisoSexo}</Alert>}
      {reference.estado !== 'SIN_MATRIZ' && groups.length > 0 && (
        <div className="reference-groups">
          {groups.length > 1 && (
            <Tabs label="Elegir la referencia a ver" idBase="ref" variant="pill" value={groups[active].sexoModelo}
              onChange={(key) => setChosen(groups.findIndex((group) => group.sexoModelo === key))}
              items={groups.map((group) => ({ key: group.sexoModelo, label: `${group.titulo}${group.aplicada ? ' · aplicada' : ''}` }))} />
          )}
          <TabPanel idBase="ref" value={groups[active].sexoModelo}>
            <Group key={groups[active].sexoModelo} group={groups[active]} value={reference.valor} demo={reference.esDemo} />
          </TabPanel>
        </div>
      )}
    </section>
  );
}
