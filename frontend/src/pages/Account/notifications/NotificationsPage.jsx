// /app/notificaciones: avisos en la página y por correo, horario para medirme y la bandeja de avisos.
// Los datos los guarda el backend (api/notificationsApi.js); la página solo muestra lo que devuelve.

import { useEffect, useState } from 'react';

import * as notificationsApi from '../../../api/notificationsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { CUENTA_INDIVIDUAL, eventosVisibles } from './notificationsCopy.js';
import { NotificationChannels } from './NotificationChannels.jsx';
import { NotificationInbox } from './NotificationInbox.jsx';
import { ReminderSchedule } from './ReminderSchedule.jsx';
import './Notifications.css';

export default function NotificationsPage() {
  const { account } = useAuth();
  const tipoCuenta = account?.usuario?.tipoCuenta;
  const individual = tipoCuenta === CUENTA_INDIVIDUAL;
  const [settings, setSettings] = useState(null);
  const [inbox, setInbox] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([notificationsApi.getNotificationSettings(), notificationsApi.getNotifications()])
      .then(([loadedSettings, loadedInbox]) => {
        if (!active) return;
        setSettings(loadedSettings);
        setInbox(loadedInbox);
      })
      .catch((error) => {
        if (active) setLoadError(friendlyError(error));
      });
    return () => {
      active = false;
    };
  }, []);

  async function attempt(action) {
    setActionError('');
    try {
      return await action();
    } catch (error) {
      setActionError(friendlyError(error));
      return null;
    }
  }

  async function changePreference(evento, changes) {
    const next = await attempt(() => notificationsApi.updateNotificationPreference(evento, changes));
    if (next) setSettings(next);
  }

  async function saveSchedule(schedule) {
    const next = await attempt(() => notificationsApi.updateReminderSchedule(schedule));
    if (next) setSettings(next);
    return Boolean(next);
  }

  async function markRead(idNotificacion) {
    const next = await attempt(() => notificationsApi.markNotificationRead(idNotificacion));
    if (next) setInbox(next);
  }

  async function markAllRead() {
    const next = await attempt(() => notificationsApi.markAllNotificationsRead());
    if (next) setInbox(next);
  }

  const header = (
    <header className="page-head">
      <h1>Notificaciones</h1>
      <p>Elegí qué avisos ver en la página y cuáles recibir por correo.</p>
    </header>
  );

  if (loadError) {
    return (
      <div className="page is-form notifications-page">
        {header}
        <Alert>{loadError}</Alert>
      </div>
    );
  }

  if (!settings || !inbox) {
    return (
      <div className="page is-form notifications-page">
        {header}
        <p className="notif-empty">Cargando tus avisos…</p>
      </div>
    );
  }

  return (
    <div className="page is-form notifications-page">
      {header}
      {actionError && <Alert>{actionError}</Alert>}
      <NotificationInbox inbox={inbox} onRead={markRead} onReadAll={markAllRead} />
      <NotificationChannels preferencias={settings.preferencias} visibles={eventosVisibles(tipoCuenta)}
        onChange={changePreference} />
      {individual && <ReminderSchedule schedule={settings.recordatorio} onSave={saveSchedule} />}
    </div>
  );
}
