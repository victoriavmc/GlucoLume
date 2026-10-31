// Formatos en que se descarga una exportación. El backend decide qué sale y lo entrega en el formato pedido (`formato`): acá solo
// se elige cuál.

export const EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV (.csv)' },
  { value: 'xlsx', label: 'Excel (.xlsx)' },
  { value: 'pdf', label: 'PDF (.pdf)' },
];
