"""Leitor de .env em stdlib puro — sem python-dotenv.

Carrega o .env da raiz do projeto para os.environ no import do pacote. Variavel ja
definida no ambiente real (EasyPanel, systemd, shell) tem prioridade: o arquivo nunca
sobrescreve. Nada aqui imprime valor de segredo.

Formato aceito:
    KEY=valor
    KEY="valor com espaco"
    export KEY=valor
    # comentario
"""
from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse(text: str) -> dict[str, str]:
    """Converte o conteudo de um .env em dict. Ignora comentarios e linhas vazias."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            # comentario inline: so vale quando ha espaco antes do # (URL com #frag fica intacta)
            for sep in (" #", "\t#"):
                if sep in value:
                    value = value.split(sep, 1)[0].rstrip()
                    break
        out[key] = value
    return out


def load(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    """Aplica o .env em os.environ. Retorna as chaves efetivamente aplicadas."""
    p = Path(path or os.environ.get("FINAGENT_ENV_FILE") or DEFAULT_ENV_FILE)
    try:
        values = parse(p.read_text(encoding="utf-8"))
    except OSError:
        return {}
    applied: dict[str, str] = {}
    for key, value in values.items():
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied


def postgres_info() -> dict:
    """Le DATABASE_URL sem jamais devolver a senha."""
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        return {"configured": False}
    try:
        u = urlsplit(url)
    except ValueError:
        return {"configured": True, "valid": False}
    if u.scheme not in ("postgres", "postgresql"):
        return {"configured": True, "valid": False, "scheme": u.scheme}
    return {
        "configured": True,
        "valid": bool(u.hostname and u.path.strip("/")),
        "scheme": u.scheme,
        "host": u.hostname or "",
        "port": u.port or 5432,
        "database": (u.path or "").strip("/").split("/")[0],
        "user": unquote(u.username or ""),
        "has_password": bool(u.password),
        "sslmode": dict(
            kv.split("=", 1) for kv in (u.query.split("&") if u.query else []) if "=" in kv
        ).get("sslmode", ""),
    }


def postgres_status(timeout: float = 1.0) -> dict:
    """Diagnostico: URL presente e host responde na porta? Nao conecta no banco."""
    info = postgres_info()
    if not info.get("configured"):
        return info
    info["used_for_journal"] = False
    if not info.get("valid"):
        info["tcp_reachable"] = False
        return info
    try:
        with socket.create_connection((info["host"], int(info["port"])), timeout=timeout):
            info["tcp_reachable"] = True
    except OSError:
        info["tcp_reachable"] = False
    return info
