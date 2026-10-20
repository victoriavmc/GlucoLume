// Aviso informativo (nunca un error ni un requisito): la edad y el sexo son opcionales para medir.

export const PROFILE_NOTICE = 'Podés realizar mediciones sin completar tu edad o sexo. Sin embargo, se recomienda informar estos datos para '
  + 'mejorar la contextualización de los resultados.';

export function RecommendedNotice({ profile }) {
  if (!profile?.perfilDisponible || !profile.datosRecomendados?.length) return null;
  return <p className="alert alert-info" role="status" id="datos-recomendados">{PROFILE_NOTICE}</p>;
}
