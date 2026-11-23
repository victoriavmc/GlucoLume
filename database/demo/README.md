# Demo: datos genéricos de GlucoLume

Carpeta para cargar datos ficticios en una base de GlucoLume. Todo lo que aparece aquí es de prueba: nombres, correos y mediciones son inventados.

## Orden de ejecución

Hacer un respaldo de la base antes de cada paso.

1. **Matriz de referencia (unificada)**: `01_matriz_completa.sql`. Agrega las columnas `referenciaBase` y `urlReferencia` a `dbo.Matriz` (si faltan) y carga la matriz global ADA. Ejecutar con `-I` y la confirmación.
   ```powershell
   sqlcmd -S <servidor> -d GlucoLume -E -C -I -b -f 65001 -v CONFIRMAR="ACTUALIZAR_MATRIZ_REFERENCIA" -i 01_matriz_completa.sql
   ```
2. **Administrador del sistema**: `02_crear_administrador.ps1`. Crea la invitación del primer administrador. No define contraseña: la persona recibe un enlace de un solo uso y elige su usuario y contraseña. Solo se puede crear uno; si ya existe un administrador activo, el comando se niega.
   ```powershell
   .\02_crear_administrador.ps1 -Nombre "<nombre>" -Apellido "<apellido>" -Correo "<correo>"
   ```
3. **Datos demo**: `03_demo.ps1`. Carga la demo con el seeder del backend (`app/cli/demoSeed.py`). Sin `-Aplicar` solo muestra lo que crearía. En producción hace falta `-AutorizarProduccion`.
   ```powershell
   .\03_demo.ps1 -Accion cargar                                 # simulación
   .\03_demo.ps1 -Accion cargar -Aplicar -AutorizarProduccion    # carga
   .\03_demo.ps1 -Accion verificar
   ```

Para quitar los datos demo: `.\03_demo.ps1 -Accion limpiar -Aplicar -AutorizarProduccion` (solo borra lo que cargó el seeder).

## Cuentas de prueba

Nueve cuentas `CONSUMIDOR_FINAL` activas, sin instituciones ni personal institucional. Correos `demo.<clave>@example.com`. Las contraseñas no están en esta carpeta: se generan al cargar y quedan en `~/GlucoLumeDemo/credenciales-demo.txt` (ver `sudo cat` abajo).

- `individual-a`: sin grupo familiar.
- Grupo «Grupo familiar DEMO»: `grupo-admin` (administrador, sus datos no se comparten) y siete integrantes `grupo-integrante-1` a `-7` con permisos distintos (datos básicos, última medición, historial, avisos). Los integrantes 6 y 7 comparten todo.
- Cada cuenta tiene su propio dispositivo (`DEMO-DISP-IND-01` a `-09`), vinculado a la cuenta.
- Mediciones desde el 01/01/2022 hasta el 23/11/2026. Cada cuenta tiene de 1 a 3 mediciones en los días que mide; la última es el 23/11/2026 a las 17:00.

Para ver las contraseñas (no las pegues en chats):

```bash
sudo cat ~/GlucoLumeDemo/credenciales-demo.txt
```

## Archivos

- `02_crear_administrador.ps1`: wrapper de `backend/app/cli/initAdmin.py`.
- `03_demo.ps1`: carga, verifica y limpia la demo con el seeder del backend.

