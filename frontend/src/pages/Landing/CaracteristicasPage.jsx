// /caracteristicas — página propia de «Características» (privacidad y tratamiento de datos), enlazada desde el navbar de la Landing.

import { Navbar } from "../../components/Navbar.jsx";
import { SiteFooter } from "../../components/SiteFooter.jsx";
import { SkipLink } from "../../components/SkipLink.jsx";
import { Features } from "./Features.jsx";
import "./Landing.css";

export default function CaracteristicasPage() {
  return (
    <div className="landing">
      <SkipLink />
      <Navbar />

      <main id="contenido" tabIndex={-1}>
        <Features />
      </main>

      <SiteFooter />
    </div>
  );
}
