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
  runtime — e deve continuar assim (o port de qualquer lógica do criptolua-v2 é
  manual, não é instalação de dependência).

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
é `INSUFFICIENT_DATA` — nunca um número inventado. Regras herdadas do criptolua-v2
(ver §5.4): `probation n=8`, `validated n=20`.

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
| Q5 | Corpus histórico: de onde? | (a) freqtrade `download-data` (b) Binance REST paginado (c) híbrido | **(c)** freqtrade para corpus bulk, Binance para amostra de validação | F1 |
| Q6 | Como medir acerto? | (a) horizonte fixo N candles (b) target/stop em R (c) ambos | **(c)** R para trade simulado, horizonte fixo para sinal | F3 |
| Q7 | Reprocessar histórico antigo? | (a) começar limpo (b) backfill | **(a)** limpo com `schema_version`; backfill só com timestamp original | F3 |
| Q8 | Sweep com que proteção contra overfit? | (a) in-sample puro (b) walk-forward (c) walk-forward + out-of-sample final | **(c)**, out-of-sample reservado e nunca tocado no sweep | F4 |

---

## 5. Varredura de reaproveitamento (o que já existe no git)

Levantamento em `/home/anderson/Projetos`, não em memória.

### 5.1 Copiar conceito, reimplementar em stdlib (alto valor)

| Origem | Arquivo | O que tem | Decisão |
|---|---|---|---|
| criptolua-v2 | `lib/signals/price-action-signal-engine.ts:1104` (`higherTimeframeBias`) | Taxonomia `ALIGNED_LONG / ALIGNED_SHORT / CONFLICT_LONG_PULLBACK / CONFLICT_SHORT_PULLBACK / RANGE / INSUFFICIENT_DATA` combinando 4h e 1h | **Portar e estender** para 3 TFs (1M/1W/1D e 1D/4H/1H). É a mesma ideia da D2, já validada em produção |
| criptolua-v2 | `types/index.ts:17` (`HTFBias`) | Contrato fechado dos 6 estados | Copiar nomes verbatim (consistência entre projetos) |
| criptolua-v2 | `lib/price-action/momentum-divergence.ts` | Divergência RSI + estocástico com pivôs, força WEAK/MEDIUM/STRONG, confirmação dupla | **Portar** como camada de divergência de momentum |
| criptolua-v2 | `lib/signals/historical-confidence-engine.ts` | Confiança por amostra histórica: escopos `EXACT`/`CONTEXT`/`STRATEGY_DIRECTION`, `MINIMUM_INFORMED_SAMPLE=8`, `MINIMUM_FULL_SAMPLE=20` | **Portar o conceito**; fonte de amostras vira o journal do finagent |
| criptolua-v2 | `lib/domain/strategy-validation.ts` | Gate de validação: `minimumSampleSize 20`, `minimumExpectancyR 0.15`, `minimumProfitFactor 1.15`, `minimumWinRatePct 30`, `probationSampleSize 8`, drawdown 12/18% | **Adotar como gate** da F3 (números já testados em produção) |
| criptolua-v2 | `scripts/auditar-historico-sinais.ts:283` (`evaluateSignal`) | Avaliação de sinal histórico → `WIN/LOSS/AMBIGUOUS/INCONCLUSIVE` por target/stop | **Portar como esqueleto** do avaliador do journal |
| criptolua-v2 | `lib/regime/market-regime-engine.ts` | Classificação de regime de mercado | **Portar** — confiança precisa ser condicionada por regime |

### 5.2 Usar como referência de parâmetro, sem portar código

| Origem | Arquivo | Uso |
|---|---|---|
| criptolua-v2 | `lib/price-action/{bos-choch,structure,swings,liquidity-sweep,series-pivots}.ts` | O finagent já tem equivalente Python; comparar thresholds e definição de swing, não reimplementar |
| criptolua-v2 | `lib/engines/volume-profile-engine.ts` | Conferir definição de POC/VAH/VAL e tratamento de bins vs. o `finagent/volume.py` |
| criptolua-v2 | `lib/domain/score-weights.ts` | Pesos de score de mercado (fear/greed, funding, OI, dominância) — insumo para a F4, não para o veredito técnico |
| criptolua-v2 | `lib/ingestion/binance-klines.ts:24` | `VALID_TIMEFRAMES` inclui `1w` e `1M`; referência de paginação e limites ao adicionar esses TFs no finagent |

### 5.3 Ferramenta de backtest e histórico

| Origem | O que é | Decisão |
|---|---|---|
| `/home/anderson/Projetos/freqtrade` | Engine completo de backtest/hyperopt em código-fonte. **Não está instalado** no interpretador do sistema (`import freqtrade` falha fora do diretório do repo; o `find_spec` anterior deu falso positivo por cwd). `user_data/data` e `backtest_results` existem mas estão **vazios** — não há corpus baixado | Duas opções na F1: (a) instalar freqtrade num venv dedicado (`python3 -m venv .venv-ft` + `pip install -e /home/anderson/Projetos/freqtrade`) e usar `download-data`/`backtesting` como fonte e validação cruzada; (b) dispensar freqtrade e paginar direto da Binance REST, que já foi **verificado agora**: `1w` e `1M` respondem 60 candles para BTCUSDT. Recomendação: (a) para corpus bulk (retomável, com fee/slippage corretos), (b) como fallback e para amostras pontuais. Nunca acoplar ao runtime do finagent |
| `/home/anderson/Projetos/freqtrade/tests/optimize/*` | 461 referências a backtest, incluindo `test_backtesting.py` | Ler para copiar semântica de fee, slippage, fill e lookahead — os erros clássicos estão testados lá |

### 5.4 Conhecimento já medido no criptolua-v2 (ler antes da F2)

| Documento | Linhas | O que já resolveu / o que evitar |
|---|---|---|
| `docs/analise-historico-sinais-executiva.md` | 47 | Números reais: 28,40% win, -1,07R, SHORT 2,06%, 61% inconclusivos. Já consolidado na §1.7 |
| `docs/plano-confiabilidade-motor-sinais.md` | 559 | Plano de endurecimento: separar score agregado em blocos mínimos obrigatórios, bloquear `TRADE_READY` sem confirmação estrutural, revalidar antes do alerta. **É o ancestral direto da D1** |
| `docs/analise-historico-sinais.md` | 116 | Metodologia da avaliação de outcome (janela, ambíguos, inconclusivos) — base da F3 |
| `docs/estrategias-gatilhos-sinais.md` | 383 | Catálogo de gatilhos por estratégia; referência para o `trigger_tf` |
| `docs/motor-estrategias-especificacao-tecnica-2026-07-08.md` | — | Especificação do motor; conferir contratos antes de criar os do finagent |
| `AUDITORIA-RADAR-JOURNAL.md`, `PLANO-RADAR-V2.md`, `plans/` | — | Decisões e dívidas do journal antigo |
| `cripto-lua-v2-estrategias-evolucao.md`, `avaliacao-cripto-lua-v2-motor-trade.md` | — | Evolução e avaliação do motor de trade |

Regra: desses documentos saem **decisões**, não código. Nenhum arquivo TypeScript
é importado pelo finagent.

### 5.5 Explicitamente NÃO reaproveitar

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
datas fixas. Ler os 4 documentos do §5.4. Corrigir P5 (matar `_tf_bias`).
Gate G0: baseline reproduzível por script.

**F1 — Corpus histórico** (1 dia)
Baixar 1h/4h/1d/1w/1M, 2019-01→hoje, BTC/ETH/SOL/BNB/XRP/ADA. **Não existe corpus
em disco hoje** (freqtrade `user_data/data` vazio, nenhum CSV/JSONL/parquet >500KB em
`/home/anderson/Projetos`) — o histórico precisa ser baixado. Caminho preferido:
instalar freqtrade em venv dedicado e usar `download-data` (retomável); alternativa
já verificada: Binance REST paginado (`1w`/`1M` respondem 60 candles para BTCUSDT).
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
  confiança condicionada por regime (portado do criptolua-v2), nunca global.

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
