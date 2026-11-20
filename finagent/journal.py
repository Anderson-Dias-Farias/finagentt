"""Journal de sinais em SQLite: registra, avalia resultado e mede expectativa."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from . import data

DB_PATH = Path(os.environ.get("FINAGENT_DB", Path.home() / ".finagent" / "journal.db"))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    # WAL: leitor (dashboard/backup) nao bloqueia escritor (monitor) e vice-versa.
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _ensure_column(c: sqlite3.Connection, table: str, name: str, decl: str) -> None:
    """Migracao aditiva: adiciona coluna se faltar. Nunca derruba dado existente."""
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if name not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init() -> None:
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL, symbol TEXT NOT NULL, tf TEXT NOT NULL,
            direction TEXT, status TEXT, setup TEXT, conviction REAL,
            price REAL, entry REAL, stop REAL, tp1 REAL, tp2 REAL,
            rr REAL, snapshot TEXT,
            outcome TEXT DEFAULT 'OPEN', exit_price REAL, r_multiple REAL,
            closed_ts INTEGER, mfe_pct REAL, mae_pct REAL
        )""")
        # bancos criados antes destas colunas continuam funcionando
        _ensure_column(c, "signals", "mfe_pct", "REAL")
        _ensure_column(c, "signals", "mae_pct", "REAL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_open ON signals(outcome, ts)")


def save(ctx: dict) -> int:
    init()
    v = ctx["verdict"]
    p = v["plan"]
    snap = {k: val for k, val in ctx.items() if k not in ("candles",)}
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO signals (ts,symbol,tf,direction,status,setup,conviction,price,entry,stop,tp1,tp2,rr,snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(time.time() * 1000), ctx["symbol"], ctx["tf"], v["direction"], v["status"],
             v["setup"], v["conviction"], ctx["price"], p["entry"], p["stop"], p["tp1"], p["tp2"],
             p["rr_tp1"], json.dumps(snap, ensure_ascii=False, default=str)),
        )
        return int(cur.lastrowid)


def list_open(limit: int = 20) -> list[dict]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM signals WHERE outcome='OPEN' ORDER BY ts DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 20) -> list[dict]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def evaluate(min_hours: float = 4.0, max_bars: int = 2000) -> list[dict]:
    """Resolve sinais abertos: stop primeiro (conservador), senao TP1/TP2."""
    init()
    results = []
    now = int(time.time() * 1000)
    for s in list_open(200):
        age_h = (now - s["ts"]) / 3_600_000
        if age_h < min_hours:
            continue
        try:
            bars = data.klines_range(s["symbol"], s["tf"], s["ts"], now)[:max_bars]
        except Exception:
            continue
        if not bars:
            continue
        long = s["direction"] == "LONG"
        entry, stop, tp1, tp2 = s["entry"], s["stop"], s["tp1"], s["tp2"]
        risk = abs(entry - stop)
        outcome, exit_price, mfe, mae = "OPEN", None, 0.0, 0.0
        for b in bars:
            if long:
                mfe = max(mfe, (b["h"] - entry) / entry * 100)
                mae = min(mae, (b["l"] - entry) / entry * 100)
                if b["l"] <= stop:
                    outcome, exit_price = "LOSS", stop
                    break
                if b["h"] >= tp2:
                    outcome, exit_price = "WIN_TP2", tp2
                    break
                if b["h"] >= tp1:
                    outcome, exit_price = "WIN_TP1", tp1
                    break
            else:
                mfe = max(mfe, (entry - b["l"]) / entry * 100)
                mae = min(mae, (entry - b["h"]) / entry * 100)
                if b["h"] >= stop:
                    outcome, exit_price = "LOSS", stop
                    break
                if b["l"] <= tp2:
                    outcome, exit_price = "WIN_TP2", tp2
                    break
                if b["l"] <= tp1:
                    outcome, exit_price = "WIN_TP1", tp1
                    break
        if outcome == "OPEN":
            continue
        r_mult = ((exit_price - entry) / risk) * (1 if long else -1) if risk else 0.0
        with _conn() as c:
            c.execute("UPDATE signals SET outcome=?, exit_price=?, r_multiple=?, closed_ts=?, mfe_pct=?, mae_pct=?"
                      " WHERE id=?", (outcome, exit_price, r_mult, now, mfe, mae, s["id"]))
        results.append({"id": s["id"], "symbol": s["symbol"], "outcome": outcome, "r": r_mult})
    return results


def stats() -> dict:
    init()
    with _conn() as c:
        rows = c.execute("""
            SELECT setup, direction, outcome, r_multiple FROM signals WHERE outcome != 'OPEN'
        """).fetchall()
        opens = c.execute("SELECT COUNT(*) n FROM signals WHERE outcome='OPEN'").fetchone()["n"]
    buckets: dict[str, list[float]] = {}
    wins = losses = 0
    total_r = 0.0
    for r in rows:
        key = f"{r['setup']} ({r['direction']})"
        buckets.setdefault(key, []).append(r["r_multiple"] or 0.0)
        total_r += r["r_multiple"] or 0.0
        if (r["r_multiple"] or 0) > 0:
            wins += 1
        else:
            losses += 1
    n = len(rows)
    return {
        "closed": n, "open": opens, "wins": wins, "losses": losses,
        "win_rate": wins / n * 100 if n else 0.0,
        "total_r": total_r, "avg_r": total_r / n if n else 0.0,
        "by_setup": {k: {"n": len(v), "avg_r": sum(v) / len(v),
                         "win_rate": sum(1 for x in v if x > 0) / len(v) * 100}
                     for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))},
    }
