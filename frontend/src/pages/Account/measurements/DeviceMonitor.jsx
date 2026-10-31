// «Medir con el dispositivo»: estado del Bluetooth/USB, lectura en vivo (BPM, SpO₂, glucosa experimental o DEMO, índice
// óptico) y la sesión de medición. Los datos llegan del firmware por el puente serie y el backend (SSE); aquí no se
// genera nada. Perfil y dispositivo los vuelve a autorizar el backend (perfil propio, o paciente a cargo del operador).

import { PlugZap, Settings } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import * as measurementsApi from '../../../api/measurementsApi.js';
import { Alert, SelectField, SubmitButton, TextAreaField, TextField } from '../../../components/FormControls.jsx';
import { SavingScreen } from '../../../components/SavingScreen.jsx';
import { useDeviceReadiness } from '../acquisition/useDeviceReadiness.js';
import { DeviceReadout } from './DeviceReadout.jsx';
import { DeviceStatusChecks } from './DeviceStatusChecks.jsx';
import { DeviceSession } from './DeviceSession.jsx';
import { MEALS, dateTimeForApi } from './measurementFormat.js';
import { OptionalMeasurementContext, initialMeasurementContext, measurementContextError, measurementContextPayload } from './OptionalMeasurementContext.jsx';
import { useDeviceStatus } from './useDeviceStatus.js';

// Modo de medición: lo elige la persona y se conserva hasta el historial y el detalle. Ambos guardan todas las lecturas válidas de la sesión
// (SpO₂, frecuencia cardíaca, índice óptico y la glucosa que informe el dispositivo con su origen). En modo glucosa, además, el resultado de
// glucosa es obligatorio para poder guardar (DEMO o experimental calibrado); el servidor no estima ni sustituye el modo.
const FOCUS_MODES = {
  OXIMETRIA: 'Oximetría',
  GLUCOSA_EXPERIMENTAL: 'Glucosa experimental',
};

function StartForm({ status, idPerfilMedicion, idInstitucion, profile, patient, extraOptions, focus, onFocus, handleOperationError, onStarted }) {
  const [devices, setDevices] = useState(null);
  const [selected, setSelected] = useState('');
  const [condicionComida, setCondicionComida] = useState('NO_INFORMADA');
  const [lastMeal, setLastMeal] = useState('');
  const [mealError, setMealError] = useState('');
  const [matrix, setMatrix] = useState(undefined); // undefined: sin consultar · null: no hay matriz aplicable
  const [observation, setObservation] = useState('');
  const [context, setContext] = useState(() => initialMeasurementContext(profile)); // edad y sexo opcionales de esta medición
  const [error, setError] = useState('');
  const [contextError, setContextError] = useState('');
  const [saving, setSaving] = useState(false);
  const code = status.puente?.codigoDispositivo ?? '';
  // Diagnóstico del backend (puerto, identidad, sensor, asociación): única fuente de «listo para medir».
  const { readiness, refresh: refreshReadiness } = useDeviceReadiness(idPerfilMedicion, status, idInstitucion);

  useEffect(() => {
    let active = true;
    measurementsApi.listDevices(idPerfilMedicion).then(
      (list) => active && setDevices(list),
      (loadError) => { if (active) { setDevices([]); setError(handleOperationError(loadError)); } },
    );
    return () => { active = false; };
  }, [idPerfilMedicion, handleOperationError]);

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
  const connected = devices?.find((item) => item.codigoDispositivo.toLowerCase() === code.toLowerCase());
  const device = devices?.find((item) => item.idDispositivo === selected) ?? connected ?? (devices?.length === 1 ? devices[0] : undefined);
  const isConnectedOne = Boolean(device && connected && device.idDispositivo === connected.idDispositivo);
  const online = status.estado === 'CONECTADO';
  const unavailable = online && !connected; // el puente atiende un dispositivo que no figura para este perfil

  async function start(event) {
    event.preventDefault();
    if (saving || !device) return;
    const invalidAge = measurementContextError(context); // solo una edad inválida; vacío nunca bloquea
    if (invalidAge) {
      setContextError(invalidAge);
      return;
    }
    setContextError('');
    setMealError(''); // «Última comida» es opcional en todos los modos: vacío nunca bloquea (ni con «Después de comer»)
    setSaving(true);
    setError('');
    try {
      onStarted(await acquisitionApi.startDeviceSession({
        idPerfilMedicion, idDispositivo: device.idDispositivo, condicionComida,
        modoMedicion: focus,
        observacion: observation.trim() || undefined,
        fechaHoraUltimaComida: glucoseMode ? dateTimeForApi(lastMeal) : undefined,
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
        {error && <Alert>{error}</Alert>}
        <DeviceStatusChecks status={status} readiness={readiness} />
        {devices === null ? (
          <p className="field-hint" role="status">Buscando el dispositivo en tu inventario…</p>
        ) : !device || unavailable ? (
          <Alert kind="info">
            {online
              ? <>El dispositivo conectado ({code}) no está disponible para medir este perfil. Tiene que estar dado de alta como operativo
                en Dispositivos y asignado a quien mide.</>
              : <>No hay un dispositivo operativo disponible para medir este perfil ahora.</>}
          </Alert>
        ) : (
          <>
            <div className="form-grid is-config">
              <SelectField label="Dispositivo" value={device.idDispositivo} onChange={(event) => setSelected(event.target.value)}
                hint={online && !isConnectedOne ? `El dispositivo conectado es ${code}: elegí ese para medir.` : undefined}
                options={devices.map((item) => ({ value: item.idDispositivo, label: [item.nombre, item.codigoDispositivo].filter(Boolean).join(' · ') }))} />
              <SelectField label="Modo de medición" value={focus} onChange={(event) => onFocus(event.target.value)}
                options={Object.entries(FOCUS_MODES).map(([key, label]) => ({ value: key, label }))}
                hint={focus === 'GLUCOSA_EXPERIMENTAL'
                  ? 'Se guarda como Glucosa experimental. Para guardarla el dispositivo debe informar un valor de glucosa (DEMO o experimental calibrado); no se cambia a Oximetría en silencio.'
                  : 'Se guarda como Oximetría, junto con todas las lecturas válidas de la sesión.'} />
              <SelectField label="Alimentación" value={condicionComida} onChange={(event) => setCondicionComida(event.target.value)}
                options={Object.entries(MEALS).map(([key, label]) => ({ value: key, label }))} />
              {glucoseMode && ( // solo la glucosa usa la hora de la última comida
                <TextField label="Inicio de la última comida (opcional)" type="datetime-local" value={lastMeal} error={mealError || undefined}
                  hint={condicionComida === 'POSTPRANDIAL' && !lastMeal
                    ? 'Sin la hora de la última comida no se puede comparar con la matriz «después de comer»; se miden igual SpO₂, frecuencia cardíaca y glucosa.'
                    : 'Si la dejás vacía se guarda como «Sin informar».'}
                  onChange={(event) => { setLastMeal(event.target.value); setMealError(''); }} />
              )}
            </div>
            {glucoseMode && (
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
              <p className="field-hint">
                La adquisición empieza recién cuando pulsás «Iniciar medición». Las lecturas anteriores no se atribuyen a esta medición:
                solo cuentan las que lleguen desde que inicies.
              </p>
              <div className="form-actions">
                <SubmitButton loading={saving} loadingLabel="Iniciando…" className="btn btn-primary btn-lg"
                  disabled={!online || !isConnectedOne || Boolean(readiness && !readiness.listo)}>Iniciar medición</SubmitButton>
                {!online && (
                  <Link to="/app/conectar-dispositivo" className="btn btn-outline"><PlugZap size={16} aria-hidden="true" /> Conectar dispositivo</Link>
                )}
              </div>
            </div>
          </>
        )}
      </section>
    </form>
  );
}

/** Pantalla de medición (cuenta individual y paciente institucional): configuración → lectura en tiempo real → resultado. */
export function DeviceMonitor({ idPerfilMedicion, idInstitucion, profileLabel, profile = null, patient = false, extraOptions = null, savingSteps = [], handleOperationError, onSaved, onCancelled }) {
  const { status, error, refresh } = useDeviceStatus();
  const [focus, setFocus] = useState('OXIMETRIA');
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
        {error && <Alert>{error}</Alert>}
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
      {error && <Alert>{error}</Alert>}
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
