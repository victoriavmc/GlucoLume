"""Genera datos de prueba ficticios para GlucoLume y los escribe en cargar_datos.sql.

Contenido:
  - 6 usuarios individuales (individuo1..individuo6@example.com), todos CONSUMIDOR_FINAL.
  - 1 grupo familiar con 5 integrantes y tres niveles de comparticion:
      individuo1 PROPIETARIO  / MEDICION_COMPLETA
      individuo2 MODERADOR    / MEDICION_COMPLETA
      individuo3 MIEMBRO      / SOLO_MOMENTO   (solo avisa que se midio, sin valores)
      individuo4 MIEMBRO      / SOLO_MOMENTO
      individuo5 MIEMBRO      / NINGUNA
      individuo6 sin grupo.
  - Historial de mediciones desde START hasta END (5 anios). individuo1 e individuo3 tienen 2 o 3
    mediciones por dia durante el ultimo anio; el resto, unas 3 por semana.
  - Avisos MEDICION_MIEMBRO_GRUPO para los integrantes que comparten el momento de medicion.

Uso (requiere Python 3 y pwdlib, que ya es dependencia del backend):
  set GLUCOLUME_PRUEBA_PASSWORD=<contrasena de prueba>
  python generar_datos.py

La contrasena nunca se escribe en el archivo: solo se guarda su hash Argon2 con los mismos
parametros que usa la aplicacion (app/core/security.py).
"""

import os
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

NS = uuid.UUID("0b7c9e52-4a1d-4f3e-8c2b-5d9e7a1f3c60")
START = date(2021, 11, 24)
END = date(2026, 11, 22)  # hoy; no se generan mediciones futuras
LAST_YEAR_START = END - timedelta(days=365)
OBS = "Dato de prueba ficticio"
OUT = Path(__file__).with_name("cargar_datos.sql")
WINDOWS = [(6, 9), (11, 14), (18, 22)]  # manana, mediodia, noche

USERS = [
    # flags: (compartePerfil, comparteUltimaMedicion, comparteHistorial, notificaMedicion)
    {"n": 1, "nombre": "Mateo", "apellido": "Quiroga", "sexo": "MASCULINO", "nac": date(1984, 3, 12), "heavy": True,
     "rol": "PROPIETARIO", "flags": (1, 1, 1, 1)},            # todos los permisos
    {"n": 2, "nombre": "Valentina", "apellido": "Molina", "sexo": "FEMENINO", "nac": date(1990, 7, 4), "heavy": False,
     "rol": "MODERADOR", "flags": (0, 0, 0, 0)},              # ninguno
    {"n": 3, "nombre": "Joaquín", "apellido": "Aguirre", "sexo": "MASCULINO", "nac": date(1975, 11, 20), "heavy": True,
     "rol": "MIEMBRO", "flags": (1, 0, 0, 0)},                # solo datos básicos del perfil
    {"n": 4, "nombre": "Renata", "apellido": "Palacios", "sexo": "FEMENINO", "nac": date(1968, 2, 9), "heavy": False,
     "rol": "MIEMBRO", "flags": (0, 1, 0, 0)},                # solo última medición
    {"n": 5, "nombre": "Benjamín", "apellido": "Cabrera", "sexo": "FEMENINO", "nac": date(2001, 9, 30), "heavy": False,
     "rol": "MIEMBRO", "flags": (0, 0, 0, 1)},                # solo aviso de medición
    {"n": 6, "nombre": "Agustina", "apellido": "Figueroa", "sexo": "MASCULINO", "nac": date(1958, 5, 17), "heavy": False,
     "rol": "MIEMBRO", "flags": (0, 0, 1, 0)},                # solo historial de mediciones
]


def nivel_legacy(flags):
    """Campo antiguo nivelComparticion (solo 3 valores). La app usa las banderas; esto es solo coherencia."""
    if flags is None or sum(flags) == 0:
        return "NINGUNA"
    if all(flags):
        return "MEDICION_COMPLETA"
    return "SOLO_MOMENTO"


class Raw(str):
    """Literal SQL ya formateado (numeros, GUIDs, funciones)."""


def gid(key):
    return Raw(f"'{str(uuid.uuid5(NS, key)).upper()}'")


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, Raw):
        return str(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, datetime):
        return f"CAST('{v:%Y-%m-%dT%H:%M:%S}.000' AS DATETIME2(3))"
    if isinstance(v, date):
        return f"CAST('{v:%Y-%m-%d}' AS DATE)"
    if isinstance(v, int):
        return str(v)
    return "N'" + str(v).replace("'", "''") + "'"


def dec(v, scale):
    return Raw(f"{v:.{scale}f}")


def insert(out, table, cols, rows):
    cols_sql = ", ".join(f"[{c}]" for c in cols)
    for i in range(0, len(rows), 900):
        chunk = rows[i:i + 900]
        vals = ",\n".join("(" + ", ".join(lit(v) for v in r) + ")" for r in chunk)
        out.append(f"INSERT INTO [dbo].[{table}] ({cols_sql}) VALUES\n{vals};\n")


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def age_on(nac, d):
    return d.year - nac.year - ((d.month, d.day) < (nac.month, nac.day))


def main():
    pwd = os.environ.get("GLUCOLUME_PRUEBA_PASSWORD")
    if not pwd:
        sys.exit("Falta la variable GLUCOLUME_PRUEBA_PASSWORD (ver README.md).")
    hasher = PasswordHash((Argon2Hasher(time_cost=3, memory_cost=64 * 1024, parallelism=4),))
    hashed = hasher.hash(pwd)

    rng = random.Random(20261122)
    matriz_id = Raw("@matriz")  # matriz GLOBAL activa existente en la base (no se crea otra)
    grupo_id = gid("grupo-familiar")

    usuarios, credenciales, consentimientos, dispositivos, perfiles = [], [], [], [], []
    grupo_usuarios, notificaciones, mediciones = [], [], []
    miembros = []  # (usuario dict, idUsuario, nivel)

    for u in USERS:
        n = u["n"]
        uid = gid(f"usuario-{n}")
        creado = datetime.combine(START, time(10, 0)) + timedelta(days=n)
        nombre = u["nombre"]
        apellido = u["apellido"]
        u.update(uid=uid, nombre=nombre, apellido=apellido, creado=creado, shift=rng.gauss(0, 5))

        usuarios.append((uid, nombre, apellido, f"individuo{n}@example.com", f"individuo{n}", "CONSUMIDOR_FINAL",
                         "ACTIVO", creado, creado, None, u["nac"], u["sexo"], 1, None, None))
        credenciales.append((gid(f"cred-{n}"), uid, hashed, 0, 0, None, None, creado, creado, creado))
        consentimientos.append((gid(f"cons-{n}"), uid, "POLITICA_PRIVACIDAD", "1.0", "ACEPTADO", creado))
        dispositivos.append((gid(f"disp-{n}"), f"PRUEBA-IND-{n:03d}", f"Dispositivo de prueba {n}", "MAX30102 de prueba",
                             "MAX30102", "1.3.0", "OPERATIVO", None, None, creado, None))

        perfil_id = gid(f"perfil-{n}")
        u["perfil"] = perfil_id
        u["disp"] = gid(f"disp-{n}")

        # Mediciones
        ultima = None
        lista = []
        d = START
        while d <= END:
            if u["heavy"] and d > LAST_YEAR_START:
                k = rng.choice([2, 3])
                wins = WINDOWS[:k]
            else:
                wins = [rng.choice(WINDOWS)] if rng.random() < 0.36 else []
            for w0, w1 in wins:
                inicio = datetime.combine(d, time(rng.randint(w0, w1 - 1), rng.randint(0, 59)))
                fin = inicio + timedelta(seconds=rng.randint(40, 90))
                glu = rng.random() < 0.6
                hora = inicio.hour
                if 6 <= hora <= 9 and rng.random() < 0.6:
                    cond, last = "AYUNO", inicio - timedelta(hours=rng.uniform(8, 12))
                    base = (96, 10, 70, 130)
                elif rng.random() < 0.5:
                    cond, last = "POSTPRANDIAL", inicio - timedelta(hours=rng.uniform(1, 3))
                    base = (140, 25, 90, 230)
                else:
                    cond, last = "NO_INFORMADA", None
                    base = (115, 20, 70, 200)
                gl = clamp(rng.gauss(base[0] + u["shift"], base[1]), base[2], base[3]) if glu else None
                mid = gid(f"med-{n}-{inicio:%Y%m%d%H%M}")
                lista.append((inicio, fin, mid))
                mediciones.append((
                    mid, perfil_id, u["disp"], matriz_id if glu else None,
                    "GLUCOSA_EXPERIMENTAL" if glu else "OXIMETRIA", "COMPLETADA", inicio, fin, last, cond,
                    age_on(u["nac"], inicio.date()), u["sexo"],
                    "1.2.0" if inicio.year < 2024 else "1.3.0", "MAX30102",
                    "1.0-prueba" if glu else None,
                    dec(rng.uniform(0.7, 0.98), 3), dec(clamp(rng.gauss(97.2, 1), 92, 100), 2),
                    int(clamp(rng.gauss(72 + u["shift"], 8), 55, 110)),
                    dec(gl, 2) if glu else None,
                    OBS, None, None, None,
                    dec(rng.uniform(0.5, 2.5), 5), rng.randint(15, 40), None, None,
                ))
                ultima = inicio if ultima is None or inicio > ultima else ultima
            d += timedelta(days=1)
        u["mediciones"] = lista
        u["ultima"] = ultima

        perfiles.append((perfil_id, "CONSUMIDOR_FINAL", uid, None, None, nombre, apellido, None, None,
                         age_on(u["nac"], END), u["sexo"], creado, ultima, None, None, None, None, None, None))

    # Grupo y permisos
    grupo_usuarios_pendientes = []
    for u in USERS:
        if not u["rol"]:
            continue
        flags = u["flags"]
        gu_id = gid(f"grupo-usuario-{u['n']}")
        grupo_usuarios.append((gu_id, grupo_id, u["uid"], u["rol"], "ACTIVO", nivel_legacy(flags),
                               u["creado"], u["creado"], None, 1, *flags))
        miembros.append(u)

    # Avisos: cada integrante que comparte el momento avisa a los demas integrantes
    for emisor in miembros:
        if not emisor["flags"][3]:
            continue
        for inicio, fin, mid in emisor["mediciones"]:
            for receptor in miembros:
                if receptor["n"] == emisor["n"]:
                    continue
                leida = fin + timedelta(hours=rng.randint(1, 48)) if rng.random() < 0.7 else None
                notificaciones.append((
                    gid(f"not-{mid}-{receptor['n']}"), receptor["uid"], "MEDICION_GRUPO",
                    "Novedad en tu grupo",
                    f"{emisor['nombre']} {emisor['apellido']} se midió el {inicio:%d/%m/%Y} a las {inicio:%H:%M}.",
                    "/app/grupo", fin, leida,
                    f"MEDICION_GRUPO:{str(emisor['uid'])[1:-1]}:{inicio:%Y%m%dT%H%M%S%f}", 1, None, None, 0,
                ))

    matriz = []  # no se inserta: se usa la matriz GLOBAL activa existente
    _unused = [(matriz_id, None, "Matriz de prueba", "1.0", "GLOBAL", date(2021, 1, 1), None,
               "Matriz ficticia para datos de prueba", None, "Datos generados de prueba", "ACTIVA", datetime.combine(START, time(0, 0)))]
    grupo = [(grupo_id, "Grupo familiar de prueba", "Grupo ficticio para pruebas", "ACTIVO",
              datetime.combine(START, time(10, 0)), datetime.combine(START, time(10, 0)))]

    out = [
        "-- Datos de prueba ficticios de GlucoLume. Generado por generar_datos.py.",
        "-- Ejecutar en la base de PRUEBA. Si ya existen los usuarios individuo1..6, primero ejecutar limpiar_datos.sql.",
        "SET NOCOUNT ON;",
        "SET ANSI_NULLS ON;",
        "SET QUOTED_IDENTIFIER ON;",
        "USE [GlucoLume];",
        "DECLARE @matriz UNIQUEIDENTIFIER = (SELECT TOP 1 idMatriz FROM dbo.Matriz WHERE ambito = N'GLOBAL' AND estado = N'ACTIVA');",
        "IF @matriz IS NULL THROW 50002, N'No hay matriz GLOBAL activa en la base.', 1;",
        "IF EXISTS (SELECT 1 FROM dbo.Usuario WHERE usuario IN (N'individuo1',N'individuo2',N'individuo3',N'individuo4',N'individuo5',N'individuo6'))",
        "    THROW 50001, N'Ya existen los usuarios de prueba. Ejecutar limpiar_datos.sql antes.', 1;",
        "SET XACT_ABORT ON;",
        "BEGIN TRANSACTION;",
    ]
    insert(out, "Usuario", ["idUsuario", "nombre", "apellido", "correoElectronico", "usuario", "tipoCuenta", "estado",
                            "fechaCreacion", "fechaActualizacion", "fechaEliminacion", "fechaNacimiento", "sexo",
                            "notificarNuevoInicioSesion", "fechaInicioGracia", "fechaVencimientoGracia"], usuarios)
    insert(out, "CredencialLocal", ["idCredencialLocal", "idUsuario", "passwordHash", "requiereCambioPassword",
                                    "intentosFallidosConsecutivos", "fechaUltimoIntentoFallido", "bloqueadoHasta",
                                    "fechaUltimoCambioPassword", "fechaCreacion", "fechaActualizacion"], credenciales)
    insert(out, "ConsentimientoUsuario", ["idConsentimiento", "idUsuario", "tipo", "version", "estado", "fechaHora"], consentimientos)
    insert(out, "Dispositivo", ["idDispositivo", "codigoDispositivo", "nombre", "modelo", "modeloSensor", "versionFirmware",
                                "estado", "idInstitucionAsignada", "idInstitucionUsuarioResponsable", "fechaRegistro",
                                "fechaAsignacionInstitucional"], dispositivos)
    insert(out, "PerfilMedicion", ["idPerfilMedicion", "tipoPerfil", "idUsuario", "idInstitucionUsuarioResponsable",
                                   "identificadorPseudonimo", "nombre", "apellido", "dni", "fechaNacimiento", "edadDeclarada",
                                   "sexoModelo", "fechaCreacion", "fechaUltimaMedicion", "fechaExpiracionDatosPersonales",
                                   "fechaDepuracionDatosPersonales", "correoResultados", "fechaAutorizacionCorreo",
                                   "fechaExpiracionCorreo", "idInstitucion"], perfiles)
    insert(out, "Matriz", ["idMatriz", "idInstitucion", "nombre", "version", "ambito", "fechaVigenciaDesde",
                           "fechaVigenciaHasta", "descripcion", "urlReferencia", "referenciaBase", "estado", "fechaCreacion"], matriz)
    insert(out, "Grupo", ["idGrupo", "nombre", "descripcion", "estado", "fechaCreacion", "fechaActualizacion"], grupo)
    insert(out, "GrupoUsuario", ["idGrupoUsuario", "idGrupo", "idUsuario", "rolGrupo", "estadoRelacion", "nivelComparticion",
                                 "fechaInvitacion", "fechaIncorporacion", "fechaBaja", "visualiza", "compartePerfil",
                                 "comparteUltimaMedicion", "comparteHistorial", "notificaMedicion"], grupo_usuarios)
    cols_med = ["idMedicion", "idPerfilMedicion", "idDispositivo", "idMatriz", "modoMedicion", "estadoMedicion",
                "fechaHoraInicio", "fechaHoraFin", "fechaHoraUltimaComida", "condicionComida", "edadAlMomento", "sexoModelo",
                "versionFirmwareAlMomento", "modeloSensorAlMomento", "versionAlgoritmo", "calidadSenal", "spo2",
                "frecuenciaCardiaca", "glucosaEstimada", "observacion", "origenGlucosa", "glucosaDispositivo",
                "unidadGlucosa", "indiceOptico", "lecturasEstabilizadas", "idReglaMatriz", "fechaVencimientoRetencion"]
    insert(out, "Medicion", cols_med, mediciones)
    insert(out, "NotificacionUsuario", ["idNotificacion", "idUsuario", "evento", "titulo", "mensaje", "url", "fechaCreacion",
                                        "fechaLectura", "claveEvento", "visible", "fechaEliminacion", "estadoCorreo",
                                        "intentosCorreo"], notificaciones)
    out.append("COMMIT TRANSACTION;")
    out.append("SELECT 'usuarios' AS tabla, COUNT(*) AS filas FROM dbo.Usuario WHERE correoElectronico LIKE N'individuo_@example.com' "
               "UNION ALL SELECT 'mediciones', COUNT(*) FROM dbo.Medicion WHERE observacion = N'" + OBS + "';")

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Escrito: {OUT}")
    print(f"Usuarios: {len(usuarios)} | Mediciones: {len(mediciones)} | Avisos de grupo: {len(notificaciones)}")


if __name__ == "__main__":
    main()
