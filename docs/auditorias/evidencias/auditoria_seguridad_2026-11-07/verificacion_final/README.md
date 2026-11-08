# Evidencia de la verificación final (08/11/2026)

Respalda `docs/auditorias/VERIFICACION_CORRECCIONES_2026-11-07.md`. Todo se midió en el banco de trabajo, no en el servidor.

| Archivo | Qué es |
|---|---|
| `comparar_openapi.py` / `contratos_openapi_base_vs_head.txt` | Comparación semántica de la API entre `a3908c0` y `1db54a6`: operaciones, parámetros, códigos de respuesta y restricciones de esquema. |
| `backend_corrida_A_head.txt` | Corrida A, HEAD `069ef6e`, zona UTC: 89 fallidas. |
| `backend_corrida_B_utc_sin_fixture.txt` | Corrida B, con el fix de timing de readiness, zona UTC: 91 fallidas (antes del aislamiento del fixture). |
| `backend_corrida_C_final.txt` | Corrida C (final), HEAD `1db54a6`, zona America/Argentina/Buenos_Aires: 86 fallidas, 2480 pasan, 203 saltan. |
| `clasificacion_fallos_backend.tsv` | Cada fallo de la corrida C, con su estado en el commit base (`a3908c0`) y su causa. |
| `frontend_vitest.txt` | Frontend: 856 pasan, 1 falla (preexistente, sin cambios de código desde `a3908c0`). |
| `http_rutas_final_head.txt` / `http_cabeceras_final_head.txt` / `http_hsts_final_head.txt` | Matrices HTTP sobre el Nginx del banco con la plantilla de HEAD. |
| `navegador_final.txt` | Resultados de las pruebas de navegador sobre HEAD (B-2, B-5, B-7). |
| `rollback_ensayo.txt` | Ensayo de `git revert` de toda la serie en un worktree desechable. |
| `commits_y_archivos.txt` | Commits y archivos modificados de la serie. |

## Cómo reproducir

```bash
# Backend, en la zona de la aplicación (como la corrida C)
cd backend && TZ=America/Argentina/Buenos_Aires python -m pytest tests -n 4 -q -p no:warnings -rfE

# Comparación de contratos (requiere generar los OpenAPI de cada ref con app.openapi())
python comparar_openapi.py openapi_base.json openapi_head.json

# Ensayo de rollback (no modifica la rama)
git worktree add /tmp/rb HEAD && cd /tmp/rb && git revert --no-commit a3908c0..HEAD
```
