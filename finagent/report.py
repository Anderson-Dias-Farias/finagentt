"""Renderizacao do relatorio (terminal/telegram) e export JSON."""
from __future__ import annotations

import json
import time

W = 78


def _line(ch: str = "-") -> str:
    return ch * W


def _fmt_usd(v: float) -> str:
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sign}${v/1e9:.2f}B"
    if v >= 1e6:
        return f"{sign}${v/1e6:.2f}M"
    if v >= 1e3:
        return f"{sign}${v/1e3:.1f}K"
    return f"{sign}${v:.2f}"


def _fmt_px(v: float) -> str:
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:.4f}"
    return f"{v:.6f}"


def _bar(value: float, width: int = 10) -> str:
    filled = min(width, int(round(abs(value) * width)))
    if value >= 0:
        return " " * width + "|" + "#" * filled + " " * (width - filled) + " "
    return " " * (width - filled) + "#" * filled + "|" + " " * width + " "


def render(ctx: dict) -> str:
    v = ctx["verdict"]
    p = v["plan"]
    st = ctx["structure"]
    vp = ctx["vp"]
    fl = ctx["flow"]
    pr = ctx.get("prints", {})
    bk = ctx["book"]
    dv = ctx["deriv"]
    ind = ctx["ind"]
    tk = ctx["ticker"]

    out: list[str] = []
    add = out.append
    add("=" * W)
    add(f" FINAGENT  |  {ctx['symbol']}  |  {ctx['tf']}  |  {time.strftime('%d/%m/%Y %H:%M')}")
    add("=" * W)
    add(f" Preco {_fmt_px(ctx['price'])}   |   24h {tk['change_24h_pct']:+.2f}%   |   "
        f"Volume 24h {_fmt_usd(tk['quote_volume_24h'])}")
    add(f" Range 24h {_fmt_px(tk['low_24h'])} - {_fmt_px(tk['high_24h'])}   |   "
        f"ATR {_fmt_px(ctx['atr'])} ({ind['atr_pct']:.2f}%)")
    add("")

    status_tag = {"EXECUTAVEL": "[EXECUTAVEL]", "EXECUTAVEL COM CAUTELA": "[CAUTELA]",
                  "AGUARDAR GATILHO": "[AGUARDAR]", "SEM SETUP": "[SEM SETUP]"}.get(v["status"], v["status"])
    add(f" VEREDITO: {status_tag}  {v['direction']}  |  conviccao {v['conviction']:.0f}/100")
    add(f" Setup: {v['setup']}")
    add("")

    add(_line())
    add(" PLANO DE TRADE")
    add(_line())
    add(f"  Entrada .......... {_fmt_px(p['entry'])}   ({p['entry_note']})")
    add(f"  Stop ............. {_fmt_px(p['stop'])}   risco {p['risk_pct_price']:.2f}% do preco")
    add(f"  Alvo 1 ........... {_fmt_px(p['tp1'])}   R:R {p['rr_tp1']:.2f}")
    add(f"  Alvo 2 ........... {_fmt_px(p['tp2'])}   R:R {p['rr_tp2']:.2f}")
    add(f"  Tamanho .......... {p['size_units']:.6g} un ({_fmt_usd(p['size_usd'])}) "
        f"| risco {_fmt_usd(p['risk_usd'])} ({p['risk_pct']}% de {_fmt_usd(p['equity'])})")
    add(f"  Invalidacao ...... {p['invalidation']}")
    add("")

    add(_line())
    add(" ESTRUTURA E TENDENCIA")
    add(_line())
    for key in ("1d", "4h", "base"):
        t = ctx["trend"][key]
        add(f"  {key:<4} {t['note']}")
    add(f"  Sequencia ........ {st.get('sequence','n/d')}")
    add(f"  BOS/CHoCH ........ {st.get('bos') or '-'} / {st.get('choch') or '-'}")
    if st.get("sweep"):
        add(f"  Sweep de liquidez  {st['sweep']}")
    add(f"  Candles .......... {st.get('candle_pattern','n/d')}")
    add(f"  Posicao no range . {st.get('range_pos_pct',0):.0f}% de 60 candles "
        f"({_fmt_px(st.get('range_low',0))} - {_fmt_px(st.get('range_high',0))})")
    for z in st.get("zones", [])[:3]:
        add(f"   - {z['kind']:<11} {_fmt_px(z['price']):>12}  ({z['dist_pct']:+.2f}%, {z['touches']} toques)")
    add("")

    add(_line())
    add(" FLUXO DE ORDENS")
    add(_line())
    add(f"  CVD ({fl.get('lookback',0)} candles) .. {_fmt_usd(fl.get('cvd_usd',0))}  "
        f"({fl.get('divergence','')})")
    add(f"  Compra/Venda ..... {_fmt_usd(fl.get('buy_usd',0))} / {_fmt_usd(fl.get('sell_usd',0))}  "
        f"imbalance {fl.get('imbalance_pct',0):+.1f}%")
    add(f"  Ultimo candle .... delta {_fmt_usd(fl.get('last_candle_delta',0))}  "
        f"taker buy {(fl.get('last_candle_buy_ratio') or 0)*100:.1f}%")
    if pr and "avg_ticket" in pr:
        win = pr.get("window_s", pr["window_min"] * 60)
        win_txt = f"{win:.0f}s" if win < 120 else f"{win/60:.1f} min"
        lim = " (amostra limitada aos 1000 prints mais recentes)" if pr.get("limited_sample") else ""
        add(f"  Ordens executadas  {pr['count']} prints em {win_txt}{lim} "
            f"({pr['trades_per_min']:.0f} prints/min)")
        add(f"  Ticket medio ..... {_fmt_usd(pr['avg_ticket'])} | mediana {_fmt_usd(pr['median_ticket'])} "
            f"| p90 {_fmt_usd(pr['p90_ticket'])} | p99 {_fmt_usd(pr['p99_ticket'])}")
        add(f"  Ordens grandes ... {pr['large_count']} prints >= {_fmt_usd(pr['large_threshold'])} "
            f"({pr['large_notional_pct']:.1f}% do volume, vies {pr['large_bias_pct']:+.0f}%)")
        add(f"  Top prints ....... " + " | ".join(
            f"{t['side']} {_fmt_usd(t['usd'])} @ {_fmt_px(t['price'])}" for t in pr.get("top_prints", [])[:3]))
    elif pr.get("error"):
        add(f"  (aggTrades indisponivel: {pr['error'][:60]})")
    add("")

    add(_line())
    add(" VOLUME PROFILE / LIQUIDEZ")
    add(_line())
    if vp:
        rc = vp.get("recent")
        op = rc or vp
        op_win = op.get("candles", vp.get("candles", "?"))
        add(f"  OPERACIONAL (ultimos {op_win} candles) — area de valor que manda na decisao")
        add(f"   POC {_fmt_px(op['poc'])}  |  VAH {_fmt_px(op['vah'])}  |  VAL {_fmt_px(op['val'])}"
            f"  |  preco {op['position']} (dist POC {op['dist_poc_pct']:+.2f}%)")
        add(f"  ESTRUTURAL ({vp.get('candles', '?')} candles) — referencia de contexto/imas")
        add(f"   POC {_fmt_px(vp['poc'])}  |  VAH {_fmt_px(vp['vah'])}  |  VAL {_fmt_px(vp['val'])}"
            f"  |  preco {vp['position']} (dist POC {vp['dist_poc_pct']:+.2f}%)"
            f"  |  VA {vp['va_vol_pct']:.0f}% do volume")
        if vp.get("hvn"):
            add(f"  HVN (nos de volume) {', '.join(_fmt_px(x) for x in vp['hvn'])}")
        if vp.get("lvn"):
            add(f"  LVN (areas vazias)  {', '.join(_fmt_px(x) for x in vp['lvn'])}")
    add(f"  Spread ........... {bk.get('spread_bps',0):.2f} bps  |  mid {_fmt_px(bk.get('mid',0))}")
    add(f"  Profundidade 0.5%  bid {_fmt_usd(bk.get('bands',{}).get('0.50%',{}).get('bid_usd',0))} / "
        f"ask {_fmt_usd(bk.get('bands',{}).get('0.50%',{}).get('ask_usd',0))}  "
        f"(imb {bk.get('imbalance_05_pct',0):+.0f}%)")
    for s in bk.get("slippage", []):
        add(f"  Slippage {_fmt_usd(s['notional']):>7} .. compra {s['buy_slippage_bps'] or 0:.1f} bps "
            f"| venda {s['sell_slippage_bps'] or 0:.1f} bps")
    if bk.get("walls"):
        add("  Paredes do book .. " + " | ".join(
            f"{w['side']} {_fmt_usd(w['usd'])} @ {_fmt_px(w['price'])} ({w['x_median']:.1f}x)"
            for w in bk["walls"][:3]))
    add("")

    if dv and not dv.get("error_funding"):
        add(_line())
        add(" DERIVATIVOS (futures)")
        add(_line())
        add(f"  Funding .......... {dv.get('funding_pct',0):.4f}% por 8h  "
            f"({dv.get('funding_annual_pct',0):+.1f}% a.a.)")
        add(f"  Open interest .... {_fmt_usd(dv.get('oi_usd',0))}  |  1h {dv.get('oi_change_1h_pct',0):+.2f}%  "
            f"|  24h {dv.get('oi_change_24h_pct',0):+.2f}%")
        add(f"  Long/Short ....... {dv.get('ls_ratio',0):.2f}  "
            f"(longs {dv.get('ls_long_pct',0):.0f}%)  |  taker buy {dv.get('taker_buy_ratio',0):.2f}")
        add(f"  Regime ........... {dv.get('regime','n/d')}")
        add("")

    add(_line())
    add(" MOMENTUM / INDICADORES")
    add(_line())
    bb = ind.get("bollinger") or {}
    add(f"  RSI(14) {ind['rsi'] or 0:.1f}  |  MACD hist {((ind.get('macd') or {}).get('hist',0)):.2f}  |  "
        f"ADX {((ind.get('adx') or {}).get('adx',0)):.1f}")
    add(f"  EMA20 {_fmt_px(ind.get('ema20') or 0)}  |  EMA50 {_fmt_px(ind.get('ema50') or 0)}  |  "
        f"EMA200 {_fmt_px(ind.get('ema200') or 0)}  |  VWAP24 {_fmt_px(ind.get('vwap') or 0)}")
    if bb:
        add(f"  Bollinger ........ {_fmt_px(bb['lower'])} - {_fmt_px(bb['mid'])} - {_fmt_px(bb['upper'])} "
            f"(largura {bb['width_pct']:.2f}%)")
    add(f"  Volume relativo .. {(ctx.get('rel_volume') or 0):.2f}x")
    add("")

    pt = ctx.get("patterns") or {}
    if pt.get("patterns"):
        add(_line())
        add(" PADROES GRAFICOS")
        add(_line())
        for p in pt["patterns"][:8]:
            tgt = f" alvo {_fmt_px(p['target'])}" if p.get("target") else ""
            add(f"  {p['name']:<20} {p['direction']:<6} {p['status']:<10} {p['conf']:>3}/100{tgt}")
            add(f"    {p['detail'][:96]}")
        add("")
    else:
        add(_line())
        add(" PADROES GRAFICOS")
        add(_line())
        add("  Nenhum padrao classico fechado na janela analisada.")
        add("")

    add(_line())
    add(" SCORE DE CONFLUENCIA")
    add(_line())
    for c in v["components"]:
        add(f"  {c['name']:<16} {_bar(c['value'])} {c['value']:+.2f}  w{c['weight']:<3} {c['note'][:26]}")
    add(f"  {'TOTAL':<16} {v['conviction']:.0f}/100 para {v['direction']}")
    if v["gates"]:
        add("")
        add(" ALERTAS / GATES")
        for g in v["gates"]:
            add(f"  ! {g}")
    add("")
    add(_line())
    add(" LEITURA")
    add(_line())
    for ln in _narrative(ctx):
        add(f"  {ln}")
    add("=" * W)
    add("  Nao e recomendacao de investimento. Gestao de risco e obrigatoria.")
    return "\n".join(out)


def _narrative(ctx: dict) -> list[str]:
    v = ctx["verdict"]
    st = ctx["structure"]
    vp = ctx["vp"]
    fl = ctx["flow"]
    dv = ctx["deriv"]
    pr = ctx.get("prints", {})
    lines = []

    trend_txt = ", ".join(f"{k} {'alta' if ctx['trend'][k]['bias'] > 0 else 'baixa' if ctx['trend'][k]['bias'] < 0 else 'lateral'}"
                          for k in ("1d", "4h", "base"))
    lines.append(f"Tendencia: {trend_txt}.")

    if st.get("sweep"):
        lines.append(f"Estrutura: {st['sweep']} - sinal classico de captura de liquidez.")
    elif st.get("bos"):
        lines.append(f"Estrutura: {st['bos']}.")
    else:
        lines.append(f"Estrutura: {st.get('sequence','sem definicao')}, sem rompimento confirmado.")

    lines.append(f"Fluxo: imbalance {fl.get('imbalance_pct',0):+.0f}% e CVD {_fmt_usd(fl.get('cvd_usd',0))} "
                 f"({fl.get('divergence','')}).")
    if pr and pr.get("large_count"):
        lines.append(f"Ordens grandes: vies {pr['large_bias_pct']:+.0f}% em {pr['large_count']} prints "
                     f"(ticket medio {_fmt_usd(pr['avg_ticket'])}).")
    if vp:
        opv = vp.get("recent") or vp
        lines.append(f"Valor: preco {opv['position'].lower()} com POC em {_fmt_px(opv['poc'])} "
                     f"e VA {_fmt_px(opv['val'])}-{_fmt_px(opv['vah'])}.")
    if dv.get("regime"):
        lines.append(f"Derivativos: {dv['regime'].lower()}.")
    lines.append(f"Conclusao: {v['status']} {v['direction']} com conviccao {v['conviction']:.0f}/100; "
                 f"setup '{v['setup']}'.")
    return lines


def to_json(ctx: dict) -> str:
    payload = {k: v for k, v in ctx.items() if k != "candles"}
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
