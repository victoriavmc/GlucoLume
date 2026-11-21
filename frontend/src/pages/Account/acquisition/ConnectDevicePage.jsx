// /app/conectar-dispositivo (cuentas individuales) y /app/instituciones/:id/conectar-dispositivo (operadores) — conexión guiada del
// Arduino UNO (MAX30100) por Bluetooth (HC-05/HC-06, 9600) o USB (115200).
//
// El Arduino lo lee el NAVEGADOR (Web Serial, Chrome/Edge de escritorio, sin instalar nada) o, como alternativa, el PUENTE de GlucoLume (programa de
// Windows con pySerial); ambos lo entregan al backend y la pantalla nunca ejecuta programas locales. Esta página PREPARA y COMPRUEBA la conexión con datos reales (estado en vivo y
// diagnóstico del backend): el puerto, la telemetría, la identidad, el registro y la asociación. Medir se hace en «Mis mediciones»
// (o en el paciente, para un operador) y el guardado en «Guardar medición»; el historial recupera lo guardado. No se duplican esas pantallas.
//
// Operador: entra desde SU institución. Acá mismo identifica el Arduino y lo registra la primera vez (queda en el inventario de la
// institución, a cargo del propietario) o lo reconoce si ya está; no hace falta que el propietario lo cargue a mano.

import { useEffect, useState } from 'react';
import { Navigate, useOutletContext } from 'react-router-dom';

import * as measurementsApi from '../../../api/measurementsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { useDeviceStatus } from '../measurements/useDeviceStatus.js';
import { webSerialSupported } from '../../../utils/browserSerialLink.js';
import { BridgeSettings } from './BridgeSettings.jsx';
import { BrowserConnection } from './BrowserConnection.jsx';
import { ConnectionGuide } from './ConnectionGuide.jsx';
import { ConnectionStatusPanel } from './ConnectionStatusPanel.jsx';
import { DeviceIdentification } from './DeviceIdentification.jsx';
import { MeasurementGuide } from './MeasurementGuide.jsx';
import { MEDIA, bridgeRunning, nextAction } from './connectModel.js';
import { useDeviceReadiness } from './useDeviceReadiness.js';
import './ConnectDevice.css';

/** `institution`: la institución donde entró un operador. Sin ella es la página de una cuenta individual. */
export function ConnectDeviceView({ institution }) {
  const individual = !institution;
  const idInstitucion = institution?.idInstitucion;
  const { status, error: statusError, refresh } = useDeviceStatus();
  const [profile, setProfile] = useState(individual ? null : { perfilDisponible: false });
  const [profileError, setProfileError] = useState('');
  const [medium, setMedium] = useState(null);
  const idPerfil = profile?.perfilDisponible ? profile.idPerfilMedicion : undefined;
  const { readiness, error: readinessError, refresh: refreshReadiness } = useDeviceReadiness(idPerfil, status, idInstitucion);

  useEffect(() => {
    if (!individual) return;
    measurementsApi.getOwnProfile().then(setProfile, (loadError) => {
      setProfileError(friendlyError(loadError));
      setProfile({ perfilDisponible: false });
    });
  }, [individual]);

  // El medio elegido parte del que el puente ya usa; puede ser AUTO (solo el selector lo entiende). La guía necesita un medio físico:
  // mientras el puente busca el GlucoLume en modo AUTO, muestra Bluetooth como antes de saber cuál usa.
  const chosenMedium = medium ?? status?.puente?.medio ?? 'BLUETOOTH';
  const guideMedium = MEDIA[chosenMedium] ? chosenMedium : 'BLUETOOTH';
  // Con Web Serial (Chrome/Edge de escritorio) el Arduino se lee desde el navegador, sin puente: solo cede ante un puente instalado que ya esté activo.
  const browserMode = webSerialSupported() && (!bridgeRunning(status) || status.puente.origen === 'NAVEGADOR');
  const action = nextAction(status, readiness, guideMedium, webSerialSupported());
  const error = statusError || readinessError || profileError;
  const refreshAll = () => { refresh(); refreshReadiness(); };

  return (
    <div className="page connect-page">
      <PageHeader as={institution ? 'h2' : 'h1'} title="Conectar dispositivo"
        back={institution ? { to: `/app/instituciones/${idInstitucion}`, label: `Panel de ${institution.nombre}` } : undefined}
        description={`Dejá listo tu Arduino UNO con sensor MAX30100 y comprobá la conexión. Se configura una sola vez; después solo${individual ? ' entrás a «Mis mediciones», medís y guardás.' : ' elegís al paciente, medís y guardás.'}`} />
      {error && <Alert>{error}</Alert>}
      {individual && profile && !profile.perfilDisponible && !profileError && (
        <Alert kind="info">Tu perfil de medición no está disponible en este momento: no se puede comprobar la asociación del dispositivo.</Alert>
      )}
      {institution && (
        <Alert kind="info">
          Estás conectando un dispositivo en {institution.nombre}. La asociación con un paciente no se hace acá: se establece al iniciar la medición,
          con las autorizaciones de cada paciente.
        </Alert>
      )}

      <ConnectionStatusPanel status={status} readiness={readiness} medium={guideMedium} onRetry={refreshAll} institutional={!individual} />
      {institution && <DeviceIdentification identification={readiness?.identificacion} onChanged={refreshAll} />}
      <div className="connect-cols">
        {browserMode
          ? <BrowserConnection status={status} medium={guideMedium} />
          : <BridgeSettings status={status} medium={chosenMedium} onMediumChange={setMedium} onChanged={refreshAll} authority={readiness?.ordenesPuente} />}
        <ConnectionGuide medium={guideMedium} onMediumChange={setMedium} />
      </div>
      <MeasurementGuide ready={Boolean(readiness?.listo)} individual={individual} blockedBy={readiness?.listo ? null : `${action.title}.`}
        measureTo={institution ? `/app/instituciones/${idInstitucion}/pacientes` : undefined} />
    </div>
  );
}

/** Operador: la conexión se hace dentro de la institución (el dispositivo se reconoce y se registra en SU inventario). */
export function InstitutionConnectDevicePage() {
  const { institution } = useOutletContext();
  if (institution.rolInstitucion !== 'OPERADOR') return <Navigate to=".." relative="path" replace />;
  return <ConnectDeviceView institution={institution} />;
}

