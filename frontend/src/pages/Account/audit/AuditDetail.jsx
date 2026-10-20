// Detalle de un evento de auditoría en su propia página (ruta con :idAuditoria), compartido por la auditoría general y
// la institucional. Cada una pasa su `loadDetail`, así que conserva su propio control de acceso en FastAPI.
// Tres bloques: resumen del evento, cambios (antes/después) y «Detalles técnicos» (contraído): la vista principal usa
// nombres y descripciones funcionales; los UUID y el JSON original quedan para trazabilidad, sin modificar el registro.

import { ArrowLeft, ArrowRight, Check, Copy, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';

import { Badge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { PatientIdentity } from '../../../components/PatientIdentity.jsx';
import { copyText } from '../../../utils/clipboard.js';
import { formatInstant } from '../../../utils/dateTime.js';
import './Audit.css';
import { ACTOR_ORIGINS, AUDIT_CLASSIFICATIONS, AUDIT_MODULES, CLASSIFICATION_HELP, eventName, resultInfo, severityInfo } from './auditLabels.js';

const ROLE_TEXT = { PROPIETARIO: 'propietario/a', MODERADOR: 'moderador/a', OPERADOR: 'operador/a' };

export function valueText(value) {
  if (!value) return '—';
  return value.rol && value.disponible !== false ? `${value.texto} (${ROLE_TEXT[value.rol] ?? value.rol})` : value.texto;
}

function Row({ label, value, note }) {
  return <div><dt>{label}</dt><dd className={value ? undefined : 'is-empty'}>{value || '—'}{note && <small className="audit-note">{note}</small>}</dd></div>;
}

/** Un dato que solo se conoce por el registro vigente puede haber cambiado desde el evento: se aclara. */
const originNote = (origin) => (origin === 'ACTUAL' ? 'dato actual' : null);

/** Copia un texto al portapapeles (con respaldo para http://glucolume.local, donde navigator.clipboard no existe) y avisa el resultado. */
function CopyButton({ text, label }) {
  const [state, setState] = useState('idle');
  async function copy() {
    const ok = await copyText(text);
    setState(ok ? 'copied' : 'failed');
    setTimeout(() => setState('idle'), 2200);
  }
  return (
    <button type="button" className={`copy-button${state === 'failed' ? ' is-failed' : ''}`} onClick={copy} aria-label={`Copiar ${label}`}>
      {state === 'copied' ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
      <span role="status">{state === 'copied' ? 'Copiado' : state === 'failed' ? 'No se pudo copiar' : 'Copiar'}</span>
    </button>
  );
}

function Changes({ changes }) {
  if (!changes?.length) return null;
  return (
    <section className="panel" aria-labelledby="auditoria-cambios">
      <h2 id="auditoria-cambios">Cambios realizados</h2>
      <div className="table-scroll">
        <table className="data-table audit-changes" aria-label="Cambios del evento">
          <thead><tr><th scope="col">Campo</th><th scope="col">Antes</th><th scope="col">Después</th></tr></thead>
          <tbody>
            {changes.map((change) => (
              <tr key={change.campo}>
                <th scope="row" data-label="Campo">{change.etiqueta}</th>
                <td data-label="Antes" className={!change.anterior || change.anterior.ausente ? 'is-empty' : undefined}>{change.anterior ? valueText(change.anterior) : 'Sin valor'}</td>
                <td data-label="Después" className={!change.nuevo || change.nuevo.ausente ? 'is-empty' : undefined}>{change.nuevo ? valueText(change.nuevo) : 'Sin valor'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TransferBlock({ transfer }) {
  return (
    <section className="panel" aria-labelledby="auditoria-transferencia">
      <h2 id="auditoria-transferencia">Transferencia</h2>
      <PatientIdentity name={transfer.paciente?.nombreCompleto} code={transfer.paciente?.identificador}
        available={transfer.paciente?.datosIdentificativos} />
      <div className="transfer-flow">
        <div className="transfer-party" aria-label="Operador de origen"><small>Operador de origen</small><b>{valueText(transfer.origen)}</b></div>
        <ArrowRight size={28} role="img" aria-label="cambia a" className="transfer-arrow" />
        <div className="transfer-party" aria-label="Operador de destino"><small>Operador de destino</small><b>{valueText(transfer.destino)}</b></div>
      </div>
    </section>
  );
}

/** `titleAs`: «h1» cuando la pantalla no tiene otro título principal (auditoría general); «h2» bajo el h1 del layout de la institución. */
export function AuditEventPage({ loadDetail, backTo, handleOperationError, titleAs = 'h2' }) {
  const { idAuditoria } = useParams();
  const location = useLocation();
  const [event, setEvent] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setEvent(null);
    setError('');
    loadDetail(idAuditoria).then(
      (result) => active && setEvent(result),
      (loadError) => active && setError(handleOperationError(loadError)),
    );
    return () => { active = false; };
  }, [idAuditoria, loadDetail, handleOperationError]);

  // Vuelve al listado con los mismos filtros y página cuando se llegó desde él.
  const back = (
    <Link to={{ pathname: backTo, search: location.state?.search ?? '' }} className="back-link">
      <ArrowLeft size={16} aria-hidden="true" /> Volver a auditoría
    </Link>
  );
  if (error) return <><Alert>{error}</Alert>{back}</>;
  if (!event) return <p className="field-hint" role="status">Cargando el evento…</p>;

  // Identificadores internos con el nombre que el backend pudo resolver (el UUID no se reemplaza); más el tipo de evento y de entidad.
  const references = event.referencias ?? [];
  const technical = [['Tipo de evento', event.tipoEvento], ['Tipo de entidad', event.tipoEntidad], ['Tabla relacionada', event.tablaRelacionada]]
    .filter(([, value]) => value);
  const json = [['Valores previos', event.valoresPrevios], ['Valores nuevos', event.valoresNuevos]].filter(([, value]) => value);
  const generic = !event.transferencia;
  const result = resultInfo(event);
  const severity = severityInfo(event);
  const Title = titleAs === 'h1' ? 'h1' : 'h2';

  return (
    <div className="audit-detail">
      {back}
      <section className="panel" aria-labelledby="auditoria-detalle">
        <div className="panel-head">
          <div className="panel-title">
            <span className="panel-icon is-lg"><ShieldCheck size={26} aria-hidden="true" /></span>
            <div>
              <Title id="auditoria-detalle">Detalle del evento</Title>
              <p>{eventName(event)}</p>
            </div>
          </div>
          <Badge tone={severity.tone}>{result.label}</Badge>
        </div>
        {event.resumen && <p className="transfer-summary">{event.resumen}</p>}
        <dl className="data-list audit-summary-list">
          <Row label="Acción" value={eventName(event)} />
          <Row label="Realizado por" value={event.usuario ?? 'Sistema'}
            note={event.origenActor === 'PLATAFORMA' || (event.origenActor === 'SISTEMA' && event.usuario) ? ACTOR_ORIGINS[event.origenActor] : null} />
          <Row label="Institución" value={event.nombreInstitucion} />
          {generic && (
            <Row label="Entidad afectada" value={event.entidad?.texto ?? event.entidadEtiqueta}
              note={[event.entidad?.tipo, originNote(event.entidad?.origen)].filter(Boolean).join(' · ') || null} />
          )}
          {generic && event.entidad?.atributos?.map((attribute) => (
            <Row key={attribute.etiqueta} label={attribute.etiqueta} value={attribute.texto} note={originNote(attribute.origen)} />
          ))}
          <Row label="Resultado" value={result.label} />
          {event.clasificacion && <Row label="Clasificación" value={AUDIT_CLASSIFICATIONS[event.clasificacion]} note={CLASSIFICATION_HELP[event.clasificacion]} />}
          {event.motivoEtiqueta && <Row label="Motivo" value={event.motivoEtiqueta} />}
          <Row label="Fecha y hora" value={formatInstant(event.fechaHora)} />
          <Row label="Módulo" value={AUDIT_MODULES[event.modulo] ?? event.modulo} />
          {generic && event.relacionada && <Row label="Persona relacionada" value={valueText(event.relacionada)} />}
          {event.descripcion && <Row label="Descripción" value={event.descripcion} />}
        </dl>
      </section>
      {(event.ipOrigen || event.agenteUsuario || event.idCorrelacion || event.referenciaIdentificador) && (
        <section className="panel" aria-labelledby="auditoria-origen">
          <h2 id="auditoria-origen">Origen de la solicitud</h2>
          <p className="field-hint">Solo lo ve la administración de la plataforma. La IP se conserva por un plazo limitado y después se anula; nunca se guardan contraseñas, tokens ni códigos.</p>
          <dl className="data-list audit-summary-list">
            <Row label="IP de origen" value={event.ipOrigen} />
            <Row label="Cliente" value={event.agenteUsuario} />
            <Row label="Identificador de correlación" value={event.idCorrelacion} />
            {event.referenciaIdentificador && (
              <Row label="Referencia del identificador" value={event.referenciaIdentificador}
                note="Huella no reversible del identificador probado en una cuenta inexistente: sirve para ver repeticiones sin guardar lo que se escribió." />
            )}
          </dl>
          {event.idCorrelacion && <CopyButton text={event.idCorrelacion} label="el identificador de correlación" />}
        </section>
      )}
      {event.transferencia && <TransferBlock transfer={event.transferencia} />}
      <Changes changes={event.cambios} />
      <details className="panel audit-technical">
        <summary>Detalles técnicos</summary>
        <p className="field-hint">Para trazabilidad y soporte. Los registros originales no se modifican y no incluyen contraseñas ni secretos.</p>
        <dl className="audit-ids">
          {references.map((reference) => (
            <div key={reference.etiqueta}>
              <dt>{reference.etiqueta}</dt>
              <dd>
                {reference.nombre && (
                  <span className={`audit-ref-name${reference.disponible ? '' : ' is-empty'}`}>
                    {reference.nombre}{originNote(reference.origen) && <small className="audit-note">{originNote(reference.origen)}</small>}
                  </span>
                )}
                {reference.id ? (
                  <span className="audit-ref-id"><small>Identificador interno</small><code>{reference.id}</code></span>
                ) : <span className="audit-ref-id is-empty">Sin identificador</span>}
                {reference.id && <CopyButton text={reference.id} label={reference.etiqueta.toLowerCase()} />}
              </dd>
            </div>
          ))}
          {technical.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>
          ))}
        </dl>
        {json.map(([label, value]) => {
          const text = JSON.stringify(value, null, 2);
          return (
            <div key={label} className="audit-json-block">
              <div className="audit-json-head"><h3 className="member-list-title">{label}</h3><CopyButton text={text} label={label.toLowerCase()} /></div>
              <pre className="audit-json" aria-label={label}>{text}</pre>
            </div>
          );
        })}
      </details>
    </div>
  );
}
