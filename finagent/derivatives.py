"""Contexto de derivativos: funding, open interest, long/short e taker ratio."""
from __future__ import annotations

from . import data


def context(symbol: str, period: str = "1h", limit: int = 48) -> dict:
    out: dict = {}
    try:
        pi = data.premium_index(symbol)
        out["funding_pct"] = pi["funding"] * 100
        out["funding_annual_pct"] = pi["funding"] * 3 * 365 * 100
        out["mark_price"] = pi["mark"]
        out["basis_pct"] = (pi["mark"] - pi["index"]) / pi["index"] * 100
    except Exception as exc:
        out["error_funding"] = str(exc)

    try:
        hist = data.oi_history(symbol, period, limit)
        if hist:
            now = hist[-1]["oi_usd"]
            prev_1 = hist[-2]["oi_usd"] if len(hist) > 1 else now
            prev_24 = hist[-25]["oi_usd"] if len(hist) > 24 else hist[0]["oi_usd"]
            out["oi_usd"] = now
            out["oi_change_1h_pct"] = (now - prev_1) / prev_1 * 100 if prev_1 else 0.0
            out["oi_change_24h_pct"] = (now - prev_24) / prev_24 * 100 if prev_24 else 0.0
    except Exception as exc:
        out["error_oi"] = str(exc)

    try:
        ls = data.long_short_ratio(symbol, period, min(limit, 30))
        if ls:
            out["ls_ratio"] = ls[-1]["ratio"]
            out["ls_long_pct"] = ls[-1]["long"] * 100
            out["ls_change"] = ls[-1]["ratio"] - ls[0]["ratio"]
    except Exception as exc:
        out["error_ls"] = str(exc)

    try:
        tk = data.taker_ratio(symbol, period, min(limit, 30))
        if tk:
            out["taker_buy_ratio"] = tk[-1]["buy"]
            out["taker_buy_ratio_avg"] = sum(x["buy"] for x in tk) / len(tk)
    except Exception as exc:
        out["error_taker"] = str(exc)

    return out


def price_oi_regime(price_change_pct: float, oi_change_pct: float) -> str:
    if price_change_pct > 0 and oi_change_pct > 0:
        return "ALTA COM NOVOS LONGS (tendencia sustentada, risco de squeeze)"
    if price_change_pct > 0 and oi_change_pct < 0:
        return "ALTA POR SHORT COVERING (combustivel diminuindo)"
    if price_change_pct < 0 and oi_change_pct > 0:
        return "BAIXA COM NOVOS SHORTS (pressao sustentada, risco de squeeze)"
    if price_change_pct < 0 and oi_change_pct < 0:
        return "BAIXA POR DESALAVANCAGEM / LONGS SAINDO"
    return "NEUTRO"
