# Notas sobre las evidencias

- `ayuda_cobertura_css.txt`: cobertura del CSS cargado en `/ayuda` (Playwright `coverage`). Es la medición que sustenta
  «4,9 % del CSS global usado».
- Cobertura de JS: la medición de cobertura precisa de JS que aparece en `ayuda_cascada_js_cls.txt` (líneas `JS-PRECISO`)
  marca 100 % en todos los bundles porque el bloque de nivel superior de cada módulo cubre todo el archivo. **No es concluyente**
  y no se usa en el informe.
- `ayuda_cascada_js_cls.txt`: cascada de carga en móvil simulado, y CLS con rueda de desplazamiento (0).
- `nginx_*.txt`: cabeceras y códigos de respuesta de Nginx 1.24 con la plantilla `docker/nginx/default.conf.template`
  (variables sustituidas, ver el informe). No es la imagen de producción `nginx-unprivileged:1.30`.
- `modelo_*.txt`: modelos mínimos (no son la aplicación completa). Ver los scripts en `../scripts/`.
- `smtp_*.json`: envíos contra un servidor SMTP de laboratorio (127.0.0.1). No salió ningún correo.
- Ningún archivo contiene claves, certificados privados ni credenciales reales.
