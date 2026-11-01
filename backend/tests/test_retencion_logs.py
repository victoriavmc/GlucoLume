# Minimización de IP en los logs operativos: el acceso de Nginx registra la red (IPv4 /24, IPv6 /48), no el equipo, y uvicorn no registra
# cada pedido. Los errores siguen registrándose. El registro formal de seguridad está en SQL Server, con su plazo de retención.
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_nginx_no_registra_la_ip_completa_del_cliente():
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    fmt = re.search(r"^log_format sin_query (.+);$", conf, re.M).group(1)
    assert "$ip_anon" in fmt and "$remote_addr" not in fmt  # ninguna IP completa en el log de accesos
    assert re.search(r"map \$remote_addr \$ip_anon \{", conf)


def test_la_plantilla_trunca_ipv4_a_24_y_ipv6_a_48():
    conf = (REPO / "docker" / "nginx" / "default.conf.template").read_text(encoding="utf-8")
    block = re.search(r"map \$remote_addr \$ip_anon \{(.*?)\n\}", conf, re.S).group(1)
    ipv4 = re.search(r'"~(\^\(\?<red>[^"]+)"\s+\$red\.0;', block).group(1)
    ipv6 = re.search(r'"~(\^\(\?<red6>[^"]+)"\s+\$red6::/48;', block).group(1)
    # Verificación con la misma expresión regular que usa Nginx (PCRE vía Python con los mismos grupos nombrados).
    m4 = re.match(ipv4.replace("(?<red>", "(?P<red>"), "198.51.100.77")
    assert m4 and m4.group("red") == "198.51.100"
    m6 = re.match(ipv6.replace("(?<red6>", "(?P<red6>"), "2001:db8:abcd:1234::77")
    assert m6 and m6.group("red6") == "2001:db8:abcd"


def test_uvicorn_no_registra_cada_acceso_pero_si_los_errores():
    dockerfile = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    cmd = re.search(r'^CMD \[(.*)\]$', dockerfile, re.M).group(1)
    assert '"--no-access-log"' in cmd
    assert "--log-level" not in cmd  # los errores siguen en el nivel por defecto
