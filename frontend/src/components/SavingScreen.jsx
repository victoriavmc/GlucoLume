// Pantalla de carga a pantalla completa mientras una operación larga termina (p. ej. guardar una medición, que también envía el resultado por
// correo). Evita que la interfaz «salte» a otro estado a mitad de camino: mantiene al usuario en una sola pantalla con un mensaje claro.
// Aparece con un pequeño retardo (CSS) para que un guardado instantáneo no parpadee. Accesible: role="status" y aria-live.

import { LogoMark } from './Logo.jsx';

export function SavingScreen({ title = 'Guardando la medición…', steps = [], note }) {
  return (
    <div className="saving-screen" role="status" aria-live="polite" aria-busy="true">
      <div className="saving-card">
        <span className="saving-mark" aria-hidden="true"><LogoMark size={68} /></span>
        <p className="saving-brand" aria-hidden="true">Gluco<span>Lume</span></p>
        <h2 className="saving-title">{title}</h2>
        {steps.length > 0 && (
          <ul className="saving-steps">
            {steps.map((step) => <li key={step}>{step}</li>)}
          </ul>
        )}
        <div className="saving-bar" aria-hidden="true"><span /></div>
        <p className="saving-note">{note ?? 'No cierres ni recargues esta pantalla: en unos segundos vas a ver el resultado.'}</p>
      </div>
    </div>
  );
}
