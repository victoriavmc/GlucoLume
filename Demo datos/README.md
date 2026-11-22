# Datos de prueba GlucoLume

Carpeta autocontenida para cargar y quitar datos ficticios. No depende del repositorio.

## Contenido

- `generar_datos.py`: genera los datos (determinístico, misma semilla).
- `cargar_datos.sql`: resultado generado por `generar_datos.py` (no incluido en el repositorio). 6 usuarios individuales (`individuo1..6@example.com`), 1 grupo familiar de 5 integrantes con tres niveles de comparticion, matriz de prueba, dispositivos, perfiles, ~5500 mediciones y los avisos de grupo.
- `limpiar_datos.sql`: borra solo esos datos.

## Reglas de los datos

- Período: 24/11/2021 a 22/11/2026 (hoy). No se generan mediciones futuras.
- `individuo1` e `individuo3` tienen 2 o 3 mediciones por día en el último año; el resto, unas 3 por semana.
- Grupo (6 integrantes, un permiso distinto cada uno): `individuo1` todos los permisos (propietario); `individuo2` ninguno (moderador); `individuo3` solo datos básicos del perfil (edad y sexo); `individuo4` solo última medición; `individuo5` solo aviso de medición (día y hora, sin valores); `individuo6` solo historial de mediciones.
- Nombres: Mateo Quiroga, Valentina Molina, Joaquín Aguirre, Renata Palacios, Benjamín Cabrera, Agustina Figueroa. Usuario: `individuo1..6`.
- Todas las mediciones llevan la observación `Dato de prueba ficticio`.
- La contraseña no se guarda en ningún archivo: solo su hash Argon2 (mismos parámetros que la app).

## Subir al servidor y cargar

1. Generar el script: con Python 3 y `pwdlib` instalado, definir `GLUCOLUME_PRUEBA_PASSWORD` con la contraseña de prueba y ejecutar `python generar_datos.py`. Esto crea `cargar_datos.sql`, que no se versiona porque contiene el hash de esa contraseña.
2. Copiar `cargar_datos.sql` al servidor junto con esta carpeta.
3. Ejecutar `cargar_datos.sql` en la base **de prueba** (no en la que tiene cuentas reales). Si el nombre de la base no es `GlucoLume`, editar la línea `USE`. Con sqlcmd, usar `-f 65001` para que los acentos se lean bien:
   `sqlcmd -S <servidor> -E -C -b -f 65001 -i cargar_datos.sql`

## Quitar los datos

Ejecutar `limpiar_datos.sql`. Borra solo lo que creó la carga, incluidos los registros de auditoría de esas cuentas (la base no permite borrar el usuario si quedan).

## Pendiente / no incluido

- No se generaron sesiones, suscripciones, mediciones de referencia capilar ni muestras crudas del sensor (`MuestraSensor`).
- No se ejecutó contra una base de datos: falta validar la carga en SQL Server.
