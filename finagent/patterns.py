"""Padroes graficos classicos detectados sobre swings + candles.

Tudo deterministico e heurístico (sem ML): cada padrao devolve nome, direcao
esperada, status (FORMANDO/CONFIRMADO), confianca 0-100, alvo medido e a
evidencia que o disparou. Serve para o score e para o relatorio.
"""
from __future__ import annotations

from .indicators import atr, slope
from .structure import swings

ALTA, BAIXA, NEUTRO = "ALTA", "BAIXA", "NEUTRO"


def _atr(candles: list[dict]) -> float:
    a = atr([c["h"] for c in candles], [c["l"] for c in candles], [c["c"] for c in candles])
    return a if a else candles[-1]["c"] * 0.01


def _pat(name: str, direction: str, status: str, conf: float, detail: str, target=None) -> dict:
    return {"name": name, "direction": direction, "status": status,
            "conf": round(conf, 0), "detail": detail,
            "target": round(target, 6) if target else None}


# ---------------------------------------------------------------- duplo topo/fundo
def _double(highs, lows, tol: float, price: float, candles) -> list[dict]:
    out = []
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if abs(h1["price"] - h2["price"]) <= tol and h2["i"] - h1["i"] >= 4:
            between = [c["l"] for c in candles[h1["i"]:h2["i"] + 1]]
            neck = min(between) if between else min(h1["price"], h2["price"])
            top = max(h1["price"], h2["price"])
            conf = 78 if price < neck else 58
            out.append(_pat(
                "DUPLO TOPO", BAIXA, "CONFIRMADO" if price < neck else "FORMANDO", conf,
                f"dois topos em {h1['price']:.2f}/{h2['price']:.2f}, pescoco {neck:.2f}",
                neck - (top - neck)))
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if abs(l1["price"] - l2["price"]) <= tol and l2["i"] - l1["i"] >= 4:
            between = [c["h"] for c in candles[l1["i"]:l2["i"] + 1]]
            neck = max(between) if between else max(l1["price"], l2["price"])
            bot = min(l1["price"], l2["price"])
            conf = 78 if price > neck else 58
            out.append(_pat(
                "DUPLO FUNDO", ALTA, "CONFIRMADO" if price > neck else "FORMANDO", conf,
                f"dois fundos em {l1['price']:.2f}/{l2['price']:.2f}, pescoco {neck:.2f}",
                neck + (neck - bot)))
    return out


# ---------------------------------------------------------------- ombro-cabeca-ombro
def _head_shoulders(sw, tol: float, price: float) -> list[dict]:
    if len(sw) < 5:
        return []
    last = sw[-5:]
    types = [s["type"] for s in last]
    out = []
    if types == ["H", "L", "H", "L", "H"]:
        s1, neck1, head, neck2, s2 = last
        if head["price"] > s1["price"] and head["price"] > s2["price"] \
                and abs(s1["price"] - s2["price"]) <= tol * 1.6:
            neck = (neck1["price"] + neck2["price"]) / 2
            conf = 76 if price < neck else 55
            out.append(_pat(
                "OMBRO-CABECA-OMBRO", BAIXA, "CONFIRMADO" if price < neck else "FORMANDO",
                conf, f"cabeca {head['price']:.2f}, ombros {s1['price']:.2f}/{s2['price']:.2f}, pescoco {neck:.2f}",
                neck - (head["price"] - neck)))
    elif types == ["L", "H", "L", "H", "L"]:
        s1, neck1, head, neck2, s2 = last
        if head["price"] < s1["price"] and head["price"] < s2["price"] \
                and abs(s1["price"] - s2["price"]) <= tol * 1.6:
            neck = (neck1["price"] + neck2["price"]) / 2
            conf = 76 if price > neck else 55
            out.append(_pat(
                "OCO INVERTIDO", ALTA, "CONFIRMADO" if price > neck else "FORMANDO",
                conf, f"cabeca {head['price']:.2f}, ombros {s1['price']:.2f}/{s2['price']:.2f}, pescoco {neck:.2f}",
                neck + (neck - head["price"])))
    return out


# ---------------------------------------------------------------- triangulo / cunha / canal
def _triangle_channel(highs, lows, atr_v: float, candles) -> list[dict]:
    if len(highs) < 3 or len(lows) < 3:
        return []
    h3, l3 = highs[-3:], lows[-3:]
    hs = slope([s["price"] for s in h3])
    ls = slope([s["price"] for s in l3])
    flat = atr_v * 0.05           # inclinacao considerada lateral
    span = max(c["h"] for c in candles[-40:]) - min(c["l"] for c in candles[-40:])
    if span <= 0:
        return []
    w_first = (h3[0]["price"] - l3[0]["price"]) / span
    w_last = (h3[-1]["price"] - l3[-1]["price"]) / span
    converging = w_last < w_first * 0.85
    out = []
    if abs(hs) < flat and ls > flat:
        out.append(_pat("TRIANGULO ASCENDENTE", ALTA, "FORMANDO", 64,
                        f"topos laterais, fundos subindo ({ls:+.3f}%/candle)", h3[-1]["price"]))
    elif abs(ls) < flat and hs < -flat:
        out.append(_pat("TRIANGULO DESCENDENTE", BAIXA, "FORMANDO", 64,
                        f"fundos laterais, topos caindo ({hs:+.3f}%/candle)", l3[-1]["price"]))
    elif hs < -flat and ls > flat and converging:
        out.append(_pat("TRIANGULO SIMETRICO", NEUTRO, "FORMANDO", 60,
                        f"topos caindo ({hs:+.3f}) e fundos subindo ({ls:+.3f})", None))
    elif hs > flat and ls > flat:
        if converging:
            out.append(_pat("CUNHA ASCENDENTE", BAIXA, "FORMANDO", 62,
                            f"alta perdendo forca: topos {hs:+.3f} vs fundos {ls:+.3f}", l3[-1]["price"]))
        elif abs(hs - ls) < flat:
            out.append(_pat("CANAL ASCENDENTE", ALTA, "FORMANDO", 55,
                            f"topos e fundos paralelos em alta ({hs:+.3f})", h3[-1]["price"]))
    elif hs < -flat and ls < -flat:
        if converging:
            out.append(_pat("CUNHA DESCENDENTE", ALTA, "FORMANDO", 62,
                            f"queda perdendo forca: topos {hs:+.3f} vs fundos {ls:+.3f}", h3[-1]["price"]))
        elif abs(hs - ls) < flat:
            out.append(_pat("CANAL DESCENDENTE", BAIXA, "FORMANDO", 55,
                            f"topos e fundos paralelos em baixa ({hs:+.3f})", l3[-1]["price"]))
    return out


# ---------------------------------------------------------------- bandeira / retangulo
def _flag(candles, atr_v: float, price: float) -> list[dict]:
    if len(candles) < 20:
        return []
    closes = [c["c"] for c in candles]
    best = None
    for j in range(5, len(candles) - 2):
        move = closes[j] - closes[j - 4]
        if abs(move) <= 2.2 * atr_v:
            continue
        cons = candles[j + 1:]
        if not (3 <= len(cons) <= 14):
            continue
        rng = max(c["h"] for c in cons) - min(c["l"] for c in cons)
        if rng <= 1.3 * atr_v:
            best = (move, cons, rng)  # fica com o impulso mais recente
    if not best:
        return []
    move, cons, rng = best
    direction = ALTA if move > 0 else BAIXA
    target = price + move * 0.65
    return [_pat("BANDEIRA DE " + ("ALTA" if move > 0 else "BAIXA"), direction, "FORMANDO", 66,
                 f"impulso de {move:+.2f} seguido de consolidacao de {rng:.2f} ({len(cons)} candles)",
                 target)]


def _range(highs, lows, tol: float, atr_v: float = 0.0) -> list[dict]:
    if len(highs) < 3 or len(lows) < 3:
        return []
    # "mesmo nivel" em swing k=2 tem ruido de candle: ate ~0.8 ATR e o mesmo preco
    rtol = max(tol, atr_v * 0.8)
    hmax = max(s["price"] for s in highs[-4:])
    hmin = min(s["price"] for s in highs[-4:])
    lmax = max(s["price"] for s in lows[-4:])
    lmin = min(s["price"] for s in lows[-4:])
    if hmax - hmin <= rtol and lmax - lmin <= rtol and hmax - lmin > rtol * 2:
        return [_pat("RETANGULO (range)", NEUTRO, "FORMANDO", 52,
                     f"topos ~{hmax:.2f} e fundos ~{lmax:.2f}", None)]
    return []


# ---------------------------------------------------------------- breakout + retest
def _breakout_retest(candles, highs, lows, tol: float, price: float) -> list[dict]:
    if len(candles) < 30 or not highs or not lows:
        return []
    hist = candles[-30:-3]
    if not hist:
        return []
    rh = max(c["h"] for c in hist)
    rl = min(c["l"] for c in hist)
    broke_up = any(c["c"] > rh for c in candles[-3:])
    broke_dn = any(c["c"] < rl for c in candles[-3:])
    out = []
    if broke_up and abs(price - rh) <= tol:
        out.append(_pat("BREAKOUT + RETEST", ALTA, "CONFIRMADO", 68,
                        f"rompeu {rh:.2f} e testa o nivel de volta", rh + (rh - rl) * 0.4))
    if broke_dn and abs(price - rl) <= tol:
        out.append(_pat("BREAKDOWN + RETEST", BAIXA, "CONFIRMADO", 68,
                        f"perdeu {rl:.2f} e testa o nivel de volta", rl - (rh - rl) * 0.4))
    return out


def detect(candles: list[dict], k: int = 2) -> dict:
    if len(candles) < 24:
        return {"patterns": [], "summary": "dados insuficientes", "bias": NEUTRO,
                "confirmed": None}
    atr_v = _atr(candles)
    price = candles[-1]["c"]
    sw = swings(candles, k)
    highs = [s for s in sw if s["type"] == "H"]
    lows = [s for s in sw if s["type"] == "L"]
    tol = atr_v * 0.3

    pats: list[dict] = []
    pats += _double(highs, lows, tol, price, candles)
    pats += _head_shoulders(sw, tol, price)
    pats += _triangle_channel(highs, lows, atr_v, candles)
    pats += _flag(candles, atr_v, price)
    pats += _range(highs, lows, tol, atr_v)
    # em range lateral, duplo topo/fundo nao confirmado e apenas ruido do range
    if any(p["name"].startswith("RETANGULO") for p in pats):
        pats = [p for p in pats
                if not (p["name"] in ("DUPLO TOPO", "DUPLO FUNDO") and p["status"] == "FORMANDO")]
    pats += _breakout_retest(candles, highs, lows, tol, price)
    pats.sort(key=lambda p: -p["conf"])

    confirmed = [p for p in pats if p["status"] == "CONFIRMADO"]
    ref = confirmed or pats
    bias = NEUTRO
    if ref:
        score_up = sum(p["conf"] for p in ref if p["direction"] == ALTA)
        score_dn = sum(p["conf"] for p in ref if p["direction"] == BAIXA)
        if score_up > score_dn * 1.25:
            bias = ALTA
        elif score_dn > score_up * 1.25:
            bias = BAIXA
    summary = "sem padrao claro"
    if pats:
        summary = "; ".join(f"{p['name']} ({p['status'].lower()}, {p['conf']:.0f})"
                            for p in pats[:3])
    return {"patterns": pats, "summary": summary, "bias": bias, "price": price,
            "atr": atr_v, "tol": tol,
            "confirmed": (confirmed[0]["name"] if confirmed else None)}
