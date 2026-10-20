// Identificación del paciente, igual en transferencias y auditoría: nombre y apellido con más jerarquía y, debajo, el
// identificador seudónimo como referencia. El nombre solo llega si el backend autoriza a quien consulta.
//   name:      nombre completo o null (sin autorización o sin dato)
//   available: null = sin autorización para ver datos identificativos; false = autorizado pero no disponibles; true = hay nombre

export function PatientIdentity({ name, code, available = null }) {
  const identifier = code ?? 'Paciente sin identificador';
  if (name) {
    return (
      <span className="patient-identity" aria-label="Paciente">
        <b className="patient-name">{name}</b>
        <small>Identificador: <span>{identifier}</span></small>
      </span>
    );
  }
  if (available === false) {
    return (
      <span className="patient-identity" aria-label="Paciente">
        <b className="patient-name">Datos identificativos no disponibles</b>
        <small>Identificador: <span>{identifier}</span></small>
      </span>
    );
  }
  return (
    <span className="patient-identity" aria-label="Paciente">
      <b>{identifier}</b>
    </span>
  );
}

export function fullName(person) {
  return [person?.nombre, person?.apellido].filter(Boolean).join(' ') || null;
}
