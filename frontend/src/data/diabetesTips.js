// Consejos educativos para personas con diabetes: contenido ESTÁTICO del frontend (sin backend ni base de datos).
//
// Cada artículo es una explicación propia, en español y en lenguaje sencillo, de recomendaciones publicadas por instituciones reconocidas.
// Las fuentes de abajo se consultaron una por una (título, institución y fecha tal como figuran en la página el día de la consulta):
// no se inventaron autores, cifras ni enlaces. Las páginas del CDC muestran «15 de mayo de 2024» sin aclarar si es publicación o revisión;
// por eso se informa como «fecha que figura en la página». Las que no muestran fecha se indican como «sin fecha visible».
//
// Esto es contenido EDUCATIVO general: no es un diagnóstico, no reemplaza la indicación de un profesional y no fija metas de glucosa
// para nadie. Los valores de GlucoLume son experimentales y, si son DEMO, simulados: no sirven para decisiones médicas.

export const DISCLAIMER =
  'La información presentada tiene fines educativos y no reemplaza la evaluación ni las recomendaciones de profesionales de la salud.';

export const CATEGORIES = [
  { id: 'alimentacion', label: 'Alimentación', shortLabel: 'Alimentación', icon: 'apple',
    description: 'Elegir alimentos, armar el plato, carbohidratos, fibra y hábitos al comer.' },
  { id: 'hidratacion', label: 'Hidratación', shortLabel: 'Hidratación', icon: 'water',
    description: 'Tomar agua, evitar bebidas azucaradas y cuidar los líquidos todos los días.' },
  { id: 'actividad', label: 'Actividad física', shortLabel: 'Actividad física', icon: 'walk',
    description: 'Caminatas, fuerza, equilibrio y precauciones para moverte con seguridad.' },
  { id: 'control', label: 'Control y seguimiento', shortLabel: 'Control', icon: 'clipboard',
    description: 'Controles de salud, registro de hábitos y educación sobre la diabetes.' },
  { id: 'pies', label: 'Cuidado de los pies', shortLabel: 'Pies', icon: 'foot',
    description: 'Revisión diaria, higiene, calzado y prevención de lesiones.' },
];

// ---------------------------------------------------------------------------------------------------------------------
// Fuentes verificadas (se reutilizan en varios artículos).
// ---------------------------------------------------------------------------------------------------------------------

const CDC_DATE = 'Fecha que figura en la página: 15 de mayo de 2024';
const NO_DATE = 'Sin fecha visible en la página';

const SOURCES = {
  cdcMealPlanning: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Diabetes Meal Planning',
    url: 'https://www.cdc.gov/diabetes/healthy-eating/diabetes-meal-planning.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcEatingOut: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Eating Out',
    url: 'https://www.cdc.gov/diabetes/healthy-eating/eating-out.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcDessert: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Can People With Diabetes Have Dessert?',
    url: 'https://www.cdc.gov/diabetes/healthy-eating/people-with-diabetes-dessert.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcBudget: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: '6 Tips for Eating Healthy on a Budget',
    url: 'https://www.cdc.gov/diabetes/healthy-eating/6-tips-eating-healthy-on-budget.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcCultural: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Diabetes and Cultural Foods',
    url: 'https://www.cdc.gov/diabetes/healthy-eating/diabetes-cultural-foods.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcSickDays: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Managing Sick Days',
    url: 'https://www.cdc.gov/diabetes/living-with/managing-sick-days.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcGetActive: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Get Active',
    url: 'https://www.cdc.gov/diabetes/living-with/physical-activity.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcHypoglycemia: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Low Blood Sugar (Hypoglycemia)',
    url: 'https://www.cdc.gov/diabetes/about/low-blood-sugar-hypoglycemia.html', dateNote: 'Fecha que figura en la página: 16 de mayo de 2024', language: 'en',
  },
  cdcMonitoring: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Monitoring Your Blood Sugar',
    url: 'https://www.cdc.gov/diabetes/diabetes-testing/monitoring-blood-sugar.html', dateNote: CDC_DATE, language: 'en',
  },
  cdcDsmes: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Referring Patients to DSMES',
    url: 'https://www.cdc.gov/diabetes/hcp/dsmes/', dateNote: CDC_DATE, language: 'en',
  },
  cdcFeetTips: {
    institution: 'CDC (Centros para el Control y la Prevención de Enfermedades, EE. UU.)', title: 'Tips for Healthy Feet Graphic',
    url: 'https://www.cdc.gov/diabetes/communication-resources/tips-for-healthy-feet.html', dateNote: CDC_DATE, language: 'en',
  },
  niddkHealthyLiving: {
    institution: 'NIDDK (Instituto Nacional de Diabetes y Enfermedades Digestivas y del Riñón, EE. UU.)', title: 'Healthy Living with Diabetes',
    url: 'https://www.niddk.nih.gov/health-information/diabetes/overview/healthy-living-with-diabetes', dateNote: 'Última revisión: octubre de 2023', language: 'en',
  },
  niddkManaging: {
    institution: 'NIDDK (Instituto Nacional de Diabetes y Enfermedades Digestivas y del Riñón, EE. UU.)', title: 'Managing Diabetes',
    url: 'https://www.niddk.nih.gov/health-information/diabetes/overview/managing-diabetes', dateNote: 'Última revisión: octubre de 2023', language: 'en',
  },
  niddkA1c: {
    institution: 'NIDDK (Instituto Nacional de Diabetes y Enfermedades Digestivas y del Riñón, EE. UU.)', title: 'The A1C Test & Diabetes',
    url: 'https://www.niddk.nih.gov/health-information/diagnostic-tests/a1c-test', dateNote: 'Última revisión: abril de 2018', language: 'en',
  },
  niddkFeet: {
    institution: 'NIDDK (Instituto Nacional de Diabetes y Enfermedades Digestivas y del Riñón, EE. UU.)', title: 'Diabetes & Foot Problems',
    url: 'https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/foot-problems', dateNote: 'Última revisión: enero de 2017', language: 'en',
  },
  niddkNeuropathy: {
    institution: 'NIDDK (Instituto Nacional de Diabetes y Enfermedades Digestivas y del Riñón, EE. UU.)', title: 'Peripheral Neuropathy',
    url: 'https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/nerve-damage-diabetic-neuropathies/peripheral-neuropathy',
    dateNote: 'Última revisión: febrero de 2018', language: 'en',
  },
  adaWater: {
    institution: 'ADA (Asociación Americana de Diabetes)', title: 'Why You Should Drink More Water',
    url: 'https://diabetes.org/food-nutrition/eating-healthy/why-drink-more-water', dateNote: NO_DATE, language: 'en',
  },
  adaFeet: {
    institution: 'ADA (Asociación Americana de Diabetes)', title: '8 Tips to Protect Your Feet with Diabetes',
    url: 'https://diabetes.org/health-wellness/diabetes-and-your-feet/8-tips-protect-your-feet', dateNote: NO_DATE, language: 'en',
  },
  whoHealthyDiet: {
    institution: 'OMS (Organización Mundial de la Salud)', title: 'Alimentación saludable',
    url: 'https://www.who.int/es/news-room/fact-sheets/detail/healthy-diet', dateNote: 'Nota descriptiva del 26 de enero de 2026', language: 'es',
  },
  whoActivity: {
    institution: 'OMS (Organización Mundial de la Salud)', title: 'Physical activity (nota descriptiva)',
    url: 'https://www.who.int/news-room/fact-sheets/detail/physical-activity', dateNote: 'Nota descriptiva del 26 de junio de 2024', language: 'en',
  },
  whoDiabetes: {
    institution: 'OMS (Organización Mundial de la Salud)', title: 'Diabetes (nota descriptiva)',
    url: 'https://www.who.int/news-room/fact-sheets/detail/diabetes', dateNote: 'Nota descriptiva del 14 de noviembre de 2024', language: 'en',
  },
  idfActivity: {
    institution: 'IDF (Federación Internacional de Diabetes)', title: 'Physical activity for diabetes and gestational diabetes and blood sugar control',
    url: 'https://idf.org/managing-diabetes/physical-activity/', dateNote: 'Publicada el 20 de agosto de 2024', language: 'en',
  },
  msalGrafica: {
    institution: 'Ministerio de Salud de la Nación (Argentina)', title: 'Gráfica de alimentación saludable',
    url: 'https://www.argentina.gob.ar/salud/alimentacion-saludable/grafico', dateNote: NO_DATE, language: 'es',
  },
};

const s = (...keys) => keys.map((key) => SOURCES[key]);

// ---------------------------------------------------------------------------------------------------------------------
// Artículos. `content`: bloques { type: 'p' | 'h' | 'list' | 'note' }. `featured`: se muestra en Inicio (2 por categoría).
// ---------------------------------------------------------------------------------------------------------------------

export const ARTICLES = [
  // ------------------------------------------------------------------------------------------------- Alimentación
  {
    id: 'metodo-del-plato', category: 'alimentacion', icon: 'plate', featured: true,
    title: 'El método del plato: una forma simple de armar tus comidas',
    summary: 'Dividí el plato en tres partes: verduras, proteínas y alimentos con carbohidratos.',
    content: [
      { type: 'p', text: 'Armar el plato con un orden sencillo ayuda a comer variado sin tener que hacer cuentas en cada comida. El CDC propone usar un plato de unos 23 cm (9 pulgadas) y dividirlo en tres partes.' },
      { type: 'list', items: [
        'La mitad del plato: verduras sin almidón, como ensalada, chauchas o brócoli.',
        'Un cuarto del plato: proteínas magras, como pollo, legumbres, tofu o huevo.',
        'Un cuarto del plato: alimentos con carbohidratos, como arroz, pan, papa o fideos.',
      ] },
      { type: 'p', text: 'Para acompañar, elegí agua u otra bebida sin calorías. Así evitás sumar azúcar sin darte cuenta.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Probá armar así tu próximo almuerzo o cena y fijate cómo se ve el plato.',
        'Si cocinás para toda la familia, servite vos mismo el plato con esta división.',
        'Pedí a tu médico o a un nutricionista que adapte el método a tus gustos, tus horarios y tus medicamentos.',
      ] },
      { type: 'note', text: 'Es una guía general. Cuánto y qué conviene comer depende de cada persona y lo define tu equipo de salud.' },
    ],
    sources: s('cdcMealPlanning', 'niddkHealthyLiving'),
  },
  {
    id: 'carbohidratos-parejos', category: 'alimentacion', icon: 'bread', featured: false,
    title: 'Carbohidratos: por qué importan y cómo repartirlos',
    summary: 'Los carbohidratos son los que más influyen en el azúcar en sangre. Repartirlos parejo ayuda.',
    content: [
      { type: 'p', text: 'Los carbohidratos están en el pan, el arroz, los fideos, la papa, las frutas, la leche y los dulces. Al digerirlos, el cuerpo los convierte en glucosa, por eso influyen en el azúcar en sangre y conviene tenerlos en cuenta al armar las comidas.' },
      { type: 'p', text: 'El CDC sugiere llevar la cuenta de los carbohidratos que comés en cada comida y tratar de que la cantidad sea parecida de una comida a otra. Comer en horarios regulares también ayuda a evitar subas y bajas bruscas.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Comé a horarios parecidos todos los días y evitá saltearte comidas.',
        'Consultá con un nutricionista cuántos carbohidratos te convienen en cada comida: no hay una cifra igual para todos.',
        'Para organizar tus comidas existen dos métodos muy usados: contar carbohidratos y el método del plato.',
        'Si tomás medicamentos para la diabetes, preguntá a tu equipo cómo se relacionan con los horarios de comida.',
      ] },
      { type: 'note', text: 'No cambies tu medicación por tu cuenta. Cualquier ajuste lo decide tu médico.' },
    ],
    sources: s('cdcMealPlanning', 'niddkHealthyLiving'),
  },
  {
    id: 'frutas-y-verduras', category: 'alimentacion', icon: 'salad', featured: true,
    title: 'Frutas y verduras todos los días',
    summary: 'Variadas y de estación: aportan fibra y nutrientes. Consultá cuántas frutas te convienen.',
    content: [
      { type: 'p', text: 'La OMS recomienda que los adultos coman al menos 400 gramos de frutas y verduras por día. Las Guías Alimentarias argentinas proponen que ocupen la mayor parte de lo que comés: cinco porciones diarias, la mitad del plato en el almuerzo y en la cena, y dos o tres frutas por día.' },
      { type: 'p', text: 'Elegir variedad y colores distintos es una buena regla, y las de estación suelen ser más baratas y de mejor calidad.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Sumá una verdura a cada almuerzo y cena: cruda en ensalada, cocida al horno o en sopa.',
        'Dejá la fruta entera a mano para la merienda en lugar de galletitas o golosinas.',
        'Preferí la fruta entera antes que el jugo: la OMS aconseja limitar los jugos, porque la mayoría tiene mucha azúcar libre.',
      ] },
      { type: 'note', text: 'Las frutas tienen azúcares naturales que también influyen en la glucosa. Preguntá a tu nutricionista cuántas porciones y de qué tipo te convienen.' },
    ],
    sources: s('whoHealthyDiet', 'msalGrafica'),
  },
  {
    id: 'comer-fuera-de-casa', category: 'alimentacion', icon: 'restaurant', featured: false,
    title: 'Comer afuera sin complicaciones',
    summary: 'Pensá qué pedir antes de llegar, cuidá las porciones y compartí el plato.',
    content: [
      { type: 'p', text: 'Salir a comer es parte de la vida social y se puede disfrutar con un poco de planificación. El CDC da consejos simples para antes y durante la comida.' },
      { type: 'h', text: 'Antes de sentarte' },
      { type: 'list', items: [
        'Decidí qué vas a pedir antes de ir, para no elegir apurado o tentado.',
        'Si vas a comer más tarde que de costumbre, podés comer algo chico antes, con fibra y proteína (por ejemplo, un puñado de frutas secas), y comer un poco menos en la comida.',
      ] },
      { type: 'h', text: 'En la mesa' },
      { type: 'list', items: [
        'Tomá un vaso grande de agua apenas te sentás: puede ayudarte a comer menos.',
        'Limitá el pan o las papas fritas de entrada, o pedí que los retiren.',
        'Elegí platos al horno, al vapor, a la plancha o a la parrilla; limitá los fritos, empanados o con cremas.',
        'Pedí verduras en lugar de papas fritas.',
        'Pedí las salsas y los aderezos aparte y usá solo lo necesario para darle sabor.',
        'Compartí el plato principal, o comé la mitad y llevate el resto.',
      ] },
    ],
    sources: s('cdcEatingOut'),
  },
  {
    id: 'postres-con-medida', category: 'alimentacion', icon: 'dessert', featured: false,
    title: '¿Se puede comer postre? Sí, con planificación',
    summary: 'Las personas con diabetes no tienen que evitar los postres por completo.',
    content: [
      { type: 'p', text: 'Según el CDC, vivir con diabetes no significa dejar los dulces para siempre. Lo importante es planificarlos y comerlos con moderación.' },
      { type: 'h', text: 'Ideas para disfrutarlos' },
      { type: 'list', items: [
        'Si sabés que vas a comer postre, comé menos carbohidratos en el resto de la comida.',
        'Comelo con la comida o justo después, y despacio: puede ayudarte a comer una porción más chica sin sentir que te privás.',
        'Elegí porciones chicas o compartí el postre.',
        'Probá la fruta como relleno o para calmar el antojo de algo dulce.',
        'En las tortas y budines, la banana pisada o el puré de manzana pueden endulzar de forma natural.',
      ] },
      { type: 'note', text: 'Las frutas igual tienen azúcares naturales que influyen en la glucosa. Consultá con tu equipo de salud qué cantidades te convienen.' },
    ],
    sources: s('cdcDessert'),
  },
  {
    id: 'comida-tradicional-y-presupuesto', category: 'alimentacion', icon: 'cart', featured: false,
    title: 'Comidas de siempre y compras con presupuesto ajustado',
    summary: 'Tus platos tradicionales pueden seguir en la mesa, y comer sano no tiene que ser caro.',
    content: [
      { type: 'p', text: 'El CDC remarca que las comidas tradicionales pueden formar parte de una alimentación saludable con diabetes. Muchas incluyen ingredientes muy buenos, como las legumbres (porotos, lentejas, arvejas), que aportan proteínas y fibra.' },
      { type: 'p', text: 'En lugar de dejar tus platos favoritos, se pueden ajustar: por ejemplo, usar pollo sin piel con arroz integral, o lentejas con coliflor en vez de papas en un guiso. Comentá con tu equipo de salud qué comidas de tu cultura querés mantener, así te ayudan a armar un plan que te guste.' },
      { type: 'h', text: 'Comer bien gastando menos' },
      { type: 'list', items: [
        'Planificá el menú de la semana y adaptá tus recetas favoritas.',
        'Hacé las compras con lista: así evitás compras de impulso y viajes de más.',
        'Comprá legumbres, frutos secos y cereales a granel si podés.',
        'Las verduras congeladas o en lata pueden ser opciones sanas y baratas: elegí las envasadas al natural (no en almíbar) y mirá la etiqueta por azúcar o sal agregados.',
        'Las marcas propias de los supermercados suelen costar menos.',
        'Si tenés lugar, cultivá hierbas o verduras en macetas.',
      ] },
    ],
    sources: s('cdcCultural', 'cdcBudget'),
  },

  // -------------------------------------------------------------------------------------------------- Hidratación
  {
    id: 'agua-bebida-principal', category: 'hidratacion', icon: 'water', featured: true,
    title: 'El agua, tu bebida principal',
    summary: 'Tomá agua a lo largo del día, sin esperar a tener sed.',
    content: [
      { type: 'p', text: 'El NIDDK recomienda elegir como bebidas principales el agua, la leche descremada o semidescremada, y el té, el café o el agua con gas sin azúcar. El Ministerio de Salud de Argentina propone tomar a diario ocho vasos de agua segura (al menos dos litros de líquidos sin azúcar, preferentemente agua) y no esperar a tener sed para hidratarse.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Tené siempre una botella o un vaso de agua a la vista.',
        'Tomá un vaso al levantarte y otro antes de las comidas.',
        'Si el agua sola no te gusta, podés darle sabor con rodajas de limón, pepino o hojas de menta, sin agregar azúcar.',
        'Usá agua segura para beber, lavar los alimentos y cocinar.',
      ] },
      { type: 'note', text: 'Si tenés una condición que exige limitar los líquidos (por ejemplo, ciertos problemas del corazón o del riñón), consultá a tu médico antes de cambiar cuánto tomás.' },
    ],
    sources: s('niddkHealthyLiving', 'msalGrafica', 'adaWater'),
  },
  {
    id: 'bebidas-azucaradas', category: 'hidratacion', icon: 'soda', featured: true,
    title: 'Bebidas azucaradas: mejor dejarlas para pocas ocasiones',
    summary: 'Gaseosas, jugos y aguas saborizadas aportan mucha azúcar sin aportar nutrientes.',
    content: [
      { type: 'p', text: 'El NIDDK aconseja limitar las bebidas azucaradas: gaseosas, jugos, café saborizado y bebidas deportivas. El Ministerio de Salud de Argentina las ubica entre los productos que no deberían ser parte de la alimentación diaria, y propone tomar agua segura en su lugar. Esto incluye las gaseosas, los jugos industrializados y las aguas saborizadas.' },
      { type: 'p', text: 'La OMS recomienda que los azúcares libres (los agregados a los alimentos y bebidas, y los de la miel, los jarabes y los jugos) sean menos del 10 % de las calorías del día. Eso equivale a unos 50 gramos, alrededor de 12 cucharaditas rasas, para una persona que come unas 2000 calorías. También indica limitar los jugos de fruta, porque la mayoría tiene mucha azúcar libre aunque no se le haya agregado.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Cambiá la gaseosa o el jugo por agua, agua con gas o té y café sin azúcar.',
        'Mirá la etiqueta de las bebidas: buscá la palabra «azúcares».',
        'Si tomás una bebida dulce de vez en cuando, que sea una porción chica y sin que se vuelva rutina.',
        'Cuidá también el azúcar que agregás al té o al café.',
      ] },
    ],
    sources: s('niddkHealthyLiving', 'msalGrafica', 'whoHealthyDiet'),
  },
  {
    id: 'tomar-mas-agua', category: 'hidratacion', icon: 'bottle', featured: false,
    title: 'Trucos para tomar más agua durante el día',
    summary: 'Pequeños hábitos que ayudan a hidratarte mejor, incluso si no te da sed.',
    content: [
      { type: 'p', text: 'La Asociación Americana de Diabetes (ADA) explica que estar bien hidratado ayuda al cuerpo a regular la temperatura y la presión arterial, y a mantener el equilibrio de minerales y hormonas. Además, la sed suele ser una señal de que ya estás algo deshidratado.' },
      { type: 'h', text: 'Ideas prácticas' },
      { type: 'list', items: [
        'Tomá un vaso de agua apenas te levantás y antes de las comidas.',
        'Usá una botella reutilizable y poné recordatorios en el celular.',
        'Agregale sabor con frutas (limón, ananá, sandía), pepino o menta.',
        'Contá también los alimentos con mucha agua, como frutas y verduras.',
        'Tomá más cuando hace calor y humedad, o cuando hacés actividad física.',
        'Fijate en el color de la orina: amarillo claro o transparente suele indicar buena hidratación; más oscuro, que necesitás tomar más.',
      ] },
      { type: 'p', text: 'La ADA también señala que el alcohol y las bebidas con cafeína pueden aumentar la pérdida de líquidos. Si sentís mareo, boca seca, cansancio inusual o dolor de cabeza, puede ser un signo de poca hidratación.' },
      { type: 'note', text: 'La cantidad de líquido que necesita cada persona varía con la edad, la actividad, el clima y las condiciones de salud. Si tenés dudas, consultá a tu médico.' },
    ],
    sources: s('adaWater'),
  },
  {
    id: 'liquidos-si-estas-enfermo', category: 'hidratacion', icon: 'thermometer', featured: false,
    title: 'Si estás enfermo: cuidá los líquidos y consultá',
    summary: 'Cuando hay fiebre, vómitos o diarrea, la deshidratación puede aparecer rápido.',
    content: [
      { type: 'p', text: 'Una gripe, una infección u otra enfermedad pueden elevar el azúcar en sangre y favorecer la deshidratación. El CDC recomienda tomar mucha agua durante esos días y tratar de comer como siempre. Si no podés comer, consultá a tu médico cómo reponer carbohidratos con líquidos.' },
      { type: 'h', text: 'Qué aconseja el CDC' },
      { type: 'list', items: [
        'Tomá mucha agua para prevenir la deshidratación.',
        'Controlá tu glucosa con la frecuencia que te indique tu médico: durante la enfermedad puede pedirte hacerlo más seguido.',
        'Tené a mano alimentos fáciles de preparar (sopas, galletitas, cereales instantáneos) y los elementos de tu botiquín.',
        'No dejes de usar tus medicamentos para la diabetes por tu cuenta: preguntá a tu equipo qué hacer cuando estás enfermo.',
      ] },
      { type: 'h', text: 'Cuándo pedir ayuda urgente' },
      { type: 'p', text: 'El CDC indica ir a una guardia si no podés retener líquidos durante más de 4 horas, si tenés vómitos o diarrea fuertes por más de 6 horas, si te cuesta respirar, o si te sentís muy cansado o confundido. En ese caso, pedí que alguien te acompañe o llame por vos.' },
      { type: 'note', text: 'Es información general. Pedí a tu equipo de salud un plan para los días de enfermedad adaptado a tu tratamiento.' },
    ],
    sources: s('cdcSickDays'),
  },
  {
    id: 'hidratacion-y-actividad', category: 'hidratacion', icon: 'run', featured: false,
    title: 'Tomar líquidos cuando te movés',
    summary: 'Hidratarte antes, durante y después de la actividad ayuda a evitar la deshidratación.',
    content: [
      { type: 'p', text: 'El NIDDK recomienda tomar líquidos durante la actividad física para prevenir la deshidratación. La Federación Internacional de Diabetes (IDF) agrega que beber agua con regularidad ayuda a mantener la glucosa y a evitar la deshidratación.' },
      { type: 'p', text: 'Para una actividad moderada, como caminar, no hace falta tomar bebidas deportivas: suelen tener bastante azúcar y calorías. El agua suele ser suficiente.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Llevá una botellita de agua cuando salgas a caminar.',
        'Tomá unos sorbos antes, durante y después de moverte.',
        'Con calor o humedad, tomá más y descansá a la sombra.',
        'Preguntá a tu equipo de salud si necesitás comer algo antes o después de la actividad.',
      ] },
    ],
    sources: s('niddkHealthyLiving', 'idfActivity'),
  },

  // ------------------------------------------------------------------------------------------- Actividad física
  {
    id: 'minutos-por-semana', category: 'actividad', icon: 'walk', featured: true,
    title: '150 minutos por semana: de a poco y a tu ritmo',
    summary: 'La meta general es moverte unos 30 minutos casi todos los días, aunque sea en tandas cortas.',
    content: [
      { type: 'p', text: 'El CDC, el NIDDK y la OMS coinciden en una recomendación general para adultos: al menos 150 minutos por semana de actividad de intensidad moderada, como caminar a paso ligero. Eso se puede lograr con unos 30 minutos casi todos los días, y el NIDDK aclara que dividirlos en períodos cortos también cuenta.' },
      { type: 'p', text: 'Moverte con regularidad ayuda a manejar la diabetes y también favorece el corazón, el peso, el ánimo y el sueño.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Si hace tiempo que no te movés, empezá con poco y aumentá de a poco.',
        'Repartí el tiempo: tres caminatas de 10 minutos suman lo mismo que una de 30.',
        'Elegí algo que te guste y puedas hacer seguido.',
        'Antes de empezar una actividad nueva o más exigente, hablalo con tu médico.',
      ] },
      { type: 'note', text: 'Son metas generales para adultos. Tu médico puede indicarte otras según tu salud, tus medicamentos y tu edad.' },
    ],
    sources: s('cdcGetActive', 'niddkHealthyLiving', 'whoActivity'),
  },
  {
    id: 'caminata-despues-de-cenar', category: 'actividad', icon: 'sunset', featured: true,
    title: 'Empezá con una caminata corta después de cenar',
    summary: 'Diez minutos son un buen punto de partida y fáciles de sostener.',
    content: [
      { type: 'p', text: 'No hace falta ir al gimnasio durante horas para obtener beneficios. El CDC propone un objetivo claro y alcanzable para empezar: una caminata de 10 minutos después de cenar. Con el tiempo se puede ir sumando.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Elegí un horario fijo para que se vuelva un hábito.',
        'Invitá a alguien de la familia o a un vecino: acompañarse ayuda a no abandonar.',
        'Procurá no pasar más de dos días seguidos sin moverte.',
        'Preguntale a tu médico qué actividades te convienen y cuáles conviene evitar en tu caso.',
      ] },
      { type: 'note', text: 'El CDC también sugiere comprobar tu glucosa antes y después de caminar para ver cómo reacciona tu cuerpo. Consultá a tu equipo cómo hacerlo en tu caso.' },
    ],
    sources: s('cdcGetActive'),
  },
  {
    id: 'fuerza-y-equilibrio', category: 'actividad', icon: 'strength', featured: false,
    title: 'Fuerza y equilibrio: dos aliados que se olvidan',
    summary: 'Ejercicios simples dos o tres veces por semana ayudan a mantener los músculos y a evitar caídas.',
    content: [
      { type: 'p', text: 'Además de caminar, el NIDDK recomienda hacer ejercicios de fuerza unas dos veces por semana y actividades de equilibrio o de estiramiento dos o tres veces por semana. La Federación Internacional de Diabetes (IDF) también aconseja trabajar la fuerza al menos dos veces por semana, por ejemplo con pesas livianas o bandas elásticas.' },
      { type: 'p', text: 'Según la IDF, la fuerza ayuda a construir músculo, a mejorar la sensibilidad a la insulina y a prevenir la pérdida de músculo.' },
      { type: 'h', text: 'Ideas para empezar' },
      { type: 'list', items: [
        'Levantarte y sentarte de una silla varias veces, sin usar las manos si podés.',
        'Elevar los brazos con botellitas de agua como pesas livianas.',
        'Estiramientos suaves después de caminar.',
        'Pedí a un profesional de la salud o a un kinesiólogo que te muestre ejercicios adecuados para vos.',
      ] },
      { type: 'note', text: 'Empezá despacio y con ayuda profesional si tenés dolores, mareos o problemas de equilibrio.' },
    ],
    sources: s('niddkHealthyLiving', 'idfActivity'),
  },
  {
    id: 'glucosa-antes-y-despues', category: 'actividad', icon: 'meter', featured: false,
    title: 'Cómo reacciona tu cuerpo: controlá antes y después de moverte',
    summary: 'El ejercicio puede modificar la glucosa durante horas. Conocer tu respuesta te da seguridad.',
    content: [
      { type: 'p', text: 'La actividad física puede cambiar el azúcar en sangre, y ese efecto a veces dura horas. El NIDDK recomienda controlar la glucosa antes, durante y después de la actividad, y avisa que los valores pueden mantenerse bajos durante horas o incluso días. El CDC señala que, al controlar antes y después de una caminata, es probable que veas un valor más bajo después.' },
      { type: 'p', text: 'La Federación Internacional de Diabetes (IDF) agrega que algunas personas necesitan controlar más seguido, ajustar la comida o cambiar el horario o la dosis de su tratamiento. Eso lo debe decidir siempre tu médico.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Preguntá a tu equipo cuándo y con qué frecuencia controlar cuando hacés actividad.',
        'Anotá cómo te sentiste y qué valor tuviste antes y después, para detectar patrones.',
        'Consultá si necesitás comer algo antes o después de moverte.',
      ] },
      { type: 'note', text: 'Los valores de GlucoLume son experimentales (y los DEMO son simulados): no los uses para decidir sobre tu actividad ni tu tratamiento.' },
    ],
    sources: s('cdcGetActive', 'niddkHealthyLiving', 'idfActivity'),
  },
  {
    id: 'bajas-de-azucar-y-actividad', category: 'actividad', icon: 'alert', featured: false,
    title: 'Hipoglucemia (azúcar baja): señales y cómo prevenirla al hacer actividad',
    summary: 'La actividad puede ser una causa de azúcar baja. Conocé las señales y qué consultar.',
    content: [
      { type: 'p', text: 'La hipoglucemia es el descenso del azúcar en sangre por debajo de lo normal. Tu médico te indicará a partir de qué valor se considera baja en tu caso. El CDC explica que la cantidad y el horario de la actividad física son una de sus posibles causas, y que a veces aparece más tarde, por ejemplo durante la noche después de un día muy activo o si hacés ejercicio cerca de la hora de dormir.' },
      { type: 'h', text: 'Señales frecuentes (CDC)' },
      { type: 'list', items: [
        'Latidos rápidos, temblores y sudor.',
        'Nerviosismo, irritabilidad o confusión.',
        'Mareo y hambre.',
      ] },
      { type: 'p', text: 'En las bajas graves puede haber debilidad, dificultad para caminar o ver bien, conducta extraña, convulsiones o desmayo. Una persona con una baja grave suele necesitar ayuda de otra para tratarla. Algunas personas no sienten síntomas (hipoglucemia inadvertida): el CDC aconseja que, en ese caso, controlen con más frecuencia, sobre todo antes de manejar o de hacer actividad física.' },
      { type: 'h', text: 'Para tener en cuenta' },
      { type: 'list', items: [
        'Comé de forma regular y no te saltees comidas.',
        'Hablá con tu equipo de salud sobre cómo prevenir bajas cuando hacés actividad y qué hacer si ocurren.',
        'Si tomás alcohol, hacelo con comida.',
      ] },
      { type: 'note', text: 'Ante una baja grave, o si no sabés qué hacer, pedí ayuda médica de inmediato.' },
    ],
    sources: s('cdcHypoglycemia', 'idfActivity'),
  },
  {
    id: 'todo-movimiento-suma', category: 'actividad', icon: 'steps', featured: false,
    title: 'Todo movimiento suma: menos tiempo sentado',
    summary: 'Cualquier actividad es mejor que ninguna, y conviene interrumpir las horas sentado.',
    content: [
      { type: 'p', text: 'La OMS afirma que cualquier cantidad de actividad física es mejor que ninguna y que toda la actividad cuenta. También recomienda que personas de todas las edades limiten el tiempo que pasan sentadas.' },
      { type: 'p', text: 'Esto es especialmente útil si todavía no llegás a los 150 minutos semanales: lo importante es moverte un poco más de lo que te movés hoy.' },
      { type: 'h', text: 'Ideas para sumar movimiento en el día' },
      { type: 'list', items: [
        'Levantate cada tanto cuando mires televisión o estés mucho tiempo sentado.',
        'Subí escaleras en lugar del ascensor si tu salud te lo permite.',
        'Hacé los mandados caminando.',
        'Dedicá unos minutos a estirarte o a hacer tareas de la casa o del jardín.',
      ] },
      { type: 'note', text: 'Si tenés dolor, mareos o dudas sobre qué actividad es segura para vos, preguntale a tu médico.' },
    ],
    sources: s('whoActivity', 'cdcGetActive'),
  },

  // -------------------------------------------------------------------------------------- Control y seguimiento
  {
    id: 'controlar-glucosa-en-casa', category: 'control', icon: 'meter', featured: true,
    title: 'Controlar la glucosa en casa: para qué sirve',
    summary: 'Medirte y anotar los resultados ayuda a entender cómo influyen la comida, el movimiento y los medicamentos.',
    content: [
      { type: 'p', text: 'El CDC presenta el control de la glucosa en casa como un paso muy importante. La comida, los medicamentos y la actividad hacen subir o bajar el azúcar, y medir con regularidad te muestra qué cosas influyen en tus números.' },
      { type: 'p', text: 'Cuántas veces conviene medir y cuáles son tus valores objetivo los define tu médico. Los rangos generales que se publican pueden no corresponder a tu caso: según la edad, el estado de salud y el tratamiento, tu objetivo personal puede ser distinto.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Preguntá a tu equipo con qué frecuencia medir y cuáles son tus objetivos.',
        'Usá la memoria del medidor o una aplicación, o anotá los valores en un cuaderno si no usás celular.',
        'Anotá si hubo algo que pudo influir en el resultado: una comida, un medicamento, actividad física o una enfermedad.',
        'Llevá tus registros a cada consulta.',
      ] },
      { type: 'note', text: 'GlucoLume es un prototipo experimental: sus valores no reemplazan un medidor de glucosa aprobado ni se usan para decidir tu tratamiento.' },
    ],
    sources: s('cdcMonitoring', 'niddkManaging'),
  },
  {
    id: 'prueba-de-a1c', category: 'control', icon: 'drop', featured: true,
    title: 'La prueba de A1C: el promedio de los últimos meses',
    summary: 'Un análisis de sangre que muestra cómo estuvo tu glucosa en promedio durante unos 3 meses.',
    content: [
      { type: 'p', text: 'La A1C (hemoglobina glicosilada) es un análisis de sangre que estima tu nivel promedio de glucosa durante los últimos 3 meses aproximadamente. A diferencia de un control con el medidor, que muestra un instante, la A1C da una mirada más amplia.' },
      { type: 'p', text: 'El NIDDK y el CDC indican que las personas con diabetes suelen hacerse esta prueba al menos dos veces por año. Si no se logran los objetivos del tratamiento, el médico puede pedirla más seguido.' },
      { type: 'h', text: 'Tu objetivo es personal' },
      { type: 'p', text: 'El NIDDK aclara que cada persona puede tener un objetivo de A1C distinto, según su historia con la diabetes y su salud general. Un objetivo más bajo no es seguro para todos, sobre todo si provoca bajas peligrosas de glucosa. Por eso es importante hablar con tu médico sobre cuál es el tuyo.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Preguntá cada cuánto te conviene hacerte la A1C y qué objetivo tenés vos.',
        'Anotá la fecha y el resultado de cada análisis.',
      ] },
    ],
    sources: s('niddkA1c', 'cdcMonitoring'),
  },
  {
    id: 'registro-de-habitos', category: 'control', icon: 'notebook', featured: false,
    title: 'Llevá un registro: tu cuaderno de hábitos',
    summary: 'Anotar comidas, actividad y controles te ayuda a vos y a tu equipo de salud.',
    content: [
      { type: 'p', text: 'El NIDDK sugiere llevar un registro de tus controles de glucosa junto con las comidas y la actividad. El CDC aconseja anotar además cualquier cosa que pueda haber influido en un resultado. Así es más fácil descubrir qué te hace bien y qué te hace subir o bajar el azúcar.' },
      { type: 'h', text: 'Qué conviene anotar' },
      { type: 'list', items: [
        'Fecha y hora de cada control y el valor.',
        'Qué comiste, y si fue antes o después del control.',
        'Si hiciste actividad física y cuánto.',
        'Cómo te sentiste, y si estuviste enfermo.',
        'Dudas para preguntar en la próxima consulta.',
      ] },
      { type: 'p', text: 'Podés usar un cuaderno, una planilla o una aplicación. Lo mejor es el método que realmente vayas a usar todos los días.' },
      { type: 'note', text: 'Llevá tu registro a cada consulta: es de mucha ayuda para que el equipo entienda cómo estás.' },
    ],
    sources: s('niddkManaging', 'cdcMonitoring'),
  },
  {
    id: 'tu-equipo-de-salud', category: 'control', icon: 'stethoscope', featured: false,
    title: 'Tu equipo de salud y cómo prepararte para las consultas',
    summary: 'Tu médico de cabecera coordina, y otros profesionales pueden sumarse al equipo.',
    content: [
      { type: 'p', text: 'Según el NIDDK, el profesional de atención primaria suele ser tu contacto principal. Puede sumarse a tu equipo un educador en diabetes, un nutricionista, un farmacéutico, un odontólogo, un oftalmólogo y un trabajador social, entre otros.' },
      { type: 'h', text: 'Para aprovechar cada consulta' },
      { type: 'list', items: [
        'Escribí una lista de preguntas antes de ir.',
        'Llevá tu registro de controles y tu lista de medicamentos.',
        'Tomá tus medicamentos como te los indicaron, aunque te sientas bien. Si el costo es un problema, contáselo a tu equipo en lugar de saltearte dosis.',
        'Consultá cada cuánto te conviene revisar la vista, los dientes, los pies, la presión y el colesterol.',
        'Si te sentís muy estresado, ansioso o desanimado, también es un tema para charlar con tu equipo.',
      ] },
    ],
    sources: s('niddkManaging'),
  },
  {
    id: 'educacion-en-diabetes', category: 'control', icon: 'book', featured: false,
    title: 'Educación en diabetes: aprender a manejarla con apoyo',
    summary: 'Hay programas de educación con profesionales que enseñan hábitos y habilidades para el día a día.',
    content: [
      { type: 'p', text: 'El CDC describe la educación y el apoyo para el automanejo de la diabetes (DSMES, por su sigla en inglés) como un servicio de capacitación, asesoramiento y seguimiento a cargo de un profesional de la salud especializado. No reemplaza a tu médico: lo complementa.' },
      { type: 'h', text: 'Para qué puede servir' },
      { type: 'list', items: [
        'Aprender hábitos clave para el manejo diario.',
        'Mejorar el control de la glucosa y de la A1C, de la presión y del colesterol.',
        'Prevenir o retrasar complicaciones.',
        'Ganar confianza y sentirte mejor para afrontar la diabetes.',
      ] },
      { type: 'h', text: 'Cuándo es buen momento' },
      { type: 'p', text: 'El CDC indica que conviene recibirla al momento del diagnóstico, durante las consultas médicas, cuando aparece una nueva complicación y cuando cambios en tu vida hacen más difícil manejar la diabetes.' },
      { type: 'note', text: 'Preguntá a tu médico o a tu cobertura de salud dónde se dan estos programas cerca tuyo.' },
    ],
    sources: s('cdcDsmes', 'niddkManaging'),
  },
  {
    id: 'chequeos-regulares', category: 'control', icon: 'eye', featured: false,
    title: 'Chequeos regulares: ojos, riñones y pies',
    summary: 'Los controles periódicos permiten detectar a tiempo los problemas que la diabetes puede causar.',
    content: [
      { type: 'p', text: 'La OMS señala que los controles y análisis de sangre periódicos con un profesional de la salud son la mejor forma de detectar la diabetes y sus efectos a tiempo. Entre los cuidados adicionales menciona el cuidado de los pies, el estudio del riñón y el examen de los ojos para detectar la retinopatía, una complicación que puede causar ceguera.' },
      { type: 'p', text: 'El NIDDK recomienda además consultar a un oftalmólogo por la enfermedad ocular de la diabetes y a un odontólogo por los problemas de encías y dientes.' },
      { type: 'h', text: 'Qué podés hacer' },
      { type: 'list', items: [
        'Preguntá a tu médico qué controles te corresponden y cada cuánto.',
        'Anotá en un calendario las fechas de tus próximos turnos.',
        'Aunque te sientas bien, no postergues las revisiones: muchas complicaciones no dan síntomas al principio.',
      ] },
    ],
    sources: s('whoDiabetes', 'niddkManaging'),
  },

  // -------------------------------------------------------------------------------------------- Cuidado de los pies
  {
    id: 'revisar-los-pies', category: 'pies', icon: 'foot', featured: true,
    title: 'Revisá tus pies todos los días',
    summary: 'Una mirada diaria permite detectar heridas o cambios antes de que se compliquen.',
    content: [
      { type: 'p', text: 'Con diabetes puede haber problemas en los pies sin sentir dolor. Por eso el NIDDK recomienda mirarlos cada día, por ejemplo a la noche cuando te sacás los zapatos, incluyendo entre los dedos. Si te cuesta agacharte, usá un espejo o pedile a alguien que te ayude.' },
      { type: 'h', text: 'Qué buscar' },
      { type: 'list', items: [
        'Cortes, llagas o manchas rojas.',
        'Hinchazón o ampollas con líquido.',
        'Uñas encarnadas.',
        'Callos, durezas o verrugas en la planta.',
        'Pie de atleta (hongos).',
        'Zonas más calientes: pueden ser la señal temprana de una ampolla o úlcera.',
      ] },
      { type: 'note', text: 'Si encontrás cualquiera de estas señales, o un corte o ampolla que no mejora en unos días, consultá a tu médico.' },
    ],
    sources: s('niddkFeet', 'cdcFeetTips'),
  },
  {
    id: 'higiene-y-piel', category: 'pies', icon: 'soap', featured: false,
    title: 'Lavado y cuidado de la piel de los pies',
    summary: 'Agua tibia, secado cuidadoso y crema en el lugar justo.',
    content: [
      { type: 'p', text: 'Una buena higiene ayuda a mantener la piel sana y a evitar infecciones. El NIDDK y la ADA coinciden en los pasos básicos.' },
      { type: 'list', items: [
        'Lavate los pies todos los días con agua tibia, no caliente, y jabón suave. No los dejes en remojo.',
        'Secalos muy bien, especialmente entre los dedos.',
        'Si la piel está seca, aplicá crema hidratante en la parte de arriba y en la planta, pero no entre los dedos.',
      ] },
    ],
    sources: s('niddkFeet', 'adaFeet'),
  },
  {
    id: 'calzado-y-medias', category: 'pies', icon: 'shoe', featured: true,
    title: 'Calzado y medias: protección todo el día',
    summary: 'Usá zapatos que calcen bien y medias siempre, también dentro de casa.',
    content: [
      { type: 'p', text: 'El NIDDK aconseja usar zapatos y medias en todo momento, incluso dentro de casa, porque caminar descalzo aumenta el riesgo de lastimarse sin notarlo. La ADA explica que el daño de los nervios puede esconder quemaduras, astillas u objetos filosos.' },
      { type: 'h', text: 'Cómo elegir' },
      { type: 'list', items: [
        'Probate los zapatos en persona y dejá lugar para los dedos (la ADA sugiere el ancho de la uña del pulgar en la punta).',
        'Evitá los zapatos de punta fina, los tacos altos y los de plástico o vinilo.',
        'Elegí medias que calcen bien, sin costuras y acolchadas si hace falta. Las de color claro permiten ver si hay sangrado.',
        'Evitá las sandalias abiertas y las ojotas, que pueden rozar y favorecer las infecciones.',
        'Revisá el interior del zapato antes de ponértelo y estrená el calzado nuevo de a poco.',
      ] },
      { type: 'note', text: 'Algunas coberturas de salud cubren calzado especial o plantillas. Preguntale a tu médico si los necesitás.' },
    ],
    sources: s('niddkFeet', 'adaFeet'),
  },
  {
    id: 'unas-y-callos', category: 'pies', icon: 'scissors', featured: false,
    title: 'Uñas y callos: cortar con cuidado y dejarlos en manos expertas',
    summary: 'Cortá las uñas derechas y no intentes sacar callos en casa.',
    content: [
      { type: 'p', text: 'Las lesiones en las uñas y los intentos de eliminar callos son una causa frecuente de heridas. Tanto el NIDDK como el CDC dan estas pautas.' },
      { type: 'h', text: 'Uñas' },
      { type: 'list', items: [
        'Cortalas rectas, de punta a punta, después de lavarte los pies, y limá los bordes para que no queden filosos.',
        'Si no llegás a tus pies, si las uñas están gruesas o amarillas, o se te encarnan, pedí que te las corte un podólogo.',
        'Si vas a una peluquería o salón de uñas, llevá tus propias herramientas.',
      ] },
      { type: 'h', text: 'Callos y durezas' },
      { type: 'list', items: [
        'No los cortes ni uses parches o líquidos para sacarlos.',
        'Si tu médico lo indica, podés alisarlos con suavidad con una piedra pómez.',
        'Consultá a un profesional de los pies para tratarlos.',
      ] },
    ],
    sources: s('niddkFeet', 'cdcFeetTips'),
  },
  {
    id: 'neuropatia-y-pies', category: 'pies', icon: 'nerve', featured: false,
    title: 'Cuando los pies «no sienten»: neuropatía periférica',
    summary: 'El daño de los nervios puede quitar la sensibilidad. Por eso es clave mirar los pies a diario.',
    content: [
      { type: 'p', text: 'La neuropatía periférica es un daño de los nervios, sobre todo en pies y piernas, y a veces en manos y brazos. Según el NIDDK es muy común: afecta hasta a la mitad de las personas con diabetes. Se asocia a niveles de glucosa elevados durante mucho tiempo.' },
      { type: 'h', text: 'Cómo se puede notar' },
      { type: 'list', items: [
        'Ardor, hormigueo, adormecimiento, dolor o debilidad.',
        'Síntomas que empeoran de noche y que suelen aparecer en ambos lados.',
        'Menor sensación de dolor o de temperatura.',
        'Problemas de equilibrio, caídas o cambios al caminar.',
      ] },
      { type: 'h', text: 'Qué ayuda a prevenirla o a que no empeore' },
      { type: 'list', items: [
        'Mantener la glucosa, la presión y el colesterol en los objetivos que te indique tu médico.',
        'Revisar tus pies todos los días y cuidarlos.',
        'Hacerte un examen completo de los pies al menos una vez al año, o más seguido si tenés problemas.',
        'Consultar enseguida ante cualquier cambio.',
      ] },
      { type: 'note', text: 'Los medicamentos para el dolor los indica el médico. No uses suplementos sin consultar antes.' },
    ],
    sources: s('niddkNeuropathy', 'niddkFeet'),
  },
  {
    id: 'cuando-consultar-y-revision-anual', category: 'pies', icon: 'calendar', featured: false,
    title: 'Cuándo consultar y por qué hacerte una revisión cada año',
    summary: 'Algunas señales piden atención rápida, y una revisión anual completa es parte del cuidado.',
    content: [
      { type: 'p', text: 'El NIDDK recomienda llamar al médico de inmediato si tenés un corte, una ampolla o un moretón que no mejora en unos pocos días, piel enrojecida, caliente o dolorosa, un callo con sangre seca, o una infección del pie con mal olor o que se pone negra.' },
      { type: 'h', text: 'Revisión anual' },
      { type: 'p', text: 'Una vez al año, como mínimo, conviene un examen completo de los pies que verifique la sensibilidad y los pulsos. El CDC suma que los pies se revisen en cada consulta médica y que se vea a un podólogo al menos una vez por año. Sacate las medias y los zapatos en el consultorio para recordarle a tu médico que mire tus pies.' },
      { type: 'note', text: 'Si tuviste cambios en la forma del pie, adormecimiento, problemas de circulación o una úlcera previa, preguntá si te conviene un examen en cada visita.' },
    ],
    sources: s('niddkFeet', 'cdcFeetTips'),
  },
];

// ---------------------------------------------------------------------------------------------------------------------
// Consultas
// ---------------------------------------------------------------------------------------------------------------------

export const categoryOf = (id) => CATEGORIES.find((category) => category.id === id);
export const articleById = (id) => ARTICLES.find((article) => article.id === id);

const normalize = (text) => String(text).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

/** Artículos de una categoría (o de todas con `all`) cuyo título, resumen o contenido contienen la búsqueda. */
export function filterArticles({ category = 'todos', query = '' } = {}) {
  const text = normalize(query).trim();
  return ARTICLES.filter((article) => {
    if (category !== 'todos' && article.category !== category) return false;
    if (!text) return true;
    const haystack = normalize([
      article.title, article.summary, categoryOf(article.category)?.label,
      ...article.content.flatMap((block) => (block.items ? block.items : [block.text])),
    ].join(' '));
    return text.split(/\s+/).every((word) => haystack.includes(word));
  });
}

/** Los destacados que se muestran en Inicio: 2 de la categoría elegida; con «Todos», uno de las dos primeras categorías con destacados. */
export function featuredArticles(category = 'todos') {
  if (category !== 'todos') return ARTICLES.filter((article) => article.category === category && article.featured).slice(0, 2);
  const byCategory = CATEGORIES.map((item) => ARTICLES.find((article) => article.category === item.id && article.featured)).filter(Boolean);
  return byCategory.slice(0, 2);
}
