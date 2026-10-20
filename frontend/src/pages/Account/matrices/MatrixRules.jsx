// Reglas de una matriz, en lectura: Criterios de aplicación → Intervalo de glucosa de referencia. Se muestran solo los criterios que
// corresponden a cada regla (sexo, edad, alimentación y tiempo desde la comida) y las reglas generales se identifican como tales. Sin
// JSON ni nombres de columnas. En pantallas chicas cada fila pasa a una tarjeta. El modelo actual de ReglaMatriz no guarda categoría,
// observaciones ni referencia por regla: no se muestran porque no existen.

import { Info } from 'lucide-react';

import { glucoseRange, isGeneralRule, ruleCriteria, sortRules } from './matrixFormat.js';
import './Matrices.css';

export function RulesTable({ rules, renderActions, caption = 'Reglas de la matriz' }) {
  const sorted = sortRules(rules);
  return (
    <div className="table-scroll">
      <table className="data-table rules-table" aria-label={caption}>
        <thead>
          <tr>
            <th scope="col">Regla</th>
            <th scope="col">Criterios de aplicación</th>
            <th scope="col">Intervalo de glucosa de referencia</th>
            {renderActions && <th scope="col"><span className="sr-only">Acciones</span></th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((rule, index) => (
            <tr key={rule.idReglaMatriz ?? `${rule.codigoRegla}-${index}`}>
              <th scope="row" data-label="Regla">
                <b>{rule.codigoRegla}</b>
                {isGeneralRule(rule) && <span className="rule-general"><Info size={14} aria-hidden="true" /> Regla general</span>}
              </th>
              <td data-label="Criterios de aplicación">
                <ul className="rule-criteria" aria-label={`Criterios de ${rule.codigoRegla}`}>
                  {ruleCriteria(rule).map((criterion) => (
                    <li key={criterion.key}><span>{criterion.label}</span> {criterion.value}</li>
                  ))}
                </ul>
              </td>
              <td data-label="Intervalo de glucosa de referencia"><span className="rule-range">{glucoseRange(rule)}</span></td>
              {renderActions && <td className="rule-actions">{renderActions(rule)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
