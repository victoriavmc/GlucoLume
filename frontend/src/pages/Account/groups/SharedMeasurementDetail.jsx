// Vista ampliada de UNA medición que otra persona del grupo compartió. Pide la medición a su propio endpoint, que vuelve a verificar la
// autorización (historial compartido, o última medición si solo compartió esa). No muestra observaciones, dispositivo, edad ni sexo.

import { ArrowLeft, FlaskConical } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';

import * as groupsApi from '../../../api/groupsApi.js';
import { friendlyError } from '../../../auth/errorMessages.js';
import { ExperimentalNotice } from '../../../components/ExperimentalNotice.jsx';
import { Alert } from '../../../components/FormControls.jsx';
import { DEMO_NOTICE, formatIndex } from '../measurements/measurementFormat.js';
import { MEALS, MODES, formatDateTime, formatNumber } from './groupFormat.js';
import { DEMO_LABEL, ORIGIN_LABELS, glucoseText } from './sharedMeasurementFormat.js';

export function SharedMeasurementDetail() {
  const { group } = useOutletContext();
  const { idGrupoUsuario, idMedicion } = useParams();
  const [state, setState] = useState({ data: null, error: null });

  useEffect(() => {
    let active = true;
    setState({ data: null, error: null });
    groupsApi.getSharedMeasurement(group.idGrupo, idGrupoUsuario, idMedicion).then(
      (data) => active && setState({ data, error: null }),
      (error) => active && setState({ data: null, error }),
    );
    return () => { active = false; };
  }, [group.idGrupo, idGrupoUsuario, idMedicion]);

  const { data, error } = state;
  const glucose = data ? glucoseText(data) : null;
  return (
    <>
      <Link to={`/app/grupo/${group.idGrupo}/compartidos?integrante=${idGrupoUsuario}`} className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Volver a los datos compartidos
      </Link>
      {error && <Alert>{friendlyError(error)}</Alert>}
      {!data && !error && <p className="field-hint" role="status">Cargando medición…</p>}
      {data && (
        <section className="panel measurement-detail" aria-labelledby="medicion-compartida">
          <div className="panel-title">
            <div>
              <h2 id="medicion-compartida">{MODES[data.modoMedicion] ?? data.modoMedicion} · {formatDateTime(data.fechaHoraInicio)}</h2>
              <p>
                Estado: {data.estadoMedicion === 'COMPLETADA' ? 'Completada' : data.estadoMedicion}
                {data.esUltima && ' · Última medición'}
                {data.esDemo && <> · <b>{DEMO_LABEL}</b></>}
              </p>
            </div>
          </div>
          {data.esDemo && <Alert kind="info"><FlaskConical size={16} aria-hidden="true" /> {DEMO_NOTICE}</Alert>}
          <ul className="result-grid" aria-label="Resultados compartidos">
            <li className="result-card"><small>Frecuencia cardíaca</small><b>{formatNumber(data.frecuenciaCardiaca, 'lpm')}</b></li>
            <li className="result-card"><small>SpO₂</small><b>{formatNumber(data.spo2, '%')}</b></li>
            <li className="result-card">
              <small>{data.esDemo ? 'Glucosa (valor DEMO, sintético)' : 'Glucosa'}</small>
              <b className={glucose ? undefined : 'is-empty'}>{glucose ? glucose.replace(/^Glucosa( \w+)?( \(simulada\))? /, '') : 'Sin dato'}</b>
            </li>
            <li className="result-card"><small>Índice óptico</small><b>{data.indiceOptico !== null ? formatIndex(data.indiceOptico) : 'Sin dato'}</b></li>
          </ul>
          <dl className="data-list" aria-label="Contexto de la medición compartida">
            <div><dt>Origen del resultado</dt><dd>{data.origenGlucosa ? (ORIGIN_LABELS[data.origenGlucosa] ?? data.origenGlucosa) : 'Sin dato'}</dd></div>
            <div><dt>Alimentación</dt><dd>{MEALS[data.condicionComida] ?? data.condicionComida}</dd></div>
            <div><dt>Fin</dt><dd>{data.fechaHoraFin ? formatDateTime(data.fechaHoraFin) : 'Sin dato'}</dd></div>
            <div><dt>Lecturas estabilizadas</dt><dd>{data.lecturasEstabilizadas ?? 'Sin dato'}</dd></div>
          </dl>
          <ExperimentalNotice variant="inline" />
        </section>
      )}
    </>
  );
}
