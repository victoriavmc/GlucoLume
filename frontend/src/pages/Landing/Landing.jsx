import {
  Activity,
  ArrowRight,
  BarChart3,
  ChevronDown,
  Droplet,
  Fingerprint,
  FlaskConical,
  GraduationCap,
  HeartPulse,
  LineChart,
  ShieldCheck,
  Stethoscope,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { ExperimentalNotice } from "../../components/ExperimentalNotice.jsx";
import { LogoMark } from "../../components/Logo.jsx";
import { SiteFooter } from "../../components/SiteFooter.jsx";
import { SkipLink } from "../../components/SkipLink.jsx";
import {
  ACADEMIC_PROJECT_ID,
  Navbar,
  SECTIONS,
} from "../../components/Navbar.jsx";
import { ContactSection } from "./ContactSection.jsx";
import { Solutions } from "./Solutions.jsx";
import "./Landing.css";

const HIGHLIGHTS = [
  {
    icon: ShieldCheck,
    title: "No invasivo",
    text: "Medición óptica experimental",
  },
  { icon: BarChart3, title: "Seguimiento", text: "Historial y estadísticas" },
  {
    icon: Users,
    title: "Uso personal e institucional",
    text: "Individual, familiar o institucional",
  },
];

const STEPS = [
  {
    icon: Fingerprint,
    title: "Colocá el dedo en el sensor",
    text: "Un sensor óptico registra la señal de tu pulso sin pinchazos.",
  },
  {
    icon: Activity,
    title: "Se procesan las señales",
    text: "GlucoLume calcula oximetría y frecuencia cardíaca, y una estimación experimental de glucosa.",
  },
  {
    icon: LineChart,
    title: "Consultá tu historial",
    text: "Tus resultados quedan guardados para seguir su evolución y compararlos con un glucómetro capilar.",
  },
];

function useActiveSection() {
  // Sin sección activa mientras se ve el hero (no figura en la navegación).
  const [active, setActive] = useState(null);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length)
          setActive(
            visible[0].target.id === "inicio" ? null : visible[0].target.id,
          );
      },
      { rootMargin: "-40% 0px -55% 0px" },
    );
    ["inicio", ...SECTIONS.map(({ id }) => id)].forEach((id) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, []);
  return active;
}

function DeviceMockup() {
  return (
    <div className="mockup" aria-hidden="true">
      <div className="mockup-screen">
        <aside className="mockup-sidebar">
          <div className="mockup-brand">
            <LogoMark size={16} />
            <span>
              Gluco<b>Lume</b>
            </span>
          </div>
          {[
            "Mis mediciones",
            "Dispositivo",
            "Historial",
            "Estadísticas",
            "Notificaciones",
          ].map((item, i) => (
            <span key={item} className={i === 0 ? "is-active" : undefined}>
              {item}
            </span>
          ))}
        </aside>
        <div className="mockup-main">
          <strong>Nueva medición</strong>
          <div className="mockup-tabs">
            <span>Oximetría</span>
            <span className="is-active">Glucosa (experimental)</span>
          </div>
          <div className="mockup-body">
            <div className="mockup-wave">
              <svg viewBox="0 0 200 80" preserveAspectRatio="none">
                <path
                  d="M0 50 L20 50 L28 20 L36 65 L44 45 L60 45 L68 15 L76 62 L84 44 L100 44 L108 18 L116 64 L124 46 L140 46 L148 22 L156 63 L164 45 L200 45"
                  fill="none"
                  stroke="#e3101e"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="mockup-start">Iniciar medición</span>
            </div>
            <div className="mockup-metrics">
              <div>
                <HeartPulse size={16} className="tone-teal" />
                <small>SpO₂</small>
                <b>98 %</b>
              </div>
              <div>
                <Activity size={16} />
                <small>Frecuencia cardíaca</small>
                <b>72 bpm</b>
              </div>
              <div>
                <Droplet size={16} />
                <small>Glucosa (estimación)</small>
                <b className="tone-red">102 mg/dL</b>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="mockup-base" />
    </div>
  );
}

export default function Landing() {
  const active = useActiveSection();

  // Al llegar desde otra página con /#seccion, la sección existe recién después del primer render.
  // También se ejecuta si ya estás en la Landing y cambia el ancla (p. ej. al tocar el logo).
  const { hash } = useLocation();
  useEffect(() => {
    const id = hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);

  return (
    <div className="landing">
      <SkipLink />
      <Navbar activeSection={active} />

      <main id="contenido" tabIndex={-1}>
        <section id={ACADEMIC_PROJECT_ID} className="hero">
          <div className="container hero-grid">
            <div className="hero-copy">
              <span className="pill">
                <GraduationCap size={16} aria-hidden="true" /> Proyecto
                académico
              </span>
              <h1>
                Tecnología al servicio <br className="hide-sm" />
                del <span className="accent">bienestar</span>
              </h1>
              <p className="lead">
                GlucoLume es una plataforma experimental para la adquisición,
                almacenamiento y análisis de señales ópticas orientadas a la
                estimación no invasiva de glucosa, con medición de oximetría y
                comparación con glucómetro capilar.
              </p>
              <ul className="highlights">
                {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
                  <li key={title}>
                    <span className="icon-tile">
                      <Icon size={22} aria-hidden="true" />
                    </span>
                    <span>
                      <b>{title}</b>
                      <small>{text}</small>
                    </span>
                  </li>
                ))}
              </ul>
              <div className="hero-actions">
                <Link to="/login" className="btn btn-primary btn-lg">
                  Comenzar ahora <ArrowRight size={18} aria-hidden="true" />
                </Link>
                <a href="#que-es" className="btn btn-outline btn-lg">
                  Conocer más <ChevronDown size={18} aria-hidden="true" />
                </a>
              </div>
            </div>

            <div className="hero-visual">
              <DeviceMockup />
              <aside className="disclaimer">
                <FlaskConical size={22} aria-hidden="true" />
                <div>
                  <b>Prueba de concepto experimental</b>
                  <p>
                    GlucoLume no es un dispositivo médico. Los resultados son
                    estimaciones experimentales.
                  </p>
                </div>
              </aside>
            </div>
          </div>
        </section>

        <div className="container landing-notice">
          <ExperimentalNotice />
        </div>

        <section id="que-es" className="section">
          <div className="container split">
            <div>
              <span className="pill">
                <Stethoscope size={16} aria-hidden="true" /> ¿Qué es?
              </span>
              <h2>Una plataforma de investigación, no un dispositivo médico</h2>
            </div>
            <div className="prose">
              <p>
                GlucoLume combina un sensor óptico de pulso con una aplicación
                web para registrar señales, calcular oximetría y frecuencia
                cardíaca y explorar una estimación experimental de glucosa.
              </p>
              <p>
                Cada resultado puede compararse con un glucómetro capilar para
                evaluar el modelo. La información presentada no sustituye una
                evaluación, diagnóstico ni indicación de un profesional de la
                salud.
              </p>
            </div>
          </div>
        </section>

        <section id="como-funciona" className="section section-tinted">
          <div className="container">
            <div className="section-head">
              <span className="pill">
                <Activity size={16} aria-hidden="true" /> Cómo funciona
              </span>
              <h2>Tres pasos, sin pinchazos</h2>
            </div>
            <ol className="steps">
              {STEPS.map(({ icon: Icon, title, text }, index) => (
                <li key={title} className="card step">
                  <span className="step-number">{index + 1}</span>
                  <span className="icon-tile">
                    <Icon size={22} aria-hidden="true" />
                  </span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <Solutions />
        <ContactSection />
      </main>

      <SiteFooter />
    </div>
  );
}
