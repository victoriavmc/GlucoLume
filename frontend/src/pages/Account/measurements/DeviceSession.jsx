// Monitor de una medición en curso con el dispositivo (estados B y C del flujo «Nueva medición»).
//
// Secuencia de la adquisición (se deduce SOLO de lo que informa el dispositivo; nunca se inventa ningún valor):
//   1. Esperando dedo        — «Colocá el dedo sobre el sensor.» Sin valores fisiológicos.
//   2. Detectando pulsaciones — hay dedo y señal óptica; se dibuja la onda PPG real y se marcan los latidos detectados.
//   3. Analizando señal      — ya hay frecuencia cardíaca / SpO₂ válidas; se sigue evaluando la estabilidad.
//   4. Señal estable         — 8 lecturas válidas seguidas: se habilita «Guardar medición» (siempre con confirmación de la persona).
// Si se pierde el dedo o la señal, el estado cambia de inmediato y el conteo de estabilidad lo reinicia el backend.

import {
  Activity, Ban, ChartColumn, CheckCircle2, Droplet, Hand, Heart, HeartPulse, Save, Settings, Signal, Smartphone, Sun, User, Wifi, Wind,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { Alert } from '../../../components/FormControls.jsx';
import { LiveChart } from '../../../components/LiveChart.jsx';
import { PpgChart, hasPpgSignal } from '../../../components/PpgChart.jsx';
import { Badge, OriginBadge } from '../../../components/Badge.jsx';
import { DemoBadge } from './DeviceReadout.jsx';
import { ORIGINS } from './measurementFormat.js';
import { SERIES_CAPACITY, useSessionSeries } from './useSessionSeries.js';

const ORIGIN_CODES = { DEMO: 'DEMO', EXPERIMENTAL: 'EXPERIMENTAL', SIN_CALIBRAR: 'SIN_CALIBRAR' };
const MEDIA = { BLUETOOTH: 'Bluetooth', USB: 'USB' };

const STAGE_ICONS = { INICIANDO: Activity, ESPERANDO_DEDO: Hand, DETECTANDO: Activity, ANALIZANDO: Activity, ESTABLE: CheckCircle2 };

const STAGES = {
  INICIANDO: { label: 'Iniciando adquisición', text: 'Esperando las primeras muestras nuevas del Arduino. Las lecturas anteriores a esta medición no se usan.' },
  ESPERANDO_DEDO: { label: 'Esperando dedo', text: 'Colocá el dedo sobre el sensor. Todavía no existe una señal válida.' },
  DETECTANDO: { label: 'Detectando pulsaciones…', text: 'Hay señal óptica: mantené el dedo quieto mientras se detectan las pulsaciones.' },
  ANALIZANDO: { label: 'Analizando señal', text: 'Se actualizan frecuencia cardíaca, SpO₂ e índice óptico y se evalúa la estabilidad.' },
  ESTABLE: { label: 'Señal estable', text: 'Ya hay lecturas válidas suficientes: podés guardar la medición.' },
};

/** Etapa de la adquisición según lo que informa el dispositivo y el backend (función pura, sin inventar nada). */
export function acquisitionStage(reading, stability, connected) {
  if (connected && !reading) return 'INICIANDO'; // todavía no llegó ninguna lectura posterior al inicio de la sesión
  if (!connected || !reading.dedo) return 'ESPERANDO_DEDO';
  if (stability?.estable) return 'ESTABLE';
  const hasValues = reading.senalValida && reading.bpm !== null && reading.bpm !== undefined;
  return hasValues && (stability?.lecturasValidas ?? 0) > 0 ? 'ANALIZANDO' : 'DETECTANDO';
}

function elapsedText(startedAt, now) {
  if (!startedAt) return '—';
  const total = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

/** Tarjeta de una variable: valor actual + disponibilidad + tendencia real de la sesión. `current` nulo = sin dato (nunca un cero). */
function MetricCard({ title, icon: Icon, tone, current, unit, decimals = 0, points, emptyText, availability, badge, note, secondary = false }) {
  const empty = current === null || current === undefined;
  const hasHistory = points.some((point) => point.value !== null && point.value !== undefined);
  return (
    <article className={`metric-live${secondary ? ' is-secondary' : ''}`} aria-label={title}>
      <header>
        <h4>{Icon && <span className={`metric-ico is-${tone}`}><Icon size={24} aria-hidden="true" /></span>}<span>{title}</span></h4>
        <span className="metric-head-end">{badge}</span>
      </header>
      {empty && !hasHistory ? (
        <div className="metric-empty">
          <p className="metric-live-value"><span className="is-empty">{emptyText}</span></p>
          <span className="metric-dash" aria-hidden="true">—</span>
          <p className={`metric-availability${empty ? ' is-off' : ''}`}>{availability}</p>
        </div>
      ) : (
        <>
          <p className="metric-live-value">
            {empty ? <span className="is-empty">{emptyText}</span> : <><b>{Number(current).toLocaleString('es-AR', { maximumFractionDigits: decimals })}</b> <small>{unit}</small></>}
          </p>
          <p className={`metric-availability${empty ? ' is-off' : ''}`}>{availability}</p>
          <LiveChart compact title={title} unit={unit} points={points} capacity={SERIES_CAPACITY} decimals={decimals} emptyText={emptyText} />
        </>
      )}
      {note && <p className="field-hint">{note}</p>}
    </article>
  );
}

/** Valor ACTUAL: el de la última lectura de la sesión y solo si es válida (sin dedo o con señal inválida no se muestra el anterior). */
const currentOf = (points, field) => points.at(-1)?.[field] ?? null;

export function DeviceSession({ status, profileLabel = 'Mi perfil', patient = false, onSaved, onCancelled, onWorking, handleOperationError }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [beats, setBeats] = useState(0); // latidos detectados por el firmware en esta sesión que ya cruzaron el «ahora» del gráfico
  const session = status.sesion;
  const stability = session.estabilidad;
  const connected = status.estado === 'CONECTADO';
  const ready = connected && Boolean(stability?.estable);
  // Solo cuentan las lecturas recibidas DESDE que empezó la sesión: una anterior (del dispositivo libre) nunca se atribuye a esta medición.
  const reading = status.lectura && Date.parse(status.lectura.instante) >= Date.parse(session.iniciada) ? status.lectura : null;
  const bridge = status.puente;
  const points = useSessionSeries(status);
  const ppg = session.ppg ?? null;
  // Muestras ópticas reales recibidas en la sesión (los huecos de señal no cuentan); sin señal de pulso del firmware no hay conteo.
  const samples = ppg ? ppg.inicio + ppg.valores.filter((value) => value !== null).length : null;
  // Los latidos solo se cuentan (y el corazón solo late) con dedo colocado y señal válida: sin lectura válida no se anima ningún pulso.
  const validReading = useRef(false);
  validReading.current = Boolean(connected && reading?.dedo && reading?.senalValida);
  const onBeat = useCallback(() => { if (validReading.current) setBeats((count) => count + 1); }, []);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  async function run(name, action, done) {
    if (busy) return;
    setBusy(name);
    onWorking?.(name); // el contenedor mantiene esta pantalla (y una carga) aunque el servidor ya libere la sesión antes de responder
    setError('');
    try {
      done(await action());
    } catch (actionError) {
      setError(handleOperationError(actionError));
      setBusy('');
      onWorking?.('');
    }
  }

  const save = () => run('save', acquisitionApi.saveDeviceSession, onSaved);
  const cancel = () => run('cancel', acquisitionApi.cancelDeviceSession, onCancelled);

  const hasReading = connected && reading;
  const stage = acquisitionStage(reading, stability, connected);
  // Con dedo pero sin señal válida el firmware ya detecta luz y todavía no hay pulso confiable: se dice «señal insuficiente», sin inventar nada.
  const weakSignal = stage === 'DETECTANDO' && hasReading && reading.dedo && !reading.senalValida;
  const stageInfo = weakSignal
    ? { label: 'Señal insuficiente', text: 'El dedo está colocado pero la señal todavía no es válida: mantenelo quieto, sin presionar de más.' }
    : STAGES[stage];
  const origin = reading?.origen ?? null;
  const demo = Boolean(reading?.esDemo);
  const required = stability?.lecturasRequeridas ?? 8;
  const valid = Math.min(stability?.lecturasValidas ?? 0, required);
  const bpm = currentOf(points, 'bpm');
  const glucose = currentOf(points, 'glucosa');
  const available = (value) => (value !== null ? 'Disponible' : stage === 'ESPERANDO_DEDO' ? 'Sin señal' : 'Sin dato válido todavía');

  return (
    <section className="panel measure-card live-acquisition measurement-monitor" aria-label="Sesión de medición con el dispositivo">
      <header className="monitor-head">
        <div className="monitor-title-row">
          <h3 className="monitor-title"><span className="panel-icon is-solid"><Activity size={22} aria-hidden="true" /></span> Medición en tiempo real <span className="sr-only">· en curso</span></h3>
          <span className="monitor-badges">
            {demo && hasReading && <DemoBadge />}
            <Badge tone={connected ? 'success' : 'neutral'}>{connected ? 'Conectado' : 'Sin conexión'}</Badge>
          </span>
        </div>
        <dl className="monitor-meta" aria-label="Datos de la medición en curso">
          <div><span className="meta-icon"><User size={20} aria-hidden="true" /></span><dt>{patient ? 'Paciente' : 'Perfil'}</dt><dd>{profileLabel}</dd></div>
          <div><span className="meta-icon"><Settings size={20} aria-hidden="true" /></span><dt>Modo</dt><dd>{session.modo === 'GLUCOSA_EXPERIMENTAL' ? 'Glucosa experimental' : 'Oximetría'}</dd></div>
          <div>
            <span className="meta-icon"><Smartphone size={20} aria-hidden="true" /></span>
            <dt>Dispositivo</dt>
            <dd>{bridge ? `${bridge.codigoDispositivo} · ${MEDIA[bridge.medio] ?? bridge.medio}${bridge.puerto ? ` · ${bridge.puerto}` : ''}` : 'Sin conexión'}</dd>
          </div>
        </dl>
      </header>
      <ul className="monitor-flags" aria-label="Indicadores de la adquisición">
        <li data-state={!hasReading ? 'off' : reading.dedo ? 'ok' : 'warn'}><Hand size={18} aria-hidden="true" /> Dedo: {hasReading ? (reading.dedo ? 'colocado' : 'no colocado') : 'sin dato'}</li>
        <li data-state={connected ? 'ok' : 'bad'}><Wifi size={18} aria-hidden="true" /> Conexión: {connected ? 'conectado' : 'sin conexión'}</li>
        <li data-state={!hasReading ? 'off' : reading.senalValida ? 'ok' : 'warn'}><Signal size={18} aria-hidden="true" /> Calidad de señal: {hasReading ? (reading.senalValida ? 'válida' : 'no válida') : 'sin dato'}</li>
        <li data-state={demo ? 'demo' : origin ? 'ok' : 'off'}>Origen de los datos: {origin ? (ORIGINS[origin] ?? origin) : 'sin dato'}</li>
      </ul>

      {error && <Alert>{error}</Alert>}
      {session.enlacePerdido && (
        <Alert kind="info">Se perdió la conexión con el dispositivo durante la sesión. Cuando vuelva, hacen falta nuevas lecturas válidas para guardar.</Alert>
      )}

      <div className={`monitor-stage is-${stage.toLowerCase()}`} role="status" data-stage={stage}>
        <span className="stage-icon">{(() => { const StageIcon = STAGE_ICONS[stage]; return <StageIcon size={26} aria-hidden="true" />; })()}</span>
        <div className="stage-body">
          <b>{stageInfo.label}</b>
          <span>{stageInfo.text}</span>
        </div>
      </div>

      <div className="monitor-grid">
        <MetricCard title="Frecuencia cardíaca" icon={Heart} tone="heart" current={bpm} unit="lpm" points={points.map((p) => ({ key: p.key, value: p.bpm }))}
          emptyText="Sin señal" availability={available(bpm)}
          note="Una lectura por segundo; si no se detectan pulsaciones, no se informa frecuencia." />
        <MetricCard title="SpO₂" icon={Wind} tone="lungs" current={currentOf(points, 'spo2')} unit="%" decimals={1} points={points.map((p) => ({ key: p.key, value: p.spo2 }))}
          emptyText="Sin señal" availability={available(currentOf(points, 'spo2'))} />
        <MetricCard title="Glucosa" icon={Droplet} tone="glucose" current={glucose} unit="mg/dL" decimals={1} points={points.map((p) => ({ key: p.key, value: p.glucosa }))}
          emptyText="Sin dato" availability={available(glucose)}
          badge={origin && hasReading && reading.dedo ? <OriginBadge origin={origin}>{ORIGIN_CODES[origin] ?? origin}</OriginBadge> : null}
          note={demo ? 'Valor DEMO: representa una simulación y no una glucemia real. Prueba de comunicación, no sale del dedo.'
            : origin === 'SIN_CALIBRAR' ? 'El dispositivo no está calibrado: no informa glucosa.' : origin ? 'Estimación experimental, no es un diagnóstico.' : null} />
        <MetricCard title="Índice óptico" icon={Sun} tone="optic" current={currentOf(points, 'indiceOptico')} unit="" decimals={4}
          points={points.map((p) => ({ key: p.key, value: p.indiceOptico }))} emptyText="Sin dato" availability={available(currentOf(points, 'indiceOptico'))}
          note="Indicador óptico asociado al procesamiento del sensor (Beer-Lambert); no es una magnitud clínica." />
      </div>

      <section className="ppg-panel" aria-label="Señal de pulso">
        <div className="ppg-head">
          <h4>Señal de pulso (PPG) en tiempo real</h4>
          <span className={`ppg-live${hasPpgSignal(ppg) ? ' is-on' : ''}`}>{hasPpgSignal(ppg) ? 'Señal en tiempo real' : 'Sin señal de pulso'}</span>
          <div className="beat-indicator" aria-label="Indicador de latidos detectados">
            <Heart key={beats} size={26} aria-hidden="true" className={beats > 0 ? 'is-beating' : undefined} />
            <span><b>{beats}</b> latidos detectados</span>
          </div>
        </div>
        <PpgChart ppg={ppg} onBeat={onBeat} />
        <dl className="ppg-stats" aria-label="Tiempo y muestras de la medición">
          <div><dt>Tiempo de medición</dt><dd>{elapsedText(session.iniciada, now)}</dd></div>
          <div><dt>Muestras recibidas</dt><dd>{samples === null ? '—' : samples.toLocaleString('es-AR')}</dd></div>
        </dl>
        <p className="field-hint">
          Muestras ópticas reales del sensor (infrarrojo, sin componente continua); no es un electrocardiograma. Los puntos marcan los latidos que
          detecta el dispositivo.{hasPpgSignal(ppg) ? '' : ' Si el firmware del Arduino no transmite la señal de pulso, solo se actualizan los valores de cada segundo.'}
        </p>
      </section>

      {stability && (
        <div className="monitor-progress">
          <div className="monitor-progress-head">
            <b id="estabilidad-progreso"><ChartColumn size={22} aria-hidden="true" className="metric-icon is-heart" /> Estabilidad de señal</b>
            <span><b>{valid}</b> de {required} lecturas</span>
          </div>
          <div className="stability-segments" aria-hidden="true">
            {Array.from({ length: required }, (_, index) => <span key={index} className={index < valid ? 'is-on' : undefined} />)}
          </div>
          <progress className="sr-only" value={valid} max={required} aria-labelledby="estabilidad-progreso" />
          {ready
            ? <Alert kind="success">Lectura estable. Podés guardar la medición.</Alert>
            : stability.motivo === 'GLUCOSA_NO_DISPONIBLE'
              ? <Alert kind="info">{stability.mensaje}</Alert>
              : connected && stability.mensaje && <p className="field-hint">{stability.mensaje}</p>}
        </div>
      )}


      <p className="field-hint">
        Se guarda la mediana de las últimas {required} lecturas válidas (dedo colocado, señal válida y valores que varían poco). Mantené
        el dedo quieto hasta completar las {required} lecturas; después podés retirarlo y guardar (vale durante 2 minutos).
      </p>
      <div className="form-actions">
        {confirming ? (
          <>
            <span className="field-hint">¿Cancelar la sesión? No se guardará ninguna lectura.</span>
            <button type="button" className="btn btn-ghost" disabled={Boolean(busy)} onClick={() => setConfirming(false)}>Volver</button>
            <button type="button" className="btn btn-primary" disabled={Boolean(busy)} onClick={cancel}>
              {busy === 'cancel' && <span className="spinner" aria-hidden="true" />} Confirmar cancelación
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-outline" disabled={Boolean(busy)} onClick={() => setConfirming(true)}>
              <Ban size={16} aria-hidden="true" /> Cancelar sesión
            </button>
            <button type="button" className="btn btn-primary" disabled={!ready || Boolean(busy)} onClick={save}>
              {busy === 'save' ? <span className="spinner" aria-hidden="true" /> : <Save size={16} aria-hidden="true" />} Guardar medición
            </button>
          </>
        )}
      </div>
    </section>
  );
}
