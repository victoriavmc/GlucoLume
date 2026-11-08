# Pruebas eliminadas en la remediación de M-2: equivalencia con las reglas vigentes

Fecha: 08/11/2026. Comparación por identificador contra `a3908c0` (suite backend completa, mismo entorno sintético).

Las 11 pruebas de `a3908c0` que dejan de existir son expectativas del **contador compartido de CredencialLocal entre login y reautenticación**,
que la auditoría (M-2) pidió eliminar: el login pasó a limitarse por (cuenta, origen) con ventanas de 5/15 min y 15/1 h, y la reautenticación
pasó a contar sus fallos por operación y usuario (3 en 15 min). Ninguna conducta de seguridad vigente quedó sin prueba: cada caso aparece abajo
con la prueba que lo cubre ahora, o con la razón por la que la conducta ya no existe.

| # | Prueba eliminada (`a3908c0`, `test_login_lockout.py` salvo indicación) | Qué verificaba | Estado | Prueba vigente que lo cubre (`test_login_m2_reglas.py` salvo indicación) |
|---|---|---|---|---|
| 1 | `test_tres_errores_consecutivos_bloquean` | Tres fallos bloquean la cuenta | Regla cambiada: ahora 5 fallos por origen | `test_cinco_fallos_limitan_ese_origen_y_el_sexto_recibe_retry_after` |
| 2 | `test_durante_el_bloqueo_no_se_procesan_intentos_ni_suman` | Mientras dura el bloqueo, ni la contraseña correcta entra ni los fallos suman | Vigente con otro umbral | `test_mientras_dura_el_limite_ni_la_contrasena_correcta_se_procesa_ni_los_fallos_suman` |
| 3 | `test_al_vencer_el_bloqueo_el_contador_vuelve_a_cero` | Al vencer el plazo, el acceso vuelve | Vigente | `test_el_tiempo_restante_disminuye_y_el_acceso_vuelve_solo` |
| 4 | `test_un_error_despues_del_desbloqueo_deja_el_contador_en_uno` | Tras vencer, un fallo cuenta una vez | Vigente: tras vencer caben cinco intentos completos | `test_no_se_puede_renovar_el_limite_insistiendo_desde_el_mismo_origen` |
| 5 | `test_tres_nuevos_errores_despues_del_desbloqueo_vuelven_a_bloquear` | Tras vencer, nuevos fallos vuelven a bloquear | Vigente | `test_no_se_puede_renovar_el_limite_insistiendo_desde_el_mismo_origen` |
| 6 | `test_inicio_de_sesion_exitoso_reinicia_el_contador` | Un login correcto reinicia el contador | **Obsoleta.** El login ya no tiene contador persistente. El límite por origen no se reinicia con un acceso correcto: es más estricto, no más laxo, y no lo puede usar un atacante sin la contraseña. Decisión de diseño a confirmar | Sin equivalente directo (intencional) |
| 7 | `test_contador_residual_sin_bloqueo_vigente_no_bloquea_anticipadamente` | Un contador residual sin bloqueo vigente no bloquea | **Obsoleta.** Era un artefacto del contador persistente de login, que ya no existe. El conteo de reautenticación solo considera fallos dentro de la ventana, lo que cubre el mismo riesgo | `test_la_reconfirmacion_se_libera_cuando_vence_la_ventana` |
| 8 | `test_cuenta_inexistente_responde_igual_que_contraseña_incorrecta` | Enumeración: misma respuesta para cuenta existente e inexistente | Vigente, mismo nombre sin el acento (el comparador lo registró como eliminada por el cambio de nombre) | `test_cuenta_inexistente_responde_igual_que_contrasena_incorrecta` (`test_login_lockout.py`) y `test_respuesta_y_trabajo_de_la_solicitud_no_revelan_si_la_cuenta_existe` |
| 9 | `test_bloqueo_informa_retry_after` | El rechazo informa Retry-After en segundos | Vigente, con los valores del nuevo límite | `test_retry_after_se_expresa_en_la_cabecera_del_rechazo` |
| 10 | `test_reautenticacion_comparte_el_mismo_contador` | La reautenticación comparte contador con el login | **Obsoleta por regla aprobada:** la reautenticación NO comparte contador con el login | `test_reautenticacion_no_comparte_el_contador_con_el_login` (`test_login_lockout.py`) y `test_la_reconfirmacion_bloquea_solo_su_operacion_y_no_el_login` |
| 11 | `test_password_incorrecta_reiterada_bloquea_como_el_login` (`test_account_deletion.py`, renombrada) | Tres contraseñas incorrectas al borrar la cuenta bloquean también el login | **Obsoleta por regla aprobada.** Ahora el bloqueo solo afecta la confirmación de borrado | `test_password_incorrecta_reiterada_bloquea_solo_la_confirmacion` (misma prueba, aserción nueva: el login sigue disponible) |

## Controles de seguridad que siguen cubiertos

- Enumeración de cuentas: `test_respuesta_y_trabajo_de_la_solicitud_no_revelan_si_la_cuenta_existe`, `test_existente_e_inexistente_reciben_la_misma_respuesta_al_limite`.
- Límite por origen y sin bloqueo global de la víctima: `test_un_tercero_desde_otro_origen_no_bloquea_el_login_de_la_victima`, `test_el_limite_es_por_identificador_no_por_origen_entero`.
- Origen fijado por el socket, no por cabeceras: `test_las_cabeceras_de_origen_del_cliente_no_cambian_el_limite`.
- Un solo proceso (el límite en memoria no se multiplica): `test_el_backend_corre_con_un_solo_proceso_y_el_limite_es_exacto`.
- Concurrencia en el límite: `test_solicitudes_simultaneas_no_superan_el_limite` (`test_login_lockout.py`).
- Auditoría de cada intento rechazado: `test_cada_intento_limitado_queda_auditado_una_vez_y_sin_IP_en_claro`, y HMAC para cuentas inexistentes: `test_intento_limitado_de_cuenta_inexistente_se_audita_solo_con_hmac`.
- Reautenticación persistente por operación, sobrevive a un proceso nuevo: `test_el_bloqueo_de_reautenticacion_sobrevive_a_un_proceso_nuevo`.
- Fallos de persistencia: `test_un_fallo_al_escribir_la_auditoria_del_limite_no_cambia_la_respuesta`, `test_si_no_se_puede_registrar_el_fallo_de_reautenticacion_la_operacion_no_pasa`.

## Pruebas nuevas en esta etapa

Se agregaron 184 pruebas respecto de `a3908c0` (la mayoría de los commits de B-1 a B-7 y M-2/M-3). Ninguna prueba preexistente se
debilitó: las únicas expectativas cambiadas son las de la lista anterior y las siguientes, cada una por una regla aprobada:

- `test_audit_security.py`: vuelve a figurar `CUENTA_BLOQUEADA` en la auditoría, con 5 fallos (antes 3). Es la forma de `a3908c0` con el nuevo umbral.
- `test_auth_access_flows.py`: el conteo de auditoría pasa de (6, 0) a (7, 0): un intento limitado más, ahora auditado.
- `test_platform_dashboard.py`, `test_user_notifications.py`: el número de fallos sale de `loginThrottle.LIMITES` (mismo valor: 5).

## Dos pruebas de retención renombradas (13 eliminadas en total)

La comparación por identificador cuenta además dos pruebas de retención que cambiaron de nombre al corregir su premisa de fechas. Los
instantes y las expectativas numéricas no cambian; cambia la escala en la que se escribe el evento (la que usa la aplicación).

| Prueba anterior | Prueba vigente | Cambio |
|---|---|---|
| `test_purga_utc.py::test_la_purga_mensual_vence_al_instante_utc_y_no_3_horas_despues` | `test_la_purga_mensual_vence_al_instante_que_guarda_la_aplicacion` | El evento se guarda en hora de Argentina (09:00 = 12:00 UTC), como lo escribe la aplicación. El corte se compara en esa misma escala |
| `test_technical_retention::test_vencimiento_usa_utc_del_evento_no_la_hora_local` | `test_vencimiento_usa_la_hora_que_guarda_la_aplicacion` | Igual: el vencimiento se calcula en hora de Argentina |

Además, `test_un_evento_escrito_por_la_aplicacion_se_guarda_en_hora_argentina` verifica directamente que la aplicación escribe la hora de Argentina.

## Otras correcciones de pruebas en esta etapa (sin pruebas eliminadas)

- `test_telemetry_sqlserver.py`: dos pruebas usaban una variable de otra prueba (`legacy`, `NameError`) desde `a3908c0`. Se apuntan a la
  medición que la misma prueba crea; las restricciones CHECK verificadas no cambian. La aserción «un DEMO borrado» espera solo la medición real.
- `tests/test_reautenticacion_sqlserver.py` (nueva): ocho sesiones simultáneas sobre la misma cuenta; deben registrarse exactamente 3 fallos
  y 5 rechazos. Detectó el defecto de `UPDLOCK` corregido en `auth.py` (ver `docs/auditorias/SQLSERVER_DESCARTABLE_2026-11-08.md`).
