// Características transversales: privacidad, confidencialidad, anonimización y tratamiento de datos.
// Coherente con lo que hace el backend: al eliminar una cuenta se anonimizan los datos personales y las
// mediciones conservan solo su contexto (edadAlMomento, sexoModelo, fecha, valores, última comida).

import {
  Bell,
  Building2,
  Database,
  EyeOff,
  FileLock2,
  Hourglass,
  LayoutDashboard,
  Lock,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  X,
  Check,
} from 'lucide-react';

const PRIVACY_CARDS = [
  {
    icon: ShieldCheck,
    title: 'Privacidad por diseño',
    text: 'Los datos personales se usan solo mientras son necesarios para brindar cada funcionalidad.',
  },
  {
    icon: FileLock2,
    title: 'Datos confidenciales',
    text: 'La información se trata con principios de privacidad, tomando como referencia la Ley 25.326.',
  },
  {
    icon: EyeOff,
    title: 'Historial anonimizado',
    text: 'Las estadísticas conservan su utilidad sin mantener los datos que identifican a la persona.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Control de la información',
    text: 'Cada usuario accede y controla la información de su cuenta y los permisos asociados.',
  },
  {
    icon: Building2,
    title: 'Gestión institucional segura',
    text: 'Los accesos institucionales dependen de los roles y permisos definidos en cada organización.',
  },
  {
    icon: Hourglass,
    title: 'Retención controlada',
    text: 'Los datos personales se conservan solo durante el período definido y luego se eliminan o anonimizan.',
  },
];

const ACTIVE_ACCOUNT_USES = [
  'Identificarte correctamente.',
  'Administrar tu cuenta.',
  'Asociar tus mediciones.',
  'Brindarte las funcionalidades correspondientes.',
];

const KEPT = [
  'Edad al momento de la medición',
  'Género',
  'Fecha y hora de la medición',
  'Valor de la medición',
  'Última comida o tiempo desde la última ingesta',
];

const NEVER_KEPT = [
  'Nombre y apellido',
  'Correo electrónico',
  'Documento',
  'Teléfono',
  'Dirección',
  'Identificadores directos de cuenta',
];

const PLATFORM_FEATURES = [
  { icon: Database, text: 'Almacenamiento seguro de datos' },
  { icon: Bell, text: 'Recordatorios de medición' },
  { icon: LayoutDashboard, text: 'Dashboards personalizados' },
  { icon: Lock, text: 'Accesos con verificación en dos pasos' },
];

export function Features() {
  return (
    <section id="caracteristicas" className="section section-tinted" aria-labelledby="caracteristicas-title">
      <div className="container">
        <div className="section-head">
          <span className="pill">
            <Scale size={16} aria-hidden="true" /> Características
          </span>
          <h2 id="caracteristicas-title">Tu información, protegida en cada etapa</h2>
          <p className="section-lead">
            GlucoLume trata la información de forma confidencial y toma como referencia la{' '}
            <strong>Ley N.º 25.326 de Protección de los Datos Personales</strong> de la República Argentina.
          </p>
        </div>

        <ul className="privacy-grid">
          {PRIVACY_CARDS.map(({ icon: Icon, title, text }) => (
            <li key={title} className="card privacy-card">
              <span className="icon-tile">
                <Icon size={22} aria-hidden="true" />
              </span>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ul>

        <div className="data-lifecycle">
          <div className="card lifecycle-card">
            <h3>Mientras tu cuenta está activa</h3>
            <p className="muted">Usamos los datos personales necesarios para:</p>
            <ul className="check-list">
              {ACTIVE_ACCOUNT_USES.map((item) => (
                <li key={item}>
                  <Check size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="card lifecycle-card">
            <h3>Cuando ya no deben conservarse</h3>
            <p className="muted">
              El historial se mantiene solo de forma anonimizada, para estadísticas y dashboards.
            </p>
            <div className="data-columns">
              <div>
                <h4>Se conserva</h4>
                <ul className="tag-list is-kept">
                  {KEPT.map((item) => (
                    <li key={item}>
                      <Check size={14} aria-hidden="true" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>No se conserva</h4>
                <ul className="tag-list is-removed">
                  {NEVER_KEPT.map((item) => (
                    <li key={item}>
                      <X size={14} aria-hidden="true" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>

        <div className="institution-note">
          <Building2 size={24} aria-hidden="true" />
          <p>
            <b>Pacientes institucionales.</b> Sus datos identificatorios pueden conservarse durante{' '}
            <strong>12 meses</strong> cuando la gestión institucional lo requiere. Después, la información para
            estadísticas y dashboards queda anonimizada, con las mismas variables indicadas arriba.
          </p>
        </div>

        <ul className="features">
          {PLATFORM_FEATURES.map(({ icon: Icon, text }) => (
            <li key={text}>
              <span className="icon-tile">
                <Icon size={22} aria-hidden="true" />
              </span>
              {text}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
