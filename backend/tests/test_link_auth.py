# Autenticación de las líneas del firmware (H-05): SipHash-2-4 contra los vectores oficiales, equivalencia entre la implementación del firmware (C) y
# la del puente (Python), verificación, anti-repetición con memoria en disco e integración con el lector serie del puente. Datos sintéticos; sin Arduino.
# Lo que estas pruebas NO demuestran: el comportamiento del sketch completo en el hardware real ni la seguridad del enlace Bluetooth (ver docs/SEGURIDAD.md).

import importlib.util
import logging
import random
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = ROOT / "backend" / "acquisition" / "bridge"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # el puente hace `import linkauth`: ambos usan el mismo módulo
    spec.loader.exec_module(module)
    return module


linkauth = load("linkauth", BRIDGE_DIR / "linkauth.py")
from tests.test_bridge import FakePort, bridgeModule, config, waitUntil  # noqa: E402 - carga también glucolume_bridge

KEY = bytes(range(16))
KEY_HEX = KEY.hex()
LINE = "BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.41492,SenalValida:1,Dedo:1,Muestras:58"


# --- SipHash-2-4 ---------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("length, expected", [(0, 0x726FDB47DD0E0E31), (8, 0x93F5F5799A932462), (15, 0xA129CA6149BE45E5), (63, 0x958A324CEB064572)])
def test_siphash24_coincide_con_los_vectores_oficiales_del_paper(length, expected):
    assert linkauth.siphash24(KEY, bytes(range(length))) == expected


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc no está instalado")
def test_la_implementacion_del_firmware_en_c_da_la_misma_etiqueta_que_la_del_puente(tmp_path):
    header = ROOT / "firmware" / "GlucoLume_MAX30100_optimizado" / "GlucoLumeSipHash.h"
    program = tmp_path / "tag.c"
    program.write_text('''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "GlucoLumeSipHash.h"
int main(void) {
  static char line[2048];
  while (fgets(line, sizeof line, stdin)) {
    size_t n = strlen(line);
    while (n && (line[n - 1] == '\\n' || line[n - 1] == '\\r')) line[--n] = 0;
    if (n < 33) continue;
    uint8_t key[16];
    for (int i = 0; i < 16; i++) { unsigned v; sscanf(line + 2 * i, "%2x", &v); key[i] = (uint8_t)v; }
    const char *msg = line + 33;  // 32 hex + un espacio; el mensaje puede estar vacio
    glsip_t s; glsip_init(&s, key);
    for (size_t i = 0; msg[i]; i++) glsip_byte(&s, (uint8_t)msg[i]);
    printf("%016llx\\n", (unsigned long long)glsip_final(&s));
  }
  return 0;
}
''', encoding="utf-8")
    binary = tmp_path / "tag"
    subprocess.run(["gcc", "-O2", "-Wall", "-Werror", f"-I{header.parent}", "-o", str(binary), str(program)], check=True)
    rng = random.Random(20261023)
    cases = []
    for _ in range(300):
        key = bytes(rng.randrange(256) for _ in range(16))
        message = "".join(chr(rng.randrange(33, 127)) for _ in range(rng.randrange(0, 160)))
        cases.append((key, message))
    stdin = "\n".join(f"{key.hex()} {message}" for key, message in cases) + "\n"
    out = subprocess.run([str(binary)], input=stdin, capture_output=True, text=True, check=True).stdout.split()
    assert len(out) == len(cases)
    for (key, message), tag in zip(cases, out, strict=True):
        assert tag == f"{linkauth.siphash24(key, message.encode()):016x}", (key.hex(), message)


def test_las_dos_copias_del_encabezado_siphash_del_firmware_son_identicas():
    first = (ROOT / "firmware" / "GlucoLume_MAX30100_optimizado" / "GlucoLumeSipHash.h").read_bytes()
    original = ROOT / "firmware" / "GlucoLume_MAX30100" / "GlucoLumeSipHash.h"
    if original.exists():
        assert original.read_bytes() == first


# --- Verificación --------------------------------------------------------------------------------------------------------------------------


def test_una_linea_firmada_se_acepta_y_se_devuelve_sin_la_firma():
    auth = linkauth.LineAuthenticator(KEY)
    signed = linkauth.sign(KEY, 1, 1, LINE)
    assert signed.startswith(LINE + "*1.1.") and len(signed) == len(LINE) + len("*1.1.") + 16
    verdict = auth.verify(signed)
    assert (verdict.payload, verdict.reason) == (LINE, None) and auth.accepted == 1


def test_lo_que_no_verifica_se_descarta_con_su_motivo():
    auth = linkauth.LineAuthenticator(KEY)
    good = linkauth.sign(KEY, 1, 5, LINE)
    assert auth.verify(LINE).reason == linkauth.REASON_UNSIGNED  # sin firma
    assert auth.verify("Sistema listo.").reason == linkauth.REASON_UNSIGNED
    assert auth.verify(good.replace("76.43", "99.99")).reason == linkauth.REASON_BAD_TAG  # línea modificada
    assert auth.verify(good[:-1] + ("0" if good[-1] != "0" else "1")).reason == linkauth.REASON_BAD_TAG  # etiqueta alterada
    assert auth.verify(linkauth.sign(bytes(range(1, 17)), 1, 6, LINE)).reason == linkauth.REASON_BAD_TAG  # otra clave
    assert auth.verify(good.replace("*1.5.", "*1.6.")).reason == linkauth.REASON_BAD_TAG  # contador cambiado a mano
    assert auth.accepted == 0
    assert auth.verify(good).payload == LINE  # y la buena sigue pasando
    assert auth.rejected == {linkauth.REASON_UNSIGNED: 2, linkauth.REASON_BAD_TAG: 4, linkauth.REASON_REPLAY: 0}


def test_repetir_o_reordenar_lineas_capturadas_falla_aunque_la_firma_sea_valida():
    auth = linkauth.LineAuthenticator(KEY)
    captured = [linkauth.sign(KEY, 3, n, LINE) for n in range(1, 6)]
    assert auth.verify(captured[0]).payload and auth.verify(captured[2]).payload  # pasa en orden creciente (puede faltar alguna)
    assert auth.verify(captured[0]).reason == linkauth.REASON_REPLAY  # repetida
    assert auth.verify(captured[2]).reason == linkauth.REASON_REPLAY  # la misma otra vez
    assert auth.verify(captured[1]).reason == linkauth.REASON_REPLAY  # fuera de orden (más vieja que la última aceptada)
    assert auth.verify(captured[3]).payload and auth.verify(linkauth.sign(KEY, 3, 5, LINE)).payload
    assert auth.verify(linkauth.sign(KEY, 2, 999, LINE)).reason == linkauth.REASON_REPLAY  # un arranque anterior
    assert auth.verify(linkauth.sign(KEY, 4, 1, LINE)).payload  # un arranque nuevo (el contador de líneas vuelve a 1)
    assert auth.verify(linkauth.sign(KEY, 3, 6, LINE)).reason == linkauth.REASON_REPLAY  # y el anterior ya no vale


def test_reiniciar_el_puente_no_reabre_la_ventana_de_repeticion(tmp_path):
    state = tmp_path / "linkauth.json"
    first = linkauth.LineAuthenticator(KEY, state, saveInterval=0)
    assert first.verify(linkauth.sign(KEY, 7, 40, LINE)).payload
    second = linkauth.LineAuthenticator(KEY, state)  # el proceso se reinició
    assert second.last == (7, 40)
    assert second.verify(linkauth.sign(KEY, 7, 40, LINE)).reason == linkauth.REASON_REPLAY
    assert second.verify(linkauth.sign(KEY, 7, 12, LINE)).reason == linkauth.REASON_REPLAY
    assert second.verify(linkauth.sign(KEY, 7, 41, LINE)).payload
    second.flush()
    assert linkauth.LineAuthenticator(KEY, state).last == (7, 41)
    assert KEY_HEX not in state.read_text(encoding="utf-8")  # el estado nunca guarda la clave


def test_un_estado_corrupto_no_detiene_el_puente_y_reiniciar_lo_limpia(tmp_path, caplog):
    state = tmp_path / "linkauth.json"
    state.write_text("{no es json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="glucolume.bridge.auth"):
        auth = linkauth.LineAuthenticator(KEY, state)
    assert auth.last == (-1, -1) and "no se pudo leer" in caplog.text
    assert auth.verify(linkauth.sign(KEY, 1, 1, LINE)).payload
    auth.reset()  # tras reprovisionar el Arduino su contador de arranques vuelve a empezar
    assert auth.verify(linkauth.sign(KEY, 1, 1, LINE)).payload


def test_los_descartes_se_registran_sin_el_contenido_de_la_linea_y_sin_inundar(caplog):
    clock = [0.0]
    auth = linkauth.LineAuthenticator(KEY, clock=lambda: clock[0])
    with caplog.at_level(logging.WARNING, logger="glucolume.bridge.auth"):
        for _ in range(50):
            auth.verify("BPM:99,datos-sensibles-de-prueba")
        clock[0] += 31
        auth.verify("BPM:99,datos-sensibles-de-prueba")
    assert caplog.text.count("Línea del dispositivo descartada") == 2 and "datos-sensibles" not in caplog.text and KEY_HEX not in caplog.text


@pytest.mark.parametrize("bad", ["", "abc", "zz" * 16, "00" * 16, "ab" * 16, "0123456789abcdef" * 3, KEY_HEX + "00"])
def test_una_clave_mal_formada_o_trivial_se_rechaza(bad):
    with pytest.raises(linkauth.KeyError_):
        linkauth.parseKey(bad)


def test_una_clave_valida_se_acepta():
    assert linkauth.parseKey(f"  {KEY_HEX.upper()} ") == KEY


# --- Integración con el puente ---------------------------------------------------------------------------------------------------------


def test_la_configuracion_acepta_la_clave_opcional_la_valida_y_no_la_persiste(tmp_path):
    env = {"SERIAL_PORT": "COM4", "BRIDGE_TOKEN": "k" * 40, "BRIDGE_DEVICE_CODE": "ARD-001"}
    assert bridgeModule.readConfig(env).deviceKey is None  # opcional: sin clave, como antes
    assert bridgeModule.readConfig({**env, "BRIDGE_DEVICE_KEY": KEY_HEX}).deviceKey == KEY
    with pytest.raises(bridgeModule.ConfigError, match="BRIDGE_DEVICE_KEY"):
        bridgeModule.readConfig({**env, "BRIDGE_DEVICE_KEY": "corta"})
    path = tmp_path / "bridge.env"
    path.write_text(f"SERIAL_PORT=COM4\nBRIDGE_DEVICE_KEY={KEY_HEX}\n", encoding="utf-8")
    bridgeModule.persistConfig(str(path), {"SERIAL_PORT": "COM9", "BRIDGE_DEVICE_KEY": "otra"})
    assert path.read_text(encoding="utf-8") == f"SERIAL_PORT=COM9\nBRIDGE_DEVICE_KEY={KEY_HEX}\n"  # los cambios remotos no tocan la clave
    assert "BRIDGE_DEVICE_KEY" in bridgeModule.ENV_KEYS


def readerWith(lines, key=KEY, statePath=None):
    buffer = bridgeModule.LineBuffer()
    stop = threading.Event()
    auth = linkauth.LineAuthenticator(key, statePath) if key is not None else None
    instance = bridgeModule.SerialReader(config(), buffer, opener=lambda p, b: FakePort(lines), stop=stop,
                                         backoff=bridgeModule.Backoff(0.01, 0.02), authenticator=auth)
    return instance, buffer, stop, auth


def test_el_lector_solo_pasa_al_backend_las_lineas_firmadas_y_sin_la_firma():
    lines = [linkauth.sign(KEY, 1, 1, LINE), LINE, "ERROR: falso", linkauth.sign(KEY, 1, 1, LINE), linkauth.sign(KEY, 1, 2, "PPG,1,0,1,2,3"),
             linkauth.sign(bytes(range(1, 17)), 1, 3, LINE)]
    instance, buffer, stop, auth = readerWith(lines)
    instance.start()
    assert waitUntil(lambda: auth.accepted == 2 and sum(auth.rejected.values()) == 4)
    stop.set()
    instance.join(2)
    assert [item.text for item in buffer.peek()] == [LINE, "PPG,1,0,1,2,3"]  # el backend recibe la línea original, nunca la firma
    assert auth.rejected == {linkauth.REASON_UNSIGNED: 2, linkauth.REASON_REPLAY: 1, linkauth.REASON_BAD_TAG: 1}


def test_sin_clave_el_comportamiento_es_el_de_siempre():
    instance, buffer, stop, auth = readerWith([LINE, "Sistema listo."], key=None)
    instance.start()
    assert waitUntil(lambda: len(buffer) == 2)
    stop.set()
    instance.join(2)
    assert auth is None and [item.text for item in buffer.peek()] == [LINE, "Sistema listo."]


def test_el_puente_registra_el_estado_de_la_autenticacion_sin_la_clave(tmp_path):
    instance, buffer, stop, auth = readerWith([linkauth.sign(KEY, 1, 1, LINE), LINE])
    instance.start()
    assert waitUntil(lambda: auth.accepted == 1 and auth.rejected[linkauth.REASON_UNSIGNED] == 1)
    stop.set()
    instance.join(2)
    written = {}

    class Status:
        def write(self, data):
            written.update(data)

    class FakeUplink:
        serverDown, lastBackendError, sent = False, None, 1

    bridgeModule.publishStatus(Status(), config(), instance, FakeUplink(), buffer, None)
    assert written["enlaceAutenticado"] is True and written["autenticacionEnlace"]["aceptadas"] == 1
    assert KEY_HEX not in repr(written)


# --- Herramientas de provisión ------------------------------------------------------------------------------------------------------------


def test_genkey_genera_una_clave_valida_y_con_save_la_deja_solo_en_el_archivo_local(tmp_path, monkeypatch, capsys):
    from tests.test_bridge_ctl import ctl  # el módulo bridge_ctl ya cargado por las pruebas del administrador

    monkeypatch.setattr(ctl, "ENV_PATH", tmp_path / "bridge.env")
    monkeypatch.setattr(ctl, "protectFile", lambda path: True)
    args = type("A", (), {"save": False})()
    assert ctl.cmdGenKey(args) == 0
    shown = capsys.readouterr().out
    key = next(token for token in shown.split() if len(token) == 32 and all(c in "0123456789abcdef" for c in token))
    assert linkauth.parseKey(key) and f"KEY,{key}" in shown and not (tmp_path / "bridge.env").exists()
    (tmp_path / "bridge.env").write_text("SERIAL_PORT=COM4\nBRIDGE_TOKEN=" + "k" * 40 + "\n", encoding="utf-8")
    assert ctl.cmdGenKey(type("A", (), {"save": True})()) == 0
    saved = (tmp_path / "bridge.env").read_text(encoding="utf-8")
    assert "SERIAL_PORT=COM4" in saved and "BRIDGE_DEVICE_KEY=" in saved and "k" * 40 in saved


def test_auth_reset_olvida_el_contador_guardado(tmp_path, monkeypatch, capsys):
    from tests.test_bridge_ctl import ctl

    monkeypatch.setenv("GLUCOLUME_BRIDGE_HOME", str(tmp_path))
    state = tmp_path / "linkauth.json"
    state.write_text('{"boot": 5, "counter": 9}', encoding="utf-8")
    assert ctl.cmdAuthReset(None) == 0 and not state.exists()
    assert ctl.cmdAuthReset(None) == 0  # sin archivo: no falla
