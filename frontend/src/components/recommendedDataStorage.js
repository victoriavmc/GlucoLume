// Clave de localStorage de la postergación del aviso «Completá tu edad y sexo» (RecommendedDataModal). Va en un módulo aparte, sin
// dependencias, para que la prueba de configuración (src/test/setup.js) pueda usarla sin cargar la pantalla.
export function postponeKey(idUsuario) {
  return `glucolume.datosRecomendados.postergadoHasta.${idUsuario}`;
}
