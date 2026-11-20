"""Motor de confluencia: componentes ponderados, vies, plano de trade e gates de risco."""
from __future__ import annotations


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _tf_bias(candles: list[dict], ema_fast: float, ema_slow: float) -> tuple[float, str]:
    if len(candles) < 60:
        return 0.0, "dados insuficientes"
    c = candles[-1]["c"]
    if c > ema_fast > ema_slow:
        return 1.0, "preco>EMA20>EMA50 (alta)"
    if c < ema_fast < ema_slow:
        return -1.0, "preco<EMA20<EMA50 (baixa)"
    return 0.0, "EMAs entrelacadas (sem tendencia)"


def score_components(ctx: dict) -> list[dict]:
    comps: list[dict] = []

    # 1. tendencia multi-timeframe
    tfs = ctx["trend"]
    weights = {"1d": 0.5, "4h": 0.3, "base": 0.2}
    acc = wsum = 0.0
    notes = []
    for key, w in weights.items():
        v, note = tfs[key]["bias"], tfs[key]["note"]
        acc += v * w
        wsum += w
        notes.append(f"{key}: {note}")
    comps.append({"name": "Tendencia MTF", "weight": 18,
                  "value": acc / wsum if wsum else 0.0, "note": " | ".join(notes)})

    # 2. estrutura
    st = ctx["structure"]
    v = 0.0
    if "ALTISTA" in st.get("sequence", ""):
        v += 0.7
    if "BAIXISTA" in st.get("sequence", ""):
        v -= 0.7
    if st.get("bos"):
        v += 0.3 if "ALTISTA" in st["bos"] else -0.3
    if st.get("choch"):
        v += 0.4 if "altista" in st["choch"] else -0.4
    note = f"{st.get('sequence','')}; {st.get('bos') or 'sem BOS'}; {st.get('choch') or 'sem CHoCH'}"
    if st.get("sweep"):
        note += f"; {st['sweep']}"
    comps.append({"name": "Estrutura", "weight": 16, "value": _clip(v), "note": note})

    # 3. fluxo / CVD
    fl = ctx["flow"]
    v = _clip(fl.get("imbalance_pct", 0) / 18) * 0.6 + _clip(fl.get("cvd_slope_norm", 0) * 4) * 0.4
    comps.append({"name": "Fluxo agressor", "weight": 15, "value": _clip(v),
                  "note": f"delta {fl.get('cvd_usd',0)/1e6:+.2f}M USD; "
                          f"compra {fl.get('buy_usd',0)/1e6:.1f}M vs venda {fl.get('sell_usd',0)/1e6:.1f}M; "
                          f"{fl.get('divergence','')}"})

    # 4. volume profile / localizacao
    vp = ctx["vp"]
    pos = vp.get("position")
    # o perfil operacional manda; o estrutural so serve de contexto
    opv = vp.get("recent") or vp
    v = {"ACIMA_VAH": 0.8, "ABAIXO_VAL": -0.8, "NO_POC": -0.1, "DENTRO_VA": 0.0}.get(opv.get("position") or pos, 0.0)
    v += _clip(-opv.get("dist_poc_pct", 0) / 6) * 0.25  # desconto favorece compra
    comps.append({"name": "Volume profile", "weight": 12, "value": _clip(v),
                  "note": f"preco {opv.get('position') or pos} (perfil operacional) | "
                          f"POC {opv.get('poc',0):.2f} "
                          f"(dist {opv.get('dist_poc_pct',0):+.2f}%) | VAH {opv.get('vah',0):.2f} "
                          f"/ VAL {opv.get('val',0):.2f}"})

    # 5. liquidez / book
    book = ctx["book"]
    imb = book.get("imbalance_05_pct", 0)
    v = _clip(imb / 35) * 0.6 + (1 if book.get("score", 0) >= 65 else -0.2) * 0.4
    comps.append({"name": "Liquidez/Book", "weight": 8, "value": _clip(v),
                  "note": f"spread {book.get('spread_bps',0):.1f}bps | "
                          f"imbalance 0.5% {imb:+.1f}% | score {book.get('score',0)}/100"})

    # 6. momentum
    ind = ctx["ind"]
    v = 0.0
    rsi_v = ind.get("rsi")
    if rsi_v:
        if rsi_v > 60:
            v += 0.4
        elif rsi_v < 40:
            v -= 0.4
        if rsi_v > 78:
            v -= 0.3  # sobrecompra
        if rsi_v < 22:
            v += 0.3
    macd_v = ind.get("macd")
    if macd_v:
        v += 0.35 if macd_v["hist"] > 0 else -0.35
        if macd_v["hist"] > macd_v["hist_prev"] and macd_v["hist"] > 0:
            v += 0.15
    adx_v = ind.get("adx") or {}
    if adx_v.get("adx", 0) > 25:
        v += 0.1 if adx_v.get("pdi", 0) > adx_v.get("ndi", 0) else -0.1
    comps.append({"name": "Momentum", "weight": 11, "value": _clip(v),
                  "note": f"RSI {rsi_v:.1f} | MACD hist {macd_v['hist']:.2f} | "
                          f"ADX {adx_v.get('adx',0):.1f} (DI+ {adx_v.get('pdi',0):.1f} / DI- {adx_v.get('ndi',0):.1f})"
                          if rsi_v and macd_v and adx_v else "indicadores incompletos"})

    # 7. derivativos
    dv = ctx["deriv"]
    v = 0.0
    fund = dv.get("funding_pct")
    if fund is not None:
        # funding muito positivo = longs pagando caro (contrarian baixista)
        v -= _clip(fund / 0.05) * 0.5
    ratio = dv.get("taker_buy_ratio")
    if ratio is not None:
        v += _clip((ratio - 1.0) * 2)
    oi_chg = dv.get("oi_change_24h_pct", 0) or 0
    regime = dv.get("regime", "")
    if "ALTA" in regime:
        v += 0.3 if oi_chg > 0 else 0.1
    if "BAIXA" in regime:
        v -= 0.2
    comps.append({"name": "Derivativos", "weight": 10, "value": _clip(v),
                  "note": f"funding {fund if fund is not None else 0:.4f}% por 8h "
                          f"({dv.get('funding_annual_pct',0):+.1f}% a.a.) | "
                          f"OI 24h {oi_chg:+.2f}% | L/S {dv.get('ls_ratio',0):.2f} | "
                          f"taker buy {ratio if ratio else 0:.2f}"})

    # 8. volume relativo / expansao
    rel = ctx.get("rel_volume") or 1.0
    v = _clip((rel - 1) * 0.8)
    if rel > 2:
        v = _clip(v + 0.2)
    comps.append({"name": "Volume", "weight": 10, "value": _clip(v),
                  "note": f"volume do candle {rel:.2f}x a media de 20"})

    # 9. padroes graficos (peso moderado: confirma ou desmente a estrutura)
    pv = ctx.get("patterns") or {}
    plist = pv.get("patterns") or []
    v = 0.0
    for p in plist:
        step = 0.45 if p.get("status") == "CONFIRMADO" else 0.15
        v += step if p.get("direction") == "ALTA" else -step
    conf_names = [p["name"] for p in plist if p.get("status") == "CONFIRMADO"]
    form_names = [p["name"] for p in plist if p.get("status") != "CONFIRMADO"]
    if plist:
        note = ("confirmados: " + ", ".join(conf_names)) if conf_names else "nenhum confirmado"
        if form_names:
            note += " | formando: " + ", ".join(form_names)
    else:
        note = "nenhum padrao classico na janela"
    comps.append({"name": "Padroes", "weight": 7, "value": _clip(v), "note": note})

    return comps


def build_verdict(ctx: dict, equity: float = 10_000, risk_pct: float = 1.0) -> dict:
    comps = score_components(ctx)
    total_w = sum(c["weight"] for c in comps)
    raw = sum(c["weight"] * c["value"] for c in comps) / total_w  # -1..1
    direction = "LONG" if raw >= 0 else "SHORT"
    conviction = abs(raw) * 100

    opposing = [c for c in comps if c["value"] * (1 if direction == "LONG" else -1) < -0.25]
    support = [c for c in comps if c["value"] * (1 if direction == "LONG" else -1) > 0.25]

    price = ctx["price"]
    atr_v = ctx["ind"]["atr"] or price * 0.01
    st = ctx["structure"]
    vp = ctx["vp"]

    if direction == "LONG":
        struct_stop = (st.get("swing_low") or price - 2 * atr_v) - 0.25 * atr_v
        entry = price
        vwap = ctx["ind"].get("vwap")
        if vwap and price - vwap > 1.2 * atr_v:
            entry = max(vwap, price - 1.0 * atr_v)
            entry_note = "preco esticado acima do VWAP: entrada em pullback"
        else:
            entry_note = "entrada a mercado / limite no preco atual"
        stop = max(struct_stop, entry - 2.2 * atr_v)
        stop = min(stop, entry - 0.7 * atr_v)
        risk = entry - stop
        tp1 = entry + 2 * risk
        tp2 = entry + 3.2 * risk
        if vp.get("vah") and vp["vah"] > entry:
            tp1 = min(tp1, vp["vah"]) if vp["vah"] - entry > risk else tp1
    else:
        struct_stop = (st.get("swing_high") or price + 2 * atr_v) + 0.25 * atr_v
        entry = price
        vwap = ctx["ind"].get("vwap")
        if vwap and vwap - price > 1.2 * atr_v:
            entry = min(vwap, price + 1.0 * atr_v)
            entry_note = "preco esticado abaixo do VWAP: entrada em pullback"
        else:
            entry_note = "entrada a mercado / limite no preco atual"
        stop = min(struct_stop, entry + 2.2 * atr_v)
        stop = max(stop, entry + 0.7 * atr_v)
        risk = stop - entry
        tp1 = entry - 2 * risk
        tp2 = entry - 3.2 * risk
        if vp.get("val") and vp["val"] < entry:
            tp1 = max(tp1, vp["val"]) if entry - vp["val"] > risk else tp1

    rr1 = abs(tp1 - entry) / risk if risk else 0
    rr2 = abs(tp2 - entry) / risk if risk else 0
    size = (equity * risk_pct / 100) / risk if risk else 0

    gates = []
    if ctx["book"].get("spread_bps", 0) > 12:
        gates.append(f"spread alto ({ctx['book']['spread_bps']:.1f}bps)")
    if ctx["book"].get("score", 100) < 40:
        gates.append(f"liquidez fraca (score {ctx['book'].get('score')}/100)")
    if conviction < 45:
        gates.append(f"conviccao baixa ({conviction:.0f}%)")
    if len(opposing) >= 3:
        gates.append("conflito entre " + ", ".join(c["name"] for c in opposing[:3]))
    if atr_v / price * 100 > 5:
        gates.append(f"volatilidade extrema (ATR {atr_v/price*100:.1f}%)")
    if ctx["deriv"].get("funding_annual_pct") and abs(ctx["deriv"]["funding_annual_pct"]) > 60:
        gates.append(f"funding extremo ({ctx['deriv']['funding_annual_pct']:+.0f}% a.a.)")

    # exaustao: momentum extremo contra a direcao do sinal
    exhausted = False
    rsi_v = ctx["ind"].get("rsi")
    if rsi_v is not None:
        if direction == "SHORT" and rsi_v <= 30:
            gates.append(f"RSI {rsi_v:.0f} sobrevendido: short em exaustao, exige pullback")
            exhausted = True
        elif direction == "LONG" and rsi_v >= 70:
            gates.append(f"RSI {rsi_v:.0f} sobrecomprado: long em exaustao, exige pullback")
            exhausted = True
    pos = vp.get("position")
    op = vp.get("recent") or {}
    if op.get("position"):
        pos = op["position"]  # area de valor operacional manda na decisao
    if direction == "SHORT" and pos == "ABAIXO_VAL":
        gates.append("short abaixo do VAL operacional: risco de reversao para a area de valor")
        exhausted = True
    elif direction == "LONG" and pos == "ACIMA_VAH":
        gates.append("long acima do VAH operacional: risco de reversao para a area de valor")
        exhausted = True

    # padrao classico confirmado contra o sinal e motivo de espera
    want = "BAIXA" if direction == "LONG" else "ALTA"
    against = [p for p in (ctx.get("patterns") or {}).get("patterns", [])
               if p.get("status") == "CONFIRMADO" and p.get("direction") == want]
    if against:
        gates.append(f"padrao {against[0]['name']} confirmado contra o sinal")
        exhausted = True

    if conviction >= 60 and not gates:
        status = "EXECUTAVEL"
    elif conviction >= 45:
        status = "AGUARDAR GATILHO" if gates else "EXECUTAVEL COM CAUTELA"
    else:
        status = "SEM SETUP"

    setup = _setup_name(ctx, direction, conviction)
    if exhausted:
        setup += " — ESTICADO, aguardar pullback"
    return {
        "direction": direction, "conviction": conviction, "status": status,
        "setup": setup, "components": comps, "opposing": [c["name"] for c in opposing],
        "supporting": [c["name"] for c in support],
        "gates": gates, "exhausted": exhausted,
        "plan": {
            "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
            "risk_pct_price": risk / entry * 100 if entry else 0,
            "rr_tp1": rr1, "rr_tp2": rr2,
            "size_units": size, "size_usd": size * entry,
            "risk_usd": equity * risk_pct / 100,
            "equity": equity, "risk_pct": risk_pct,
            "entry_note": entry_note,
            "invalidation": ("fechamento abaixo de " if direction == "LONG" else "fechamento acima de ")
                            + f"{stop:.2f}",
        },
    }


def _setup_name(ctx: dict, direction: str, conviction: float) -> str:
    vp = ctx["vp"]
    st = ctx["structure"]
    if st.get("sweep") and conviction >= 50:
        return f"Liquidity sweep + reversao ({direction})"
    if st.get("bos") and conviction >= 50:
        return f"Breakout/BOS com continuacao ({direction})"
    if vp.get("position") in ("ACIMA_VAH", "ABAIXO_VAL") and conviction >= 50:
        return f"Aceitacao de valor + tendencia ({direction})"
    if "COMPRESSAO" in st.get("sequence", ""):
        return "Compressao: aguardar expansao"
    return f"Confluencia tecnica ({direction})" if conviction >= 45 else "Sem setup definido"
