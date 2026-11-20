"""Estrutura de mercado: swings, BOS/CHoCH, suporte/resistencia, padrões e sweeps."""
from __future__ import annotations

from .indicators import atr, slope


def swings(candles: list[dict], k: int = 2) -> list[dict]:
    out = []
    for i in range(k, len(candles) - k):
        h, l = candles[i]["h"], candles[i]["l"]
        if all(h > candles[j]["h"] for j in range(i - k, i + k + 1) if j != i):
            out.append({"i": i, "type": "H", "price": h, "t": candles[i]["t"]})
        if all(l < candles[j]["l"] for j in range(i - k, i + k + 1) if j != i):
            out.append({"i": i, "type": "L", "price": l, "t": candles[i]["t"]})
    return out[-12:]


def structure(candles: list[dict], k: int = 2) -> dict:
    if len(candles) < 20:
        return {}
    sw = swings(candles, k)
    highs = [s for s in sw if s["type"] == "H"]
    lows = [s for s in sw if s["type"] == "L"]
    price = candles[-1]["c"]

    seq = "INDEFINIDA"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"] > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"] < lows[-2]["price"]
        if hh and hl:
            seq = "ALTISTA (HH/HL)"
        elif lh and ll:
            seq = "BAIXISTA (LH/LL)"
        elif hh and ll:
            seq = "EXPANSAO (range ampliando)"
        elif lh and hl:
            seq = "COMPRESSAO (triangulo)"

    last_h = highs[-1]["price"] if highs else None
    last_l = lows[-1]["price"] if lows else None
    bos = choch = None
    if last_h and price > last_h:
        bos = f"BOS ALTISTA acima de {last_h:.2f}"
    if last_l and price < last_l:
        bos = f"BOS BAIXISTA abaixo de {last_l:.2f}"
    if highs and len(highs) >= 2 and last_h:
        if price > last_h and highs[-1]["price"] < highs[-2]["price"]:
            choch = "CHoCH altista (rompeu topo descendente)"
    if lows and len(lows) >= 2 and last_l:
        if price < last_l and lows[-1]["price"] > lows[-2]["price"]:
            choch = "CHoCH baixista (rompeu fundo ascendente)"

    # sweep de liquidez: pavio rompe swing e fecha de volta
    sweep = None
    last = candles[-1]
    if last_h and last["h"] > last_h and last["c"] < last_h:
        sweep = f"SWEEP no topo {last_h:.2f} (pavio acima, fechou abaixo)"
    if last_l and last["l"] < last_l and last["c"] > last_l:
        sweep = f"SWEEP no fundo {last_l:.2f} (pavio abaixo, fechou acima)"

    # zonas de S/R por agrupamento
    atr_val = atr([c["h"] for c in candles], [c["l"] for c in candles],
                  [c["c"] for c in candles]) or price * 0.01
    zones = _cluster_zones(sw, atr_val, price)

    return {
        "swing_high": last_h, "swing_low": last_l,
        "sequence": seq, "bos": bos, "choch": choch, "sweep": sweep,
        "zones": zones,
        "range_high": max(c["h"] for c in candles[-60:]),
        "range_low": min(c["l"] for c in candles[-60:]),
        "range_pos_pct": _range_pos(candles, price),
        "slope_norm": slope([c["c"] for c in candles[-30:]]) / price,
        "candle_pattern": candle_patterns(candles),
    }


def _range_pos(candles: list[dict], price: float) -> float:
    window = candles[-60:]
    hi = max(c["h"] for c in window)
    lo = min(c["l"] for c in window)
    if hi <= lo:
        return 50.0
    return (price - lo) / (hi - lo) * 100


def _cluster_zones(sw: list[dict], atr_val: float, price: float, tol_mult: float = 0.45) -> list[dict]:
    pts = sorted(sw, key=lambda s: s["price"])
    zones: list[list[dict]] = []
    for p in pts:
        if zones and abs(p["price"] - zones[-1][-1]["price"]) <= atr_val * tol_mult:
            zones[-1].append(p)
        else:
            zones.append([p])
    out = []
    for z in zones:
        lvl = sum(x["price"] for x in z) / len(z)
        out.append({
            "price": lvl,
            "touches": len(z),
            "kind": "RESISTENCIA" if lvl > price else "SUPORTE",
            "dist_pct": (lvl - price) / price * 100,
        })
    return sorted(out, key=lambda x: abs(x["dist_pct"]))[:5]


def candle_patterns(candles: list[dict]) -> str:
    if len(candles) < 3:
        return "n/d"
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    body = lambda c: abs(c["c"] - c["o"])
    rng = lambda c: max(c["h"] - c["l"], 1e-12)
    tags = []

    if c3["c"] > c3["o"] and c2["c"] < c2["o"] and c3["c"] > c2["o"] and c3["o"] < c2["c"]:
        tags.append("ENGULFING ALTISTA")
    if c3["c"] < c3["o"] and c2["c"] > c2["o"] and c3["c"] < c2["o"] and c3["o"] > c2["c"]:
        tags.append("ENGULFING BAIXISTA")

    upper = c3["h"] - max(c3["o"], c3["c"])
    lower = min(c3["o"], c3["c"]) - c3["l"]
    if lower > body(c3) * 2 and upper < body(c3) * 0.6:
        tags.append("MARTELO (rejeicao de baixa)")
    if upper > body(c3) * 2 and lower < body(c3) * 0.6:
        tags.append("ESTRELA CADENTE (rejeicao de alta)")
    if body(c3) / rng(c3) < 0.15:
        tags.append("DOJI (indecisao)")
    if c3["h"] < c2["h"] and c3["l"] > c2["l"]:
        tags.append("INSIDE BAR (compressao)")
    if c2["h"] < c3["h"] and c2["l"] > c3["l"]:
        tags.append("OUTSIDE BAR (expansao)")

    return " + ".join(tags) if tags else "sem padrao relevante"
