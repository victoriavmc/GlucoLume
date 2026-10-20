import { AlertCircle, CheckCircle2, Eye, EyeOff, Info } from 'lucide-react';
import { forwardRef, useId, useState } from 'react';

/** Ids y `aria-describedby` de un campo: ayuda y error quedan asociados al control para los lectores de pantalla. */
function useFieldAria({ hint, error, extra }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null, extra].filter(Boolean).join(' ') || undefined;
  return { id, hintId, errorId, describedBy, invalid: error ? 'true' : undefined };
}

function FieldMessages({ hint, hintId, error, errorId }) {
  return (
    <>
      {hint && <p className="field-hint" id={hintId}>{hint}</p>}
      {error && <p className="field-error" id={errorId}>{error}</p>}
    </>
  );
}

/** Campo de texto con ícono, etiqueta, ayuda opcional y error accesible. `revealable` agrega mostrar/ocultar contraseña. */
export const TextField = forwardRef(function TextField(
  { label, icon: Icon, hint, error, revealable = false, type = 'text', 'aria-describedby': extraDescribedBy, ...inputProps },
  ref,
) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldAria({ hint, error, extra: extraDescribedBy });
  const [revealed, setRevealed] = useState(false);
  const inputType = revealable ? (revealed ? 'text' : 'password') : type;

  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className="field-control">
        {Icon && <Icon className="field-icon" size={20} aria-hidden="true" />}
        <input
          ref={ref}
          id={id}
          type={inputType}
          className={`field-input${revealable ? ' has-action' : ''}${Icon ? '' : ' has-no-icon'}`}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          {...inputProps}
        />
        {revealable && (
          <button
            type="button"
            className="field-action"
            aria-label={revealed ? 'Ocultar contraseña' : 'Mostrar contraseña'}
            aria-pressed={revealed}
            onClick={() => setRevealed((value) => !value)}
          >
            {revealed ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        )}
      </div>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
});

/** Lista desplegable con la misma etiqueta, ayuda y error que `TextField`. `options` = [{ value, label }] o `children` (<option>). */
export const SelectField = forwardRef(function SelectField(
  { label, hint, error, options, children, 'aria-describedby': extraDescribedBy, className = '', ...selectProps },
  ref,
) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldAria({ hint, error, extra: extraDescribedBy });
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <select ref={ref} id={id} className={`field-input field-select ${className}`.trim()} aria-invalid={invalid} aria-describedby={describedBy} {...selectProps}>
        {options ? options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>) : children}
      </select>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
});

/** Texto largo. Con `maxLength` muestra el contador «n / máximo» (decorativo: el límite lo aplica el propio control). */
export const TextAreaField = forwardRef(function TextAreaField(
  { label, hint, error, maxLength, value, 'aria-describedby': extraDescribedBy, className = '', rows = 4, ...textareaProps },
  ref,
) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldAria({ hint, error, extra: extraDescribedBy });
  const length = typeof value === 'string' ? value.length : 0;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <textarea ref={ref} id={id} rows={rows} maxLength={maxLength} value={value} className={`field-input field-textarea ${className}`.trim()}
        aria-invalid={invalid} aria-describedby={describedBy} {...textareaProps} />
      {maxLength ? (
        <div className="field-hint-row">
          <span>{hint && <span className="field-hint" id={hintId}>{hint}</span>}</span>
          <span className="field-counter" aria-hidden="true">{length} / {maxLength}</span>
        </div>
      ) : hint && <p className="field-hint" id={hintId}>{hint}</p>}
      {error && <p className="field-error" id={errorId}>{error}</p>}
    </div>
  );
});

/** Casilla con etiqueta clicable, ayuda y error asociados al control. */
export const CheckField = forwardRef(function CheckField(
  { label, hint, error, 'aria-describedby': extraDescribedBy, ...inputProps },
  ref,
) {
  const { id, hintId, errorId, describedBy, invalid } = useFieldAria({ hint, error, extra: extraDescribedBy });
  return (
    <div className="field-check-block">
      <label className="check" htmlFor={id}>
        <input ref={ref} id={id} type="checkbox" aria-invalid={invalid} aria-describedby={describedBy} {...inputProps} />
        {label}
      </label>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
});

/** Opción de un grupo de radios (el grupo va en un `fieldset` con `legend`), con la misma etiqueta clicable y ayuda que `CheckField`. */
export const RadioField = forwardRef(function RadioField(
  { label, hint, 'aria-describedby': extraDescribedBy, ...inputProps },
  ref,
) {
  const { id, hintId, describedBy } = useFieldAria({ hint, error: null, extra: extraDescribedBy });
  return (
    <div className="field-check-block">
      <label className="check" htmlFor={id}>
        <input ref={ref} id={id} type="radio" aria-describedby={describedBy} {...inputProps} />
        {label}
      </label>
      <FieldMessages hint={hint} hintId={hintId} />
    </div>
  );
});

const ALERT_ICONS = { error: AlertCircle, info: Info, success: CheckCircle2 };

export function Alert({ kind = 'error', children }) {
  const Icon = ALERT_ICONS[kind];
  return (
    <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function SubmitButton({ loading, loadingLabel, children, className = 'btn btn-primary btn-block btn-lg', ...props }) {
  return (
    <button type="submit" className={className} disabled={loading} aria-busy={loading || undefined} {...props}>
      {loading ? (
        <>
          <span className="spinner" aria-hidden="true" />
          {loadingLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}
