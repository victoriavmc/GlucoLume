# Demo: datos genéricos de GlucoLume

Carpeta para cargar datos ficticios en una base de GlucoLume. Todo lo que aparece aquí es de prueba: nombres, correos y mediciones son inventados.

## Orden de ejecución

Hacer un respaldo de la base antes de cada paso.

1. **Matriz (prerrequisito)**: `01_matriz_prerequisito.sql`. Agrega las columnas `referenciaBase` y `urlReferencia` a `dbo.Matriz`. Es idempotente y no borra filas.
   ```powershell
   sqlcmd -S <servidor> -d GlucoLume -E -C -b -f 65001 -v CONFIRMAR="ACTUALIZAR_MATRIZ_REFERENCIA" -i 01_matriz_prerequisito.sql
   ```
2. **Matriz de referencia**: `02_matriz.sql`. Carga la matriz global ADA (adultos no gestantes) y reemplaza la anterior, que queda inactiva. Se puede ejecutar también desde SSMS con F5, sin seleccionar texto.
   ```powershell
   sqlcmd -S <servidor> -d GlucoLume -E -C -b -f 65001 -i 02_matriz.sql
   ```
3. **Administrador del sistema**: `03_crear_administrador.ps1`. Crea la invitación del primer administrador. No define contraseña: la persona recibe un enlace de un solo uso y elige su usuario y contraseña. Solo se puede crear uno; si ya existe un administrador activo, el comando se niega.
   ```powershell
   .\03_crear_administrador.ps1 -Nombre "<nombre>" -Apellido "<apellido>" -Correo "<correo>"
   ```
4. **Datos genéricos**: `04_cargar_datos_demo.ps1`. Genera el script y lo carga. Antes definir la contraseña de prueba en la variable de entorno `GLUCOLUME_PRUEBA_PASSWORD` (no se guarda en ningún archivo).
   ```powershell
   $env:GLUCOLUME_PRUEBA_PASSWORD = "<contraseña de prueba>"
   .\04_cargar_datos_demo.ps1 -Servidor "<servidor>"
   ```

Para quitar los datos genéricos: `05_limpiar_datos_demo.sql` (solo borra lo que cargó el paso 4).

## Usuarios de prueba

Todos son cuentas `CONSUMIDOR_FINAL` activas. La contraseña es la misma para todos y no está en esta carpeta: la define quien ejecuta el paso 4.

| Usuario | Nombre y apellido | Correo | Rol en el grupo | Permisos que comparte con el grupo |
|---|---|---|---|---|
| `individuo1` | Mateo Quiroga | individuo1@example.com | Propietario | Todos: datos básicos del perfil, última medición, historial y aviso de medición |
| `individuo2` | Valentina Molina | individuo2@example.com | Moderador | Ninguno |
| `individuo3` | Joaquín Aguirre | individuo3@example.com | Miembro | Solo datos básicos del perfil (edad y sexo) |
| `individuo4` | Renata Palacios | individuo4@example.com | Miembro | Solo última medición |
| `individuo5` | Benjamín Cabrera | individuo5@example.com | Miembro | Solo aviso de medición (día y hora, sin valores) |
| `individuo6` | Agustina Figueroa | individuo6@example.com | Miembro | Solo historial de mediciones |

- Grupo: «Grupo familiar de prueba», con los seis integrantes anteriores.
- Mediciones: entre el 24/11/2021 y el 22/11/2026. `individuo1` e `individuo3` tienen 2 o 3 mediciones por día durante el último año; el resto, unas 3 por semana. Todas llevan la observación `Dato de prueba ficticio`.
- Avisos de grupo: los generan `individuo1` y `individuo5`, porque son los que comparten el aviso de medición.

## Archivos

- `01_matriz_prerequisito.sql`, `02_matriz.sql`: copias de `database/reference`.
- `03_crear_administrador.ps1`: wrapper de `backend/app/cli/initAdmin.py`.
- `04_cargar_datos_demo.ps1`: ejecuta `generar_datos.py` y luego carga el resultado.
- `generar_datos.py`: genera los datos. No necesita la base para generarlos.
- `05_limpiar_datos_demo.sql`: borra solo los datos genéricos.

El archivo `cargar_datos.sql` que genera el paso 4 queda fuera del repositorio (`.gitignore`), porque contiene el hash de la contraseña de prueba.
