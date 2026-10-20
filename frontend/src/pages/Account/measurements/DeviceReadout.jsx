// Lectura en vivo del dispositivo: conexión Bluetooth/USB, BPM, SpO₂, glucosa experimental, índice óptico, origen, dedo y
// señal. Solo muestra lo que el backend recibió del firmware: un campo sin valor (NA) se muestra «Sin dato», nunca 0.

import { Bluetooth, Droplet, FlaskConical, Hand, HeartPulse, Signal, Target, TriangleAlert, Usb, Wind } from 'lucide-react';

import { Badge, toneFromClass } from '../../../components/Badge.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { DEMO_NOTICE, DEVICE_STATES, ORIGINS, formatIndex, formatNumber } from './measurementFormat.js';
import { SharedDeviceBanner } from './SharedDeviceBanner.jsx';

const MEDIA = { BLUETOOTH: { label: 'Bluetooth', icon: Bluetooth }, USB: { label: 'USB', icon: Usb } };

function Row({ label, children, empty, focus }) {
  return (
    <div className={focus ? 'is-focus' : undefined}>
      <dt>{label}</dt>
      <dd className={empty ? 'is-empty' : undefined}>{empty ? 'Sin dato' : children}</dd>
    </div>
  );
}

/** Aviso informativo con su ícono dentro de un círculo (un solo ícono, sin el genérico de las alertas). */
function Note({ icon: Icon, children }) {
  return (
    <div className="device-note" role="status">
      <span className="device-note-icon"><Icon size={20} aria-hidden="true" /></span>
      <p>{children}</p>
    </div>
  );
}

/** Una lectura de la vista previa: ícono, nombre y valor («Sin dato» si el firmware no lo informó, nunca 0). */
function Tile({ icon: Icon, tone, label, empty, focus, children }) {
  return (
    <div className={`sensor-tile is-${tone}${focus ? ' is-focus' : ''}`}>
      <span className="sensor-tile-icon"><Icon size={22} aria-hidden="true" /></span>
      <dt>{label}</dt>
      <dd className={empty ? 'is-empty' : undefined}>{empty ? 'Sin dato' : children}</dd>
    </div>
  );
}

export function DemoBadge() {
  return <Badge tone="warning" icon={FlaskConical} title={DEMO_NOTICE}>DEMO</Badge>;
}

/**
 * `compact`: «Vista previa del sensor» (antes de iniciar): lecturas que todavía no pertenecen a ninguna medición y no se guardan.
 * `part`: «all» (todo), «status» (solo conexión y avisos del dispositivo) o «preview» (solo avisos de la lectura y la vista previa).
 */
export function DeviceReadout({ status, focus, onRetry, compact = false, part = 'all' }) {
  if (!status) return part === 'preview' ? null : <p className="field-hint" role="status">Consultando el dispositivo…</p>;
  const state = DEVICE_STATES[status.estado] ?? DEVICE_STATES.SIN_PUENTE;
  const reading = status.lectura;
  const bridge = status.puente;
  const Medium = bridge ? (MEDIA[bridge.medio] ?? MEDIA.BLUETOOTH) : null;

  return (
    <div className={`device-readout${compact ? " sensor-preview" : ""}`}>
      {part !== 'preview' && (
      <>
      <div className={`device-banner${status.estado === 'CONECTADO' && !status.ocupado ? ' is-ok' : ''}`}>
        <p className="device-readout-state">
          <Badge tone={toneFromClass(state.tone)} icon={Medium?.icon}>{state.label}</Badge>
          {bridge && !status.ocupado && (
            <small>
              {Medium.label}{bridge.puerto ? ` · ${bridge.puerto}` : ''} · dispositivo {bridge.codigoDispositivo}
            </small>
          )}
        </p>
        <SharedDeviceBanner status={status} onRetry={onRetry} />
      </div>
      {!status.ocupado && status.estado !== 'CONECTADO' && (
        <Alert kind="info">
          {state.hint}
          {status.estado === 'PUERTO_DESCONECTADO' && bridge?.reintento > 0 && ` Reintento ${bridge.reintento}…`}
          {status.estado === 'PUERTO_DESCONECTADO' && bridge?.ultimoError && <><br /><small>{bridge.ultimoError}</small></>}
        </Alert>
      )}
      {status.avisoDispositivo?.error && <Alert>{status.avisoDispositivo.texto}</Alert>}
      </>
      )}

      {part !== 'status' && reading && (
        <>
          {reading.esDemo && <Note icon={FlaskConical}>{DEMO_NOTICE}</Note>}
          {!reading.dedo && <Note icon={Hand}>El dedo no está colocado sobre el sensor. Apoyalo sin presionar de más.</Note>}
          {reading.dedo && !reading.senalValida && <Note icon={TriangleAlert}>La señal todavía no es válida: mantené el dedo quieto.</Note>}
          {compact && (
            <>
              <h3 className="member-list-title">Vista previa del sensor</h3>
              <p className="field-hint">Estas lecturas todavía no pertenecen a ninguna medición y no se guardarán.</p>
            </>
          )}
          {compact ? (
            <dl className="sensor-tiles" aria-label="Vista previa del sensor">
              <Tile icon={HeartPulse} tone="heart" label="Frecuencia cardíaca" empty={reading.bpm === null} focus={focus === 'OXIMETRIA'}>{formatNumber(reading.bpm, 'lpm')}</Tile>
              <Tile icon={Wind} tone="lungs" label="SpO₂" empty={reading.spo2 === null} focus={focus === 'OXIMETRIA'}>{formatNumber(reading.spo2, '%')}</Tile>
              <Tile icon={Droplet} tone="glucose" label={reading.esDemo ? 'Glucosa (valor DEMO)' : 'Glucosa experimental'} empty={reading.glucosa === null} focus={focus === 'GLUCOSA_EXPERIMENTAL'}>
                {formatNumber(reading.glucosa, reading.unidadGlucosa ?? 'mg/dL')} {reading.esDemo && <DemoBadge />}
              </Tile>
              <Tile icon={Target} tone="optic" label="Índice óptico (Beer-Lambert)" empty={reading.indiceOptico === null}>{formatIndex(reading.indiceOptico)}</Tile>
              <Tile icon={Hand} tone="finger" label="Dedo">{reading.dedo ? 'Colocado' : 'No colocado'}</Tile>
              <Tile icon={Signal} tone="signal" label="Señal">{reading.senalValida ? 'Válida' : 'No válida'}</Tile>
              <Tile icon={FlaskConical} tone="origin" label="Origen de la glucosa">{ORIGINS[reading.origen] ?? reading.origen}</Tile>
            </dl>
          ) : (
            <dl className="data-list" aria-label={compact ? 'Vista previa del sensor' : 'Lectura en vivo del dispositivo'}>
              <Row label="Frecuencia cardíaca" empty={reading.bpm === null} focus={focus === 'OXIMETRIA'}>{formatNumber(reading.bpm, 'lpm')}</Row>
              <Row label="SpO₂" empty={reading.spo2 === null} focus={focus === 'OXIMETRIA'}>{formatNumber(reading.spo2, '%')}</Row>
              <Row label={reading.esDemo ? 'Glucosa (valor DEMO)' : 'Glucosa experimental'} empty={reading.glucosa === null} focus={focus === 'GLUCOSA_EXPERIMENTAL'}>
              {formatNumber(reading.glucosa, reading.unidadGlucosa ?? 'mg/dL')} {reading.esDemo && <DemoBadge />}
              </Row>
              <Row label="Índice óptico (Beer-Lambert)" empty={reading.indiceOptico === null}>{formatIndex(reading.indiceOptico)}</Row>
              <Row label="Origen de la glucosa">{ORIGINS[reading.origen] ?? reading.origen}</Row>
              <Row label="Dedo">{reading.dedo ? 'Colocado' : 'No colocado'}</Row>
              <Row label="Señal">{reading.senalValida ? 'Válida' : 'No válida'}</Row>
            </dl>
          )}
        </>
      )}
    </div>
  );
}
