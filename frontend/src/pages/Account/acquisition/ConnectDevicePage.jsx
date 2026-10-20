// /app/conectar-dispositivo (cuentas individuales) y /app/instituciones/:id/conectar-dispositivo (operadores) — conexión guiada del
// Arduino UNO (MAX30100) por Bluetooth (HC-05/HC-06, 9600) o USB (115200).
//
// El Arduino lo lee el PUENTE de GlucoLume (programa de Windows con pySerial) y lo entrega al backend; el navegador nunca toca
// un puerto COM ni ejecuta programas locales. Esta página PREPARA y COMPRUEBA la conexión con datos reales (estado en vivo y
// diagnóstico del backend): el puerto, la telemetría, la identidad, el registro y la asociación. Medir se hace en «Mis mediciones»
// (o en el paciente, para un operador) y el guardado en «Guardar medición»; el historial recupera lo guardado. No se duplican esas pantallas.
//
// Operador: entra desde SU institución. Acá mismo identifica el Arduino y lo registra la primera vez (queda en el inventario de la
// institución, a cargo del propietario) o lo reconoce si ya está; no hace falta que el propietario lo cargue a mano.

import { useEffect, useState } from 'react';
import { Link, Navigate, useOutletContext } from 'react-router-dom';

import * as institutionsApi from '../../../api/institutionsApi.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { useAuth } from '../../../auth/AuthContext.jsx';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Alert } from '../../../components/FormControls.jsx';
import { PageHeader } from '../../../components/PageHeader.jsx';
import { useDeviceStatus } from '../measurements/useDeviceStatus.js';
import { BridgeSettings } from './BridgeSettings.jsx';
import { ConnectionGuide } from './ConnectionGuide.jsx';
import { ConnectionStatusPanel } from './ConnectionStatusPanel.jsx';
import { DeviceIdentification } from './DeviceIdentification.jsx';
import { MeasurementGuide } from './MeasurementGuide.jsx';
import { nextAction } from './connectModel.js';
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

  // El medio que muestra la guía parte del que el puente ya usa; antes de saberlo, Bluetooth.
  const effectiveMedium = medium ?? status?.puente?.medio ?? 'BLUETOOTH';
  const action = nextAction(status, readiness, effectiveMedium);
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

      <ConnectionStatusPanel status={status} readiness={readiness} medium={effectiveMedium} onRetry={refreshAll} institutional={!individual} />
      {institution && <DeviceIdentification identification={readiness?.identificacion} onChanged={refreshAll} />}
      <div className="connect-cols">
        <BridgeSettings status={status} medium={effectiveMedium} onMediumChange={setMedium} onChanged={refreshAll} authority={readiness?.ordenesPuente} />
        <ConnectionGuide medium={effectiveMedium} onMediumChange={setMedium} status={status} readiness={readiness} institutional={!individual} />
      </div>
      <MeasurementGuide ready={Boolean(readiness?.listo)} individual={individual} blockedBy={readiness?.listo ? null : `${action.title}.`}
        measureTo={institution ? `/app/instituciones/${idInstitucion}/pacientes` : undefined} />
    </div>
  );
}

/** Cuenta individual: su propia página de conexión. */
export function ConnectDevicePage() {
  const { account } = useAuth();
  if (account.usuario.tipoCuenta === 'USUARIO_INSTITUCIONAL') return <ConnectDeviceEntry />;
  return <ConnectDeviceView />;
}

/** Operador: la conexión se hace dentro de la institución (el dispositivo se reconoce y se registra en SU inventario). */
export function InstitutionConnectDevicePage() {
  const { institution } = useOutletContext();
  if (institution.rolInstitucion !== 'OPERADOR') return <Navigate to=".." relative="path" replace />;
  return <ConnectDeviceView institution={institution} />;
}

/**
 * Entrada desde los enlaces «Conectar dispositivo» de todo el sistema: una cuenta institucional elige en qué institución conecta
 * (si opera en una sola, entra directo).
 */
function ConnectDeviceEntry() {
  const [institutions, setInstitutions] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    institutionsApi.getMyInstitutions().then(
      (list) => setInstitutions(list.filter((item) => item.rolInstitucion === 'OPERADOR' && item.estadoRelacion === 'ACTIVO' && item.estado === 'ACTIVA')),
      (loadError) => setError(friendlyError(loadError)),
    );
  }, []);

  if (error) return <div className="page"><Alert>{error}</Alert></div>;
  if (institutions === null) return <div className="auth-status" role="status"><span className="spinner" aria-hidden="true" /> Cargando tus instituciones…</div>;
  if (institutions.length === 1) return <Navigate to={`/app/instituciones/${institutions[0].idInstitucion}/conectar-dispositivo`} replace />;
  return (
    <div className="page connect-page">
      <PageHeader title="Conectar dispositivo" description="El dispositivo se conecta y se reconoce dentro de una institución: elegí en cuál vas a medir." />
      {institutions.length === 0 ? (
        <Alert kind="info">Solo los operadores de una institución conectan dispositivos y miden. No tenés una institución activa donde seas operador/a.</Alert>
      ) : (
        <ul className="connect-institutions">
          {institutions.map((item) => (
            <li key={item.idInstitucion}>
              <Link className="btn btn-outline" to={`/app/instituciones/${item.idInstitucion}/conectar-dispositivo`}>{item.nombre}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
