import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { Logo } from "./Logo.jsx";
import "./Navbar.css";

// Secciones de la Landing, en el orden en que aparecen. El logo lleva a «Proyecto académico» (sección de inicio de la Landing).
// Las que tienen `path` son páginas propias: el enlace va a esa ruta en vez de a un ancla.
export const SECTIONS = [
  { id: "que-es", label: "¿Qué es?" },
  { id: "como-funciona", label: "Cómo funciona" },
  { id: "soluciones", label: "Soluciones" },
  { id: "caracteristicas", label: "Características", path: "/caracteristicas" },
  { id: "contacto", label: "Contacto" },
];

/** Navegación pública. En la Landing las secciones son anclas; desde otras páginas vuelven a la Landing. */
export const ACADEMIC_PROJECT_ID = "proyecto-academico";

export function Navbar({ activeSection }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const onLanding = pathname === "/";

  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Logo
          to={`/#${ACADEMIC_PROJECT_ID}`}
          label="GlucoLume, ir a Proyecto académico"
        />
        <button
          type="button"
          className="navbar-toggle"
          aria-expanded={open}
          aria-controls="navbar-menu"
          aria-label={open ? "Cerrar menú" : "Abrir menú"}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
        <div
          id="navbar-menu"
          className={`navbar-menu${open ? " is-open" : ""}`}
        >
          <nav aria-label="Secciones">
            <ul className="navbar-links">
              {SECTIONS.map((section) => {
                const current = section.path
                  ? pathname === section.path
                  : onLanding && activeSection === section.id;
                const linkProps = {
                  className: current ? "is-active" : undefined,
                  "aria-current": current ? "true" : undefined,
                  onClick: () => setOpen(false),
                };
                return (
                  <li key={section.id}>
                    {section.path ? (
                      <Link to={section.path} {...linkProps}>
                        {section.label}
                      </Link>
                    ) : (
                      <a href={onLanding ? `#${section.id}` : `/#${section.id}`} {...linkProps}>
                        {section.label}
                      </a>
                    )}
                  </li>
                );
              })}
              <li>
                <Link
                  to="/consejos"
                  className={pathname.startsWith("/consejos") ? "is-active" : undefined}
                  aria-current={pathname.startsWith("/consejos") ? "page" : undefined}
                  onClick={() => setOpen(false)}
                >
                  Consejos
                </Link>
              </li>
            </ul>
          </nav>
          <div className="navbar-actions">
            <Link to="/login" className="btn btn-outline">
              Iniciar sesión
            </Link>
            <Link to="/registro" className="btn btn-primary">
              Registrarse
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
