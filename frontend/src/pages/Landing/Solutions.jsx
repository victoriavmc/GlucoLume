// Soluciones: para quién está pensada GlucoLume.
//
// Los roles corresponden al modelo existente (backend/app/models):
//   GrupoUsuario.rolGrupo:            PROPIETARIO | MODERADOR | MIEMBRO
//   GrupoUsuario.nivelComparticion:   NINGUNA (por defecto) | SOLO_MOMENTO | MEDICION_COMPLETA
//   InstitucionUsuario.rolInstitucion: PROPIETARIO | MODERADOR | OPERADOR
// Las etiquetas visibles son las mismas que usan los correos (app/emails/formatting.py: ROLE_LABELS).

import {
  ArrowRight,
  BarChart3,
  Building2,
  Check,
  ClipboardList,
  EyeOff,
  History,
  KeyRound,
  LayoutDashboard,
  Network,
  ShieldCheck,
  Stethoscope,
  User,
  UserCog,
  UserPlus,
  Users,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const INDIVIDUAL_FEATURES = [
  'Registrar tus datos con una cuenta propia.',
  'Vincular cada medición con tu perfil.',
  'Consultar tu historial y visualizar tu evolución.',
  'Ver indicadores relacionados con tus mediciones.',
  'Indicar el contexto de cada medición, como el tiempo desde la última comida.',
  'Administrar la información de tu cuenta.',
];

const GROUP_ROLES = [
  {
    icon: UserCog,
    name: 'Propietario/a',
    text: 'Crea el grupo y lo administra: invita o quita integrantes y asigna roles.',
  },
  { icon: Users, name: 'Moderador/a', text: 'Colabora con la administración del grupo según los permisos asignados.' },
  { icon: User, name: 'Integrante', text: 'Participa del grupo y decide qué comparte con los demás.' },
];

const SHARING_LEVELS = [
  { name: 'Nada', text: 'opción inicial al incorporarte' },
  { name: 'Solo el momento', text: 'cuándo se realizó la medición' },
  { name: 'Medición completa', text: 'incluye los valores registrados' },
];

const GROUP_FACTS = [
  { icon: EyeOff, text: 'Pertenecer a un grupo no da acceso automático a tu información privada.' },
  { icon: KeyRound, text: 'Lo que cada integrante ve o administra depende de los permisos otorgados.' },
  { icon: ShieldCheck, text: 'Siempre podés consultar tus propios datos, estés o no en un grupo.' },
  { icon: History, text: 'Si abandonás un grupo, tu historial personal de mediciones se conserva.' },
];

const INSTITUTION_REASONS = [
  { icon: ClipboardList, title: 'Pacientes organizados', text: 'Registro y seguimiento de pacientes en un entorno controlado.' },
  { icon: LayoutDashboard, title: 'Dashboards institucionales', text: 'Historial e indicadores para consultar la evolución.' },
  { icon: Network, title: 'Responsabilidades claras', text: 'Cada persona accede según el rol que le asigna la institución.' },
];

const INSTITUTION_ROLES = [
  {
    icon: Building2,
    name: 'Propietario/a',
    text: 'Registra la institución y la administra, junto con sus responsables y su configuración.',
  },
  {
    icon: UserCog,
    name: 'Moderador/a',
    text: 'Gestiona operadores y la organización diaria, según los permisos asignados.',
  },
  {
    icon: Stethoscope,
    name: 'Operador/a',
    text: 'Profesional que registra pacientes a su cargo, realiza mediciones autorizadas y consulta su historial.',
  },
];

const INSTITUTION_FACTS = [
  { icon: UserPlus, text: 'Una institución puede sumar múltiples operadores.' },
  { icon: Network, text: 'Un mismo profesional puede trabajar con más de una institución.' },
  { icon: KeyRound, text: 'Pertenecer a la institución no da acceso a toda la información: lo define el rol.' },
  { icon: BarChart3, text: 'Cada paciente tiene un operador responsable, y puede transferirse a otro cuando corresponde.' },
];

function RoleList({ roles }) {
  return (
    <ul className="role-list">
      {roles.map(({ icon: Icon, name, text }) => (
        <li key={name}>
          <span className="role-icon">
            <Icon size={20} aria-hidden="true" />
          </span>
          <span>
            <b>{name}</b>
            <small>{text}</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

function FactList({ facts }) {
  return (
    <ul className="fact-list">
      {facts.map(({ icon: Icon, text }) => (
        <li key={text}>
          <Icon size={18} aria-hidden="true" />
          {text}
        </li>
      ))}
    </ul>
  );
}

export function Solutions() {
  return (
    <section id="soluciones" className="section solutions" aria-labelledby="soluciones-title">
      <div className="container">
        <div className="section-head">
          <span className="pill">
            <Users size={16} aria-hidden="true" /> Soluciones
          </span>
          <h2 id="soluciones-title">Soluciones de GlucoLume</h2>
          <p className="section-lead">
            Una misma plataforma para el seguimiento personal, el acompañamiento familiar y el trabajo institucional.
          </p>
        </div>

        <div className="solution-list">
          <article className="card solution" aria-labelledby="sol-individual">
            <div className="solution-intro">
              <span className="icon-tile">
                <User size={26} aria-hidden="true" />
              </span>
              <span className="solution-kicker">Cuenta personal</span>
              <h3 id="sol-individual">Usuario individual</h3>
              <p>
                Con tu propia cuenta registrás y seguís la información obtenida con GlucoLume. No es una herramienta de
                diagnóstico: está pensada para registrar, seguir y visualizar tus mediciones.
              </p>
              <Link to="/registro?tipo=usuario" className="btn btn-primary">
                Crear mi cuenta <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
            <ul className="check-list">
              {INDIVIDUAL_FEATURES.map((item) => (
                <li key={item}>
                  <Check size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </article>

          <article className="card solution" aria-labelledby="sol-grupo">
            <div className="solution-intro">
              <span className="icon-tile">
                <Users size={26} aria-hidden="true" />
              </span>
              <span className="solution-kicker">Desde tu cuenta individual</span>
              <h3 id="sol-grupo">Grupo</h3>
              <p>
                Con tu cuenta individual podés crear un grupo o sumarte a uno. No es otro tipo de cuenta ni
                otro registro: el grupo se administra después, desde tu cuenta.
              </p>
              <blockquote className="motto">
                Compartir cuando sea necesario, manteniendo el control sobre la información personal.
              </blockquote>
              <Link to="/registro?tipo=usuario" className="btn btn-outline">
                Crear cuenta individual <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
            <div className="solution-detail solution-cols">
              <div className="solution-col">
                <h4>Roles dentro del grupo</h4>
                <RoleList roles={GROUP_ROLES} />
              </div>
              <div className="solution-col">
                <h4>Cada integrante elige qué compartir</h4>
                <ol className="levels">
                  {SHARING_LEVELS.map(({ name, text }) => (
                    <li key={name}>
                      <b>{name}</b>
                      <small>{text}</small>
                    </li>
                  ))}
                </ol>
                <FactList facts={GROUP_FACTS} />
              </div>
            </div>
          </article>

          <article className="card solution is-institutional" aria-labelledby="sol-institucion">
            <div className="solution-intro">
              <span className="icon-tile">
                <Building2 size={26} aria-hidden="true" />
              </span>
              <span className="solution-kicker">Organizaciones de salud</span>
              <h3 id="sol-institucion">Institución</h3>
              <p className="solution-question">¿Por qué una institución usaría GlucoLume?</p>
              <ul className="reason-list">
                {INSTITUTION_REASONS.map(({ icon: Icon, title, text }) => (
                  <li key={title}>
                    <Icon size={20} aria-hidden="true" />
                    <span>
                      <b>{title}</b>
                      <small>{text}</small>
                    </span>
                  </li>
                ))}
              </ul>
              <Link to="/registro?tipo=institucion" className="btn btn-outline-blue">
                Crear cuenta institucional <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
            <div className="solution-detail solution-cols">
              <div className="solution-col">
                <h4>Niveles de responsabilidad</h4>
                <RoleList roles={INSTITUTION_ROLES} />
              </div>
              <div className="solution-col">
                <FactList facts={INSTITUTION_FACTS} />
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
