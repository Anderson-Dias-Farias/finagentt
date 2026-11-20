"""Monitor em loop: alerta quando o veredito muda de direcao/status."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import analysis, report

STATE = Path(os.environ.get("FINAGENT_STATE", Path.home() / ".finagent" / "state.json"))


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def notify(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                      "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def run(symbols: list[str], tf: str, interval: int, equity: float, risk_pct: float,
        only_changes: bool = True, once: bool = False) -> None:
    state = _load()
    while True:
        alerts: list[str] = []
        for sym in symbols:
            try:
                ctx = analysis.analyze(sym, tf=tf, days=14, equity=equity, risk_pct=risk_pct)
            except Exception as exc:
                print(f"[{time.strftime('%H:%M:%S')}] {sym} erro: {exc}")
                continue
            v = ctx["verdict"]
            key = f"{v['direction']}|{v['status']}"
            prev = state.get(sym, {}).get("key")
            state[sym] = {"key": key, "ts": int(time.time()), "conviction": v["conviction"],
                          "price": ctx["price"], "setup": v["setup"]}
            changed = prev != key
            line = (f"{sym} {v['direction']} {v['conviction']:.0f}/100 [{v['status']}] "
                    f"@ {ctx['price']:.4f} - {v['setup']}")
            print(f"[{time.strftime('%H:%M:%S')}] {line}" + ("  <== MUDOU" if changed else ""))
            if changed and (prev is not None or not only_changes):
                plan = v["plan"]
                alerts.append(
                    f"FINAGENT {sym} {tf}\n{v['direction']} conv {v['conviction']:.0f}\n"
                    f"{v['status']} - {v['setup']}\nPreco {ctx['price']:.4f}\n"
                    f"Entrada {plan['entry']:.4f} | Stop {plan['stop']:.4f}\n"
                    f"TP1 {plan['tp1']:.4f} (R:R {plan['rr_tp1']:.2f}) | TP2 {plan['tp2']:.4f}\n"
                    f"Gates: {', '.join(v['gates']) if v['gates'] else 'nenhum'}"
                )
        _save(state)
        if alerts:
            body = "\n\n".join(alerts)
            sent = notify(body)
            print(f"\n=== ALERTA ===\n{body}\n(telegram: {'enviado' if sent else 'nao configurado'})\n")
        if once:
            break
        time.sleep(interval)
