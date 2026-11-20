"""Acesso a dados publicos da Binance (spot + futures), somente stdlib."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SPOT = "https://api.binance.com"
FAPI = "https://fapi.binance.com"

TF_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

_UA = "finagent/1.0 (personal research)"
_cache: dict[str, tuple[float, Any]] = {}


class BinanceError(RuntimeError):
    pass


def _get(base: str, path: str, params: dict[str, Any] | None = None, ttl: float = 0.0) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if ttl and url in _cache:
        ts, val = _cache[url]
        if time.time() - ts < ttl:
            return val
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            if ttl:
                _cache[url] = (time.time(), data)
            return data
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            last_err = BinanceError(f"HTTP {exc.code} em {path}: {body}")
            if exc.code in (418, 429):
                time.sleep(2 * (attempt + 1))
                continue
            if exc.code == 400:
                raise last_err
            time.sleep(1 + attempt)
        except Exception as exc:  # rede instavel
            last_err = exc
            time.sleep(1 + attempt)
    raise BinanceError(f"falha ao consultar {path}: {last_err}")


def normalize(symbol: str) -> str:
    s = symbol.upper().replace("-", "").replace("/", "").strip()
    if s.endswith("USDT") or s.endswith("BUSD") or s.endswith("USDC"):
        return s
    if s.endswith("USD"):
        return s[:-3] + "USDT"
    return s + "USDT"


def klines(symbol: str, interval: str = "1h", limit: int = 500,
           start: int | None = None, end: int | None = None) -> list[dict]:
    rows = _get(SPOT, "/api/v3/klines", {
        "symbol": symbol, "interval": interval, "limit": min(limit, 1000),
        "startTime": start, "endTime": end,
    })
    out = []
    for r in rows:
        out.append({
            "t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
            "c": float(r[4]), "v": float(r[5]), "t_close": int(r[6]),
            "qv": float(r[7]), "trades": int(r[8]),
            "tbv": float(r[9]), "tbq": float(r[10]),
        })
    return out


def klines_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    step = TF_MS[interval]
    out: list[dict] = []
    cursor = start_ms
    while cursor < end_ms:
        chunk = klines(symbol, interval, 1000, start=cursor)
        if not chunk:
            break
        out.extend(chunk)
        cursor = chunk[-1]["t"] + step
        if len(chunk) < 1000:
            break
    return [k for k in out if k["t"] <= end_ms]


def ticker24h(symbol: str | None = None) -> Any:
    p = {"symbol": symbol} if symbol else None
    return _get(SPOT, "/api/v3/ticker/24hr", p, ttl=20)


def agg_trades(symbol: str, limit: int = 1000) -> list[dict]:
    rows = _get(SPOT, "/api/v3/aggTrades", {"symbol": symbol, "limit": min(limit, 1000)}, ttl=5)
    out = []
    for r in rows:
        p, q = float(r["p"]), float(r["q"])
        out.append({
            "t": int(r["T"]), "p": p, "q": q, "notional": p * q,
            # m=True  => comprador e maker => venda agressiva (taker sell)
            "side": "SELL" if r["m"] else "BUY",
        })
    return out


def order_book(symbol: str, limit: int = 500) -> dict:
    d = _get(SPOT, "/api/v3/depth", {"symbol": symbol, "limit": limit}, ttl=3)
    bids = [(float(p), float(q)) for p, q in d["bids"]]
    asks = [(float(p), float(q)) for p, q in d["asks"]]
    return {"bids": bids, "asks": asks, "ts": time.time()}


# ---------------- futures ----------------

def premium_index(symbol: str) -> dict:
    d = _get(FAPI, "/fapi/v1/premiumIndex", {"symbol": symbol}, ttl=30)
    return {
        "mark": float(d["markPrice"]),
        "index": float(d["indexPrice"]),
        "funding": float(d["lastFundingRate"]),
        "next_funding": int(d["nextFundingTime"]),
    }


def open_interest(symbol: str) -> float:
    d = _get(FAPI, "/fapi/v1/openInterest", {"symbol": symbol}, ttl=30)
    return float(d["openInterest"])


def oi_history(symbol: str, period: str = "1h", limit: int = 48) -> list[dict]:
    rows = _get(FAPI, "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": limit}, ttl=60)
    return [{"t": int(r["timestamp"]), "oi": float(r["sumOpenInterest"]),
             "oi_usd": float(r["sumOpenInterestValue"])} for r in rows]


def long_short_ratio(symbol: str, period: str = "1h", limit: int = 24) -> list[dict]:
    rows = _get(FAPI, "/futures/data/globalLongShortAccountRatio",
                {"symbol": symbol, "period": period, "limit": limit}, ttl=60)
    return [{"t": int(r["timestamp"]), "ratio": float(r["longShortRatio"]),
             "long": float(r["longAccount"]), "short": float(r["shortAccount"])} for r in rows]


def taker_ratio(symbol: str, period: str = "1h", limit: int = 24) -> list[dict]:
    rows = _get(FAPI, "/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": period, "limit": limit}, ttl=60)
    return [{"t": int(r["timestamp"]), "buy": float(r["buySellRatio"]),
             "buy_vol": float(r["buyVol"]), "sell_vol": float(r["sellVol"])} for r in rows]
