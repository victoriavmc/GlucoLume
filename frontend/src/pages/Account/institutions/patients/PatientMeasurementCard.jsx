// Tarjeta «Datos del paciente» que abre la pantalla de medición institucional. Muestra solo lo que ya está registrado en el perfil
// del paciente (nada se vuelve a pedir ni se completa con valores predeterminados). La edad se calcula hoy desde la fecha de
// nacimiento; solo si no hay fecha se usa la edad declarada, y se rotula como tal. El sexo es el sexo biológico del modelo
// experimental (no el género): si no está registrado, se muestra «Sin informar».

import { Building2, CalendarDays, ChevronRight, IdCard, UserCog, VenusAndMars } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Alert } from '../../../../components/FormControls.jsx';
import { Badge } from '../../../../components/Badge.jsx';
import { SEXO_LABELS, formatDate } from '../institutionFormat.js';

/** Edad cumplida a `today` desde 'AAAA-MM-DD' (null si la fecha falta o es inválida). */
export function ageFromBirthDate(birthDate, today = new Date()) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(birthDate ?? '');
  if (!match) return null;
  const [year, month, day] = match.slice(1).map(Number);
  let age = today.getFullYear() - year;
  if (today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day)) age -= 1;
  return age >= 0 && age <= 130 ? age : null;
}

/** Perfil para `OptionalMeasurementContext`: la edad sugerida sale de la fecha de nacimiento a hoy, no de un valor guardado viejo. */
export function patientMeasurementProfile(patient, today = new Date()) {
  const fromBirth = ageFromBirthDate(patient.fechaNacimiento, today);
  return { ...patient, edad: fromBirth ?? patient.edad ?? null };
}

const initials = (patient) => [patient.nombre, patient.apellido].filter(Boolean).map((part) => part[0]).join('').toUpperCase() || 'P';

/** Un dato del paciente: ícono, etiqueta solo para lectores de pantalla y valor («sin informar» si el perfil no lo tiene, nunca un valor inventado). */
function Fact({ icon: Icon, label, children, emptyText, prefix = null }) {
  return (
    <li className={children ? undefined : 'is-empty'}>
      <Icon size={17} aria-hidden="true" />
      {children ? <>{prefix ? <span className="pm-fact-label">{prefix}</span> : <span className="sr-only">{label}: </span>}{children}</> : emptyText}
    </li>
  );
}

export function PatientMeasurementCard({ patient, institution }) {
  const fromBirth = ageFromBirthDate(patient.fechaNacimiento);
  const age = fromBirth ?? patient.edad ?? null;
  const responsible = patient.responsable ? [patient.responsable.nombre, patient.responsable.apellido].filter(Boolean).join(' ') : '';
  const fullName = [patient.nombre, patient.apellido].filter(Boolean).join(' ') || patient.identificadorPseudonimo;
  const missing = [age === null && 'fecha de nacimiento', !patient.sexoModelo && 'sexo'].filter(Boolean);
  const birth = patient.fechaNacimiento
    ? `${formatDate(patient.fechaNacimiento)}${age !== null ? ` (${age} años${fromBirth === null ? ', declarada' : ''})` : ''}`
    : age !== null && `Edad declarada: ${age} años`;
  return (
    <section className="panel pm-patient" aria-labelledby="medicion-paciente">
      <div className="pm-patient-main">
        <span className="pm-avatar" aria-hidden="true">{initials(patient)}</span>
        <div className="pm-patient-body">
          <div className="pm-patient-name">
            <h2 id="medicion-paciente"><span className="sr-only">Datos del paciente: </span>{fullName}</h2>
            <Badge tone={patient.estado === 'ACTIVO' ? 'success' : 'neutral'}>{patient.estado === 'ACTIVO' ? 'Paciente activo' : 'Paciente de baja'}</Badge>
            {patient.esMio && <Badge tone="info">A mi cargo</Badge>}
          </div>
          <ul className="pm-facts" aria-label="Datos registrados del paciente">
            <Fact icon={CalendarDays} label="Fecha de nacimiento y edad" emptyText="Fecha de nacimiento sin informar">{birth}</Fact>
            <Fact icon={VenusAndMars} label="Sexo biológico (modelo)" emptyText="Sexo sin informar">{SEXO_LABELS[patient.sexoModelo]}</Fact>
            <Fact icon={IdCard} label="Identificador">{patient.identificadorPseudonimo}</Fact>
            <Fact icon={Building2} label="Institución">{institution?.nombre}</Fact>
            <Fact icon={UserCog} label="Operador responsable" prefix="Responsable: ">{responsible && `${responsible}${patient.responsable.activo === false ? ' (desvinculado)' : ''}`}</Fact>
          </ul>
        </div>
        <Link to=".." relative="path" className="btn btn-outline pm-patient-link">
          Ver ficha completa <ChevronRight size={16} aria-hidden="true" />
        </Link>
      </div>
      <Alert kind="info">
        {missing.length > 0
          ? <>Este paciente no tiene {missing.join(' ni ')} registrado. Podés medir oximetría igual; para la glucosa experimental son necesarios. Informalos
            abajo como datos opcionales solo para esta medición (no modifican el perfil) o completalos desde su ficha.</>
          : <>La fecha de nacimiento y el sexo provienen del perfil del paciente: no se vuelven a pedir. La edad se calcula a hoy. Si algo cambió, completalo
            desde su ficha.</>}
      </Alert>
    </section>
  );
}
