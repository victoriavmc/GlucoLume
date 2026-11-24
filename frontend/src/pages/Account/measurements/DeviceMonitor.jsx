// «Medir con el dispositivo»: estado del Bluetooth/USB, lectura en vivo (BPM, SpO₂, glucosa experimental o DEMO, índice
// óptico) y la sesión de medición. Los datos llegan del firmware por el puente serie y el backend (SSE); aquí no se
// genera nada. Perfil y dispositivo los vuelve a autorizar el backend (perfil propio, o paciente a cargo del operador).

import { PlugZap, Settings } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { Alert, SelectField, SubmitButton, TextAreaField } from '../../../components/FormControls.jsx';
import { SavingScreen } from '../../../components/SavingScreen.jsx';
import { Modal } from '../../../components/Modal.jsx';
import { NO_DATA_ERROR, STATES, browserLink, useBrowserLink } from '../../../utils/browserSerialLink.js';
import { useDeviceReadiness } from '../acquisition/useDeviceReadiness.js';
import { DeviceReadout } from './DeviceReadout.jsx';
import { DeviceSession } from './DeviceSession.jsx';
import { MEALS } from './measurementFormat.js';
import { OptionalMeasurementContext, initialMeasurementContext, measurementContextError, measurementContextPayload } from './OptionalMeasurementContext.jsx';
import { useDeviceStatus } from './useDeviceStatus.js';

// Modo de medición: lo elige la persona y se conserva hasta el historial y el detalle. Ambos guardan todas las lecturas válidas de la sesión
// (SpO₂, frecuencia cardíaca, índice óptico y la glucosa que informe el dispositivo con su origen). En modo glucosa, además, el resultado de
// glucosa es obligatorio para poder guardar (DEMO o experimental calibrado); el servidor no estima ni sustituye el modo.
const FOCUS_MODES = {
  OXIMETRIA: 'Oximetría',
  GLUCOSA_EXPERIMENTAL: 'Glucosa experimental',
};

// Cada cuánto se reintenta la reconexión automática mientras el Arduino no esté conectado.
const AUTO_CONNECT_MS = 5000;

const MEDIUM_LABEL = { USB: 'USB', BLUETOOTH: 'Bluetooth' };

/** Conectar el Arduino desde la propia medición (sin pantalla aparte). Un solo botón: el selector del navegador muestra USB y Bluetooth, y el medio
 * se reconoce del puerto elegido. El clic es obligatorio: el navegador pide elegir el puerto la primera vez; después «Nueva medición» lo reconecta sola. */
function ConnectArduino() {
  const link = useBrowserLink();
  const busy = link.estado === STATES.CONNECTING;
  const noData = link.error === NO_DATA_ERROR;
  // Una sola ventana por error: se descarta al cerrarla y vuelve a abrirse solo si aparece un error nuevo.
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => { if (!noData) setDismissed(false); }, [noData]);
  return (
    <div className="connect-arduino">
      <div className="form-actions">
        <button type="button" className="btn btn-outline" disabled={busy} onClick={() => link.connect()}>
          <PlugZap size={16} aria-hidden="true" /> Conectar con el dispositivo
        </button>
      </div>
      {noData && !dismissed && (
        <Modal
          title="El dispositivo no está enviando datos"
          onClose={() => setDismissed(true)}
          actions={(
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setDismissed(true)}>Cerrar</button>
              <button type="button" className="btn btn-primary" onClick={() => { setDismissed(true); link.connect(); }}>Reintentar</button>
            </>
          )}
        >
          <p>{NO_DATA_ERROR}</p>
        </Modal>
      )}
      {link.estado === STATES.CONNECTED && link.verificado && link.medio && (
        <p className="field-hint" role="status">Arduino reconocido por {MEDIUM_LABEL[link.medio]}.</p>
      )}
      {link.estado === STATES.CONNECTING && link.medio && (
        <p className="field-hint" role="status">Puerto {MEDIUM_LABEL[link.medio]} abierto. Esperando datos del Arduino…</p>
      )}
      {!link.supported && <p className="field-hint">Para conectar el Arduino sin instalar nada usá Chrome o Edge en una computadora.</p>}
      {link.error && !noData && <p className="field-error" role="alert">{link.error}</p>}
    </div>
  );
}

function StartForm({ status, idPerfilMedicion, idInstitucion, profile, patient, extraOptions, focus, onFocus, handleOperationError, onStarted }) {
  const [devices, setDevices] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState('');
  const [selected, setSelected] = useState('');
  const [condicionComida, setCondicionComida] = useState('NO_INFORMADA');
  const [matrix, setMatrix] = useState(undefined); // undefined: sin consultar · null: no hay matriz aplicable
  const [observation, setObservation] = useState('');
  const [context, setContext] = useState(() => initialMeasurementContext(profile)); // edad y sexo opcionales de esta medición
  const [error, setError] = useState('');
  const [contextError, setContextError] = useState('');
  const [saving, setSaving] = useState(false);
  const code = status.puente?.codigoDispositivo ?? '';
  // Diagnóstico del backend (puerto, identidad, sensor, asociación): única fuente de «listo para medir».
  const { readiness, refresh: refreshReadiness } = useDeviceReadiness(idPerfilMedicion, status, idInstitucion);

  const loadDevices = () => measurementsApi.listDevices(idPerfilMedicion).then(
    (list) => setDevices(list),
    (loadError) => { setDevices([]); setError(handleOperationError(loadError)); },
  );

  useEffect(() => {
    let active = true;
    measurementsApi.listDevices(idPerfilMedicion).then(
      (list) => active && setDevices(list),
      (loadError) => { if (active) { setDevices([]); setError(handleOperationError(loadError)); } },
    );
    return () => { active = false; };
  }, [idPerfilMedicion, handleOperationError]);

  // Cuenta individual: conecta el dispositivo de prueba (el backend decide si hace falta crear uno nuevo).
  async function connectTestDevice() {
    setConnecting(true);
    setConnectError('');
    try {
      await acquisitionApi.connectTestDevice();
      await loadDevices();
      refreshReadiness();
    } catch (failure) {
      setConnectError(handleOperationError(failure));
    } finally {
      setConnecting(false);
    }
  }

  // La matriz la decide el backend: solo se muestra, nunca se elige ni se envía.
  const glucoseMode = focus === 'GLUCOSA_EXPERIMENTAL';
  useEffect(() => {
    if (!glucoseMode) return undefined;
    let active = true;
    measurementsApi.getMatrixPreview(idPerfilMedicion).then(
      (result) => active && setMatrix(result),
      () => active && setMatrix(undefined),
    );
    return () => { active = false; };
  }, [glucoseMode, idPerfilMedicion]);

  // Solo se puede medir con el dispositivo que atiende el puente; el backend lo vuelve a comprobar.
  const online = status.estado === 'CONECTADO';
  // Cuenta individual: la lista trae SU dispositivo vinculado; conectado el puente, ese es el que se usa (la confirmación de «Conectar»
  // y la comprobación de «listo» del backend lo validan). Institución: se compara el código que atiende el puente.
  const individual = !idInstitucion;
  // Cuenta individual: solo cuenta como conectado si el backend lo confirma (readiness.dispositivo es el vinculado y confirmado).
  const confirmedOwn = individual && online && devices?.[0] && readiness?.dispositivo?.idDispositivo === devices[0].idDispositivo;
  const connected = devices?.find((item) => item.codigoDispositivo.toLowerCase() === code.toLowerCase())
    ?? (confirmedOwn ? devices[0] : undefined);
  const device = devices?.find((item) => item.idDispositivo === selected) ?? connected ?? (devices?.length === 1 ? devices[0] : undefined);
  const isConnectedOne = Boolean(device && connected && device.idDispositivo === connected.idDispositivo);
  const unavailable = online && !individual && !connected; // el puente atiende un dispositivo que no figura para este perfil (institución)
  // Con un dispositivo identificado solo (el conectado o el único del inventario) no se muestra un selector: solo se informa cuál es.
  const pickable = !connected && (devices?.length ?? 0) > 1;

  // Cuenta individual, un solo toque: apenas el Arduino queda conectado, se confirma con la cuenta sin otro botón. Si el puente todavía no
  // está listo, reintenta sola (en silencio) cuando se actualiza el diagnóstico; se detiene al confirmar o tras varios intentos.
  const autoConfirm = useRef({ code: '', attempts: 0, done: false });
  useEffect(() => {
    if (!online) {
      autoConfirm.current = { code: '', attempts: 0, done: false };
      return;
    }
    const state = autoConfirm.current;
    if (!individual || patient || !code || state.done) return;
    if (state.code !== code) autoConfirm.current = { code, attempts: 0, done: false };
    const current = autoConfirm.current;
    if (current.attempts >= 6) return;
    current.attempts += 1;
    acquisitionApi.connectTestDevice().then(
      () => {
        autoConfirm.current.done = true;
        loadDevices();
        refreshReadiness();
      },
      () => {},
    );
  }, [online, individual, patient, code, readiness]); // eslint-disable-line react-hooks/exhaustive-deps

  async function start(event) {
    event.preventDefault();
    if (saving || !device) return;
    const invalidAge = measurementContextError(context); // solo una edad inválida; vacío nunca bloquea
    if (invalidAge) {
      setContextError(invalidAge);
      return;
    }
    setContextError('');
    setSaving(true);
    setError('');
    try {
      onStarted(await acquisitionApi.startDeviceSession({
        idPerfilMedicion, idDispositivo: device.idDispositivo, condicionComida,
        modoMedicion: focus,
        observacion: observation.trim() || undefined,
        ...measurementContextPayload(context, profile),
      }));
    } catch (startError) {
      setError(handleOperationError(startError));
      refreshReadiness(); // p. ej. la identidad del Arduino no estaba confirmada: el estado se actualiza con el motivo real
    } finally {
      setSaving(false);
    }
  }

  const suggested = initialMeasurementContext(profile);
  const missingContext = suggested.edad === '' || suggested.sexo === '';
  return (
    <form className="measure-form" onSubmit={start} noValidate aria-label="Iniciar sesión de medición con el dispositivo">
      <section className="panel measure-card" aria-labelledby="sesion-config">
        <div className="panel-title">
          <span className="panel-icon is-solid"><Settings size={22} aria-hidden="true" /></span>
          <h3 id="sesion-config">Configuración de la medición</h3>
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        {devices === null ? (
          <p className="field-hint" role="status">Buscando el dispositivo en tu inventario…</p>
        ) : !device || unavailable ? (
          // No bloquea el formulario: tipo de medición, alimentación y datos opcionales se completan igual; solo falta el dispositivo para iniciar.
          // En «Nueva medición» (cuenta propia) el aviso de dispositivo conectado no aparece nunca; solo en la medición de un paciente.
          online && !individual
            ? (patient && (
              <Alert kind="info">
                El dispositivo conectado ({code}) no está disponible para medir este perfil. Tiene que estar dado de alta como operativo
                en Dispositivos y asignado a quien mide.
              </Alert>
            ))
            : (
              <>
                {individual && online
                  ? <Alert kind="info">Todavía no tenés un dispositivo vinculado a tu cuenta: conectá el Arduino y registralo.</Alert>
                  : <Alert kind="info">No hay un dispositivo operativo disponible para medir este perfil ahora.</Alert>}
                {!patient && online && (
                  <div className="form-actions">
                    <button type="button" className="btn btn-outline" disabled={connecting} onClick={connectTestDevice}>
                      <PlugZap size={16} aria-hidden="true" /> Conectar dispositivo de prueba
                    </button>
                  </div>
                )}
                {connectError && <p className="field-error" role="alert">{connectError}</p>}
              </>
            )
        ) : null}
        <>
            <div className="form-grid is-config">
              {device && (pickable ? (
                <SelectField label="Dispositivo" value={device.idDispositivo} onChange={(event) => setSelected(event.target.value)}
                  hint="Hay más de un dispositivo en tu inventario: elegí cuál vas a usar."
                  options={devices.map((item) => ({ value: item.idDispositivo, label: [item.nombre, item.codigoDispositivo].filter(Boolean).join(' · ') }))} />
              ) : null)}
              <SelectField label="Modo de medición" value={focus} onChange={(event) => onFocus(event.target.value)}
                options={Object.entries(FOCUS_MODES).map(([key, label]) => ({ value: key, label }))} />
              <SelectField label="Alimentación" value={condicionComida} onChange={(event) => setCondicionComida(event.target.value)}
                options={Object.entries(MEALS).map(([key, label]) => ({ value: key, label }))} />
            </div>
            {glucoseMode && (
              <details className="optional-details">
                <summary>Matriz de referencia <small>({matrix ? matrix.nombre : 'sin matriz activa'})</small></summary>
                <Alert kind="info">
                  {matrix ? (
                    <>
                      Matriz que se aplicará (la elige el sistema, no se puede cambiar): <b>{matrix.nombre}, versión {matrix.version}</b>
                      {' '}· {matrix.ambito === 'INSTITUCION' ? 'Institucional' : 'Global de GlucoLume'}.
                    </>
                  ) : matrix === null ? (
                    <>Hoy no hay una matriz activa y vigente para estimar glucosa, así que esta medición no se puede iniciar.</>
                  ) : null}{' '}
                  Este modo elige su regla de referencia según la edad y el sexo: sin esos datos no se puede estimar (no se inventan). La oximetría
                  no los necesita. No es un diagnóstico.
                </Alert>
              </details>
            )}
            {/* Con edad y sexo ya registrados el bloque queda plegado: no se vuelve a pedir lo que existe; si falta algo, se abre. */}
            <details className="optional-details" open={missingContext || Boolean(contextError)}>
              <summary>Datos opcionales de esta medición <small>(edad, sexo y observaciones)</small></summary>
              <OptionalMeasurementContext profile={profile} patient={patient} value={context} onChange={setContext} idPrefix="sesion" error={contextError}>
                <TextAreaField label="Observaciones (opcional)" rows={3} maxLength={500} value={observation}
                  placeholder="Escribí aquí si querés agregar alguna nota sobre esta medición…" onChange={(event) => setObservation(event.target.value)} />
              </OptionalMeasurementContext>
            </details>
            {extraOptions}
            <div className="measure-footer">
              <div className="form-actions">
                <SubmitButton loading={saving} loadingLabel="Iniciando…" className="btn btn-primary btn-lg"
                  disabled={!online || !isConnectedOne || Boolean(readiness && !readiness.listo)}>Iniciar medición</SubmitButton>
                {!online && <ConnectArduino />}
              </div>
            </div>
        </>
      </section>
    </form>
  );
}

/** Pantalla de medición (cuenta individual y paciente institucional): configuración → lectura en tiempo real → resultado. */
export function DeviceMonitor({ idPerfilMedicion, idInstitucion, profileLabel, profile = null, patient = false, extraOptions = null, savingSteps = [], handleOperationError, onSaved, onCancelled, autoConnect = false }) {
  const { status, error, refresh } = useDeviceStatus();
  const [focus, setFocus] = useState('OXIMETRIA');
  // Cuenta propia: mientras no haya conexión, se reconecta sola al último Arduino usado (sin pedir el puerto de nuevo). Reintenta cada pocos
  // segundos y también al enchufar el Arduino, así que no hace falta tocar nada si el puerto ya se eligió una vez.
  const link = useBrowserLink();
  const linked = status?.estado === 'CONECTADO' || link.estado === STATES.CONNECTED;
  const occupied = Boolean(status?.ocupado);
  // Al cambiar el enlace del navegador (conectó, confirmó el Arduino o se cortó), se pide el estado sin esperar al próximo sondeo.
  useEffect(() => { refresh(); }, [link.estado, link.verificado, link.puerto, refresh]);
  useEffect(() => {
    if (!autoConnect || linked || occupied) return undefined;
    const tryConnect = () => { browserLink.autoConnect(); };
    tryConnect();
    const timer = setInterval(tryConnect, AUTO_CONNECT_MS);
    const serial = typeof navigator !== 'undefined' ? navigator.serial : undefined;
    serial?.addEventListener?.('connect', tryConnect);
    return () => {
      clearInterval(timer);
      serial?.removeEventListener?.('connect', tryConnect);
    };
  }, [autoConnect, linked, occupied]);
  const inSession = Boolean(status && !status.ocupado && status.sesion);
  // Guardar o cancelar: el servidor libera la sesión ANTES de responder (y al guardar también envía el resultado por correo), así que el estado
  // del dispositivo ya dice «sin sesión» mientras la respuesta tarda. Se conserva la última sesión y una pantalla de carga hasta que responda,
  // en vez de volver un momento al formulario.
  const [working, setWorking] = useState('');
  const lastSession = useRef(null);
  if (inSession) lastSession.current = status;
  const sessionStatus = inSession ? status : (working ? lastSession.current : null);

  if (sessionStatus) {
    // Estados B y C: el panel de monitoreo reemplaza al formulario (los datos opcionales ya quedaron fijados al iniciar).
    return (
      <section className="measure-flow" aria-label="Medición con el dispositivo">
        {error && <p className="field-error" role="alert">{error}</p>}
        <DeviceSession status={sessionStatus} profileLabel={profileLabel} patient={patient} handleOperationError={handleOperationError}
          onWorking={setWorking}
          onSaved={(detail) => { setWorking(''); refresh(); onSaved?.(detail); }} onCancelled={(detail) => { setWorking(''); refresh(); onCancelled?.(detail); }} />
        {working === 'save' && <SavingScreen title="Guardando la medición…" steps={['Registrando los resultados', ...savingSteps]} />}
        {working === 'cancel' && <SavingScreen title="Cancelando la medición…" note="Un momento: liberamos el dispositivo." />}
      </section>
    );
  }
  return (
    <section className="measure-flow" aria-labelledby="medir-dispositivo">
      <h2 id="medir-dispositivo" className="sr-only">Nueva medición</h2>
      {error && <p className="field-error" role="alert">{error}</p>}
      {!status && <p className="field-hint" role="status">Consultando el dispositivo…</p>}
      {status?.ocupado && (
        <section className="panel measure-card" aria-label="Dispositivo en uso">
          <DeviceReadout status={status} onRetry={refresh} part="status" />
        </section>
      )}
      {/* Antes de iniciar solo hay configuración y estado del dispositivo: la «Medición en tiempo real» aparece con la sesión. */}
      {status && !status.ocupado && (
        <StartForm status={status} idPerfilMedicion={idPerfilMedicion} idInstitucion={idInstitucion} profile={profile} patient={patient} extraOptions={extraOptions}
          focus={focus} onFocus={setFocus} handleOperationError={handleOperationError} onStarted={refresh} />
      )}
    </section>
  );
}
