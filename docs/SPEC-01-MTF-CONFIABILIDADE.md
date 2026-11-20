# SPEC-01 — Confluência Multi-Timeframe, Divergência e Confiabilidade Medida

status: in-progress
criada: 2026-11-20
projeto: /home/anderson/Projetos/finagent
autor: Hermes + Anderson
branch: (a definir antes da F1)

---

## 0. Por que esta spec existe

O finagent hoje produz um veredito único (peso somado) para qualquer horizonte. A
conversa de 20/11 levantou três problemas conceituais e uma proposta de método:

1. A confiança exibida não é probabilidade e nunca foi medida.
2. Multi-timeframe hoje é **média ponderada**, não hierarquia — e média apaga
   justamente a informação de conflito (pullback vs. reversão).
3. Não existe detecção de divergência entre timeframes; só preço × CVD no TF base.
4. Proposta: spec consolidada + varredura do que já existe no git antes de escrever
   código ("não codar tanto").

Esta spec é o documento de trabalho: estado verificado, decisões, dúvidas abertas,
inventário de reaproveitamento, fases e gates.

---

## 1. Estado atual verificado (não estimado)

### 1.1 Código

- Repositório: 2 commits (`73a82c3`, `60a71f4`), árvore limpa.
- Testes: 43/43 OK (`python3 -m unittest discover -s tests`).
- Python puro/stdlib. Front em `http.server` na porta 3000. Sem pandas/numpy em
  runtime — e deve continuar assim (qualquer lógica adotada de terceiro entra como
  reimplementação manual, nunca como dependência instalada).

### 1.2 Dados que entram na análise

| Item | Valor real | Arquivo |
|---|---|---|
| Candles do TF base | 500 | `finagent/analysis.py` |
| Candles 4h | 300 (~50 dias) | `finagent/analysis.py` |
| Candles 1d | 300 (~10 meses) | `finagent/analysis.py` |
| Prints de fluxo | máx. 1000 `aggTrades` (segundos a poucos minutos em BTC) | `finagent/flow.py` |
| Book | snapshot de 500 níveis, sem streaming | `finagent/liquidity.py` |
| Timeframes aceitos na UI | 5m, 15m, 1h, 4h, 1d | `web/index.html` |

### 1.3 Como a tendência entra hoje

- `analysis._ema_bias`: EMA20/50 por timeframe, três timeframes (1d, 4h, base).
- Agregação: `0.5 * 1d + 0.3 * 4h + 0.2 * base`, arredondada para booleano.
- `score._tf_bias` existe e **não é chamada em produção** — só pelos testes.
  Duas implementações do mesmo conceito, uma morta. Dívida a matar nesta spec.

### 1.4 Divergência

- Existe apenas preço × CVD no TF base (`flow` → campo `divergence`).
- Não existe divergência de momentum (RSI/stoch) nem entre timeframes.

### 1.5 Journal / medição

- `finagent/monitor.py` persiste estado em `~/.finagent/state.json`.
- Guarda veredito e alertas. **Não** guarda resultado posterior, não calcula acerto,
  não separa por classe de confluência nem por regime.
- Não existe backtest no finagent. Nenhum hit rate medido. Nenhum peso calibrado.

### 1.6 Consequência prática

`conviction = 62%` significa "62% do peso disponível está a favor", não "62% de acerto".
Não há base estatística para dimensionar posição a partir desse número. Esta spec
existe para fechar essa lacuna, não para maquiar o rótulo.

---

### 1.7 Evidência empírica do projeto anterior (não é opinião)

O criptolua-v2 já rodou essa medição em 2026-07-03 sobre sinais reais persistidos
(`docs/analise-historico-sinais-executiva.md`):

| Métrica | Valor |
|---|---|
| Sinais analisados | 3.591 |
| Resolvidos | 1.405 |
| Inconclusivos | 2.186 (61%) |
| Win rate sobre resolvidos | **28,40%** |
| Loss rate sobre resolvidos | **71,60%** |
| Resultado médio | **-1,07R** |
| LONG | 52,96% de acerto |
| SHORT | **2,06%** de acerto |
| Melhor estratégia | RELATIVE_STRENGTH_MOMENTUM (47%) |
| Regime dominante | RANGE_MARKET |

Leituras que valem para esta spec:

1. Confiança sem amostra produziu **-1,07R** médio. É a prova de que o número de
   convicção atual do finagent não pode ser levado a sério antes da F3.
2. **SHORT com 2,06%** é um achado estrutural, não ruído: o motor anterior não sabia
   operar queda. Qualquer short no finagent nasce com `INSUFFICIENT_DATA` até prova
   em contrário — não se herda confiança de long para short.
3. 61% de inconclusivos mostra que "não resolvido" precisa ser categoria de primeira
   classe. Truncar a janela para forçar resolução inventa win rate.
4. O maior bloqueador foi **"Price Action ainda não confirmou gatilho"** (939 casos),
   o que sustenta a D1 (gatilho explícito no TF base) em vez de score somado.
5. A recomendação final do próprio documento é exatamente a F3 desta spec: "backtest
   por candle futuro, janela conservadora, contagem separada de ambíguos e
   inconclusivos".

Esse é o argumento mais forte contra repetir o desenho antigo: não é falta de
indicador, é falta de medir.

## 2. Problemas a resolver

**P1 — Média destrói conflito.**
`1d alta (+1), 4h baixa (-1), 1h baixa (-1)` → `0.5-0.3-0.2 = 0` → "sem tendência".
É exatamente o cenário de pullback em tendência de alta, um dos melhores contextos
de compra. O sistema o classifica como ruído.

**P2 — Um score para dois operadores.**
Swing e daytrade têm prazos de decisão diferentes e recebem o mesmo número. O
horizonte do operador não entra no cálculo.

**P3 — Confiança sem lastro.**
Nenhuma validação histórica. Pesos escolhidos a dedo. Impossível distinguir
"alinhado 3/3" de "conflito" em termos de resultado esperado.

**P4 — Dado ambíguo apresentado como preciso.**
Candle aberto entra em EMA/volume/padrões; fluxo é janela de minutos rotulada como
fluxo da sessão; book é foto. Nada disso é erro de fórmula — é erro de enquadramento.

**P5 — Duplicação de lógica de viés** (`analysis._ema_bias` vs `score._tf_bias`).

---

## 3. Decisões propostas

### D1 — Hierarquia por permissão, não soma de pesos

```
SWING     1M permissão  →  1W viés  →  1D gatilho
DAYTRADE  1D permissão  →  4H zona  →  1H gatilho
```

O TF superior **veta**, não pontua. Se 1M está em downtrend, long no diário não sai
como EXECUTÁVEL independentemente da beleza do 1h. Veredito passa de "soma de
evidências" para "permissão + gatilho".

### D2 — Confluência como classe explícita (taxonomia fechada)

```
ALIGNED_LONG            todos concordam para cima        → seguir
ALIGNED_SHORT           todos concordam para baixo       → seguir
CONFLICT_LONG_PULLBACK  longo+médio alta, curto baixa    → comprar retorno a favor
CONFLICT_SHORT_PULLBACK longo+médio baixa, curto alta    → vender repique a favor
REVERSAL_WATCH          longo lateral, médio+curto contra→ aguardar confirmação
RANGE                   sem direção dominante            → não operar tendência
INSUFFICIENT_DATA       falta histórico no TF superior    → rebaixar para o TF abaixo
```

Sete estados, cada um com ação própria. Aritmética de três estados, não modelo.

### D3 — Um motor, duas configurações

`confluence(tfs=[...], base_tf=...)` recebe lista ordenada de timeframes e devolve
matriz + classe. Swing e daytrade são parâmetros, não módulos separados.

### D4 — Confiança passa a ser medida, com amostra explícita

Todo número de confiança carrega `(n=amostra, escopo)`. Sem amostra mínima, o campo
é `INSUFFICIENT_DATA` — nunca um número inventado. Política de amostra adotada:
`probation n=8`, `validated n=20` — herdada da única medição real que temos (§1.7),
não de biblioteca de terceiro.

### D5 — Journal é a fonte de verdade

Só entra no cálculo de confiança o que foi registrado **antes** do resultado
(timestamp de detecção + preço de entrada), senão há lookahead. Backfill de sinais
antigos só é permitido se o timestamp original existir.

### D6 — Nenhum candle aberto decide nada

Motor de confluência e calibração usam exclusivamente candles fechados. O candle em
formação pode ser exibido como "em curso", jamais como sinal.

---

## 4. Dúvidas abertas (precisam de decisão antes da fase indicada)

| # | Dúvida | Opções | Recomendação | Trava |
|---|---|---|---|---|
| Q1 | Tendência em 1M/1W: EMA ou estrutura? | (a) EMA50 (exige ~4 anos) (b) EMA10/21 (c) estrutura HH/HL | **(c)** estrutura + fallback `INSUFFICIENT_DATA`; EMA só em 4H/1H | F2 |
| Q2 | TF superior veta ou desconta? | (a) gate absoluto (b) desconto de peso | **(a)** gate, com exceção explícita para setups de reversão | F2 |
| Q3 | Perfis fixos ou configuráveis? | (a) 2 perfis fixos (b) lista livre de TFs | **(a)** agora, (b) depois — simplicidade primeiro | F2 |
| Q4 | Divergência cross-TF: estrutura ou momentum? | (a) estrutura/fluxo (b) RSI/MACD multi-TF (c) ambos | **(a)** primeiro; momentum entra como modificador (Q4b) | F2/F3 |
| Q5 | Corpus histórico: de onde? | (a) `data.binance.vision` ZIP mensal (b) Binance REST paginado (c) freqtrade `download-data` | **(a)** para bulk (candles + funding + metrics ± ticks), **(b)** só para amostra recente. Freqtrade fica fora do caminho de dados | F1 |
| Q6 | Como medir acerto? | (a) horizonte fixo N candles (b) target/stop em R (c) ambos | **(c)** R para trade simulado, horizonte fixo para sinal | F3 |
| Q7 | Reprocessar histórico antigo? | (a) começar limpo (b) backfill | **(a)** limpo com `schema_version`; backfill só com timestamp original | F3 |
| Q8 | Sweep com que proteção contra overfit? | (a) in-sample puro (b) walk-forward (c) walk-forward + out-of-sample final | **(c)**, out-of-sample reservado e nunca tocado no sweep | F4 |

---

## 5. Varredura de reaproveitamento (o que já existe no git)

A varredura online está consolidada em [`SCAN-01-FERRAMENTAS.md`](SCAN-01-FERRAMENTAS.md):
repos do GitHub verificados um a um (estrelas, último push, licença) e endpoints da
Binance testados por HEAD/Range. Abaixo, só o que muda decisão.

`criptolua` / `criptolua-v2` **não é fonte de nada** nesta spec. Acerto < 50%,
-1,07R e SHORT 2,06% (§1.7) desqualificam o motor como referência de lógica.
Ele aparece na §5.4 apenas como **registro de falha medida**, para não repetir.

### 5.1 Dados históricos — resolvido, e melhor que o freqtrade

`data.binance.vision` publica ZIP mensal sem chave. Verificado por HEAD real:
spot aggTrades `2020-01` = 214,9 MB; futures UM aggTrades `2020-01` = 102,6 MB;
klines `1h` `2019-01` = 40 KB; fundingRate = 906 bytes; metrics diário = 11 KB/dia
(contém OI, long/short ratio, taker buy/sell).

Limites **medidos** da REST da Binance (testados, não documentados):

- `aggTrades` com `fromId` antigo (`1`, `1000`, `1000000`) → satura em `2024-11-20`.
  **Ticks pela REST cobrem só ~12 meses.** Order flow histórico exige o ZIP mensal.
- `klines` com `startTime=0` → vai ao início do par: `1d` desde `2017-08-17`,
  paginável 1000 por vez. Cobre todo o backtest de candles.
- `1w`/`1M` respondem na REST mas **não são publicados** em arquivo mensal →
  derivar por agregação do `1d`.
- `liquidationSnapshot` foi descontinuado (404).

Decisão: `scripts/fetch_data.py` em stdlib puro (ZIP → JSONL + manifesto com hash),
contra `data.binance.vision`. Sem pandas, sem ccxt, sem freqtrade no caminho.

### 5.2 Backtest — freqtrade como juiz, nunca como dependência

| Repo | ★ | Push | Licença | Decisão |
|---|---|---|---|---|
| `freqtrade/freqtrade` | 57.104 | 2026-11-19 | GPL-3.0 | **CLI em `.venv-ft` isolado**, só para conferir fee/fill/slippage do nosso backtest. Nunca `import` |
| `jesse-ai/jesse` | 8.823 | 2026-11-17 | MIT | Ler semântica de fee/fill cripto |
| `edtechre/pybroker` | 3.724 | 2026-11-16 | NOASSERTION | Ler desenho de **walk-forward** (F4) |
| `pmorissette/bt` | 3.045 | 2026-11-20 | MIT | Referência de alocação, se virar multi-ativo |
| `mementum/backtrader` | 23.766 | **2024-08** | GPL-3.0 | **Morto.** Descartar |
| `polakowo/vectorbt` | 9.902 | 2026-11-11 | NOASSERTION | Open congelado, empurra PRO pago. Descartar |
| `kernc/backtesting.py` | 9.267 | 2026-08 | **AGPL-3.0** | Licença contamina serviço. Descartar |
| `nautilus_trader`, `hummingbot` | 31.7k / 21.3k | ativos | LGPL/Apache | Execução, não pesquisa. Fora |
| `QuantConnect/Lean` | 22.631 | ativo | Apache-2.0 | Infra .NET. Fora |

### 5.3 Order flow — não há o que portar

O melhor repo Python da categoria tem **269★ e só desenha** footprint
(`OrderflowChart`). Depois: 225★ screener TS, 146★ reshape de tick
(`AndreaFerrante/Orderflow`, MIT), 139★ TCA (`flowforge`, BSD-2). Nenhuma
biblioteca madura de tape reading em Python existe aberta.

Leitura: `flow.py` e `volume.py` já estão na fronteira do que existe. A lacuna não
é indicador, é **medição com tick real** — que a §5.1 agora torna possível.

Duas referências de definição (ler, não instalar): `flowforge` para TCA/slippage
por faixa de notional; `AndreaFerrante/Orderflow` para agrupamento de tick em barra
de volume e definição de delta/imbalance por nível.

Estrutura/SMC: `joshyattridge/smart-money-concepts` (2.252★, MIT, pandas) é a única
com adoção real — serve para calibrar threshold de swing e regra de invalidação do
BOS/CHoCH que já temos, contra a definição que o mercado usa.

### 5.4 Confluência MTF — vazio confirmado (a spec é original)

Busca por nome/descrição/topic (`multi timeframe confluence`, `topic:market-structure`,
`topic:order-flow`, `topic:volume-profile`): **nenhum repo com adoção relevante faz
hierarquia multi-TF com classificação de conflito**. O que existe é indicador Pine
fechado, soma de pesos no mesmo TF (justamente o erro da §1.3) ou indicador que lê
candle aberto do TF superior e repinta.

Consequência: D1 e D2 não têm precedente aberto para copiar. Isso é risco declarado,
não bug de pesquisa.

### 5.5 Registro de falha medida (não é fonte de lógica)

| Documento | Linhas | Por que consta |
|---|---|---|
| `criptolua-v2/docs/analise-historico-sinais-executiva.md` | 47 | 3.591 sinais, 28,40% win, -1,07R, SHORT 2,06%, 61% inconclusivos. Consolidado na §1.7 |
| `criptolua-v2/docs/analise-historico-sinais.md` | 116 | Metodologia de outcome (janela, ambíguo, inconclusivo) — útil como **anti-exemplo** do que não fazer: 61% ficou sem resolução |

Nada além disso é lido do criptolua. Nenhum arquivo TypeScript é importado nem
portado pelo finagent.

### 5.6 Explicitamente NÃO reaproveitar

- Prisma/Next/TypeScript como runtime do finagent (o núcleo é stdlib).
- `lib/signals/opportunity-engine.ts` (79 KB) — monolito acoplado a DB e tipos do app.
  Ideias sim, código não.
- `lib/engines/defi-rate-arbitrage.ts`, `pool-quality-score.ts` — fora de escopo.
- `domain/eth-labels-generated.ts` (53 KB) — dataset estático, não serve.
- Estratégias freqtrade inexistentes: não há `user_data/strategies/`; não importar
  estratégia de terceiro para "resolver" o veredito.

---

## 6. Arquitetura proposta

```
finagent/
  finagent/
    confluence.py      NOVO  motor multi-TF: matriz, taxonomia, permissão/gatilho
    divergence.py      NOVO  divergência preço×fluxo (existe) + momentum (portado)
    calibration.py     NOVO  amostra histórica → confiança com (n, escopo)
    journal.py         NOVO  registro imutável de sinal + avaliação posterior
    backtest.py        NOVO  runner sobre candles fechados, sem lookahead
  tools/
    sweep.py           NOVO  varredura de parâmetros com walk-forward
```

Contratos centrais:

```python
@dataclass(frozen=True)
class TFState:
    tf: str
    trend: str          # UP | DOWN | RANGE | INSUFFICIENT_DATA
    source: str         # STRUCTURE | EMA
    candles: int
    last_closed: int

@dataclass(frozen=True)
class Confluence:
    profile: str        # SWING | DAYTRADE
    states: list[TFState]
    klass: str          # ALIGNED_LONG | ... | INSUFFICIENT_DATA
    permission: str     # LONG | SHORT | NONE
    trigger_tf: str
    vetoed_by: str | None
```

Regra de ouro do motor: **determinístico e puro**. Recebe candles fechados, devolve
estrutura. Sem I/O, sem rede, sem relógio — testável sem mock.

---

## 7. Fases e gates

**F0 — Baseline e inventário** (0,5 dia)
Congelar os números atuais (veredito, conviction, viés por TF) para 6 símbolos em 2
datas fixas. Ler os 2 documentos do §5.5 (evidência de falha, para não repetir). Corrigir P5 (matar `_tf_bias`).
Gate G0: baseline reproduzível por script.

**F1 — Corpus histórico** (1 dia)
Baixar 1h/4h/1d, 2019-01→hoje, BTC/ETH/SOL/BNB/XRP/ADA, de `data.binance.vision`
(ZIP mensal, sem chave, verificado por HEAD). `1w`/`1M` derivam de agregação do `1d`
— não são publicados em arquivo mensal. Funding/OI vêm de `monthly/fundingRate` e
`daily/metrics`. `scripts/fetch_data.py` em stdlib: baixa, valida, converte para
JSONL e grava manifesto com hash, tudo retomável. Amostra de tick (1 mês de
aggTrades spot) só para calibrar order flow — a REST limita `aggTrades` a ~12 meses.
Converter para o formato interno (JSONL por símbolo/TF), versionar manifesto com
hash e contagem de candles.
Gate G1: manifesto confere (sem gaps além dos documentados pela Binance), 1M com
≥ 60 candles para BTC/ETH, `INSUFFICIENT_DATA` correto para os demais.

**F2 — Motor de confluência** (2 dias)
`confluence.py` + `divergence.py`. Matriz na UI (uma linha por TF, conflito
destacado). Perfis SWING/DAYTRADE. Testes com fixtures sintéticas para as 7 classes.
Gate G2: 7 classes cobertas por teste; nenhum candle aberto usado; UI exibe matriz.

**F3 — Journal e calibração** (2 dias)
`journal.py` + `calibration.py` + avaliador portado. Confiança por classe × regime,
com `(n, escopo)` e gate de validação (n≥20 para "validada", n≥8 "em prova").
Gate G3: nenhum número de confiança exibido sem amostra; backfill bloqueado sem
timestamp original.

**F4 — Sweep com walk-forward** (2 dias)
`tools/sweep.py`: varredura de parâmetros (limiares de estrutura, janelas de pivô,
pesos) em in-sample, validação walk-forward, out-of-sample intocado até o fim.
Gate G4: relatório com degradação in→out; nenhum parâmetro promovido com n<20 por
bucket; resultado reproduzível por seed.

**F5 — Integração no veredito** (1 dia)
Confluência vira gate; conviction passa a carregar amostra; docs atualizados.
Gate G5: veredito muda apenas quando gate/gatilho mudam (diff auditável); suíte
inteira verde; README documenta os rótulos.

---

## 8. Critérios de aceite da spec

1. Nenhum número de confiança sem `(n, escopo)` visível.
2. `INSUFFICIENT_DATA` é estado de primeira classe, não erro nem zero.
3. Zero candle aberto em qualquer cálculo que produza sinal.
4. As 7 classes de confluência têm teste dedicado.
5. Backtest e sweep não vazam futuro: nenhuma função recebe candles além do índice.
6. Nenhuma lógica de viés duplicada (P5 fechado).
7. Todo reaproveitamento do §5 rastreável a um arquivo de origem.
8. Suíte ≥ 43 testes verde + novos testes das fases.

---

## 9. Riscos

- **Lookahead** por candle em formação ou por backfill de sinal com timestamp
  retroativo. Mitigação: D5/D6 + gate G3.
- **Overfit no sweep.** 6 ativos × 5 TFs geram combinações suficientes para achar
  ruído. Mitigação: walk-forward, out-of-sample reservado, n mínimo por bucket.
- **Amostras não independentes.** BTC domina a correlação; 6 ativos não são 6
  amostras. Mitigação: reportar por ativo e agregado, nunca só agregado.
- **1M/1W escassos em altcoins.** Mitigação: Q1 (estrutura em vez de EMA) +
  fallback hierárquico para o TF abaixo.
- **Mudança de regime estrutural** (2020-21 vareta vs. 2024-26). Mitigação:
  confiança condicionada por regime, nunca global (regime é camada própria, sem porte externo).

## 10. Não-objetivos

Executar ordens, prever preço, ML/LLM no veredito, acoplar freqtrade ao runtime,
migrar o front para framework, mexer em billing/telegram além do alerta existente.

---

## 11. Anexo A — pseudocódigo do motor

```python
def confluence(candles_by_tf, profile):
    states = [tf_state(tf, candles_by_tf[tf]) for tf in profile.tfs]
    top, mid, trig = states
    if any(s.trend == "INSUFFICIENT_DATA" for s in states[:2]):
        return degrade(states)          # usa o TF abaixo como permissão
    permission = "NONE" if top.trend == "RANGE" else ("LONG" if top.trend == "UP" else "SHORT")
    klass = classify(top.trend, mid.trend, trig.trend)
    vetoed = top.tf if permission == "NONE" else None
    return Confluence(profile.name, states, klass, permission, trig.tf, vetoed)
```

`classify` é a tabela fechada da D2 — implementada como dicionário de 3 estados,
sem if/elif encadeado, para que cada combinação seja testável individualmente.

## 12. Anexo B — schema do journal

```json
{
  "schema_version": 2,
  "id": "uuid",
  "created_at": "ISO8601",
  "symbol": "BTCUSDT",
  "profile": "DAYTRADE",
  "base_tf": "1h",
  "confluence": {"klass": "CONFLICT_LONG_PULLBACK", "permission": "LONG", "vetoed_by": null},
  "states": [{"tf": "1d", "trend": "UP", "source": "STRUCTURE", "candles": 300}],
  "verdict": "EXECUTAVEL",
  "conviction": {"value": 62, "n": 0, "scope": "INSUFFICIENT_DATA"},
  "price_at_signal": 91234.5,
  "closed_candle_ts": "ISO8601",
  "outcome": {"status": "PENDING", "r": null, "evaluated_at": null}
}
```

`closed_candle_ts` é obrigatório: é o que impede avaliar com dado que ainda não
existia no momento do sinal.
