"""CLI do FinAgent."""
from __future__ import annotations

import argparse
import json
import sys

from . import analysis, data, envfile, journal, report


def cmd_analyze(args) -> int:
    ctx = analysis.analyze(args.symbol, tf=args.tf, days=args.days,
                           equity=args.equity, risk_pct=args.risk,
                           with_derivs=not args.no_derivs)
    if args.json:
        print(report.to_json(ctx))
    else:
        print(report.render(ctx))
    if args.save:
        sid = journal.save(ctx)
        if not args.json:
            print(f"\nSinal salvo no journal (id {sid}). Avalie depois com: finagent journal --evaluate")
    return 0


def _quick(symbol: str) -> dict | None:
    try:
        base = data.klines(symbol, "1h", 300)
        if len(base) < 80:
            return None
        ctx = analysis.analyze(symbol, tf="1h", days=14, with_derivs=False)
        v = ctx["verdict"]
        return {"symbol": symbol, "price": ctx["price"], "conviction": v["conviction"],
                "direction": v["direction"], "status": v["status"], "setup": v["setup"]}
    except Exception:
        return None


STABLES = {"USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "USD1", "AEUR", "XUSD"}


def _is_tradable(sym: str) -> bool:
    base = sym[:-4] if sym.endswith("USDT") else ""
    if not base or base in STABLES:
        return False
    return not any(base.endswith(s) for s in ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S"))


def cmd_scan(args) -> int:
    if args.symbols:
        syms = [data.normalize(s) for s in args.symbols.split(",")]
    else:
        tickers = data.ticker24h()
        usdt = [t for t in tickers if _is_tradable(t["symbol"])]
        usdt.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
        syms = [t["symbol"] for t in usdt[: args.top]]
    rows = []
    for s in syms:
        r = _quick(s)
        if r:
            rows.append(r)
            print(f"  ... {s}", file=sys.stderr)
    rows.sort(key=lambda r: r["conviction"], reverse=True)
    print(f"{'SYMBOL':<12}{'PRECO':>12}  {'DIR':<6}{'CONV':>6}  {'STATUS':<20} SETUP")
    for r in rows:
        print(f"{r['symbol']:<12}{r['price']:>12.4f}  {r['direction']:<6}{r['conviction']:>6.0f}  "
              f"{r['status']:<20} {r['setup'][:28]}")
    return 0


def cmd_book(args) -> int:
    from .liquidity import book_metrics
    sym = data.normalize(args.symbol)
    bk = book_metrics(data.order_book(sym, 500))
    print(f"{sym}  mid {bk['mid']:.4f}  spread {bk['spread_bps']:.2f}bps  score {bk['score']}/100")
    print(f"  snapshot cobre {bk['coverage_pct_lo']:.2f}% a {bk['coverage_pct_hi']:.2f}% do mid "
          f"({bk['levels']} niveis)" if bk.get("coverage_pct_hi") else "")
    for band, d in bk["bands"].items():
        print(f"  {band:>6}  bid {d['bid_usd']:>14,.0f}  ask {d['ask_usd']:>14,.0f}  imb {d['imbalance_pct']:+.0f}%")
    for s in bk["slippage"]:
        print(f"  {s['notional']:>10,.0f} USD  buy {s['buy_slippage_bps']:.1f}bps  sell {s['sell_slippage_bps']:.1f}bps")
    for w in bk["walls"]:
        print(f"  parede {w['side']} {w['usd']:,.0f} @ {w['price']:.4f} ({w['x_median']:.1f}x)")
    return 0


def cmd_flow(args) -> int:
    from .flow import flow_summary, trade_prints
    sym = data.normalize(args.symbol)
    candles = data.klines(sym, args.tf, 200)
    fl = flow_summary(candles, lookback=args.lookback)
    pr = trade_prints(data.agg_trades(sym, 1000))
    print(f"{sym} {args.tf} fluxo {args.lookback} candles")
    print(f"  CVD {fl['cvd_usd']:+,.0f} USD | imbalance {fl['imbalance_pct']:+.1f}% | {fl['divergence']}")
    print(f"  buy {fl['buy_usd']:,.0f} vs sell {fl['sell_usd']:,.0f}")
    print(f"  ultimo candle delta {fl['last_candle_delta']:+,.0f}")
    print(f"  prints: {pr['count']} trades/{pr['window_min']:.0f}min | ticket medio {pr['avg_ticket']:,.0f} "
          f"| mediana {pr['median_ticket']:,.0f} | p99 {pr['p99_ticket']:,.0f}")
    print(f"  grandes: {pr['large_count']} >= {pr['large_threshold']:,.0f} | vies {pr['large_bias_pct']:+.0f}%")
    for t in pr["top_prints"]:
        print(f"    {t['side']:<4} {t['usd']:>12,.0f} @ {t['price']:.4f}  ({t['ago_s']:.0f}s atras)")
    return 0


def cmd_journal(args) -> int:
    if args.evaluate:
        res = journal.evaluate(min_hours=args.min_hours)
        print(f"Avaliados {len(res)} sinais.")
        for r in res:
            print(f"  #{r['id']} {r['symbol']} {r['outcome']} {r['r']:+.2f}R")
        return 0
    rows = journal.recent(args.limit)
    if not rows:
        print("Journal vazio.")
        return 0
    print(f"{'ID':<4}{'DATA':<12}{'SYMBOL':<10}{'DIR':<6}{'CONV':>5}  {'STATUS':<24}{'OUTCOME':<10}{'R':>7}")
    import time as _t
    for r in rows:
        d = _t.strftime("%d/%m %H:%M", _t.localtime(r["ts"] / 1000))
        print(f"{r['id']:<4}{d:<12}{r['symbol']:<10}{r['direction'] or '':<6}{r['conviction'] or 0:>5.0f}  "
              f"{(r['status'] or ''):<24}{(r['outcome'] or ''):<10}{(r['r_multiple'] or 0):>7.2f}")
    return 0


def cmd_stats(args) -> int:
    s = journal.stats()
    if not s["closed"] and not s["open"]:
        print("Sem sinais registrados ainda. Use: finagent analyze BTCUSDT --save")
        return 0
    print(f"Fechados {s['closed']} | abertos {s['open']} | win rate {s['win_rate']:.1f}% | "
          f"R total {s['total_r']:+.2f} | R medio {s['avg_r']:+.3f}")
    for k, v in s["by_setup"].items():
        print(f"  {k:<52} n={v['n']:<3} wr={v['win_rate']:5.1f}%  avgR={v['avg_r']:+.2f}")
    return 0


def cmd_monitor(args) -> int:
    from . import monitor
    syms = ([data.normalize(s) for s in args.symbols.split(",")] if args.symbols
            else ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    monitor.run(syms, args.tf, args.interval, args.equity, args.risk,
                only_changes=not args.all, once=args.once)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="finagent", description="Agente de analise de fluxo, volume, liquidez e estrutura")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", aliases=["a"], help="analise completa de um ativo")
    a.add_argument("symbol")
    a.add_argument("--tf", default="1h")
    a.add_argument("--days", type=int, default=30)
    a.add_argument("--equity", type=float, default=10_000)
    a.add_argument("--risk", type=float, default=1.0)
    a.add_argument("--json", action="store_true")
    a.add_argument("--save", action="store_true")
    a.add_argument("--no-derivs", action="store_true")
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("scan", help="ranking rapido de ativos")
    s.add_argument("--symbols")
    s.add_argument("--top", type=int, default=15)
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("book", help="liquidez do book")
    b.add_argument("symbol")
    b.set_defaults(func=cmd_book)

    f = sub.add_parser("flow", help="fluxo de ordens e prints")
    f.add_argument("symbol")
    f.add_argument("--tf", default="1h")
    f.add_argument("--lookback", type=int, default=24)
    f.set_defaults(func=cmd_flow)

    j = sub.add_parser("journal", help="sinais registrados")
    j.add_argument("--evaluate", action="store_true")
    j.add_argument("--min-hours", type=float, default=4.0)
    j.add_argument("--limit", type=int, default=30)
    j.set_defaults(func=cmd_journal)

    st = sub.add_parser("stats", help="performance por setup")
    st.set_defaults(func=cmd_stats)

    m = sub.add_parser("monitor", help="monitora ativos e alerta mudanca de veredito")
    m.add_argument("--symbols")
    m.add_argument("--tf", default="15m")
    m.add_argument("--interval", type=int, default=300)
    m.add_argument("--equity", type=float, default=10_000)
    m.add_argument("--risk", type=float, default=1.0)
    m.add_argument("--all", action="store_true", help="alerta tambem na primeira leitura")
    m.add_argument("--once", action="store_true", help="roda uma vez e sai")
    m.set_defaults(func=cmd_monitor)

    w = sub.add_parser("serve", help="dashboard web + operacao continua (porta 3000)")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=3000)
    w.add_argument("--monitor", action="store_true", help="roda o monitor em thread")
    w.add_argument("--symbols", help="lista separada por virgula (default BTC,ETH,SOL)")
    w.add_argument("--tf", default="15m", help="timeframe do monitor")
    w.add_argument("--interval", type=int, default=300, help="segundos entre ciclos do monitor")
    w.set_defaults(func=cmd_serve)

    bk = sub.add_parser("backup", help="copia consistente do journal SQLite")
    bk.set_defaults(func=cmd_backup)
    return p


def cmd_serve(args) -> int:
    from .webapp import serve
    syms = [data.normalize(s) for s in args.symbols.split(",")] if args.symbols else None
    return serve(host=args.host, port=args.port, monitor=args.monitor,
                 symbols=syms, tf=args.tf, interval=args.interval)


def cmd_backup(args) -> int:
    from . import ops
    ops.init_storage()
    path = ops.backup()
    print(f"backup: {path}" if path else "nada para copiar (journal ainda nao existe)")
    return 0


def main(argv: list[str] | None = None) -> int:
    envfile.load()  # .env da raiz (nao sobrescreve env real)
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
