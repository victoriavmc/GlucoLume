# Construcciones oficiales intentadas en el entorno cloud (23/10/2026)

| Imagen | Dockerfile oficial | Resultado |
|---|---|---|
| db | docker/mssql/Dockerfile | **Construida** (apt de Ubuntu alcanzable) |
| backend | backend/Dockerfile | **No se pudo**: `apt-get update` → «Could not resolve deb.debian.org» (host bloqueado por la política de red; probados varios espejos de Debian, todos bloqueados) |
| frontend | frontend/Dockerfile | **No se pudo**: `apk upgrade` necesita dl-cdn.alpinelinux.org (bloqueado) y `npm ci` dentro de Docker termina con «Exit handler never called» tras el proxy de salida |

Extractos:
```text
#8 7.395   Could not resolve 'deb.debian.org'
#8 7.396   Could not resolve 'deb.debian.org'
#8 7.396   Could not resolve 'deb.debian.org'
#15 71.27 npm error Exit handler never called!
```
