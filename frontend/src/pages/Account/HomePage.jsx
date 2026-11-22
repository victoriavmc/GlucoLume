// /app/inicio: pantalla inicial del espacio privado.
//   Cuenta individual: últimos valores medidos y glucosa reciente.
//   Cuenta institucional: saludo y fecha (los accesos están en el menú lateral).
// Los valores salen de las mediciones guardadas (nada inventado ni clasificado): se muestran con su origen, experimental o DEMO.

import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext.jsx';
import { Alert } from '../../components/FormControls.jsx';
import { DateBlock, HomeFilters, LatestKpis, MeasurementMix, RecentEvolution, WellbeingNotice } from './home/HomeParts.jsx';
import { useHomeData } from './home/useHomeData.js';
import { effectiveGrouping } from './measurements/evolutionModel.js';
import './home/home.css';

export default function HomePage() {
  const { account, flash } = useAuth();
  const { pathname } = useLocation();
  const notice = flash?.path === pathname ? flash.message : null;
  const user = account.usuario;
  const individual = user.tipoCuenta === 'CONSUMIDOR_FINAL';
  const firstName = user.nombre || user.usuario || '';
  const [chartDays, setChartDays] = useState(7);
  const [chosenGrouping, setChosenGrouping] = useState(null); // null: la agrupación por defecto de cada período
  const grouping = effectiveGrouping(chartDays, chosenGrouping);
  const { latest, chart, error } = useHomeData({ enabled: individual, chartDays });

  return (
    <div className="page is-wide home">
      <header className="home-head">
        <div className="home-greeting">
          <h1>Hola{firstName ? `, ${firstName}` : ''} <span className="home-wave" aria-hidden="true">👋</span></h1>
          <p className="home-lead">Nos alegra verte de nuevo en GlucoLume.</p>
          <p className="home-sub">Aquí podés ver tu resumen de salud y acceder rápidamente a las funciones más importantes.</p>
        </div>
        <div className="home-head-side">
          <DateBlock />
          <WellbeingNotice />
        </div>
      </header>

      {notice && (
        <Alert kind="success">
          {notice} <Link to="/app/seguridad">Ir a Seguridad</Link>
        </Alert>
      )}
      {error && <Alert>{error}</Alert>}

      {individual && <HomeFilters days={chartDays} onDaysChange={setChartDays} grouping={grouping} onGroupingChange={setChosenGrouping} />}
      {individual && <LatestKpis latest={latest} />}

      {individual && <MeasurementMix chart={chart} days={chartDays} grouping={grouping} />}

      {individual && <RecentEvolution chart={chart} days={chartDays} grouping={grouping} />}
    </div>
  );
}
