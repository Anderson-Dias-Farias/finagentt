# SCAN-01 — Varredura online por ferramentas reaproveitáveis

Varredura executada em 2026-11-20 contra a API do GitHub (`/search/repositories` e
`/repos/{owner}/{repo}`) e contra os endpoints públicos da Binance.
Objetivo: achar o que **já existe** para backtest multi-anual, dados históricos de
cripto, confluência multi-timeframe, medição de hit rate e order flow — em vez de
codar do zero.

Método: busca por nome/descrição/topic (não por README — README produz listas
"awesome" e polui o resultado), ordenação por estrelas, e verificação individual
de cada candidato por endpoint `/repos` para capturar atividade, licença e
arquivamento. Números são do momento da varredura.

---

## 1. Achado principal — o dado existe e é de graça, mas não pela API

O ponto que travava a F1 era "não há corpus histórico em disco". A varredura
resolve isso, e resolve melhor do que o freqtrade resolveria.

**`data.binance.vision` publica arquivos mensais em ZIP, sem chave, sem login.**
Verificado por HEAD/Range real (não por documentação):

| Dataset | Caminho | Verificação |
|---|---|---|
| Spot aggTrades | `data/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2020-01.zip` | HTTP 200, **214,9 MB** |
| Spot aggTrades (recente) | `.../BTCUSDT-aggTrades-2025-10.zip` | HTTP 200, **589,1 MB** |
| Futures UM aggTrades | `data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2020-01.zip` | HTTP 200, **102,6 MB** |
| Spot klines 1h | `data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-01.zip` | HTTP 200, **40 KB** |
| Futures fundingRate | `data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2022-01.zip` | HTTP 200, 906 bytes |
| Futures metrics (OI, long/short, taker) | `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2025-10-01.zip` | HTTP 200, 11.310 bytes/dia |

Diretórios confirmados no bucket de `futures/um/monthly/`:
`aggTrades`, `bookTicker`, `fundingRate`, `indexPriceKlines`, `klines`,
`markPriceKlines`, `premiumIndexKlines`, `trades`.

### Limites medidos da API REST (testados, não supostos)

| Endpoint | Limite real |
|---|---|
| `aggTrades` com `fromId` | **Só ~1 ano.** Qualquer `fromId` antigo (`1`, `1000`, `1000000`) satura em `2024-11-20T18:00` — o exchange descarta o resto |
| `aggTrades` com `startTime=2020-01-01` | Retorna o mesmo piso de 2024-11-20 |
| `klines` com `startTime=0` | **Vai ao início do par**: 1d desde `2017-08-17`; paginável 1000 por vez |
| `1w` / `1M` em `klines` | Servidos pela REST, mas **não publicados** como arquivo mensal → derivar por agregação do 1d |
| `liquidationSnapshot` | Descontinuado no data.binance.vision (404) |

Consequência prática e direta para a F1:

- **Candles (1d/4h/1h/1w/1M):** REST paginado resolve, de 2017 até hoje, zero dependência.
  1w e 1M saem de agregação do 1d — não confiar em `1M` da REST para backtest longo,
  porque o candle mensal corrente vem aberto.
- **Ticks/aggTrades (order flow histórico):** REST **não** resolve além de 12 meses.
  Precisa do ZIP mensal. E isso é exatamente o insumo que o finagent não tem hoje:
  delta, CVD, footprint e detecção de ordem grande só podem ser calibrados com tick real.
- **Derivativos:** fundingRate mensal + metrics diário (OI, long/short ratio, taker
  buy/sell) dão a série histórica de funding/OI de graça — hoje o finagent só lê
  o valor instantâneo.

Custo: aggTrades de BTC spot é ~200–600 MB/mês. Dez anos de BTC spot ≈ 30–50 GB
comprimido. Não é "baixar tudo"; é baixar por janela, agregar para o formato interno
e descartar o ZIP. Um mês de ticks de BTC é suficiente para calibrar order flow;
anos de candles são suficientes para calibrar confluência.

---

## 2. Motores de backtest — o que presta, o que está morto, o que tem licença armadilha

| Repo | ★ | Último push | Lang | Licença | Veredito |
|---|---|---|---|---|---|
| `freqtrade/freqtrade` | 57.104 | 2026-11-19 | Python | GPL-3.0 | **Adotar como CLI isolado** para validação cruzada. GPL: nunca `import` no núcleo |
| `ccxt/ccxt` | 44.934 | 2026-11-20 | Python | MIT | Não precisamos: REST da Binance cru já é stdlib. Só se formos multi-exchange |
| `nautechsystems/nautilus_trader` | 31.707 | 2026-11-20 | Rust | LGPL-3.0 | Overkill. Engine de execução com matching próprio — não é ferramenta de pesquisa |
| `mementum/backtrader` | 23.766 | **2024-08-19** | Python | GPL-3.0 | **Morto.** 2+ anos sem push. Descartar |
| `hummingbot/hummingbot` | 21.313 | 2026-11-20 | Python | Apache-2.0 | Execução/market making, não pesquisa. Fora de escopo |
| `QuantConnect/Lean` | 22.631 | 2026-11-20 | C# | Apache-2.0 | Infra .NET, Docker pesado. Descartar |
| `polakowo/vectorbt` | 9.902 | 2026-11-11 | Python | NOASSERTION | Open congelado, empurra para o PRO pago. Descartar |
| `kernc/backtesting.py` | 9.267 | 2026-08-05 | Python | **AGPL-3.0** | Bom desenho, licença contamina qualquer serviço. Descartar |
| `jesse-ai/jesse` | 8.823 | 2026-11-17 | Python | MIT | O único backtest cripto-nativo com licença limpa. **Ler como referência** |
| `edtechre/pybroker` | 3.724 | 2026-11-16 | Python | NOASSERTION | Tem **walk-forward nativo** — é a peça da F4. Ler como referência |
| `pst-group/pysystemtrade` | 3.638 | 2026-11-02 | Python | GPL-3.0 | Rigor de portfólio futuro; ideias de custo/risco |
| `pmorissette/bt` | 3.045 | 2026-11-20 | Python | **MIT** | Alocação/pesos por árvore. Útil se um dia for multi-ativo |
| `hudson-and-thames/mlfinlab` | 4.972 | **2023-10-02** | Python | NOASSERTION | Parado + licença comercial. Descartar código; ideia de *triple barrier* fica |

Nenhum deles é dependência do finagent. O núcleo continua stdlib; freqtrade entra
como **executável separado em venv**, só para responder "meu backtest concorda com
um motor maduro em fee, fill e slippage?" — que é o erro clássico de backtest caseiro.

---

## 3. Order flow / volume profile / microstructure — aqui não há o que reaproveitar

Esta é a camada central do finagent e a mais pobre em open source. Números:

| Repo | ★ | Último push | Licença | O que é |
|---|---|---|---|---|
| `murtazayusuf/OrderflowChart` | 269 | 2026-11-01 | Apache-2.0 | **Só desenha** footprint com plotly |
| `zadescoxp/order-flow-screener` | 225 | 2026-11-20 | Apache-2.0 | Screener em TypeScript, tempo real |
| `AndreaFerrante/Orderflow` | 146 | 2026-11-20 | **MIT** | Reshape tick → footprint/imbalance. Melhor código Python do lote |
| `jialuechen/flowforge` | 139 | 2026-08-23 | **BSD-2** | Inferência de order flow + **TCA** (slippage por tamanho de ordem) |
| `tiagosiebler/orderflow` | 86 | 2025-03-31 | MIT | Serviço TS de footprint via websocket |
| `Azhagesan-dev/OrderFlowMap` | 114 | 2026-04-01 | MIT | Visualizador estilo Bookmap em HTML único |
| `mahmoud20138/OrderFlow-Analysis-Pro` | 85 | 2026-04-15 | MIT | Footprint Bybit + MT5 |
| `tapedelta/kline-orderbook-chart` | 77 | 2026-07-16 | — | Heatmap de book + footprint + liquidações |

Leitura honesta: **não existe biblioteca madura de tape reading em Python.** O topo
tem 269 estrelas e faz gráfico. Isso não é motivo para portar código — é confirmação
de que o `finagent/flow.py` e o `finagent/volume.py` já estão na fronteira do que
existe aberto, e que a lacuna real não é indicador, é **medição**.

Das duas com licença permissiva e conteúdo real:
- `flowforge` (BSD-2): a parte de **TCA** — custo de execução por faixa de notional — é
  diretamente aplicável ao `slippage` que o finagent já calcula. Vale ler a metodologia.
- `AndreaFerrante/Orderflow` (MIT): conferir como agrupa tick em barra de volume e
  como define imbalance/delta por nível. É a definição que o finagent precisa acertar
  quando passar a usar aggTrades histórico em vez de 1000 prints ao vivo.

---

## 4. Market structure / SMC

| Repo | ★ | Último push | Licença | Uso |
|---|---|---|---|---|
| `joshyattridge/smart-money-concepts` | 2.252 | 2026-04-03 | **MIT** | BOS/CHoCH, order blocks, FVG, liquidity. Única com adoção real |
| `Prasad1612/smart-money-concept` | 62 | 2025-09-19 | — | Versão mínima, sem manutenção |
| `SrsBlack/ict-knowledge-library` | 86 | 2026-11-09 | — | Base de conhecimento ICT (texto, não código) |

O finagent já tem BOS/CHoCH/swings em `structure.py`. O valor aqui não é código
novo: é **calibrar threshold de swing e confirmar a regra de invalidação** contra a
implementação que 2,2 mil pessoas usam, para não ficar com definição própria
idiossincrática. `smart-money-concepts` é pandas — leitura, não dependência.

---

## 5. Confluência multi-timeframe — o vazio confirma a spec

Busquei por nome, descrição e topic (`multi timeframe confluence`, `topic:market-structure`,
`topic:order-flow`, `topic:volume-profile`). Resultado: **nenhum repositório com adoção
relevante implementa hierarquia multi-timeframe com classificação de conflito.**

O que existe é:
- indicador MTF em Pine Script (fechado, preso ao TradingView);
- "confluence score" que soma pesos de indicadores no mesmo TF (exatamente o que a
  §1.3 da SPEC-01 identifica como destrutivo);
- bibliotecas de indicadores que aceitam `timeframe=` e devolvem o último valor do TF
  superior — repintam, porque leem candle aberto.

Ou seja: a D1 (hierarquia por permissão) e a D2 (taxonomia fechada de conflito) não
têm equivalente aberto para copiar. É trabalho original — e a varredura é a evidência
disso, não uma opinião.

Bibliotecas de indicadores, para constar:
`TA-Lib/ta-lib-python` (12.426★, BSD-2, Cython — exige lib C, quebra o "só stdlib"),
`twopirllc/pandas-ta` / `pandas-ta/pandas-ta` (pandas, licença NOASSERTION),
`jesse-ai/jesse` (tem indicadores próprios, MIT).

---

## 6. Dados e conectores

| Repo | ★ | Último push | Licença | Nota |
|---|---|---|---|---|
| `binance/binance-public-data` | 2.572 | 2026-10-16 | — | Documenta o `data.binance.vision` (seção 1). **É o caminho** |
| `bmoscon/cryptofeed` | 3.039 | 2026-11-18 | NOASSERTION | Websocket multi-exchange. Só se for tempo real |
| `binance/binance-connector-python` | 2.961 | 2026-11-18 | MIT | Wrapper oficial. Desnecessário: REST cru é stdlib |
| `binance/binance-futures-connector-python` | 1.237 | 2025-07-18 | MIT | Mesmo caso |
| `tardis-dev/tardis-python` | 151 | 2026-10-28 | MPL-2.0 | Tick-level histórico normalizado, **pago** para volume. Amostras grátis |

`tardis` é a alternativa "limpa" para order book L2 histórico — mas é serviço pago.
Fica registrado como referência: se um dia o finagent precisar de book histórico
(hoje só tem snapshot de 500 níveis), é a única fonte séria, e o custo é o motivo
de não estar no plano.

---

## 7. O que adotar, concretamente

Prioridade por relação valor/custo, respeitando "núcleo stdlib, sem dependência pesada":

**Adotar de verdade (entra na F1/F4)**
1. `data.binance.vision` — klines mensais (1h/1d) + fundingRate + metrics diário.
   Um `scripts/fetch_data.py` stdlib: baixa ZIP, valida hash, converte para JSONL,
   grava manifesto. Sem pandas, sem ccxt.
2. `freqtrade` em `.venv-ft` isolado — **só** como validação cruzada de backtest
   (fee 0,1%/0,05%, fill, slippage). CLI, nunca import.

**Ler como referência antes de implementar (não instalar)**
3. `flowforge` → metodologia de TCA/slippage por notional.
4. `AndreaFerrante/Orderflow` → definição de footprint/delta por nível a partir de tick.
5. `joshyattridge/smart-money-concepts` → threshold de swing e invalidação de BOS/CHoCH.
6. `pybroker` → desenho de walk-forward (F4) e `jesse` → semântica de fee/fill cripto.

**Descartar, com motivo registrado**
7. `backtrader` (morto desde 2024-08), `vectorbt` (open congelado → PRO pago),
   `backtesting.py` (AGPL), `Lean` (C#/infra), `hummingbot`/`nautilus` (execução),
   `mlfinlab` (parado desde 2023 + licença comercial), `TA-Lib` (lib C, quebra stdlib).

**Nada a reaproveitar**
8. Confluência MTF: vazio. Segue como trabalho original da spec.
9. Order flow Python: nada maduro. O finagent já está no limite do que existe aberto;
   o ganho não vem de biblioteca, vem de tick histórico real.

---

## 8. Impacto na SPEC-01

| Seção | Antes | Depois desta varredura |
|---|---|---|
| §1.7 | Evidência de falha do criptolua | **Mantida** — é o único dado empírico de hit rate que temos, e é negativo |
| §5.1–5.2 | Portar conceitos do `criptolua-v2` | **Removida como fonte.** Nenhum porte assumido. Criptolua fica só como evidência de falha |
| §5.3 | "freqtrade ou Binance REST" | Resolvido: **data.binance.vision** para bulk, REST só para candles e amostras |
| F1 | "baixar via freqtrade" | `fetch_data.py` stdlib contra `data.binance.vision`; freqtrade só valida |
| F4 | "sweep com walk-forward" | Acrescentar conferência contra `freqtrade backtesting` e desenho do `pybroker` |
| D1/D2 | Proposta sem precedente | Confirmado: **não há precedente aberto** — é original, e isso é risco declarado |

O que a varredura **não** mudou: a tese da spec. O problema nunca foi falta de
indicador — é que nenhum veredito do finagent foi medido contra outcome. Nenhuma
ferramenta encontrada resolve isso por nós; todas resolvem pedaços do *como medir*.
