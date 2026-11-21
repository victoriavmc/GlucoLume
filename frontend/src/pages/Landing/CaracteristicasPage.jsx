// /caracteristicas — página propia de «Características» (privacidad y tratamiento de datos), enlazada desde el navbar de la Landing.

import { Navbar } from "../../components/Navbar.jsx";
import { SiteFooter } from "../../components/SiteFooter.jsx";
import { SkipLink } from "../../components/SkipLink.jsx";
import { usePageMeta } from "../../utils/usePageMeta.js";
import { Features } from "./Features.jsx";
import "./Landing.css";

export default function CaracteristicasPage() {
  usePageMeta(
    "Características y privacidad · GlucoLume",
    "Privacidad por diseño en GlucoLume: control de tus datos, acceso y retención de la información, con referencia a la Ley 25.326. Prototipo académico.",
  );

  return (
    <div className="landing">
      <SkipLink />
      <Navbar />

      <main id="contenido" tabIndex={-1}>
        {/* Título de la página para lectores de pantalla (A-9): el visible es el h2 de la sección, sin cambiar el diseño. */}
        <h1 className="sr-only">Características y privacidad</h1>
        <Features />
      </main>

      <SiteFooter />
    </div>
  );
}
