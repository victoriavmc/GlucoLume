// Descarta las respuestas viejas: si el usuario cambia un filtro o de página antes de que vuelva la consulta anterior, solo la ÚLTIMA puede
// actualizar la pantalla (sin esto, una respuesta lenta pisa a una más nueva y la lista muestra datos de otro filtro). También las invalida al
// desmontar la pantalla. Sirve para funciones de carga reutilizadas (eventos, intervalos) donde un indicador por efecto no alcanza.
//
//   const begin = useLatestRequest();
//   async function load() {
//     const isCurrent = begin();                 // invalida las consultas anteriores
//     const data = await api.list(filters);
//     if (isCurrent()) setPage(data);            // false si llegó otra consulta después o se desmontó
//   }

import { useCallback, useEffect, useRef } from 'react';

export function useLatestRequest() {
  const counter = useRef(0);

  useEffect(() => {
    const current = counter;
    return () => { current.current += 1; };
  }, []);

  return useCallback(() => {
    counter.current += 1;
    const mine = counter.current;
    return () => mine === counter.current;
  }, []);
}
