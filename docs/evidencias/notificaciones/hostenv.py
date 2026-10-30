import json, os
s = json.load(open(os.path.join(os.environ["IT_DIR"], "secrets.json")))
for line in open(os.path.join(os.environ["IT_DIR"], "backend.env"), encoding="utf-8"):
    k, _, v = line.strip().partition("=")
    os.environ.setdefault(k, v)
os.environ["DB_HOST"] = "127.0.0.1"; os.environ["DB_PORT"] = "14330"
os.environ["GLUCOLUME_ENV_FILE"] = os.devnull
os.environ.pop("SSL_CERT_FILE", None)
