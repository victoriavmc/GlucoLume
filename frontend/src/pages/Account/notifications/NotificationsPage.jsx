// /app/notificaciones: la bandeja de notificaciones. Las preferencias están aparte (/app/notificaciones/preferencias).
// Los datos los guarda el backend (api/notificationsApi.js); la página solo muestra lo que devuelve.

import { BellOff, CheckCheck, Settings } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '../../../auth/AuthContext.jsx';
import { Tabs, TabPanel } from '../../../components/Tabs.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { EmptyState } from '../../../components/EmptyState.jsx';
import { NotificationCard } from './NotificationCard.jsx';
import { CATEGORIAS, RUTA_PREFERENCIAS, agruparPorDia, destinoSeguro, filtrosVisibles } from './notificationsCopy.js';
import { useNotificationList } from './useNotificationList.js';
import './Notifications.css';

const TAB_BASE = 'notif-filtro';

function emptyMessage(filtro) {
  if (filtro.key === 'TODAS') return { title: 'Todavía no tenés notificaciones', text: 'Cuando haya novedades en tu cuenta, tu grupo o tus recordatorios, aparecen acá.' };
  if (filtro.key === 'NO_LEIDAS') return { title: 'No tenés notificaciones sin leer', text: 'Estás al día.' };
  return { title: `No hay notificaciones de ${CATEGORIAS[filtro.categoria].titulo.toLowerCase()}`, text: 'Probá con otro filtro para ver el resto.' };
}

export default function NotificationsPage() {
  const { account } = useAuth();
  const navigate = useNavigate();
  const tipoCuenta = account?.usuario?.tipoCuenta;
  const filtros = useMemo(() => filtrosVisibles(tipoCuenta), [tipoCuenta]);
  const [filterKey, setFilterKey] = useState('TODAS');
  const filtro = filtros.find((item) => item.key === filterKey) ?? filtros[0];
  const list = useNotificationList(filtro.params);
  const { status, items, noLeidas, hayMas, total, loadingMore, loadError, actionError } = list;
  const groups = useMemo(() => agruparPorDia(items), [items]);

  function open(notificacion) {
    list.markRead(notificacion.idNotificacion);
    const destino = destinoSeguro(notificacion.url);
    if (destino) navigate(destino);
  }

  const summary = noLeidas === null ? '' : noLeidas > 0 ? `Tenés ${noLeidas} sin leer.` : 'No tenés avisos sin leer.';

  return (
    <div className="page notifications-page">
      <header className="notif-head">
        <div className="page-head">
          <h1>Notificaciones</h1>
          <p aria-live="polite">{summary}</p>
        </div>
        <div className="notif-head-actions">
          <button type="button" className="btn btn-ghost" onClick={list.markAllRead} disabled={!noLeidas}>
            <CheckCheck size={18} aria-hidden="true" /> Marcar todas como leídas
          </button>
          <Link to={RUTA_PREFERENCIAS} className="btn btn-ghost">
            <Settings size={18} aria-hidden="true" /> Preferencias
          </Link>
        </div>
      </header>

      {actionError && <Alert>{actionError}</Alert>}

      <Tabs label="Filtrar notificaciones" idBase={TAB_BASE} variant="pill" value={filtro.key} onChange={setFilterKey}
        items={filtros.map(({ key, label }) => ({ key, label }))} />

      <TabPanel idBase={TAB_BASE} value={filtro.key} className="notif-panel">
        {status === 'loading' && <p className="notif-state" role="status">Cargando tus notificaciones…</p>}

        {status === 'error' && (
          <div className="notif-state">
            <Alert>{loadError}</Alert>
            <button type="button" className="btn btn-ghost" onClick={list.reload}>Reintentar</button>
          </div>
        )}

        {status === 'ready' && items.length === 0 && (
          <EmptyState icon={BellOff} title={emptyMessage(filtro).title} description={emptyMessage(filtro).text} role="status"
            action={filtro.key === 'TODAS' ? <Link to={RUTA_PREFERENCIAS} className="btn btn-ghost">Elegir qué avisos recibir</Link> : null} />
        )}

        {status === 'ready' && items.length > 0 && (
          <>
            {groups.map((group) => (
              <section key={group.key} className="notif-day" aria-labelledby={`notif-dia-${group.key}`}>
                <h2 id={`notif-dia-${group.key}`}>{group.label}</h2>
                <ul className="notif-list">
                  {group.items.map((notificacion) => (
                    <NotificationCard key={notificacion.idNotificacion} notificacion={notificacion} onOpen={open} />
                  ))}
                </ul>
              </section>
            ))}
            <div className="notif-more">
              <span>Mostrando {items.length} de {total}</span>
              {hayMas && (
                <button type="button" className="btn btn-ghost" onClick={list.loadMore} disabled={loadingMore} aria-busy={loadingMore || undefined}>
                  {loadingMore ? 'Cargando…' : 'Cargar más'}
                </button>
              )}
            </div>
          </>
        )}
      </TabPanel>
    </div>
  );
}
