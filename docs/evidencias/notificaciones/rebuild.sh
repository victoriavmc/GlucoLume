source "$(dirname "$0")/env.sh"
sq -Q "IF DB_ID('GlucoLume') IS NOT NULL BEGIN ALTER DATABASE GlucoLume SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE GlucoLume; END" || exit 1
sq -Q "CREATE DATABASE GlucoLume COLLATE Modern_Spanish_CI_AS" || exit 1
sq -d GlucoLume -i /tmp/v5_old.sql > "$SP/it/v5_old.out" 2>&1 || exit 2
sq -d GlucoLume -i /tmp/permisos_old.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME > "$SP/it/perm_old.out" 2>&1 || exit 3
docker cp "$SP/it/seed_legacy.sql" $N:/tmp/seed_legacy.sql
sq -d GlucoLume -i /tmp/seed_legacy.sql || exit 4
sq -d GlucoLume -i /tmp/permisos_new.sql -v API_LOGIN=glucolume_app JOBS_LOGIN=glucolume_jobs CONFIRMAR=APLICAR_PERMISOS_GLUCOLUME > "$SP/it/perm_new1.out" 2>&1 || exit 5
sq -d GlucoLume -i /tmp/notif_v2.sql -v CONFIRMAR=ACTUALIZAR_NOTIFICACIONES_V2 > "$SP/it/v2_run1.out" 2>&1 || exit 6
sq -d GlucoLume -i /tmp/notif_v3.sql -v CONFIRMAR=ACTUALIZAR_NOTIFICACIONES_V3 > "$SP/it/v3_run1.out" 2>&1 || exit 9
(cd "$SP/it" && PYTHONPATH="$SP/site;$SP/it" python mkusers.py > /dev/null 2>&1) || exit 7
sq -d GlucoLume -Q "UPDATE dbo.Usuario SET estado=N'ACTIVO' WHERE usuario IN (N'ana',N'beto',N'carla')" > /dev/null || exit 8
echo "reconstruida: esquema anterior + datos heredados + permisos + v2 + usuarios sintéticos"
