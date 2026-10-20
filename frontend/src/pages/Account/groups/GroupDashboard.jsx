// Dashboard del grupo y página de cada integrante. Todo sale de FastAPI, que evalúa los permisos personales de
// compartición EN CADA CONSULTA: si alguien revoca, deja de aparecer en la siguiente. Nada privado llega a React para
// ocultarse después. Roles del grupo: ADMINISTRADOR y MIEMBRO.

import {
  ArrowLeft, ArrowRight, BarChart3, Bell, Clock, Crown, Droplet, FileText, Info, Lock, UserRound, Users,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';

import * as dashboardApi from '../../../api/dashboardApi.js';
import * as groupsApi from '../../../api/groupsApi.js';
import { Badge, OriginBadge } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { MetricBlocks, PeriodFilter, periodLabel } from '../../../components/dashboard.jsx';
import { GroupEvolution } from './GroupEvolution.jsx';
import { MODES, ROLE_LABELS, SHARING_OPTIONS, formatNumber, formatWeekdayDateTime, glucoseText, personName, sharesAnything } from './groupFormat.js';
import { MemberHero } from './MemberHero.jsx';
import { EvolutionNotShared, MemberSections } from './SharedData.jsx';

const SHARING_ICONS = { compartePerfil: UserRound, comparteUltimaMedicion: Droplet, comparteHistorial: BarChart3, notificaMedicion: Bell };

/** Estado de cada permiso del integrante: verde «Compartido» o gris «No compartido». Nunca muestra los datos en sí. */
export function SharingBadges({ member, columns = false }) {
  return (
    <ul className={`gd-share-list${columns ? ' is-columns' : ''}`} aria-label={`Qué comparte ${personName(member)}`}>
      {SHARING_OPTIONS.map(({ field, label }) => {
        const Icon = SHARING_ICONS[field];
        return (
          <li key={field}>
            <Icon size={16} aria-hidden="true" />
            {label}: <Badge tone={member[field] ? 'success' : 'neutral'}>{member[field] ? 'Compartido' : 'No compartido'}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function Avatar({ person, tone, large = false }) {
  const initial = personName(person).charAt(0).toUpperCase();
  return <span className={`gd-avatar${tone ? ` is-${tone}` : ''}${large ? ' is-large' : ''}`} aria-hidden="true">{initial}</span>;
}

function SectionHead({ icon: Icon, id, title, hint }) {
  return (
    <div className="gd-section-head">
      <h2 id={id}><span className="gd-section-icon"><Icon size={20} aria-hidden="true" /></span>{title}</h2>
      {hint && <p>{hint}</p>}
    </div>
  );
}

// Un indicador por tarjeta: ícono, descripción y cantidad. Los valores los calcula el backend con pertenencias y permisos vigentes.
function SummaryKpis({ data }) {
  const items = [
    { label: 'Integrantes activos', value: data.integrantesActivos, icon: Users, tone: 'rose', hint: 'Personas con pertenencia activa en el grupo.' },
    { label: 'Administradores', value: data.administradores, icon: Crown, tone: 'amber' },
    { label: 'Miembros', value: data.miembros, icon: UserRound, tone: 'blue' },
    { label: 'Comparten la última medición', value: data.comparteUltimaMedicion, icon: Droplet, tone: 'green' },
    { label: 'Comparten el historial', value: data.comparteHistorial, icon: FileText, tone: 'violet' },
  ];
  return (
    <ul className="gd-kpis" aria-label="Resumen del grupo">
      {items.map(({ label, value, icon: Icon, tone, hint }) => (
        <li key={label} className={`gd-kpi is-${tone}`}>
          <span className="gd-kpi-top">
            <Icon size={22} aria-hidden="true" />
            <small>{label}</small>
            {hint && <span className="gd-info" title={hint} role="img" aria-label={hint}><Info size={14} aria-hidden="true" /></span>}
          </span>
          <b>{value}</b>
        </li>
      ))}
    </ul>
  );
}

function MemberCards({ members }) {
  return (
    <ul className="gd-members" aria-label="Integrantes del grupo">
      {members.map((member) => {
        const shares = sharesAnything(member);
        return (
          <li key={member.idGrupoUsuario} className="gd-member">
            <div className="gd-member-head">
              <Avatar person={member} tone={member.rol === 'ADMINISTRADOR' ? 'rose' : 'violet'} />
              <b>{personName(member)}{member.esVos && ' (vos)'}</b>
              <Badge tone={member.rol === 'ADMINISTRADOR' ? 'brand' : 'info'} icon={member.rol === 'ADMINISTRADOR' ? Crown : undefined}>
                {ROLE_LABELS[member.rol]}
              </Badge>
            </div>
            <SharingBadges member={member} />
            {member.esVos ? (
              <Link to="privacidad" relative="path" className="gd-member-action">
                Cambiar mi privacidad <ArrowRight size={16} aria-hidden="true" />
              </Link>
            ) : (
              <Link to={`integrantes/${member.idGrupoUsuario}`} className="gd-member-action">
                {shares && member.tienePerfil ? 'Ver sus datos compartidos' : 'Ver integrante'} <ArrowRight size={16} aria-hidden="true" />
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// Lista cronológica de lo que cada persona autorizó mostrar, siempre con día, fecha y hora. Con «Última medición» o «Historial» trae los
// valores autorizados (las pruebas DEMO rotuladas, sin confundirse con las experimentales). Con solo «Aviso de medición» llega únicamente
// el hecho («Realizó una medición»): el backend no envía valores, y acá tampoco se muestra ninguno.
function ActivityTimeline({ items }) {
  return (
    <ul className="gd-timeline" aria-label="Actividad compartida reciente">
      {items.map((item) => {
        const measurement = item.medicion ?? null;
        const when = item.fechaHoraInicio ?? measurement?.fechaHoraInicio;
        const notice = item.tipo === 'AVISO' || !measurement;
        const glucose = measurement ? glucoseText(measurement) : null;
        return (
          <li key={`${item.idGrupoUsuario}-${when}-${notice ? 'aviso' : 'medicion'}`} className={`gd-activity${notice ? ' is-notice' : ''}`}>
            <span className="gd-activity-dot" aria-hidden="true" />
            <Avatar person={item} />
            <div className="gd-activity-who">
              <b>{personName(item)}</b>
              <small>{formatWeekdayDateTime(when)}</small>
            </div>
            {notice ? (
              <div className="gd-activity-body">
                <span className="gd-activity-tags">
                  <Badge tone="neutral" icon={Bell}>Aviso de medición compartido</Badge>
                </span>
                <small>Realizó una medición</small>
              </div>
            ) : (
              <div className="gd-activity-body">
                <span className="gd-activity-tags">
                  <Badge tone="brand">{MODES[measurement.modoMedicion] ?? measurement.modoMedicion}</Badge>
                  {measurement.esDemo && <OriginBadge origin="DEMO">DEMO (prueba)</OriginBadge>}
                </span>
                <small>
                  SpO₂ {formatNumber(measurement.spo2, '%')} · Frecuencia cardíaca {formatNumber(measurement.frecuenciaCardiaca, 'lpm')}
                  {glucose && ` · ${glucose}`}
                </small>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Panel del grupo: una sola consulta al dashboard (resumen, integrantes, actividad y estadísticas del período). */
export function GroupDashboardSection() {
  const { group, handleOperationError } = useOutletContext();
  const [period, setPeriod] = useState({ dias: 30 });
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    dashboardApi.getGroupDashboard(group.idGrupo, period).then(
      (result) => { if (active) { setData(result); setError(''); } },
      (loadError) => { if (active) setError(handleOperationError(loadError)); },
    );
    return () => { active = false; };
  }, [group.idGrupo, JSON.stringify(period), handleOperationError]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) {
    return (
      <section className="gd-panel" aria-label="Panel del grupo">
        {error ? <Alert>{error}</Alert> : <p className="field-hint" role="status">Cargando el panel del grupo…</p>}
      </section>
    );
  }

  return (
    <>
      {error && <Alert>{error}</Alert>}
      <section className="gd-panel" aria-labelledby="grupo-resumen">
        <SectionHead icon={BarChart3} id="grupo-resumen" title="Resumen del grupo" hint="Una vista rápida de la actividad y participación del grupo." />
        <SummaryKpis data={data} />
      </section>

      <section className="gd-panel" aria-labelledby="grupo-actividad">
        <SectionHead icon={Clock} id="grupo-actividad" title="Actividad compartida reciente"
          hint="Últimas mediciones que los integrantes compartieron en el grupo." />
        {data.actividadReciente.length === 0 ? (
          <p className="field-hint">Nadie compartió mediciones recientes con el grupo.</p>
        ) : (
          <ActivityTimeline items={data.actividadReciente} />
        )}
      </section>

      <section className="gd-panel" aria-labelledby="grupo-estadisticas">
        <SectionHead icon={BarChart3} id="grupo-estadisticas" title="Estadísticas del grupo"
          hint="Visualizá tendencias del grupo según el período seleccionado." />
        <PeriodFilter value={period} onChange={setPeriod} idPrefix="dash-grupo" />
        {data.agregado ? (
          <>
            <p className="field-hint">
              Período: {periodLabel(data.periodo)}. Incluye a: {data.agregado.participantes.join(', ')}. Solo mediciones completadas
              de quienes compartieron su historial.
            </p>
            <MetricBlocks statistics={data.agregado.estadisticas} />
          </>
        ) : (
          <div className="gd-note" role="status">
            <span className="gd-note-icon"><BarChart3 size={22} aria-hidden="true" /></span>
            <p>{data.motivoSinAgregado}</p>
          </div>
        )}
      </section>

      <GroupEvolution idGrupo={group.idGrupo} members={data.integrantes} />

      <section className="gd-panel" aria-labelledby="grupo-integrantes-panel">
        <SectionHead icon={Users} id="grupo-integrantes-panel" title="Integrantes"
          hint="Cada integrante decide qué comparte en su configuración de privacidad." />
        <MemberCards members={data.integrantes} />
      </section>

      <p className="gd-footnote">
        <Lock size={15} aria-hidden="true" />
        Pertenecer al grupo no comparte tus datos: cada persona, incluido el administrador, decide en «Mi privacidad» qué información de sus
        mediciones ve el resto.
      </p>
    </>
  );
}

/** Grupo → Integrantes → persona: nombre, rol, permisos y solo los datos autorizados. */
export function GroupMemberPage() {
  const { group, handleOperationError } = useOutletContext();
  const { idGrupoUsuario } = useParams();
  const [members, setMembers] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setMembers(await groupsApi.getSharedMembers(group.idGrupo));
    } catch (loadError) {
      setError(handleOperationError(loadError));
      setMembers([]);
    }
  }, [group.idGrupo, handleOperationError]);

  useEffect(() => { load(); }, [load]);

  const member = members?.find((item) => item.idGrupoUsuario === idGrupoUsuario) ?? null;
  // Sin migas de pan ni «volver»: las pestañas del grupo (Panel, Integrantes…) ya son la navegación.
  const toPanel = <Link to="../.." relative="path" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Volver al panel</Link>

  if (members === null) return <p className="field-hint" role="status">Cargando…</p>;
  if (!member) {
    return (
      <>
        {error && <Alert>{error}</Alert>}
        <Alert kind="info">
          No encontramos a ese integrante entre los demás integrantes activos del grupo. Tus propios datos están en «Mis mediciones».
        </Alert>
        {toPanel}
      </>
    );
  }
  const canView = member.tienePerfil && sharesAnything(member);
  return (
    <>
      <MemberHero member={member} />
      {canView ? (
        <MemberSections group={group} member={member} handleOperationError={handleOperationError} onRevoked={load} />
      ) : (
        <>
          <Alert kind="info">Este integrante no habilitó la visualización de sus datos de medición.</Alert>
          <EvolutionNotShared />
        </>
      )}
    </>
  );
}
