"""Dashboard web do finagent — http.server da stdlib, zero dependencias.

Uso:
    python3 server.py                     # http://127.0.0.1:3000
    python3 finagent.py serve --port 3000
    FINAGENT_HOST=0.0.0.0 python3 server.py
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analysis, ops
from .report import to_json

WEB = Path(__file__).resolve().parent.parent / "web"
TTL = float(os.environ.get("FINAGENT_TTL", "25"))
ALLOWED_TF = {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"}

_cache: dict[tuple, tuple[float, str]] = {}
_cache_lock = threading.Lock()


def analyze_json(symbol: str, tf: str, equity: float, risk: float) -> tuple[str, bool]:
    """(json, veio_do_cache). Cache curto para nao martelar a Binance."""
    key = (symbol, tf, equity, risk)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < TTL:
            return hit[1], True
    ctx = analysis.analyze(symbol, tf=tf, equity=equity, risk_pct=risk)
    payload = to_json(ctx)
    with _cache_lock:
        _cache[key] = (time.time(), payload)
        if len(_cache) > 64:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:32]:
                _cache.pop(k, None)
    return payload, False


class Handler(BaseHTTPRequestHandler):
    server_version = "finagent/1.0"

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/health":
            try:
                body = ops.health()
            except Exception as exc:
                self._json(503, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200 if body.get("ok") else 503, body)
            return

        if path == "/api/state":
            try:
                self._json(200, ops.state())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return

        if path == "/api/report":
            try:
                self._json(200, ops.performance())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return

        if path == "/api/analyze":
            q = parse_qs(parsed.query)
            symbol = (q.get("symbol", ["BTCUSDT"])[0] or "BTCUSDT").upper().strip()
            tf = q.get("tf", ["1h"])[0]
            try:
                equity = float(q.get("equity", ["10000"])[0])
                risk = float(q.get("risk", ["1"])[0])
            except ValueError:
                self._json(400, {"error": "equity/risk precisam ser numeros"})
                return
            if tf not in ALLOWED_TF:
                self._json(400, {"error": f"tf invalido; use {sorted(ALLOWED_TF)}"})
                return
            if not symbol.isalnum() or len(symbol) > 16:
                self._json(400, {"error": "symbol invalido"})
                return
            t0 = time.time()
            try:
                body, cached = analyze_json(symbol, tf, equity, risk)
            except Exception as exc:
                traceback.print_exc()
                self._json(502, {"error": f"{type(exc).__name__}: {exc}",
                                 "hint": "simbolo inexistente ou Binance fora do ar"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Cache", "HIT" if cached else "MISS")
            self.send_header("X-Elapsed", f"{time.time() - t0:.2f}")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return

        if path in ("/", "/index.html"):
            try:
                with open(WEB / "index.html", "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, b"web/index.html nao encontrado", "text/plain; charset=utf-8")
            return

        self._json(404, {"error": "rota nao encontrada",
                         "paths": ["/", "/api/analyze", "/api/health", "/api/state",
                                   "/api/report"]})


def make_server(host: str = "127.0.0.1", port: int = 3000) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def serve(host: str = "127.0.0.1", port: int = 3000, monitor: bool = False,
          symbols: list[str] | None = None, tf: str = "15m", interval: int = 300) -> int:
    storage = ops.init_storage()
    started = ops.start_background()
    if monitor:
        from . import monitor as _monitor
        syms = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        threading.Thread(target=_monitor.run,
                         args=(syms, tf, interval, 10_000, 1.0, True, False),
                         daemon=True, name="finagent-monitor").start()
        started.append("monitor")
    srv = make_server(host, port)
    print(f"finagent dashboard em http://{host}:{port}  (Ctrl+C para parar)", flush=True)
    print(f"  db: {storage['db']}   backup: {storage['backup_dir']}", flush=True)
    print(f"  background: {', '.join(started) or 'nenhum'}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando")
    finally:
        srv.server_close()
    return 0
