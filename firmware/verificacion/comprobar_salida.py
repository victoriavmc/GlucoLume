"""Comprueba la salida emitida por firma.ino en el ATmega328P simulado con el verificador del puente (linkauth.py)."""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
import linkauth  # noqa: E402

KEY = bytes(range(16))
raw = bytes.fromhex(Path(sys.argv[1]).read_text().strip()).decode("ascii")
lines = raw.split("\r\n")
assert lines.pop() == "", "la salida debe terminar en fin de linea"
expected_payloads = [
    "BPM:76.43,SpO2:99.65,GluExp_mgdl:117.0,Origen:DEMO,IndiceOptico:2.41492,SenalValida:1,Dedo:1,Muestras:58",
    "PPG,7,5,-150,-113,-76,-39,-2,35,72,109,146,183",
    "MODO:DEMO_ACTIVO",
    "GLUCOLUME,ID=0123,SENSOR=MAX30100,FW=1.2.0,SR=50",
    "X",
]
assert lines[0] == "Sistema listo." and lines[-1] == "KEY:BORRADA", lines  # sin clave: salen tal cual, sin firma
signed = lines[1:-1]
assert len(signed) == len(expected_payloads), signed
auth = linkauth.LineAuthenticator(KEY)
for text, want in zip(signed, expected_payloads, strict=True):
    verdict = auth.verify(text)
    assert verdict.payload == want, (text, verdict, want)
    print("OK", verdict.payload[:60])
assert auth.last == (3, 4294967291), auth.last  # contadores 1..4 y luego el cercano al limite de 32 bits (4294967290 + 1)
assert linkauth.LineAuthenticator(bytes(range(1, 17))).verify(signed[0]).reason == linkauth.REASON_BAD_TAG  # otra clave
print("TODO OK:", len(signed), "lineas firmadas verificadas; contador final", auth.last)
