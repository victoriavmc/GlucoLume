// Reautenticación reforzada para acciones sensibles de la administración: contraseña (si la cuenta tiene credencial local)
// y código de la aplicación autenticadora. El backend las verifica en cada acción; aquí solo se recogen.

import { useState } from 'react';

import { TextField } from './FormControls.jsx';

export function useReauth(hasPassword) {
  const [value, setValue] = useState({ password: '', codigo: '' });
  const missing = (hasPassword && !value.password) || !/^\d{6}$/.test(value.codigo.trim());
  return {
    value, setValue, missing,
    /** Cuerpo `reautenticacion` del API. */
    body: () => ({ ...(hasPassword ? { password: value.password } : {}), codigo: value.codigo.trim() }),
    reset: () => setValue({ password: '', codigo: '' }),
  };
}

export function ReauthFields({ reauth, hasPassword, idPrefix = 'reauth' }) {
  const { value, setValue } = reauth;
  return (
    <fieldset className="reauth" aria-label="Confirmá tu identidad">
      <legend className="field-label">Confirmá tu identidad</legend>
      {hasPassword && (
        <TextField label="Tu contraseña" name={`${idPrefix}-password`} revealable autoComplete="current-password" maxLength={128}
          value={value.password} onChange={(event) => setValue((current) => ({ ...current, password: event.target.value }))} />
      )}
      <TextField label="Código de verificación (6 dígitos)" name={`${idPrefix}-codigo`} inputMode="numeric" autoComplete="one-time-code"
        maxLength={6} value={value.codigo}
        onChange={(event) => setValue((current) => ({ ...current, codigo: event.target.value.replace(/\D/g, '') }))} />
      <p className="field-hint">Es una acción sensible: se pide tu contraseña y el código de tu aplicación autenticadora.</p>
    </fieldset>
  );
}
