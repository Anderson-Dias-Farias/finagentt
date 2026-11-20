"""Fluxo de ordens: delta por candle, CVD, tamanho medio de ordem e prints grandes."""
from __future__ import annotations

from .indicators import percentile, slope


def delta_from_candles(candles: list[dict]) -> list[dict]:
    """Delta agressor por candle (taker buy - taker sell), em USD."""
    out = []
    for c in candles:
        qv = c.get("qv") or c["v"] * c["c"]
        tbq = c.get("tbq", 0.0)
        delta = 2 * tbq - qv
        out.append({
            "t": c["t"], "delta": delta, "qv": qv,
            "buy_ratio": (tbq / qv) if qv else None,
            "close": c["c"],
        })
    return out


def flow_summary(candles: list[dict], lookback: int = 24) -> dict:
    series = delta_from_candles(candles)
    if not series:
        return {}
    window = series[-lookback:]
    cvd = 0.0
    curve = []
    for row in window:
        cvd += row["delta"]
        curve.append(cvd)
    total_vol = sum(r["qv"] for r in window)
    buy_notional = sum((r["qv"] + r["delta"]) / 2 for r in window)
    sell_notional = total_vol - buy_notional
    price_change = (window[-1]["close"] - window[0]["close"]) / window[0]["close"] * 100
    cvd_slope = slope(curve) / (total_vol / len(window) or 1)  # normalizado

    # divergencia preco x fluxo
    if price_change > 0.4 and cvd < 0:
        divergence = "BAIXISTA (preco sobe, fluxo vende)"
    elif price_change < -0.4 and cvd > 0:
        divergence = "ALTISTA (preco cai, fluxo compra)"
    else:
        divergence = "ALINHADO"

    return {
        "lookback": lookback,
        "cvd_usd": cvd,
        "cvd_slope_norm": cvd_slope,
        "buy_usd": buy_notional,
        "sell_usd": sell_notional,
        "imbalance_pct": (buy_notional - sell_notional) / total_vol * 100 if total_vol else 0,
        "price_change_pct": price_change,
        "divergence": divergence,
        "last_candle_delta": series[-1]["delta"],
        "last_candle_buy_ratio": series[-1]["buy_ratio"],
        "curve": curve,
    }


def trade_prints(trades: list[dict], large_mult: float = 8.0, min_large_usd: float = 25_000) -> dict:
    """Estatistica de ordens executadas (aggTrades): ticket medio, grandes players."""
    if not trades:
        return {}
    notional = [t["notional"] for t in trades]
    total = sum(notional)
    buy = sum(t["notional"] for t in trades if t["side"] == "BUY")
    sell = total - buy
    avg = total / len(trades)
    med = percentile(notional, 0.5) or avg
    p90 = percentile(notional, 0.90) or avg
    p99 = percentile(notional, 0.99) or avg
    threshold = max(min_large_usd, med * large_mult)
    large = [t for t in trades if t["notional"] >= threshold]
    large_buy = sum(t["notional"] for t in large if t["side"] == "BUY")
    large_sell = sum(t["notional"] for t in large if t["side"] == "SELL")
    span_min = max(1e-9, (trades[-1]["t"] - trades[0]["t"]) / 60_000)

    top = sorted(trades, key=lambda t: t["notional"], reverse=True)[:5]
    return {
        "count": len(trades),
        "window_min": span_min,
        "total_usd": total,
        "buy_usd": buy,
        "sell_usd": sell,
        "avg_ticket": avg,
        "median_ticket": med,
        "p90_ticket": p90,
        "p99_ticket": p99,
        "trades_per_min": len(trades) / span_min,
        "window_s": span_min * 60,
        "limited_sample": len(trades) >= 1000,
        "large_threshold": threshold,
        "large_count": len(large),
        "large_buy_usd": large_buy,
        "large_sell_usd": large_sell,
        "large_bias_pct": (large_buy - large_sell) / (large_buy + large_sell) * 100
        if (large_buy + large_sell) else 0.0,
        "large_notional_pct": sum(t["notional"] for t in large) / total * 100 if total else 0,
        "top_prints": [{"side": t["side"], "usd": t["notional"], "price": t["p"],
                        "ago_s": (trades[-1]["t"] - t["t"]) / 1000} for t in top],
    }
