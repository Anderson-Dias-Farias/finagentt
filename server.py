#!/usr/bin/env python3
"""Sobe o dashboard do finagent.

    python3 server.py                       # http://127.0.0.1:3000
    FINAGENT_HOST=0.0.0.0 python3 server.py # acessivel na rede local
"""
import os

from finagent.webapp import serve

if __name__ == "__main__":
    raise SystemExit(serve(
        host=os.environ.get("FINAGENT_HOST", "127.0.0.1"),
        port=int(os.environ.get("FINAGENT_PORT", "3000")),
    ))
