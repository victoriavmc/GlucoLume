# Estado del stack integrado (modo producción con Caddy), 23/10/2026

```text
NAMES                  IMAGE                                   STATUS                    PORTS
glucolume-backend-1    backend:validacion            Up 26 seconds (healthy)   8000/tcp
glucolume-proxy-1      caddy:2.11-alpine                       Up 42 seconds             443/udp, 2019/tcp, 127.0.0.1:18079->80/tcp, 127.0.0.1:18444->443/tcp
glucolume-frontend-1   frontend:validacion           Up 42 seconds (healthy)   127.0.0.1:18080->8080/tcp, 127.0.0.1:18081->8080/tcp
glucolume-redis-1      redis:7-alpine                          Up 42 seconds (healthy)   6379/tcp
glucolume-db-1         mssql:2022-CU16-pvalidacion   Up 42 seconds (healthy)   1433/tcp

-- redes:
glucolume_data bridge
glucolume_edge bridge
-- volúmenes:
glucolume_caddy-config
glucolume_caddy-data
glucolume_mssql-data

-- usuario / solo lectura / capacidades:
backend: user=glucolume readonly=true capdrop=[ALL] secopt=[no-new-privileges:true] restart=always
frontend: user=101 readonly=true capdrop=[ALL] secopt=[no-new-privileges:true] restart=always
redis: user=999:1000 readonly=true capdrop=[ALL] secopt=[no-new-privileges:true] restart=unless-stopped

-- lifecycle:
contenedores lifecycle: 0
-- puertos publicados en el anfitrión (db y redis NO deben figurar):
proxy-1 443/udp, 2019/tcp, 127.0.0.1:18079->80/tcp, 127.0.0.1:18444->443/tcp
frontend-1 127.0.0.1:18080->8080/tcp, 127.0.0.1:18081->8080/tcp
```
