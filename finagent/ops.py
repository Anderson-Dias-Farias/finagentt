"""Operacao continua: storage, backup, avaliacao periodica, estado e relatorio.

Tudo em stdlib. O ponto central deste modulo e que o banco de sinais e o ativo
que nao pode sumir: ele vive em FINAGENT_DATA (no container: /data, volume
persistente) e tem backup periodico consistente via sqlite3 backup API.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from . import envfile, journal

DATA_DIR = Path(os.environ.get("FINAGENT_DATA", Path.home() / ".finagent"))
BACKUP_DIR = Path(os.environ.get("FINAGENT_BACKUP_DIR", DATA_DIR / "backups"))
KEEP_BACKUPS = int(os.environ.get("FINAGENT_BACKUP_KEEP", "14"))
EVAL_INTERVAL = int(os.environ.get("FINAGENT_EVAL_INTERVAL", "600"))
BACKUP_INTERVAL = int(os.environ.get("FINAGENT_BACKUP_INTERVAL", "21600"))
STARTED_AT = time.time()

_runtime = {"evaluate_ts": 0, "evaluate_n": 0, "backup_ts": 0, "backup_path": ""}
_lock = threading.Lock()


def init_storage() -> dict:
    """Cria schema (idempotente) e diretorio de backup. Seguro rodar em todo boot."""
    journal.init()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return {"db": str(journal.DB_PATH), "backup_dir": str(BACKUP_DIR)}


def _db_size() -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(journal.DB_PATH) + suffix)
        if p.exists():
            total += p.stat().st_size
    return total


def backup() -> str | None:
    """Copia consistente do banco (funciona com escritor ativo). Podruga antigos."""
    if not journal.DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"journal-{time.strftime('%Y%m%d-%H%M%S')}.db"
    src = sqlite3.connect(str(journal.DB_PATH))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    olds = sorted(BACKUP_DIR.glob("journal-*.db"))
    for p in olds[: max(0, len(olds) - KEEP_BACKUPS)]:
        try:
            p.unlink()
        except OSError:
            pass
    with _lock:
        _runtime["backup_ts"] = int(time.time())
        _runtime["backup_path"] = str(dest)
    return str(dest)


def counts() -> dict:
    journal.init()
    with journal._conn() as c:
        row = c.execute(
            "SELECT COUNT(*) n, SUM(outcome='OPEN') o, MIN(ts) first, MAX(ts) last FROM signals"
        ).fetchone()
    return {"signals": row["n"] or 0, "open": row["o"] or 0,
            "first_ts": row["first"], "last_ts": row["last"]}


def _bucket(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0, "wins": 0, "win_rate": 0.0, "avg_r": 0.0, "sum_r": 0.0,
                "best_r": 0.0, "worst_r": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0}
    rs = [r["r_multiple"] or 0.0 for r in rows]
    wins = sum(1 for x in rs if x > 0)
    return {
        "n": n, "wins": wins, "win_rate": wins / n * 100,
        "avg_r": sum(rs) / n, "sum_r": sum(rs),
        "best_r": max(rs), "worst_r": min(rs),
        "avg_mfe": sum(r["mfe_pct"] or 0.0 for r in rows) / n,
        "avg_mae": sum(r["mae_pct"] or 0.0 for r in rows) / n,
    }


def _conv_bucket(conviction: float | None) -> str:
    v = conviction or 0.0
    if v >= 60:
        return ">=60"
    if v >= 45:
        return "45-60"
    return "<45"


def performance(limit: int = 5000) -> dict:
    """Expectativa real por setup, por TF e por faixa de conviccao."""
    journal.init()
    with journal._conn() as c:
        closed = [dict(r) for r in c.execute(
            "SELECT setup, tf, direction, conviction, outcome, r_multiple, mfe_pct, mae_pct"
            " FROM signals WHERE outcome != 'OPEN' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    by_setup: dict[str, list] = {}
    by_tf: dict[str, list] = {}
    by_conv: dict[str, list] = {}
    for r in closed:
        by_setup.setdefault(f"{r['setup']} ({r['direction']})", []).append(r)
        by_tf.setdefault(r["tf"], []).append(r)
        by_conv.setdefault(_conv_bucket(r["conviction"]), []).append(r)
    total = _bucket(closed)
    return {
        "total": total,
        "sample_warning": ("amostra insuficiente: n<8 e ruido, n<20 ainda e indicio"
                           if total["n"] < 20 else None),
        "by_setup": {k: _bucket(v) for k, v in
                     sorted(by_setup.items(), key=lambda kv: -len(kv[1]))},
        "by_tf": {k: _bucket(v) for k, v in sorted(by_tf.items())},
        "by_conviction": {k: _bucket(v) for k, v in sorted(by_conv.items())},
    }


def state() -> dict:
    """Estado operacional: o que o monitor viu por ultimo e se o storage esta sao."""
    mon_state: dict = {}
    path = Path(os.environ.get("FINAGENT_STATE", DATA_DIR / "state.json"))
    try:
        mon_state = json.loads(path.read_text())
    except Exception:
        mon_state = {}
    db = Path(str(journal.DB_PATH))
    with _lock:
        runtime = dict(_runtime)
    return {
        "uptime_s": int(time.time() - STARTED_AT),
        "db": {"path": str(db), "exists": db.exists(), "size_bytes": _db_size(),
               "writable": os.access(db.parent, os.W_OK) if db.parent.exists() else False},
        "counts": counts(),
        "monitor": mon_state,
        "runtime": runtime,
        "env": {"eval_interval_s": EVAL_INTERVAL, "backup_interval_s": BACKUP_INTERVAL,
                "keep_backups": KEEP_BACKUPS},
        "postgres": envfile.postgres_status(),
    }


def health() -> dict:
    st = state()
    ok = st["db"]["exists"] and st["db"]["writable"]
    return {"ok": ok, "uptime_s": st["uptime_s"], "db": st["db"],
            "signals": st["counts"]["signals"], "open": st["counts"]["open"],
            "last_evaluate_ts": st["runtime"]["evaluate_ts"]}


def _loop(name: str, interval: int, fn) -> None:
    while True:
        try:
            fn()
        except Exception as exc:  # nunca derruba o processo por falha de ciclo
            print(f"[ops] {name} falhou: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(interval)


def _eval_once() -> None:
    res = journal.evaluate()
    with _lock:
        _runtime["evaluate_ts"] = int(time.time())
        _runtime["evaluate_n"] += len(res)
    if res:
        print(f"[ops] evaluate resolveu {len(res)} sinal(is)", flush=True)


def _backup_once() -> None:
    p = backup()
    if p:
        print(f"[ops] backup em {p}", flush=True)


def start_background(evaluate: bool = True, backups: bool = True) -> list[str]:
    """Sobe threads daemon de avaliacao e backup. Retorna o que foi iniciado."""
    started = []
    if evaluate and EVAL_INTERVAL > 0:
        threading.Thread(target=_loop, args=("evaluate", EVAL_INTERVAL, _eval_once),
                         daemon=True, name="finagent-eval").start()
        started.append("evaluate")
    if backups and BACKUP_INTERVAL > 0:
        threading.Thread(target=_loop, args=("backup", BACKUP_INTERVAL, _backup_once),
                         daemon=True, name="finagent-backup").start()
        started.append("backup")
    return started
