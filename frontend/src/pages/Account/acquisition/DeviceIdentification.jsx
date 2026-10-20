// «Dispositivo de esta conexión»: el operador, dentro de su institución, ve qué Arduino hay conectado y lo reconoce, registra o vincula.
// Todo sale del diagnóstico del backend (`readiness.identificacion`); acá solo se presenta y se piden las acciones permitidas:
//   - «Registrar nuevo dispositivo»: el Arduino todavía no está en ningún inventario; solo se pide un nombre;
//   - «Vincular a la institución»: el dispositivo existe pero no pertenece a ninguna institución; pasa a la de la persona SOLO con una
//     confirmación explícita (deja de estar disponible para las cuentas individuales; sus mediciones anteriores se conservan);
//   - «Confirmar dispositivo»: uno que ya es del inventario de la institución (firmware sin ID propio: se elige a mano cuál es).
// Con firmware sin ID propio nada prueba qué Arduino es: registrar o vincular exige además confirmar que el Arduino conectado es ese.
// Un dispositivo de otra institución no se ofrece ni se transfiere. El paciente no se asocia acá: se elige al iniciar la medición.

import { Cpu, Info, Link2 } from 'lucide-react';
import { useState } from 'react';

import * as acquisitionApi from '../../../api/acquisitionApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { Badge } from '../../../components/Badge.jsx';
import { Alert, SubmitButton } from '../../../components/FormControls.jsx';
import { DEVICE_STATES } from '../devices/deviceFormat.js';

const MEDIA = { BLUETOOTH: 'Bluetooth', USB: 'USB' };

function Facts({ identification, device }) {
  return (
    <dl className="data-list identification-facts">
      <div><dt>Institución</dt><dd>{identification.institucion.nombre}</dd></div>
      {device && <div><dt>Estado administrativo</dt><dd>{DEVICE_STATES[device.estado] ?? device.estado}</dd></div>}
      <div><dt>Identificador del Arduino</dt><dd><code>{identification.codigo}</code></dd></div>
      {(device?.versionFirmware || identification.firmware) && <div><dt>Firmware</dt><dd>{identification.firmware ?? device.versionFirmware}</dd></div>}
      {identification.medio && <div><dt>Conexión de esta sesión</dt><dd>{MEDIA[identification.medio] ?? identification.medio}</dd></div>}
    </dl>
  );
}

function Confirm({ id, checked, onChange, children }) {
  return (
    <label className="check identification-confirm" htmlFor={id}>
      <input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

function RegisterNew({ identification, onDone }) {
  const unverified = identification.requiereConfirmacion;
  const [name, setName] = useState('');
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await acquisitionApi.registerConnectedDevice({
        idInstitucion: identification.institucion.idInstitucion, nombre: name.trim(), ...(unverified ? { confirmaIdentidad: true } : {}),
      });
      onDone(result);
    } catch (registerError) {
      setError(friendlyError(registerError));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Registrar nuevo dispositivo">
      <Alert kind="info">
        Es un dispositivo nuevo: todavía no está en el inventario de {identification.institucion.nombre}. Al registrarlo queda en el inventario de
        la institución, a cargo de su propietario/a; vos no lo adquirís ni quedás como responsable. No hace falta pedirle que lo cargue a mano.
      </Alert>
      {error && <Alert>{error}</Alert>}
      <Facts identification={identification} device={null} />
      <div className="field">
        <label className="field-label" htmlFor="registro-nombre">Nombre del dispositivo</label>
        <input id="registro-nombre" className="field-input" maxLength={100} autoComplete="off" value={name} placeholder="Por ejemplo: Arduino Consultorio 1"
          onChange={(event) => setName(event.target.value)} />
        <p className="field-hint">Un nombre que lo identifique en el consultorio. El código, el sensor y el firmware los informa el propio Arduino. Podés cambiarlo después desde el inventario.</p>
      </div>
      {unverified && (
        <Confirm id="registro-confirma" checked={sure} onChange={setSure}>
          Confirmo que el Arduino conectado ahora es el que quiero registrar (este firmware no informa un identificador propio).
        </Confirm>
      )}
      <div className="form-actions">
        <SubmitButton loading={busy} loadingLabel="Registrando…" className="btn btn-primary" disabled={!name.trim() || (unverified && !sure)}>
          <Cpu size={16} aria-hidden="true" /> Registrar nuevo dispositivo
        </SubmitButton>
      </div>
    </form>
  );
}

/** Dispositivo existente sin institución (`device`): se vincula con confirmación explícita. */
function LinkExisting({ identification, device, onDone }) {
  const unverified = identification.requiereConfirmacion;
  const [name, setName] = useState('');
  const [sure, setSure] = useState(false);
  const [sureIdentity, setSureIdentity] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const institution = identification.institucion.nombre;

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      onDone(await acquisitionApi.linkConnectedDevice({
        idInstitucion: identification.institucion.idInstitucion, idDispositivo: device.idDispositivo, nombre: name.trim(),
        confirmaVinculacion: true, ...(unverified ? { confirmaIdentidad: true } : {}),
      }));
    } catch (linkError) {
      setError(friendlyError(linkError));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Vincular a la institución">
      <Alert kind="info">
        «{device.nombre || device.codigoDispositivo}» ya existe en GlucoLume, pero no pertenece a ninguna institución (por ejemplo, lo dio de alta el puente o lo
        usó una cuenta individual). Para medir pacientes de {institution} tiene que estar en su inventario.
      </Alert>
      {error && <Alert>{error}</Alert>}
      <Facts identification={identification} device={device} />
      <div className="field">
        <label className="field-label" htmlFor="vinculo-nombre">Nombre del dispositivo (opcional)</label>
        <input id="vinculo-nombre" className="field-input" maxLength={100} autoComplete="off" value={name} placeholder={device.nombre ?? 'Por ejemplo: Arduino Consultorio 1'}
          onChange={(event) => setName(event.target.value)} />
        <p className="field-hint">Si lo dejás vacío se conserva el nombre actual.</p>
      </div>
      <Confirm id="vinculo-confirma" checked={sure} onChange={setSure}>
        Confirmo que quiero vincular este dispositivo a {institution}: pasa al inventario de la institución, a cargo de su propietario/a, y deja de estar disponible
        para las cuentas individuales. Sus mediciones anteriores se conservan.
      </Confirm>
      {unverified && (
        <Confirm id="vinculo-identidad" checked={sureIdentity} onChange={setSureIdentity}>
          Confirmo que el Arduino conectado ahora es este dispositivo (este firmware no informa un identificador propio).
        </Confirm>
      )}
      <div className="form-actions">
        <SubmitButton loading={busy} loadingLabel="Vinculando…" className="btn btn-primary" disabled={!sure || (unverified && !sureIdentity)}>
          <Link2 size={16} aria-hidden="true" /> Vincular a la institución
        </SubmitButton>
      </div>
    </form>
  );
}

function ConfirmExisting({ identification, onDone }) {
  const candidates = identification.candidatos ?? [];
  const suggested = candidates.find((item) => item.sugerido)?.idDispositivo ?? '';
  const [chosen, setChosen] = useState(suggested);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function confirm(event) {
    event.preventDefault();
    if (busy || !chosen) return;
    setBusy(true);
    setError('');
    try {
      onDone(await acquisitionApi.confirmConnectedDevice({ idInstitucion: identification.institucion.idInstitucion, idDispositivo: chosen }));
    } catch (confirmError) {
      setError(friendlyError(confirmError));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={confirm} noValidate aria-label="Confirmar dispositivo">
      {error && <Alert>{error}</Alert>}
      {candidates.length === 0 ? (
        <p className="field-hint">No hay dispositivos de {identification.institucion.nombre} que puedas usar para confirmar.</p>
      ) : (
        <div className="field">
          <label className="field-label" htmlFor="confirmar-dispositivo">Dispositivo de la institución</label>
          <select id="confirmar-dispositivo" className="field-input field-select" value={chosen} onChange={(event) => setChosen(event.target.value)}>
            <option value="">Elegí un dispositivo</option>
            {candidates.map((item) => (
              <option key={item.idDispositivo} value={item.idDispositivo}>
                {item.nombre ? `${item.nombre} (${item.codigoDispositivo})` : item.codigoDispositivo}{item.sugerido ? ' — coincide con el código del puente' : ''}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="form-actions">
        <SubmitButton loading={busy} loadingLabel="Confirmando…" className="btn btn-primary" disabled={!chosen}>Confirmar dispositivo</SubmitButton>
      </div>
    </form>
  );
}

/** Firmware sin ID propio: nada prueba qué Arduino es, así que cada opción pide confirmarlo explícitamente. */
function Unverified({ identification, onDone }) {
  return (
    <>
      <Alert kind="info">
        No se pudo confirmar qué Arduino es: este firmware no informa un identificador propio, y el puerto, el medio o la velocidad no alcanzan
        para saberlo. Elegí qué querés hacer y confirmá que el Arduino conectado es ese dispositivo. Para identificarlo automáticamente, cargá el firmware actualizado.
      </Alert>
      {identification.candidatos?.length > 0 && (
        <>
          <h3 className="identification-option">Es un dispositivo de la institución</h3>
          <ConfirmExisting identification={identification} onDone={onDone} />
        </>
      )}
      {identification.puedeVincular && identification.dispositivoDeclarado && (
        <>
          <h3 className="identification-option">Es el dispositivo sin institución que informa el puente</h3>
          <LinkExisting identification={identification} device={identification.dispositivoDeclarado} onDone={onDone} />
        </>
      )}
      {identification.puedeRegistrar && (
        <>
          <h3 className="identification-option">Es un dispositivo nuevo</h3>
          <RegisterNew identification={identification} onDone={onDone} />
        </>
      )}
      {!identification.candidatos?.length && !identification.puedeVincular && !identification.puedeRegistrar && (
        <p className="field-hint">No hay dispositivos de {identification.institucion.nombre} que puedas usar. Pedí al propietario/a que lo registre desde el inventario de dispositivos.</p>
      )}
    </>
  );
}

export function DeviceIdentification({ identification, onChanged }) {
  const [notice, setNotice] = useState('');
  if (!identification) return null;
  const { situacion, dispositivo: device } = identification;

  function done(result) {
    const label = result.identificacion.dispositivo?.nombre ?? result.identificacion.dispositivo?.codigoDispositivo ?? result.identificacion.codigo;
    if (result.creado) setNotice(`Registramos «${label}» en ${identification.institucion.nombre}.`);
    else if (result.vinculado) setNotice(`Vinculamos «${label}» a ${identification.institucion.nombre}: ya figura en su inventario.`);
    else setNotice('Dispositivo reconocido.');
    onChanged?.(result);
  }

  let body;
  if (situacion === 'SIN_COMUNICACION') {
    body = (
      <p className="field-hint">
        Cuando el Arduino se comunique, acá aparece su nombre y la institución a la que está vinculado, o la opción de registrarlo si es nuevo. Un puerto COM
        o un emparejamiento Bluetooth solos no alcanzan: hace falta que el Arduino responda.
      </p>
    );
  } else if (situacion === 'NO_REGISTRADO') {
    body = <RegisterNew identification={identification} onDone={done} />;
  } else if (situacion === 'IDENTIDAD_NO_CONFIRMADA') {
    body = <Unverified identification={identification} onDone={done} />;
  } else if (situacion === 'DE_OTRA_INSTITUCION') {
    body = (
      <>
        <Alert>El Arduino conectado ya está registrado en otra institución. No se transfiere automáticamente: pedí a la administración de GlucoLume el procedimiento de reasignación.</Alert>
        <Facts identification={identification} device={null} />
      </>
    );
  } else if (situacion === 'SIN_INSTITUCION' && identification.puedeVincular && device) {
    body = <LinkExisting identification={identification} device={device} onDone={done} />;
  } else {
    body = (
      <>
        <p className="identification-name">
          <b>{device?.nombre || device?.codigoDispositivo}</b>
          <Badge tone={identification.usable ? 'success' : 'warning'}>{identification.usable ? 'Se puede usar' : 'No se puede usar'}</Badge>
        </p>
        {identification.motivoNoDisponible && !identification.usable && <Alert>{identification.motivoNoDisponible}</Alert>}
        <Facts identification={identification} device={device} />
        <p className="field-hint"><Info size={14} aria-hidden="true" /> Vinculado a {identification.institucion.nombre}. Al medir se elige al paciente; el dispositivo no queda asociado a ninguno.</p>
      </>
    );
  }

  return (
    <section className="panel connect-panel identification-panel" aria-labelledby="dispositivo-conexion">
      <div className="panel-title">
        <span className="panel-icon"><Cpu size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="dispositivo-conexion">Dispositivo de esta conexión</h2>
          <p>Identificá el Arduino conectado y confirmá su vinculación con {identification.institucion.nombre}.</p>
        </div>
      </div>
      {notice && <Alert kind="success">{notice}</Alert>}
      {body}
    </section>
  );
}
