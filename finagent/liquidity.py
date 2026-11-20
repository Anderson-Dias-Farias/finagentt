"""Liquidez de book: spread, profundidade, desequilíbrio, slippage e paredes."""
from __future__ import annotations


def _walk(levels: list[tuple[float, float]], notional: float) -> tuple[float, float]:
    """Retorna (preco_medio_executado, fracao_preenchida) para um notional USD."""
    remaining, spent, qty = notional, 0.0, 0.0
    for price, size in levels:
        avail = price * size
        take = min(avail, remaining)
        qty += take / price
        spent += take
        remaining -= take
        if remaining <= 1e-9:
            break
    if qty == 0:
        return 0.0, 0.0
    return spent / qty, (notional - max(remaining, 0)) / notional


def book_metrics(book: dict, notionals: tuple[float, ...] = (10_000, 50_000, 250_000)) -> dict:
    bids, asks = book["bids"], book["asks"]
    if not bids or not asks:
        return {}
    bb, ba = bids[0][0], asks[0][0]
    mid = (bb + ba) / 2
    spread_bps = (ba - bb) / mid * 10_000

    bands = {}
    for pct in (0.001, 0.0025, 0.005, 0.01):
        b_lim, a_lim = mid * (1 - pct), mid * (1 + pct)
        b_depth = sum(p * q for p, q in bids if p >= b_lim)
        a_depth = sum(p * q for p, q in asks if p <= a_lim)
        bands[f"{pct*100:.2f}%"] = {
            "bid_usd": b_depth, "ask_usd": a_depth,
            "imbalance_pct": (b_depth - a_depth) / (b_depth + a_depth) * 100
            if (b_depth + a_depth) else 0.0,
        }

    slip = []
    for n in notionals:
        bp, bfill = _walk(bids, n)
        ap, afill = _walk(asks, n)
        slip.append({
            "notional": n,
            "sell_slippage_bps": (mid - bp) / mid * 10_000 if bp else None,
            "buy_slippage_bps": (ap - mid) / mid * 10_000 if ap else None,
            "buy_fill_pct": afill * 100,
            "sell_fill_pct": bfill * 100,
            "complete": afill >= 0.999 and bfill >= 0.999,
        })

    # paredes: niveis muito acima da mediana dentro de 1%
    near_bids = [(p, p * q) for p, q in bids if p >= mid * 0.99]
    near_asks = [(p, p * q) for p, q in asks if p <= mid * 1.01]
    coverage_lo = (mid - bids[-1][0]) / mid * 100 if bids else 0.0
    coverage_hi = (asks[-1][0] - mid) / mid * 100 if asks else 0.0
    def walls(levels: list[tuple[float, float]], side: str) -> list[dict]:
        if not levels:
            return []
        vals = sorted(n for _, n in levels)
        med = vals[len(vals) // 2] or 1
        out = [{"side": side, "price": p, "usd": n, "x_median": n / med}
               for p, n in levels if n > med * 4]
        return sorted(out, key=lambda w: w["usd"], reverse=True)[:3]
    walls_list = walls(near_bids, "BID") + walls(near_asks, "ASK")

    depth_05 = bands["0.50%"]["bid_usd"] + bands["0.50%"]["ask_usd"]
    # score simples: spread estreito + profundidade alta
    spread_score = max(0.0, min(1.0, (12 - spread_bps) / 12))
    depth_score = max(0.0, min(1.0, depth_05 / 2_000_000))
    score = round((spread_score * 0.45 + depth_score * 0.55) * 100)

    return {
        "best_bid": bb, "best_ask": ba, "mid": mid,
        "spread_bps": spread_bps,
        "bands": bands,
        "imbalance_05_pct": bands["0.50%"]["imbalance_pct"],
        "depth_05_usd": depth_05,
        "slippage": slip,
        "walls": walls_list,
        "score": score,
        "levels": len(bids) + len(asks),
        "coverage_pct_lo": coverage_lo,
        "coverage_pct_hi": coverage_hi,
    }
