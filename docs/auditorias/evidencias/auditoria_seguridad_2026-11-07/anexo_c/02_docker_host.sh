#!/usr/bin/env bash
# Anexo C (auditoría 07/11/2026). DIAGNÓSTICO DE SOLO LECTURA de Docker en el host.
# Solo usa docker inspect, docker ps, docker image ls, docker network/volume inspect y lectura de archivos.
# No ejecuta docker compose up/down/restart, no hace docker pull ni docker prune. No imprime valores de variables de entorno.
#
# Uso (el usuario debe estar en el grupo docker, o usar sudo):
#   bash 02_docker_host.sh [PROYECTO=glucolume] 2>&1 | tee "$HOME/diag_02_docker_$(date +%F).txt"
PROY="${1:-glucolume}"
sec() { printf '\n===== %s =====\n' "$1"; }

sec "4. Motor Docker"
ls -l /var/run/docker.sock 2>/dev/null || echo "(socket de Docker no encontrado en /var/run)"
echo "miembros del grupo docker (equivalen a root en el host): $(getent group docker | cut -d: -f4)"

docker version --format 'cliente {{.Client.Version}} / servidor {{.Server.Version}}' 2>&1
docker info --format 'cgroup={{.CgroupDriver}} | liveRestore={{.LiveRestoreEnabled}} | seguridad={{.SecurityOptions}}' 2>&1
docker compose version 2>&1
echo "--- /etc/docker/daemon.json (si existe):"
cat /etc/docker/daemon.json 2>/dev/null || echo "(no existe: valores por defecto)"

sec "5. Puertos publicados por contenedor (0.0.0.0 = todas las interfaces)"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1

sec "4. Usuario, capacidades y privilegios por contenedor"
for c in $(docker ps -a --format '{{.Names}}' --filter "label=com.docker.compose.project=$PROY" 2>/dev/null); do
  echo "--- $c"
  docker inspect -f 'usuario={{.Config.User}} privilegiado={{.HostConfig.Privileged}} soloLectura={{.HostConfig.ReadonlyRootfs}} capAdd={{.HostConfig.CapAdd}} capDrop={{.HostConfig.CapDrop}} seguridad={{.HostConfig.SecurityOpt}} pid={{.HostConfig.PidMode}} red={{.HostConfig.NetworkMode}} reinicio={{.HostConfig.RestartPolicy.Name}} limiteMem={{.HostConfig.Memory}}' "$c"
  docker inspect -f 'estadoSalud={{if .State.Health}}{{.State.Health.Status}}{{else}}sin healthcheck{{end}} imagen={{.Config.Image}} digest={{.Image}}' "$c"
  docker inspect -f 'logs={{.HostConfig.LogConfig.Type}} {{.HostConfig.LogConfig.Config}}' "$c"
  echo "montajes (origen -> destino, modo):"
  docker inspect -f '{{range .Mounts}}  {{.Type}} {{.Source}} -> {{.Destination}} rw={{.RW}}{{println}}{{end}}' "$c"
  echo "variables de entorno (SOLO NOMBRES):"
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | cut -d= -f1 | sort | tr '\n' ' '; echo
  echo "redes:"; docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c"
done
echo "--- contenedores con el socket de Docker montado (equivale a root en el host):"
for c in $(docker ps -q 2>/dev/null); do
  docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' "$c" | grep -q 'docker.sock' && docker inspect -f '{{.Name}}' "$c"
done; echo "(fin)"
echo "--- contenedores privilegiados (debe estar vacío):"
for c in $(docker ps -q 2>/dev/null); do docker inspect -f '{{.Name}} {{.HostConfig.Privileged}}' "$c"; done | grep true || echo "(ninguno)"

sec "3. Imágenes (versión, antigüedad y digest)"
docker image ls --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' 2>&1 | head -n 40
echo "--- digest de las imágenes base (fijadas en los Dockerfile):"
docker image ls --digests --format '{{.Repository}}:{{.Tag}} {{.Digest}}' 2>&1 | grep -Ei 'python|node|nginx|caddy|mssql|redis|golang|debian' | head -n 20

sec "5. Redes internas (¿'Internal=true' en data?)"
for n in $(docker network ls --format '{{.Name}}' --filter "label=com.docker.compose.project=$PROY" 2>/dev/null); do
  echo "$n internal=$(docker network inspect -f '{{.Internal}}' "$n")"
done

sec "10. Volúmenes"
docker volume ls --filter "label=com.docker.compose.project=$PROY" 2>&1
for v in $(docker volume ls -q --filter "label=com.docker.compose.project=$PROY" 2>/dev/null); do
  echo "$v -> $(docker volume inspect -f '{{.Mountpoint}}' "$v")"
done
echo "--- tamaño (requiere root):"; du -sh /var/lib/docker/volumes/${PROY}_* 2>/dev/null || echo "(sin permisos o sin volúmenes)"

sec "12. Logs de los contenedores (tamaño y rotación)"
du -sh /var/lib/docker/containers/*/*-json.log 2>/dev/null | sort -h | tail -n 10 || echo "(sin permisos)"

sec "2. Archivos del proyecto (solo nombres y dueños; no se abren los .env)"
docker compose ls 2>&1 | head -n 5

echo
echo "Fin del diagnóstico de Docker. Enviar la salida completa (sin editarla) para el análisis."
