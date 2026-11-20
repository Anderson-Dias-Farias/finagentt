"""Testes determinísticos do nucleo (sem rede)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finagent import flow, indicators, liquidity, patterns, score, structure, volume_profile  # noqa: E402


def path_candles(legs, spread=0.3, v=10):
    """Série controlada: legs = [(inicio, fim, n_candles), ...]."""
    closes = []
    for s, e, n in legs:
        for j in range(n):
            closes.append(s + (e - s) * j / n)
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        out.append(candle(prev, c + spread, c - spread, c, v, t=i))
        prev = c
    return out


def zigzag(high, low, swings, spread=0.3, v=10):
    """Alterna high/low `swings` vezes, 4 candles por perna."""
    pts = [low if i % 2 == 0 else high for i in range(swings + 1)]
    legs = [(pts[i], pts[i + 1], 4) for i in range(len(pts) - 1)]
    return path_candles(legs, spread=spread, v=v)


def candle(o, h, l, c, v, tbq_usd=None, t=0):
    """v em unidades, qv/tbq em USD (como a Binance entrega)."""
    qv = v * c
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "qv": qv,
            "tbq": qv / 2 if tbq_usd is None else tbq_usd, "n": 100}


def series(n=120, start=100.0, step=0.5):
    out, p = [], start
    for i in range(n):
        p += step
        out.append(candle(p, p + 1, p - 1, p + 0.5, 10, t=i))
    return out


def wave(n=60, amp=3.0, period=5):
    out, p = [], 100.0
    for i in range(n):
        p += amp if (i // period) % 2 == 0 else -amp
        out.append(candle(p, p + 2, p - 2, p, 10, t=i))
    return out


H = lambda cs: [c["h"] for c in cs]  # noqa: E731
L = lambda cs: [c["l"] for c in cs]  # noqa: E731
C = lambda cs: [c["c"] for c in cs]  # noqa: E731


def make_ctx(**over):
    """Contexto minimo viavel para build_verdict()."""
    ctx = {
        "price": 100.0,
        "trend": {
            "1d": {"bias": -1.0, "note": "baixa"},
            "4h": {"bias": -1.0, "note": "baixa"},
            "base": {"bias": -1.0, "note": "baixa"},
        },
        "structure": {"sequence": "BAIXISTA (LH/LL)", "bos": "BOS BAIXISTA abaixo de 101",
                      "choch": None, "sweep": None, "swing_high": 103.0, "swing_low": 96.0},
        "flow": {"imbalance_pct": -6.0, "cvd_slope_norm": -0.02, "cvd_usd": -5e6,
                 "buy_usd": 4e6, "sell_usd": 5e6, "divergence": "ALINHADO"},
        "vp": {"position": "DENTRO_VA", "dist_poc_pct": -1.0, "poc": 101.0,
               "vah": 104.0, "val": 98.0},
        "book": {"imbalance_05_pct": -5.0, "score": 80, "spread_bps": 1.0},
        "ind": {"rsi": 45.0, "macd": {"hist": -0.4, "hist_prev": -0.2},
                "adx": {"adx": 30.0, "pdi": 15.0, "ndi": 30.0}, "atr": 1.2, "vwap": 100.5},
        "deriv": {"funding_pct": 0.01, "funding_annual_pct": 10.0, "taker_buy_ratio": 0.95,
                  "oi_change_24h_pct": -2.0, "regime": "BAIXA", "ls_ratio": 2.0},
        "rel_volume": 1.2,
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(ctx.get(k), dict):
            ctx[k] = {**ctx[k], **v}
        else:
            ctx[k] = v
    return ctx


class TestIndicators(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(indicators.sma([1, 2, 3, 4, 5], 5), 3.0)

    def test_ema_seed_no_primeiro_valor(self):
        # seed = xs[0], alpha = 2/(n+1) -> 4.0625 para [1..5], n=3
        self.assertAlmostEqual(indicators.ema([1, 2, 3, 4, 5], 3), 4.0625, places=6)

    def test_rsi_extremos(self):
        self.assertGreater(indicators.rsi(C(series(60, step=1.0))), 95)
        self.assertLess(indicators.rsi(C(series(60, start=300, step=-1.0))), 5)

    def test_atr_positivo(self):
        cs = series(60)
        self.assertGreater(indicators.atr(H(cs), L(cs), C(cs)), 0)

    def test_realized_vol_escala(self):
        # corpo fixo de 1% -> vol na casa de 1, nao de 1000
        cs = [candle(100 * (1.01 ** i), 100 * (1.01 ** i) * 1.005,
                     100 * (1.01 ** i) * 0.995, 100 * (1.01 ** (i + 1)), 10) for i in range(50)]
        self.assertLess(indicators.realized_vol(C(cs)), 5)

    def test_macd_e_bollinger(self):
        cs = series(120)
        self.assertIn("hist", indicators.macd(C(cs)))
        bb = indicators.bollinger(C(cs))
        self.assertLess(bb["lower"], bb["upper"])


class TestFlow(unittest.TestCase):
    def test_delta_formula(self):
        # delta = 2*tbq - qv ; candle de 10 un a 100 => qv=1000
        d = flow.delta_from_candles([candle(100, 101, 99, 100, 10, tbq_usd=700)])[0]
        self.assertAlmostEqual(d["delta"], 2 * 700 - 1000)

    def test_delta_comprador_total(self):
        # agressao 100% compradora: tbq == qv => delta == +qv
        d = flow.delta_from_candles([candle(100, 101, 99, 100, 10, tbq_usd=1000)])[0]
        self.assertAlmostEqual(d["delta"], 1000.0)
        self.assertAlmostEqual(d["buy_ratio"], 1.0)

    def test_delta_vendedor_total(self):
        d = flow.delta_from_candles([candle(100, 101, 99, 100, 10, tbq_usd=0)])[0]
        self.assertAlmostEqual(d["delta"], -1000.0)

    def test_summary_imbalance(self):
        buys = [candle(100, 101, 99, 100, 10, tbq_usd=900, t=i) for i in range(30)]
        s = flow.flow_summary(buys)
        self.assertGreater(s["imbalance_pct"], 50)
        self.assertEqual(s["lookback"], 24)


class TestVolumeProfile(unittest.TestCase):
    def test_ordem_poc_na_value_area(self):
        vp = volume_profile.build_profile(wave(80), bins=30)
        self.assertTrue(vp["val"] <= vp["poc"] <= vp["vah"])
        self.assertGreaterEqual(vp["va_vol_pct"], 60)
        self.assertLessEqual(vp["va_vol_pct"], 100)

    def test_faixa_cobre_os_candles(self):
        cs = wave(80)
        vp = volume_profile.build_profile(cs, bins=20)
        self.assertAlmostEqual(vp["low"], min(c["l"] for c in cs), places=6)
        self.assertAlmostEqual(vp["high"], max(c["h"] for c in cs), places=6)

    def test_relative_volume_neutro(self):
        cs = [candle(100, 100.5, 99.5, 100, 10, t=i) for i in range(40)]
        self.assertAlmostEqual(volume_profile.relative_volume(cs, 20), 1.0, places=6)

    def test_relative_volume_detecta_expansao(self):
        cs = [candle(100, 100.5, 99.5, 100, 10, t=i) for i in range(40)]
        for c in cs[-3:]:
            c["v"] *= 5
            c["qv"] *= 5
        self.assertGreater(volume_profile.relative_volume(cs, 20), 1.5)

    def test_relative_volume_sem_dados(self):
        self.assertIsNone(volume_profile.relative_volume([candle(100, 101, 99, 100, 10)], 20))


class TestStructure(unittest.TestCase):
    def test_swings_alternam(self):
        sw = structure.swings(wave(60), k=2)
        self.assertGreater(len(sw), 4)
        types = [s["type"] for s in sw]
        self.assertTrue(all(a != b for a, b in zip(types, types[1:])))

    def test_sequencia_alta(self):
        st = structure.structure(series(80, step=1.0), k=2)
        self.assertIn(st["sequence"], ("ALTA (HH/HL)", "LATERAL", "INDEFINIDA", "BAIXA (LH/LL)"))

    def test_bos_em_rompimento(self):
        base = wave(50)
        top = base + [candle(120, 130, 119, 129, 20, t=50), candle(129, 131, 127, 130, 20, t=51)]
        st = structure.structure(top, k=2)
        self.assertIn("bos", st)

    def test_range_pos_nos_limites(self):
        cs = wave(60)
        st = structure.structure(cs, k=2)
        self.assertGreaterEqual(st["range_pos_pct"], 0)
        self.assertLessEqual(st["range_pos_pct"], 100)


class TestLiquidity(unittest.TestCase):
    def test_spread_e_cobertura(self):
        book = {"bids": [[100.0, 5.0], [99.9, 3.0]], "asks": [[100.1, 4.0], [100.2, 2.0]]}
        m = liquidity.book_metrics(book)
        self.assertAlmostEqual(m["mid"], 100.05, places=4)
        self.assertGreater(m["spread_bps"], 0)
        self.assertAlmostEqual(m["coverage_pct_lo"], (100.05 - 99.9) / 100.05 * 100, places=4)
        self.assertEqual(m["levels"], 4)

    def test_imbalance_lado(self):
        book = {"bids": [[100.0, 10.0]], "asks": [[100.1, 1.0]]}
        self.assertGreater(liquidity.book_metrics(book)["bands"]["0.10%"]["imbalance_pct"], 0)

    def test_slippage_cresce_com_tamanho(self):
        # book fundo o bastante para preencher todos os notionais
        book = {"bids": [[100.0 - i * 0.01, 5000.0] for i in range(60)],
                "asks": [[100.01 + i * 0.01, 5000.0] for i in range(60)]}
        m = liquidity.book_metrics(book)
        sl = [s["buy_slippage_bps"] for s in m["slippage"]]
        self.assertEqual(sl, sorted(sl))
        self.assertTrue(all(s["complete"] for s in m["slippage"]))

    def test_slippage_marca_book_rasco(self):
        book = {"bids": [[100.0, 0.01]], "asks": [[100.1, 0.01]]}
        m = liquidity.book_metrics(book)
        self.assertFalse(m["slippage"][0]["complete"])
        self.assertLess(m["slippage"][0]["buy_fill_pct"], 1)


class TestScore(unittest.TestCase):
    def test_clip(self):
        self.assertEqual(score._clip(5), 1)
        self.assertEqual(score._clip(-5), -1)
        self.assertAlmostEqual(score._clip(0.3), 0.3)

    def test_bias(self):
        up = series(80, step=1.0)
        dn = series(80, start=300, step=-1.0)
        # _tf_bias recebe os VALORES das EMAs (nao os periodos)
        fast_up, slow_up = indicators.ema(C(up), 20), indicators.ema(C(up), 50)
        fast_dn, slow_dn = indicators.ema(C(dn), 20), indicators.ema(C(dn), 50)
        self.assertGreater(fast_up, slow_up)
        self.assertLess(fast_dn, slow_dn)
        self.assertEqual(score._tf_bias(up, fast_up, slow_up)[0], 1.0)
        self.assertEqual(score._tf_bias(dn, fast_dn, slow_dn)[0], -1.0)

    def test_bias_indefinido_com_poucos_candles(self):
        self.assertEqual(score._tf_bias(series(20), 1.0, 0.5), (0.0, "dados insuficientes"))

    def test_bias_entrelacado(self):
        cs = series(80)
        c = cs[-1]["c"]
        # EMAs cruzadas (fast acima da slow) mas preco abaixo das duas -> sem tendencia
        self.assertEqual(score._tf_bias(cs, c * 1.02, c * 1.01)[0], 0.0)

    def test_veredicto_short_base(self):
        v = score.build_verdict(make_ctx())
        self.assertEqual(v["direction"], "SHORT")
        self.assertFalse(v["exhausted"])
        self.assertNotIn("ESTICADO", v["setup"])
        self.assertTrue(0 <= v["conviction"] <= 100)

    def test_gate_exaustao_short_sobrevendido(self):
        v = score.build_verdict(make_ctx(ind={"rsi": 26.0}))
        self.assertTrue(v["exhausted"])
        self.assertIn("ESTICADO", v["setup"])
        self.assertTrue(any("exaustao" in g for g in v["gates"]))
        self.assertNotEqual(v["status"], "EXECUTAVEL")

    def test_gate_exaustao_long_sobrecomprado(self):
        v = score.build_verdict(make_ctx(
            ind={"rsi": 78.0, "macd": {"hist": 0.6, "hist_prev": 0.4},
                 "adx": {"adx": 30.0, "pdi": 30.0, "ndi": 15.0}},
            flow={"imbalance_pct": 8.0, "cvd_slope_norm": 0.03, "cvd_usd": 6e6,
                  "buy_usd": 6e6, "sell_usd": 4e6, "divergence": "ALINHADO"},
            trend={"1d": {"bias": 1.0, "note": "alta"},
                   "4h": {"bias": 1.0, "note": "alta"},
                   "base": {"bias": 1.0, "note": "alta"}},
            structure={"sequence": "ALTISTA (HH/HL)", "bos": "BOS ALTISTA acima de 101",
                       "choch": None, "sweep": None, "swing_high": 104.0, "swing_low": 97.0},
            deriv={"regime": "ALTA", "oi_change_24h_pct": 2.0, "funding_pct": -0.01,
                   "funding_annual_pct": -10.0, "taker_buy_ratio": 1.05},
            vp={"position": "ACIMA_VAH", "dist_poc_pct": 6.0},
        ))
        self.assertEqual(v["direction"], "LONG")
        self.assertTrue(v["exhausted"])
        self.assertIn("ESTICADO", v["setup"])


class TestPatterns(unittest.TestCase):
    def names(self, det):
        return [p["name"] for p in det["patterns"]]

    def test_duplo_topo(self):
        cs = path_candles([(95, 110, 10), (110, 100, 6), (100, 110, 8), (110, 95, 10)])
        det = patterns.detect(cs)
        self.assertIn("DUPLO TOPO", self.names(det))
        p = next(p for p in det["patterns"] if p["name"] == "DUPLO TOPO")
        self.assertEqual(p["direction"], patterns.BAIXA)
        self.assertEqual(p["status"], "CONFIRMADO")
        self.assertLess(p["target"], det["price"])

    def test_duplo_fundo(self):
        cs = path_candles([(110, 95, 10), (95, 105, 6), (105, 95, 8), (95, 110, 10)])
        det = patterns.detect(cs)
        self.assertIn("DUPLO FUNDO", self.names(det))
        p = next(p for p in det["patterns"] if p["name"] == "DUPLO FUNDO")
        self.assertEqual(p["direction"], patterns.ALTA)
        self.assertGreater(p["target"], det["price"])

    def test_oco_cabeca_ombro(self):
        cs = path_candles([(100, 110, 5), (110, 104, 5), (104, 118, 6),
                           (118, 105, 6), (105, 111, 5), (111, 95, 8)])
        det = patterns.detect(cs)
        self.assertIn("OMBRO-CABECA-OMBRO", self.names(det))
        self.assertEqual(det["bias"], patterns.BAIXA)

    def test_triangulo_ascendente(self):
        cs = path_candles([(95, 110, 5), (110, 97, 4), (97, 110, 5), (110, 101, 4),
                           (101, 110, 5), (110, 105, 4), (105, 110, 4)])
        det = patterns.detect(cs)
        self.assertIn("TRIANGULO ASCENDENTE", self.names(det))
        p = next(p for p in det["patterns"] if p["name"] == "TRIANGULO ASCENDENTE")
        self.assertEqual(p["direction"], patterns.ALTA)

    def test_bandeira_alta(self):
        cs = path_candles([(96, 99, 10), (100, 112, 6), (112, 111.8, 9)])
        det = patterns.detect(cs)
        self.assertTrue(any("BANDEIRA" in n for n in self.names(det)))

    def test_retangulo(self):
        # range precisa de 3 toques em cada lado para nao ser so um zigzag
        cs = path_candles([(100, 110, 5), (110, 100, 5), (100, 110, 5), (110, 100, 5),
                           (100, 110, 5), (110, 100, 5), (100, 110, 5)])
        det = patterns.detect(cs)
        self.assertIn("RETANGULO (range)", self.names(det))
        ret = [p for p in det["patterns"] if p["name"].startswith("RETANGULO")][0]
        self.assertIsNone(ret["target"])
        self.assertEqual(ret["direction"], patterns.NEUTRO)

    def test_dados_insuficientes(self):
        det = patterns.detect(series(10))
        self.assertEqual(det["patterns"], [])
        self.assertEqual(det["summary"], "dados insuficientes")

    def test_serie_monotonica_sem_duplo_topo(self):
        det = patterns.detect(series(80))
        self.assertNotIn("DUPLO TOPO", self.names(det))
        self.assertNotIn("DUPLO FUNDO", self.names(det))


if __name__ == "__main__":
    unittest.main(verbosity=2)
