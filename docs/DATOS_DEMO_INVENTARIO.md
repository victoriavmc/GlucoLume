# Cuentas de demostración: inventario sin contraseñas

Generado por `app/demo/inventory.py` para la fecha de ancla 2026-11-04. Todas las cuentas son sintéticas: los correos usan el dominio reservado `example.com`, los documentos llevan el prefijo `DEMO` y los dispositivos son `DEMO-DISP-*`. Las contraseñas están solo en el archivo privado de credenciales (fuera del repositorio).

## Usuarios individuales

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `individual-a` | Valeria Soto | `demo.individual-a@example.com` | Individual (CONSUMIDOR_FINAL) | Individual sin grupo | Sin grupo familiar | No aplica | A: perfil propio con mediciones en distintos días, estadísticas, historial y última medición. Sin vínculos institucionales. |

## Integrantes del grupo familiar

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `grupo-admin` | Tomás Herrera | `demo.grupo-admin@example.com` | Individual (CONSUMIDOR_FINAL) | Individual - administrador de grupo familiar | Grupo familiar DEMO (administrador) | Sus datos no se comparten con el grupo (todas en no) | B: administra el grupo. Sus propios datos no están compartidos: el grupo no los ve. |
| `grupo-integrante-1` | Sofía Castro | `demo.grupo-integrante-1@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 1 | Grupo familiar DEMO (integrante) | Datos básicos: sí · Última medición: no · Historial: no · Avisos: no | B - Integrante 1: solo datos básicos (edad y sexo). No comparte última medición, historial ni avisos. |
| `grupo-integrante-2` | Nicolás Vega | `demo.grupo-integrante-2@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 2 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: sí · Historial: no · Avisos: no | B - Integrante 2: solo la última medición. No comparte datos básicos ni historial. |
| `grupo-integrante-3` | Julieta Pardo | `demo.grupo-integrante-3@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 3 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: no · Historial: sí · Avisos: no | B - Integrante 3: solo el historial (incluye gráficos y estadísticas). No comparte última medición ni avisos. |
| `grupo-integrante-4` | Mateo Ríos | `demo.grupo-integrante-4@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 4 | Grupo familiar DEMO (integrante) | Datos básicos: no · Última medición: no · Historial: no · Avisos: sí | B - Integrante 4: solo avisos (fecha y hora de cada medición, nunca valores). |
| `grupo-integrante-5` | Carla Núñez | `demo.grupo-integrante-5@example.com` | Individual (CONSUMIDOR_FINAL) | Integrante del grupo familiar 5 | Grupo familiar DEMO (integrante) | Datos básicos: sí · Última medición: sí · Historial: sí · Avisos: sí | B - Integrante 5: comparte datos básicos, última medición, historial y avisos. |

## Propietarios

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `propietario-a` | Gabriel Montes | `demo.propietario-a@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Propietario | Institución Demo A, Institución Demo C | No aplica | C: propietario de la Institución Demo A y de la Institución Demo C (administra más de una institución). |
| `propietario-b` | Patricia Lencina | `demo.propietario-b@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Propietario | Institución Demo B | No aplica | C: propietaria de la Institución Demo B. No ve datos de la Institución Demo A. |

## Moderadores

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `moderador-a-1` | Lorena Acosta | `demo.moderador-a-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo A | No aplica | C: gestiona operadores y ve el panel institucional de la Institución Demo A; no administra moderadores. |
| `moderador-a-2` | Diego Salinas | `demo.moderador-a-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo A | No aplica | C: segundo moderador de la Institución Demo A. |
| `moderador-b-1` | Ezequiel Funes | `demo.moderador-b-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo B | No aplica | C: gestiona operadores de la Institución Demo B. |
| `moderador-b-2` | Romina Ledesma | `demo.moderador-b-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Moderador | Institución Demo B | No aplica | C: segundo moderador de la Institución Demo B. |

## Operadores

| Clave | Nombre | Correo de acceso | Tipo de cuenta | Rol | Institución o grupo | Privacidad (grupo) | Escenario que demuestra |
|---|---|---|---|---|---|---|---|
| `operador-a-1` | Camila Ortiz | `demo.operador-a-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-2` | Federico Luna | `demo.operador-a-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-3` | Irene Paz | `demo.operador-a-3@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-a-4` | Hernán Quiroga | `demo.operador-a-4@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo A | No aplica | D: opera solo sus pacientes asignados en la Institución Demo A. |
| `operador-b-1` | Sabrina Dávila | `demo.operador-b-1@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-2` | Matías Benítez | `demo.operador-b-2@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-3` | Noelia Sosa | `demo.operador-b-3@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
| `operador-b-4` | Ignacio Correa | `demo.operador-b-4@example.com` | Institucional (USUARIO_INSTITUCIONAL) | Operador | Institución Demo B | No aplica | D: opera solo sus pacientes asignados en la Institución Demo B. |
