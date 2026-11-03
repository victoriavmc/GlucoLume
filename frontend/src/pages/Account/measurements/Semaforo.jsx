// Semáforo de una glucosa frente al intervalo recomendado de su regla: rojo «Muy alto», amarillo «Revisar» (al borde o por debajo)
// y verde «Está bien». Es una comparación con el intervalo configurado, no una clasificación clínica. Lo calcula el backend (`semaforo`).

const LIGHTS = ['ROJO', 'AMARILLO', 'VERDE'];
const LABELS = { ROJO: 'Muy alto', AMARILLO: 'Revisar', VERDE: 'Está bien' };

export function Semaforo({ color }) {
  if (!color || !LABELS[color]) return null;
  return (
    <span className={`semaforo is-${color.toLowerCase()}`}>
      <span className="semaforo-luces" aria-hidden="true">
        {LIGHTS.map((light) => (
          <i key={light} className={`semaforo-luz is-${light.toLowerCase()}${light === color ? ' is-on' : ''}`} />
        ))}
      </span>
      <span>{LABELS[color]}</span>
    </span>
  );
}
