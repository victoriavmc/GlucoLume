// «Registrar dispositivo» y edición de sus datos. Los valores y la validación definitiva son los de FastAPI (código
// único, sensor MAX30100/MAX30102, estado, institución activa y responsable de esa institución). El código es el
// identificador PROPIO del dispositivo (no el puerto COM) y no se cambia después del alta.
// En una institución NO se elige responsable: el backend asigna el dispositivo al propietario vigente (solo se informa).
// El alta normal se hace desde la primera conexión de un operador («Conectar dispositivo»); este formulario es el alta ADMINISTRATIVA
// manual (un equipo que todavía no se conectó, o con firmware sin identificador). Comparte el código único: nunca duplica un dispositivo.
// Al modificar, una institución cambia el nombre y el modelo; el sensor y el firmware los informa la propia conexión del Arduino.

import { Cpu, Save, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Alert, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';
import { DEVICE_STATES, EDITABLE_STATES, SENSORS, personLabel } from './deviceFormat.js';

const EMPTY = { codigo: '', nombre: '', modelo: '', sensor: 'MAX30102', firmware: '', estado: 'OPERATIVO', institucion: '', responsable: '' };

const FIELD_ROUTES = {
  codigoDispositivo: 'codigo', nombre: 'nombre', modelo: 'modelo', modeloSensor: 'sensor', versionFirmware: 'firmware',
  estado: 'estado', idInstitucionAsignada: 'institucion', idInstitucionUsuarioResponsable: 'responsable',
};

/**
 * `device`: presente al editar. `canAssign`: el administrador elige institución al registrar (inventario global);
 * en una institución, el dispositivo queda siempre en esa institución y a cargo de su propietario (no se elige).
 */
export function DeviceForm({ api, device, institutional, canAssign, onSaved, onCancel, handleOperationError }) {
  const editing = Boolean(device);
  const technicalLocked = editing && institutional;
  const [form, setForm] = useState(() => (device ? {
    ...EMPTY, codigo: device.codigoDispositivo, nombre: device.nombre ?? '', modelo: device.modelo ?? '',
    sensor: device.modeloSensor, firmware: device.versionFirmware ?? '',
  } : EMPTY));
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [institutionOptions, setInstitutionOptions] = useState([]);
  const [responsibles, setResponsibles] = useState([]);

  // Instituciones (solo administrador, inventario global) y posibles responsables de la institución elegida.
  useEffect(() => {
    if (editing || !canAssign) return;
    api.institutionOptions().then(setInstitutionOptions, () => setInstitutionOptions([]));
  }, [api, editing, canAssign]);

  useEffect(() => {
    if (editing || institutional) return undefined;
    let active = true;
    const load = form.institucion ? api.institutionResponsibles(form.institucion) : null;
    if (!load) {
      setResponsibles([]);
      return undefined;
    }
    load.then((list) => active && setResponsibles(list), () => active && setResponsibles([]));
    return () => { active = false; };
  }, [api, editing, institutional, form.institucion]);

  function update(field) {
    return (event) => {
      const { value } = event.target;
      setForm((current) => ({ ...current, [field]: value, ...(field === 'institucion' ? { responsable: '' } : {}) }));
      if (errors[field]) setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const found = {};
    if (!editing && form.codigo.trim().length < 3) found.codigo = 'Ingresá el código único del dispositivo (mínimo 3 caracteres).';
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    setError('');
    try {
      const saved = editing
        ? await api.edit(device.idDispositivo, {
          nombre: form.nombre.trim() || null, modelo: form.modelo.trim() || null,
          ...(technicalLocked ? {} : { modeloSensor: form.sensor, versionFirmware: form.firmware.trim() || null }),
        })
        : await api.register({
          codigoDispositivo: form.codigo.trim(), nombre: form.nombre.trim() || undefined, modelo: form.modelo.trim() || undefined,
          modeloSensor: form.sensor, versionFirmware: form.firmware.trim() || undefined, estado: form.estado,
          ...(form.institucion ? { idInstitucionAsignada: form.institucion } : {}),
          ...(!institutional && form.responsable ? { idInstitucionUsuarioResponsable: form.responsable } : {}),
        });
      onSaved(saved);
    } catch (saveError) {
      const byField = {};
      for (const item of saveError.fields ?? []) {
        const key = FIELD_ROUTES[item.ruta];
        if (key && !byField[key]) byField[key] = item.mensaje;
      }
      if (saveError.codigo === 'DISPOSITIVO_DUPLICADO') byField.codigo = saveError.message;
      setErrors(byField);
      if (!Object.keys(byField).length) setError(handleOperationError(saveError));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit} noValidate aria-labelledby="dispositivo-form">
      <div className="panel-title">
        <span className="panel-icon"><Cpu size={22} aria-hidden="true" /></span>
        <div>
          <h2 id="dispositivo-form">{editing ? 'Modificar dispositivo' : 'Registrar dispositivo'}</h2>
          <p>{editing ? `Código ${device.codigoDispositivo}` : institutional
            ? 'Alta administrativa manual. Normalmente un operador lo registra solo la primera vez que conecta el Arduino; usá este formulario para un equipo que todavía no se conectó.'
            : 'Cargá el identificador propio del dispositivo y sus características.'}</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="form-grid">
        {!editing && (
          <TextField label="Código único del dispositivo" maxLength={100} autoComplete="off" value={form.codigo}
            onChange={update('codigo')} error={errors.codigo} />
        )}
        <TextField label="Nombre descriptivo" maxLength={100} value={form.nombre} onChange={update('nombre')} error={errors.nombre} />
        <TextField label="Modelo" maxLength={100} value={form.modelo} onChange={update('modelo')} error={errors.modelo} />
        <SelectField label="Modelo del sensor" value={form.sensor} onChange={update('sensor')} error={errors.sensor}
          disabled={technicalLocked} hint={technicalLocked ? 'Lo informa la conexión del Arduino: una institución no lo modifica.' : undefined}>
          {SENSORS.map((sensor) => <option key={sensor} value={sensor}>{sensor}</option>)}
        </SelectField>
        <TextField label="Versión de firmware" maxLength={50} value={form.firmware} onChange={update('firmware')} error={errors.firmware}
          disabled={technicalLocked}
          hint={technicalLocked ? 'Se actualiza sola cuando el Arduino informa su versión.' : editing ? 'Las mediciones anteriores conservan el firmware que tenía el dispositivo al medir.' : undefined} />
        {!editing && (
          <SelectField label="Estado" value={form.estado} onChange={update('estado')} error={errors.estado}>
            {EDITABLE_STATES.map((state) => <option key={state} value={state}>{DEVICE_STATES[state]}</option>)}
          </SelectField>
        )}
        {!editing && canAssign && (
          <SelectField label="Institución asignada (opcional)" value={form.institucion} onChange={update('institucion')}
            error={errors.institucion}>
            <option value="">Sin asignar</option>
            {institutionOptions.map((option) => <option key={option.idInstitucion} value={option.idInstitucion}>{option.nombre}</option>)}
          </SelectField>
        )}
        {!editing && institutional && (
          <div className="field">
            <span className="field-label">Propietario asignado</span>
            <p className="field-hint">Se asigna automáticamente al propietario/a de la institución. No se puede elegir otra persona.</p>
          </div>
        )}
        {!editing && !institutional && form.institucion && (
          <SelectField label="Responsable (opcional)" value={form.responsable} onChange={update('responsable')}
            error={errors.responsable} hint="Solo integrantes activos de la institución del dispositivo.">
            <option value="">Sin responsable</option>
            {responsibles.map((person) => (
              <option key={person.idInstitucionUsuario} value={person.idInstitucionUsuario}>{personLabel(person)}</option>
            ))}
          </SelectField>
        )}
      </div>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}><X size={16} aria-hidden="true" /> Cancelar</button>
        <SubmitButton loading={saving} loadingLabel="Guardando…" className="btn btn-primary">
          <Save size={16} aria-hidden="true" /> {editing ? 'Guardar cambios' : 'Registrar dispositivo'}
        </SubmitButton>
      </div>
    </form>
  );
}
