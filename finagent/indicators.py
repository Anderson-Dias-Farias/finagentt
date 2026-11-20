"""Indicadores tecnicos em Python puro (sem pandas/numpy)."""
from __future__ import annotations


def sma(xs: list[float], n: int) -> float | None:
    if len(xs) < n or n <= 0:
        return None
    return sum(xs[-n:]) / n


def ema_series(xs: list[float], n: int) -> list[float]:
    if not xs:
        return []
    k = 2 / (n + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def ema(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    return ema_series(xs, n)[-1]


def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    if len(closes) < slow + signal:
        return None
    ef, es = ema_series(closes, fast), ema_series(closes, slow)
    line = [a - b for a, b in zip(ef, es)]
    sig = ema_series(line, signal)
    hist = [a - b for a, b in zip(line, sig)]
    return {"macd": line[-1], "signal": sig[-1], "hist": hist[-1],
            "hist_prev": hist[-2] if len(hist) > 1 else hist[-1]}


def atr(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def bollinger(closes: list[float], n: int = 20, k: float = 2.0) -> dict | None:
    if len(closes) < n:
        return None
    mid = sma(closes, n)
    var = sum((c - mid) ** 2 for c in closes[-n:]) / n
    sd = var ** 0.5
    return {"mid": mid, "upper": mid + k * sd, "lower": mid - k * sd, "sd": sd,
            "width_pct": (2 * k * sd) / mid * 100 if mid else None}


def adx(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> dict | None:
    if len(closes) < n * 2:
        return None
    trs, pdm, ndm = [], [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        ndm.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    def smooth(xs: list[float]) -> float:
        s = sum(xs[:n])
        for x in xs[n:]:
            s = s - s / n + x
        return s

    str_, sp, sn = smooth(trs), smooth(pdm), smooth(ndm)
    if str_ == 0:
        return None
    pdi = 100 * sp / str_
    ndi = 100 * sn / str_
    dx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0
    return {"adx": dx, "pdi": pdi, "ndi": ndi}


def realized_vol(closes: list[float], n: int = 20) -> float | None:
    if len(closes) < n + 1:
        return None
    rets = []
    for i in range(len(closes) - n, len(closes)):
        if closes[i - 1] > 0:
            rets.append(closes[i] / closes[i - 1] - 1)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return (var ** 0.5) * 100  # desvio padrao percentual por candle


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    idx = (len(s) - 1) * p
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def slope(xs: list[float]) -> float:
    """Regressao linear simples: retorna inclinacao normalizada por unidade."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2
    my = sum(xs) / n
    num = sum((i - mx) * (x - my) for i, x in enumerate(xs))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0
