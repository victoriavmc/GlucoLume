// /app/notificaciones/preferencias: qué avisos recibir (en la aplicación y por correo, por separado) y el horario de los recordatorios.
// Los datos los guarda el backend (api/notificationsApi.js); la página solo muestra lo que devuelve.

import { ArrowLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import * as notificationsApi from '../../../api/notificationsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { NotificationChannels } from './NotificationChannels.jsx';
import { CUENTA_INDIVIDUAL, RUTA_BANDEJA, categoriasVisibles } from './notificationsCopy.js';
import { ReminderSchedule } from './ReminderSchedule.jsx';
import './Notifications.css';

export default function NotificationPreferencesPage() {
  const { account } = useAuth();
  const tipoCuenta = account?.usuario?.tipoCuenta;
  const individual = tipoCuenta === CUENTA_INDIVIDUAL;
  const [settings, setSettings] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [savingEvent, setSavingEvent] = useState(null);

  useEffect(() => {
    let active = true;
    notificationsApi.getNotificationSettings()
      .then((loaded) => {
        if (active) setSettings(loaded);
      })
      .catch((error) => {
        if (active) setLoadError(friendlyError(error));
      });
    return () => {
      active = false;
    };
  }, []);

  async function changePreference(evento, changes) {
    setActionError('');
    setSavingEvent(evento);
    try {
      setSettings(await notificationsApi.updateNotificationPreference(evento, changes));
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setSavingEvent(null);
    }
  }

  async function saveSchedule(schedule) {
    setActionError('');
    try {
      setSettings(await notificationsApi.updateReminderSchedule(schedule));
      return true;
    } catch (error) {
      setActionError(friendlyError(error));
      return false;
    }
  }

  const header = (
    <header className="notif-head">
      <div className="page-head">
        <h1>Preferencias de notificaciones</h1>
        <p>Elegí qué avisos recibir, en la aplicación, por correo o en ambos. Cada canal se configura por separado.</p>
      </div>
      <div className="notif-head-actions">
        <Link to={RUTA_BANDEJA} className="btn btn-ghost">
          <ArrowLeft size={18} aria-hidden="true" /> Volver a la bandeja
        </Link>
      </div>
    </header>
  );

  if (loadError) {
    return (
      <div className="page notifications-page">
        {header}
        <Alert>{loadError}</Alert>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="page notifications-page">
        {header}
        <p className="notif-state" role="status">Cargando tus preferencias…</p>
      </div>
    );
  }

  return (
    <div className="page notifications-page">
      {header}
      {actionError && <Alert>{actionError}</Alert>}
      <div className="notif-prefs">
        {categoriasVisibles(tipoCuenta).map((categoria) => (
          <div key={categoria} className="notif-prefs-block">
            <NotificationChannels categoria={categoria} savingEvent={savingEvent} onChange={changePreference}
              preferencias={settings.preferencias.filter((preferencia) => preferencia.categoria === categoria)} />
            {categoria === 'RECORDATORIO' && individual && <ReminderSchedule schedule={settings.recordatorio} onSave={saveSchedule} />}
          </div>
        ))}
      </div>
    </div>
  );
}
