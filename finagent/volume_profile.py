"""Volume profile (volume-at-price) a partir de candles."""
from __future__ import annotations


def build_profile(candles: list[dict], bins: int = 60, value_area: float = 0.70) -> dict:
    if len(candles) < 5:
        return {}
    lo = min(c["l"] for c in candles)
    hi = max(c["h"] for c in candles)
    if hi <= lo:
        return {}
    step = (hi - lo) / bins
    vol = [0.0] * bins
    for c in candles:
        qv = c.get("qv") or c["v"] * c["c"]
        if qv <= 0:
            continue
        # distribui o volume do candle uniformemente entre low e high
        i0 = int((c["l"] - lo) / step)
        i1 = int((c["h"] - lo) / step)
        i0 = max(0, min(bins - 1, i0))
        i1 = max(0, min(bins - 1, i1))
        width = i1 - i0 + 1
        for i in range(i0, i1 + 1):
            vol[i] += qv / width
    total = sum(vol)
    if total <= 0:
        return {}
    centers = [lo + (i + 0.5) * step for i in range(bins)]
    poc_i = max(range(bins), key=lambda i: vol[i])

    # value area: expande a partir do POC pegando o vizinho mais forte
    in_va = {poc_i}
    acc = vol[poc_i]
    left, right = poc_i - 1, poc_i + 1
    while acc / total < value_area and (left >= 0 or right < bins):
        lv = vol[left] if left >= 0 else -1
        rv = vol[right] if right < bins else -1
        if lv >= rv and left >= 0:
            in_va.add(left)
            acc += vol[left]
            left -= 1
        elif right < bins:
            in_va.add(right)
            acc += vol[right]
            right += 1
        else:
            break
    va_idx = sorted(in_va)
    val = centers[va_idx[0]] - step / 2
    vah = centers[va_idx[-1]] + step / 2

    avg = total / bins
    hvn = [centers[i] for i in range(bins) if vol[i] > avg * 1.6]
    lvn = [centers[i] for i in range(bins) if vol[i] < avg * 0.35]
    price = candles[-1]["c"]

    if price > vah:
        position = "ACIMA_VAH"
    elif price < val:
        position = "ABAIXO_VAL"
    elif abs(price - centers[poc_i]) <= step:
        position = "NO_POC"
    else:
        position = "DENTRO_VA"

    # volume nos extremos (aceitacao de preco)
    top_q = sum(vol[int(bins * 0.85):])
    bot_q = sum(vol[: int(bins * 0.15)])

    return {
        "low": lo, "high": hi, "step": step,
        "poc": centers[poc_i], "vah": vah, "val": val,
        "poc_vol_pct": vol[poc_i] / total * 100,
        "va_vol_pct": acc / total * 100,
        "position": position,
        "dist_poc_pct": (price - centers[poc_i]) / centers[poc_i] * 100,
        "dist_vah_pct": (price - vah) / vah * 100,
        "dist_val_pct": (price - val) / val * 100,
        "hvn": hvn[-4:], "lvn": lvn[:4] if lvn else [],
        "top_volume_pct": top_q / total * 100,
        "bottom_volume_pct": bot_q / total * 100,
        "bins": bins, "step_size": step, "candles": len(candles),
    }


def relative_volume(candles: list[dict], n: int = 20) -> float | None:
    if len(candles) < n + 1:
        return None
    vols = [c.get("qv") or c["v"] * c["c"] for c in candles]
    base = sum(vols[-n - 1:-1]) / n
    return vols[-1] / base if base else None
