# Matriz de referencia de glucosa (catálogo global, v1)

Matriz: **«ADA Diabetes Tests - objetivos adultos no gestantes», versión 1** (`database/reference/MATRIZ.SQL`).
Reemplaza en el catálogo global a la v2 «ADA 2026 - Seguimiento adulto no gestante» (DEMO, sin fuente clínica), que queda INACTIVA y sin cambios.

Alcance: GlucoLume es académico y experimental. Esta matriz **no es un diagnóstico ni una clasificación clínica**. Sirve para comparar un valor de glucosa capilar con un objetivo de la guía, y para nada más.

## Fuente

Única fuente de los valores: **ADA, Diabetes Tests**, https://diabetes.org/living-with-diabetes/treatment-care/checking-your-blood-sugar (consultada el 30/10/2026). Dice que la ADA sugiere estos objetivos «para la mayoría de los adultos no gestantes con diabetes»:

- Antes de comer (preprandial): **80–130 mg/dL**.
- 1–2 horas desde el inicio de la comida (posprandial): **menor de 180 mg/dL**.

## Reglas

| Código | Condición de comida | Edad | Sexo | Ventana | Glucosa |
|---|---|---|---|---|---|
| R-001 | AYUNO (preprandial) | 18–130 | cualquiera | — | 80 – 130 mg/dL |
| R-002 | POSTPRANDIAL | 18–130 | cualquiera | 60–120 min desde el inicio de la comida | menor de 180 mg/dL (sin límite inferior) |

- **Comida no informada:** no hay regla ni objetivo. La consulta muestra los dos objetivos sin elegir ninguno; la medición no recibe una clasificación.
- **Edad no informada:** no hay regla ni objetivo.
- **Sexo:** la regla vale para cualquier sexo (`CUALQUIER_SEXO`), informado o no.

## Tabla comparativa: v2 (anterior) frente a v1 (actual)

| Criterio | v2 (anterior) | v1 (actual) | Fuente | Justificación |
|---|---|---|---|---|
| Nombre y procedencia | «ADA 2026 - Seguimiento…»; «matriz de prueba DEMO (ficticia, sin fuente clínica)» | «ADA Diabetes Tests - objetivos…»; referencia y enlace reales | ADA, Diabetes Tests | No atribuir a ADA 2026 algo no verificado |
| Ayuno (AYUNO) | 80–130 | 80–130, rotulado preprandial | ADA, Diabetes Tests | El valor coincide con la guía; es objetivo para personas con diabetes, no rango de referencia |
| Posprandial, mínimo | 70 | sin límite inferior | ADA, Diabetes Tests | La guía no da piso posprandial; 70 es el umbral de hipoglucemia, no un objetivo |
| Posprandial, máximo | 179,99 | 179,99 (menor de 180) | ADA, Diabetes Tests | Equivale a «menor de 180» con dos decimales |
| Ventana posprandial | 60–120 min | 60–120 min desde el **inicio** de la comida | ADA, Diabetes Tests («1–2 hours after beginning of the meal») | Misma definición en backend (`_minutes`, `glucoseReference.py`) y en SQL (`@MinutosComida`) |
| Comida no informada | 70–180 | sin regla | — | No hay fuente. Sin comida no se elige objetivo |
| Edad | 18–64, 65–130 y no informada, con rangos casi iguales | 18–130 para todas las reglas | Sección 13 no verificada; ADA, Diabetes Tests (individualización) | Sin respaldo para distinguir por edad. El rango 70–180 de «edad no informada» no tenía fuente |
| Sexo | femenino, masculino y no informado, con los mismos valores | cualquier sexo | — | No se encontró objetivo distinto por sexo |
| Cantidad de reglas | 27 | 2 | — | Consecuencia de las filas anteriores |

## Qué no está en la matriz, y por qué

- **Hipoglucemia (54 y 70 mg/dL):** el procedimiento SQL las usa como categorías `MUY_BAJO` y `BAJO`. **Pendiente de verificar** con la Sección 6 de ADA (no accesible en la revisión: HTTP 403). No son objetivos.
- **Tiempo en rango, CGM y criterios diagnósticos:** no se incluyen. Son métricas de otra naturaleza y sus cifras no se pudieron verificar.
- **Grupos de adultos mayores (Sección 13):** la individualización por estado de salud no se pudo verificar en la fuente primaria (HTTP 403). La matriz no distingue grupos.
- **Embarazo:** fuera de alcance (la matriz es para adultos no gestantes).

## Limitaciones explícitas

1. Los objetivos son de la guía para personas con diabetes. Aplicarlos a personas sin diabetes es una extrapolación no validada.
2. AYUNO se usa como preprandial (antes de comer). Son conceptos cercanos pero no idénticos.
3. La ventana posprandial se calcula con `fechaHoraUltimaComida`, que debe ser el **inicio** de la comida. El nombre del campo no lo dice: la interfaz tiene que indicarlo así (pendiente de revisar el texto del formulario). Si se registra otra hora, el objetivo posprandial se aplica mal.
4. La comparación no clasifica ni diagnostica. Los valores de los dispositivos DEMO son simulados y los EXPERIMENTAL no están validados.

## Coherencia backend y SQL

- Backend: `backend/app/services/matrix.py` (`resolveRule`), `backend/app/services/glucoseReference.py` (`position`, `build`).
- SQL: `database/reference/MATRIZ.SQL` (`usp_GlucoLume_CompararGlucosa`). Los mismos criterios: sexo comodín, ventana posprandial desde el inicio de la comida, sin piso posprandial.
- Pruebas: `backend/tests/test_matrix_objetivos_ada.py` (reglas, ventana, vista de referencia y coincidencia de valores con el instalador SQL).

## Cambios de esquema (controlados)

- `CK_ReglaMatriz_sexo` admite `CUALQUIER_SEXO`.
- `ReglaMatriz.glucosaMinReferencia` admite `NULL` (solo tope); `CK_ReglaMatriz_glucosaReferencia` se actualiza.
- `MATRIZ.SQL` es idempotente sobre el esquema existente y no toca filas de matrices activadas ni mediciones.
- Prerrequisito: `GlucoLume_matriz_referencia.sql` (columnas `referenciaBase` y `urlReferencia`).

## Pendientes

- Verificar la Sección 6 (hipoglucemia y tiempo en rango) y la Sección 13 (adultos mayores) desde un navegador. Con esas cifras, se completan las categorías de hipoglucemia y, si corresponde, la distinción por estado de salud.
- Ejecutar `MATRIZ.SQL` en una base de desarrollo restaurada (no se pudo en esta sesión: no hay SQL Server disponible) y verificar con `python -m app.cli.schemaCheck`.
