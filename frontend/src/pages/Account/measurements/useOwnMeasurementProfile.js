// Perfil de medición propio y autorización de almacenamiento, compartidos por las pantallas de «Mediciones»
// (dashboard, nueva medición, configuración de perfil). El backend resuelve siempre el perfil de la sesión.

import { useCallback, useEffect, useState } from 'react';

import * as authApi from '../../../api/authApi.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';

export function useOwnMeasurementProfile({ enabled = true } = {}) {
  const [profile, setProfile] = useState(null); // null: cargando
  const [consent, setConsent] = useState(null); // null: cargando · { aceptado, ... }
  const [error, setError] = useState('');

  const reloadProfile = useCallback(() => measurementsApi.getOwnProfile().then(setProfile, (loadError) => {
    setError(friendlyError(loadError));
    setProfile({ perfilDisponible: false });
  }), []);

  useEffect(() => {
    if (!enabled) return;
    reloadProfile();
    authApi.getConsents().then((all) => setConsent(all.DATOS_EXPERIMENTALES), (loadError) => {
      setError(friendlyError(loadError));
      setConsent({ aceptado: false });
    });
  }, [enabled, reloadProfile]);

  return { profile, consent, setConsent, error, reloadProfile };
}
