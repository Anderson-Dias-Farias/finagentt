"""Orquestra a coleta de dados e monta o contexto completo de analise."""
from __future__ import annotations

from . import data, derivatives, flow, indicators, liquidity, patterns, structure, volume_profile
from .score import build_verdict


def _ema_bias(candles: list[dict]) -> tuple[float, str]:
    closes = [c["c"] for c in candles]
    ef = indicators.ema(closes, 20)
    es = indicators.ema(closes, 50)
    if ef is None or es is None:
        return 0.0, "dados insuficientes"
    price = closes[-1]
    if price > ef > es:
        return 1.0, "alta (preco>EMA20>EMA50)"
    if price < ef < es:
        return -1.0, "baixa (preco<EMA20<EMA50)"
    return 0.0, "lateral (EMAs cruzadas)"


def _vwap(candles: list[dict], n: int = 24) -> float | None:
    window = candles[-n:]
    qv = sum(c.get("qv") or c["v"] * c["c"] for c in window)
    vol = sum(c["v"] for c in window)
    return qv / vol if vol else None


def analyze(symbol: str, tf: str = "1h", days: int = 30, equity: float = 10_000,
            risk_pct: float = 1.0, with_derivs: bool = True) -> dict:
    sym = data.normalize(symbol)
    limit = 500
    base = data.klines(sym, tf, limit)
    if len(base) < 60:
        raise RuntimeError(f"poucos candles para {sym} em {tf}")
    htf = data.klines(sym, "4h", 300)
    daily = data.klines(sym, "1d", 300)

    closes = [c["c"] for c in base]
    highs = [c["h"] for c in base]
    lows = [c["l"] for c in base]
    price = closes[-1]

    tick = data.ticker24h(sym)
    change_24h = float(tick["priceChangePercent"])

    ind = {
        "rsi": indicators.rsi(closes),
        "macd": indicators.macd(closes),
        "atr": indicators.atr(highs, lows, closes),
        "bollinger": indicators.bollinger(closes),
        "adx": indicators.adx(highs, lows, closes),
        "ema20": indicators.ema(closes, 20),
        "ema50": indicators.ema(closes, 50),
        "ema200": indicators.ema(closes, 200),
        "vwap": _vwap(base, 24),
    }
    atr_v = ind["atr"] or price * 0.01
    ind["atr_pct"] = atr_v / price * 100

    # volume profile: janela estrutural + janela operacional recente
    hours = max(24, min(days * 24, 1000))
    vp_candles = data.klines(sym, "1h", min(hours, 1000))
    vp = volume_profile.build_profile(vp_candles, bins=60)
    recent_window = max(48, min(len(base), 240))
    vp_recent = volume_profile.build_profile(base[-recent_window:], bins=50)
    if vp_recent:
        vp["recent"] = vp_recent

    fl = flow.flow_summary(base, lookback=min(48, len(base)))
    try:
        prints = flow.trade_prints(data.agg_trades(sym, 1000))
    except Exception as exc:
        prints = {"error": str(exc)}

    book = liquidity.book_metrics(data.order_book(sym, 500))

    st = structure.structure(base, k=2)

    deriv: dict = {}
    if with_derivs:
        deriv = derivatives.context(sym, "1h", 48)
        deriv["regime"] = derivatives.price_oi_regime(change_24h, deriv.get("oi_change_24h_pct", 0.0))

    ctx = {
        "symbol": sym, "tf": tf, "price": price, "atr": atr_v,
        "ticker": {
            "change_24h_pct": change_24h,
            "high_24h": float(tick["highPrice"]),
            "low_24h": float(tick["lowPrice"]),
            "quote_volume_24h": float(tick["quoteVolume"]),
            "trades_24h": int(tick["count"]),
        },
        "trend": {"1d": dict(zip(("bias", "note"), _ema_bias(daily))),
                  "4h": dict(zip(("bias", "note"), _ema_bias(htf))),
                  "base": dict(zip(("bias", "note"), _ema_bias(base)))},
        "ind": ind, "vp": vp, "flow": fl, "prints": prints,
        "book": book, "structure": st, "deriv": deriv,
        "rel_volume": volume_profile.relative_volume(base, 20),
        "patterns": patterns.detect(base),
        "candles": base,
    }
    verdict = build_verdict(ctx, equity=equity, risk_pct=risk_pct)
    ctx["verdict"] = verdict
    return ctx
