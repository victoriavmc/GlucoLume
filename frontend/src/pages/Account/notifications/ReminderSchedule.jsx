// Horario para recordarme medirme: cada cierto tiempo o a horas fijas (hasta 6). Se puede modificar o eliminar. Los canales (aplicación y correo) se eligen arriba.

import { Clock, Plus, Trash2, X } from 'lucide-react';
import { useState } from 'react';

import { Alert, RadioField, SelectField, SubmitButton, TextField } from '../../../components/FormControls.jsx';

const INTERVALOS_HORAS = [1, 2, 3, 4, 6, 8, 12, 24];
const MAX_HORARIOS = 6;
const HORA_VACIA = '08:00';

function intervaloLabel(horas) {
  return horas === 1 ? 'Cada hora' : `Cada ${horas} horas`;
}

export function scheduleSummary(schedule) {
  if (schedule.modo === 'INTERVALO') return `Te recordamos ${intervaloLabel(schedule.intervaloHoras).toLowerCase()}.`;
  if (schedule.modo === 'HORARIOS') return `Te recordamos todos los días a las ${schedule.horarios.join(', ')}.`;
  return 'No tenés ningún recordatorio programado.';
}

export function ReminderSchedule({ schedule, onSave }) {
  const [modo, setModo] = useState(schedule.modo);
  const [intervaloHoras, setIntervaloHoras] = useState(schedule.intervaloHoras ?? 4);
  const [horarios, setHorarios] = useState(schedule.horarios.length ? schedule.horarios : [HORA_VACIA]);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  function changeHorario(index, value) {
    setHorarios((current) => current.map((hora, i) => (i === index ? value : hora)));
  }

  function removeHorario(index) {
    setHorarios((current) => current.filter((_, i) => i !== index));
  }

  function addHorario() {
    setHorarios((current) => [...current, HORA_VACIA]);
  }

  async function submit(event) {
    event.preventDefault();
    setSaved(false);
    setError('');
    if (modo === 'HORARIOS') {
      if (horarios.some((hora) => !hora)) {
        setError('Completá cada horario o quitá los que dejaste vacíos.');
        return;
      }
      if (new Set(horarios).size !== horarios.length) {
        setError('Hay horarios repetidos. Dejá uno solo por horario.');
        return;
      }
    }
    const payload = modo === 'INTERVALO' ? { modo, intervaloHoras }
      : modo === 'HORARIOS' ? { modo, horarios }
        : { modo: 'NINGUNO' };
    setSaving(true);
    const ok = await onSave(payload);
    setSaving(false);
    setSaved(ok);
  }

  async function remove() {
    setSaved(false);
    setError('');
    setSaving(true);
    const ok = await onSave({ modo: 'NINGUNO' });
    setSaving(false);
    if (ok) {
      setModo('NINGUNO');
      setHorarios([HORA_VACIA]);
      setSaved(true);
    }
  }

  return (
    <section className="panel" aria-labelledby="notif-horario">
      <div className="panel-title">
        <span className="panel-icon">
          <Clock size={22} aria-hidden="true" />
        </span>
        <div>
          <h2 id="notif-horario">Horario para medirme</h2>
          <p aria-live="polite">{scheduleSummary(schedule)} Los canales se eligen en «Recordatorios de medición».</p>
        </div>
      </div>
      <form className="notif-schedule" onSubmit={submit} noValidate>
        <fieldset className="notif-modes">
          <legend>¿Cuándo querés que te recordemos?</legend>
          <RadioField label="No recordarme" name="modo" value="NINGUNO" checked={modo === 'NINGUNO'}
            onChange={() => setModo('NINGUNO')} />
          <RadioField label="Cada cierto tiempo" name="modo" value="INTERVALO" checked={modo === 'INTERVALO'}
            onChange={() => setModo('INTERVALO')} />
          <RadioField label="A horas específicas" name="modo" value="HORARIOS" checked={modo === 'HORARIOS'}
            onChange={() => setModo('HORARIOS')} />
        </fieldset>

        {modo === 'INTERVALO' && (
          <SelectField label="Cada cuántas horas" value={intervaloHoras}
            onChange={(event) => setIntervaloHoras(Number(event.target.value))}
            options={INTERVALOS_HORAS.map((horas) => ({ value: horas, label: intervaloLabel(horas) }))} />
        )}

        {modo === 'HORARIOS' && (
          <div className="notif-times">
            {horarios.map((hora, index) => (
              <div key={index} className="notif-time-row">
                <TextField label={`Horario ${index + 1}`} type="time" value={hora}
                  onChange={(event) => changeHorario(index, event.target.value)} />
                {horarios.length > 1 && (
                  <button type="button" className="btn btn-ghost btn-sm" aria-label={`Quitar horario ${index + 1}`}
                    onClick={() => removeHorario(index)}>
                    <X size={16} aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
            {horarios.length < MAX_HORARIOS && (
              <button type="button" className="btn btn-ghost" onClick={addHorario}>
                <Plus size={16} aria-hidden="true" /> Agregar horario
              </button>
            )}
          </div>
        )}

        {error && <Alert>{error}</Alert>}
        {saved && <Alert kind="success">{modo === 'NINGUNO' ? 'Quitamos tu programación.' : 'Guardamos tu horario.'}</Alert>}
        <div className="notif-schedule-actions">
          <SubmitButton className="btn btn-primary" loading={saving} loadingLabel="Guardando…">Guardar horario</SubmitButton>
          {schedule.modo !== 'NINGUNO' && (
            <button type="button" className="btn btn-ghost" onClick={remove} disabled={saving}>
              <Trash2 size={16} aria-hidden="true" /> Eliminar programación
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
