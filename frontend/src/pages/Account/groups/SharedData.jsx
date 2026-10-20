// Datos compartidos: tarjetas de los demás integrantes con lo que cada uno habilitó. Al elegir una persona se piden
// solo las secciones que autorizó (cada una a su propio endpoint, que vuelve a verificar el permiso en FastAPI). No
// se consulta nada no autorizado ni se guarda en el navegador. Si la persona revoca, la próxima consulta devuelve
// 403 y la sección se cierra.

import { Activity, Bell, BellRing, CalendarDays, ChevronLeft, ChevronRight, Eye, History, UserRound, Venus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { OriginBadge } from '../../../components/Badge.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import {
  MEALS, MODES, ROLE_LABELS, SHARING_OPTIONS, formatDate, formatDateTime, formatNoticeMoment, formatNumber, personName,
  sharesAnything,
} from './groupFormat.js';
import { GroupEvolution } from './GroupEvolution.jsx';
import { MemberHero } from './MemberHero.jsx';
import { DEMO_LABEL, ORIGIN_LABELS, glucoseText } from './sharedMeasurementFormat.js';

const SEXO = { FEMENINO: 'Femenino', MASCULINO: 'Masculino' };

function useShared(loader, deps) {
  const [state, setState] = useState({ data: null, error: '' });
  useEffect(() => {
    let active = true;
    setState({ data: null, error: '' });
    loader().then(
      (data) => active && setState({ data, error: '' }),
      (error) => active && setState({ data: null, error }),
    );
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

function Section({ icon: Icon, title, subtitle, id, action, children }) {
  return (
    <section className="gd-panel" aria-labelledby={id}>
      <div className="gm-section-head">
        <span className="gm-section-icon">
          <Icon size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id={id}>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action && <div className="gm-section-action">{action}</div>}
      </div>
      {children}
    </section>
  );
}

function SectionError({ error, onRevoked }) {
  // Revocación o salida de la persona: se recargan las tarjetas con el estado real (fuera del render).
  useEffect(() => {
    if (['DATOS_NO_COMPARTIDOS', 'MIEMBRO_NO_ENCONTRADO', 'GRUPO_NO_ENCONTRADO'].includes(error?.codigo)) onRevoked();
  }, [error, onRevoked]);
  return <Alert>{friendlyError(error)}</Alert>;
}

/** Una medición compartida: una prueba DEMO se rotula siempre como tal y nunca como medición clínica. «Ver detalle» abre su vista ampliada. */
export function MeasurementLine({ measurement, group, member }) {
  const glucose = glucoseText(measurement);
  return (
    <>
      <span>
        <b>{formatDateTime(measurement.fechaHoraInicio)}</b>
        <small> · {MODES[measurement.modoMedicion] ?? measurement.modoMedicion} · {MEALS[measurement.condicionComida] ?? measurement.condicionComida}</small>
        {measurement.esDemo && <> <OriginBadge origin="DEMO">{DEMO_LABEL}</OriginBadge></>}
        <br />
        <small>
          SpO₂ {formatNumber(measurement.spo2, '%')} · Frecuencia cardíaca {formatNumber(measurement.frecuenciaCardiaca, 'lpm')}
          {glucose && ` · ${glucose}`}
          {measurement.origenGlucosa && ` · Origen: ${ORIGIN_LABELS[measurement.origenGlucosa] ?? measurement.origenGlucosa}`}
          {' · Completada'}
        </small>
      </span>
      <Link to={`/app/grupo/${group.idGrupo}/compartidos/${member.idGrupoUsuario}/mediciones/${measurement.idMedicion}`} className="btn btn-outline">Ver detalle</Link>
    </>
  );
}

const RECENT_LIMIT = 5; // por defecto solo se ven los últimos de la persona; el botón del costado abre todos
const PAGE_SIZE = 10;

/** Botón del costado del título: alterna entre «los últimos 5» y «todos». */
function ExpandButton({ expanded, onToggle, total, label }) {
  if (!expanded && total <= RECENT_LIMIT) return null;
  return (
    <button type="button" className="btn btn-outline" onClick={onToggle} aria-expanded={expanded}>
      {expanded ? `Ver solo los últimos ${RECENT_LIMIT}` : label}
    </button>
  );
}

function NoticesSection({ group, member, onRevoked }) {
  const [expanded, setExpanded] = useState(false);
  const [pagina, setPagina] = useState(1);
  const size = expanded ? PAGE_SIZE : RECENT_LIMIT;
  const { data, error } = useShared(
    () => groupsApi.getSharedNotices(group.idGrupo, member.idGrupoUsuario, size, expanded ? pagina : 1),
    [member.idGrupoUsuario, expanded, pagina],
  );
  const name = personName(member);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  return (
    <Section icon={Bell} title="Avisos de medición" subtitle="Notificaciones que genera esta persona en el grupo." id="compartido-avisos"
      action={data && <ExpandButton expanded={expanded} total={data.total} label="Ver todos los avisos"
        onToggle={() => { setExpanded((value) => !value); setPagina(1); }} />}>
      {error ? <SectionError error={error} onRevoked={onRevoked} /> : !data ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : data.items.length === 0 ? (
        <EmptyState icon={BellRing} title="Todavía no realizó mediciones." description="Cuando esta persona registre mediciones, sus avisos aparecerán aquí." />
      ) : (
        <>
          <ul className="gm-notices" aria-label="Avisos de medición">
            {data.items.map((notice) => (
              <li key={notice.fechaHoraInicio}>
                <span className="gm-notice-icon"><BellRing size={18} aria-hidden="true" /></span>
                <span>{name} realizó una medición el {formatNoticeMoment(notice.fechaHoraInicio)}</span>
              </li>
            ))}
          </ul>
          {expanded && data.total > PAGE_SIZE && (
            <nav className="pagination" aria-label="Páginas de los avisos">
              <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                <ChevronLeft size={16} aria-hidden="true" /> Anterior
              </button>
              <span>Página {pagina} de {totalPages}</span>
              <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
                Siguiente <ChevronRight size={16} aria-hidden="true" />
              </button>
            </nav>
          )}
          <p className="field-hint">
            {expanded ? `${data.total} avisos en total. ` : data.total > RECENT_LIMIT ? `Se muestran los últimos ${RECENT_LIMIT} de ${data.total}. ` : ''}
            Solo se informa cuándo se midió, sin resultados.
          </p>
        </>
      )}
    </Section>
  );
}

function ProfileSection({ group, member, handleOperationError, onRevoked }) {
  const { data, error } = useShared(() => groupsApi.getSharedProfile(group.idGrupo, member.idGrupoUsuario), [member.idGrupoUsuario]);
  return (
    <Section icon={UserRound} title="Datos básicos del perfil" subtitle="Información personal compartida en el grupo." id="compartido-perfil">
      {error ? <SectionError error={error} onRevoked={onRevoked} /> : !data ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : (
        <dl className="gm-facts">
          <div><span className="gm-fact-icon"><CalendarDays size={22} aria-hidden="true" /></span><dt>Edad</dt><dd>{data.edad ?? 'Sin informar'}</dd></div>
          <div><span className="gm-fact-icon"><Venus size={22} aria-hidden="true" /></span><dt>Sexo (modelo)</dt><dd>{data.sexoModelo ? (SEXO[data.sexoModelo] ?? data.sexoModelo) : 'Sin informar'}</dd></div>
        </dl>
      )}
    </Section>
  );
}

function LatestSection({ group, member, handleOperationError, onRevoked }) {
  const { data, error } = useShared(() => groupsApi.getSharedLatest(group.idGrupo, member.idGrupoUsuario), [member.idGrupoUsuario]);
  return (
    <Section icon={Activity} title="Última medición" subtitle="Su medición más reciente, compartida con el grupo." id="compartido-ultima">
      {error ? <SectionError error={error} onRevoked={onRevoked} /> : !data ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : data.medicion ? (
        <div className="gm-measure"><MeasurementLine measurement={data.medicion} group={group} member={member} /></div>
      ) : (
        <EmptyState icon={Activity} title="Todavía no tiene mediciones completadas." description="Cuando complete una medición, aparecerá aquí." />
      )}
    </Section>
  );
}

function HistorySection({ group, member, handleOperationError, onRevoked }) {
  const [expanded, setExpanded] = useState(false);
  const [pagina, setPagina] = useState(1);
  const size = expanded ? PAGE_SIZE : RECENT_LIMIT;
  const { data, error } = useShared(
    () => groupsApi.getSharedHistory(group.idGrupo, member.idGrupoUsuario, expanded ? pagina : 1, size), [member.idGrupoUsuario, expanded, pagina],
  );
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.tamanioPagina)) : 1;
  return (
    <Section icon={History} title="Historial de mediciones" subtitle="Mediciones completadas que compartió con el grupo." id="compartido-historial"
      action={data && <ExpandButton expanded={expanded} total={data.total} label="Ver historial"
        onToggle={() => { setExpanded((value) => !value); setPagina(1); }} />}>
      {error ? <SectionError error={error} onRevoked={onRevoked} /> : !data ? (
        <p className="field-hint" role="status">Cargando…</p>
      ) : data.items.length === 0 ? (
        <EmptyState icon={Activity} title="Todavía no tiene mediciones completadas." description="Cuando complete una medición, aparecerá aquí." />
      ) : (
        <>
          <ul className="gm-measures" aria-label="Historial compartido">
            {data.items.map((measurement) => (
              <li key={measurement.idMedicion} className="gm-measure"><MeasurementLine measurement={measurement} group={group} member={member} /></li>
            ))}
          </ul>
          {expanded && data.total > data.tamanioPagina && (
            <nav className="pagination" aria-label="Páginas del historial">
              <button type="button" className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                <ChevronLeft size={16} aria-hidden="true" /> Anterior
              </button>
              <span>Página {data.pagina} de {totalPages}</span>
              <button type="button" className="btn btn-ghost" disabled={pagina >= totalPages} onClick={() => setPagina((p) => p + 1)}>
                Siguiente <ChevronRight size={16} aria-hidden="true" />
              </button>
            </nav>
          )}
          <p className="field-hint">
            {expanded ? `${data.total} mediciones en total.` : data.total > RECENT_LIMIT ? `Se muestran las últimas ${RECENT_LIMIT} de ${data.total}.` : ''}
          </p>
        </>
      )}
    </Section>
  );
}

// Cualquiera de los cuatro permisos: el aviso (solo fecha y hora) también se consulta sin los demás.
const sharesSomething = sharesAnything;

export function SharedData() {
  const { group, handleOperationError } = useOutletContext();
  const [members, setMembers] = useState(null);
  // ?integrante=<idGrupoUsuario> preselecciona a la persona elegida desde el listado de integrantes.
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState(() => searchParams.get('integrante'));
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setMembers(await groupsApi.getSharedMembers(group.idGrupo));
    } catch (loadError) {
      setError(handleOperationError(loadError));
      setMembers([]);
    }
  }, [group.idGrupo, handleOperationError]);

  useEffect(() => {
    load();
  }, [load]);

  const found = members?.find((member) => member.idGrupoUsuario === selectedId) ?? null;
  const selected = found && found.tienePerfil && sharesSomething(found) ? found : null;
  // Si una consulta indica que la persona revocó (o salió), se recargan las tarjetas con el estado real.
  const onRevoked = useCallback(() => { load(); }, [load]);

  return (
    <>
      <section className="panel" aria-labelledby="compartidos">
        <div className="panel-title">
          <span className="panel-icon">
            <Eye size={22} aria-hidden="true" />
          </span>
          <div>
            <h2 id="compartidos">Datos compartidos</h2>
            <p>Solo lo que cada persona decidió compartir con el grupo.</p>
          </div>
        </div>
        {error && <Alert>{error}</Alert>}
        {members === null ? (
          <p className="field-hint" role="status">Cargando…</p>
        ) : members.length === 0 ? (
          <p className="field-hint">Todavía no hay otros integrantes en el grupo.</p>
        ) : (
          <ul className="summary-grid institution-list" aria-label="Integrantes y lo que comparten">
            {members.map((member) => (
              <li key={member.idGrupoUsuario}>
                <button type="button" className={`summary-card shared-card${member.idGrupoUsuario === selectedId ? ' is-selected' : ''}`}
                  onClick={() => setSelectedId(member.idGrupoUsuario)} disabled={!sharesSomething(member) || !member.tienePerfil}>
                  <small>{ROLE_LABELS[member.rol]}</small>
                  <b>{personName(member)}</b>
                  {!member.tienePerfil ? (
                    <span className="field-hint">Todavía no tiene perfil de medición.</span>
                  ) : sharesSomething(member) ? (
                    <span className="field-hint">
                      Comparte: {SHARING_OPTIONS.filter(({ field }) => member[field]).map(({ label }) => label.toLowerCase()).join(', ')}.
                    </span>
                  ) : (
                    <span className="field-hint">No habilitó datos de medición para el grupo.</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected && (
        <>
          <h2 className="shared-title">Datos de {personName(selected)}</h2>
          <MemberHero member={selected} />
          <MemberSections group={group} member={selected} handleOperationError={handleOperationError} onRevoked={onRevoked} />
        </>
      )}
    </>
  );
}

/** El gráfico de evolución exige «Historial de mediciones»: ni la última medición ni el aviso alcanzan (tampoco para el administrador). */
export function EvolutionNotShared() {
  return (
    <Alert kind="info">
      Este integrante no habilitó compartir su historial de mediciones, por lo que no se puede mostrar su evolución.
    </Alert>
  );
}

/**
 * Solo las secciones que la persona autorizó: lo que no está habilitado ni siquiera se consulta (el backend lo
 * rechazaría de todos modos). Los gráficos y estadísticas se habilitan con el historial: no hay un permiso aparte.
 */
export function MemberSections({ group, member, handleOperationError, onRevoked }) {
  return (
    <>
      {member.compartePerfil && <ProfileSection key={`p-${member.idGrupoUsuario}`} group={group} member={member} handleOperationError={handleOperationError} onRevoked={onRevoked} />}
      {member.comparteUltimaMedicion && <LatestSection key={`l-${member.idGrupoUsuario}`} group={group} member={member} handleOperationError={handleOperationError} onRevoked={onRevoked} />}
      {member.comparteHistorial && (
        <>
          <HistorySection key={`h-${member.idGrupoUsuario}`} group={group} member={member} handleOperationError={handleOperationError} onRevoked={onRevoked} />
          <GroupEvolution key={`e-${member.idGrupoUsuario}`} idGrupo={group.idGrupo} members={[member]}
            title={`Evolución de ${personName(member)}`}
            description={`Mediciones que ${personName(member)} compartió con el grupo. Las pruebas DEMO también se muestran, identificadas aparte (línea punteada) y sin mezclarse con las experimentales.`} />
        </>
      )}
      {member.notificaMedicion && <NoticesSection key={`n-${member.idGrupoUsuario}`} group={group} member={member} onRevoked={onRevoked} />}
      {!member.comparteHistorial && <EvolutionNotShared />}
      {!sharesSomething(member) && <Alert kind="info">Esta persona no habilitó datos de medición para el grupo.</Alert>}
    </>
  );
}
