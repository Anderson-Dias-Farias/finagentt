# FinAgent

Agente de análise de mercado para decisão de trade. Lê **fluxo de ordens, volume,
liquidez de book, estrutura de mercado, volume profile e derivativos**, e devolve um
veredito com convicção, plano de trade e gestão de risco.

Dados públicos da Binance (Spot + Futures). **Sem API key, sem dependências externas,
sem custo.** Só Python 3.10+ stdlib.

## Instalação

```bash
cd ~/Projetos/finagent
./install.sh          # cria o comando `finagent` em ~/.local/bin
finagent analyze BTCUSDT
```

Ou sem instalar: `python3 finagent.py analyze BTCUSDT`

## Comandos

### `analyze` — leitura completa de um ativo

```bash
finagent analyze BTCUSDT                 # 1h, 30 dias, equity 10k
finagent analyze ETHUSDT --tf 15m --days 7 --equity 5000 --risk 0.5
finagent analyze SOLUSDT --json          # saída JSON para script
finagent analyze BTCUSDT --save          # grava no journal p/ avaliação futura
finagent analyze BTCUSDT --no-derivs     # sem funding/OI (mais rápido)
```

Entrega:
- **Veredito** com direção, convicção 0-100 e status (`EXECUTAVEL`, `EXECUTAVEL COM CAUTELA`, `AGUARDAR`, `SEM SETUP`)
- **Plano**: entrada, stop, TP1, TP2, R:R, tamanho da posição pelo risco em %, nível de invalidação
- **Score de confluência** decomposto em 8 componentes com peso e nota individual (você vê *por que* o veredito é aquele)
- **Leitura** em texto: tendência, estrutura, fluxo, ordens grandes, valor, conclusão

### `scan` — ranking dos ativos mais líquidos

```bash
finagent scan --top 15
finagent scan --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

Ordena por convicção. Filtra stablecoins e tokens alavancados.

### `book` — liquidez real do livro

```bash
finagent book BTCUSDT
```

Spread em bps, profundidade por banda (0.1/0.25/0.5/1%), desequilíbrio bid/ask,
slippage estimado para ordens de 10k/50k/250k USD, paredes anômalas e cobertura do snapshot.

### `flow` — tape reading

```bash
finagent flow BTCUSDT --tf 5m --lookback 12
```

CVD, delta agressor, imbalance compra/venda, tamanho médio e mediana de print,
p99, prints grandes (≥ limiar dinâmico), viés dos grandes e os maiores negócios recentes.

### `journal` — histórico e expectativa

```bash
finagent journal                    # últimos sinais
finagent journal --evaluate         # resolve sinais abertos contra o preço real
finagent journal --evaluate --min-hours 1
```

### `stats` — performance por setup

```bash
finagent stats
```

Win rate, R total, R médio e breakdown por `setup + direção`. É aqui que você
descobre **quais setups realmente pagam** no seu mercado — em vez de achar.

### `monitor` — vigilância com alerta

```bash
finagent monitor --symbols BTCUSDT,ETHUSDT --tf 15m --interval 300
finagent monitor --once          # uma leitura e sai
```

Alerta quando o veredito muda de direção/status. Telegram opcional:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
finagent monitor --symbols BTCUSDT
```

### `serve` — dashboard no navegador

```bash
finagent serve                  # http://127.0.0.1:3000
finagent serve --host 0.0.0.0   # acessível no celular pela rede local
python3 server.py               # mesmo servidor, direto
```

Página única (`web/index.html`) servida por `http.server` da stdlib — zero dependência.
Mostra veredito, gates, convicção, preço, fluxo agressor, perfil de volume
(operacional vs estrutural), liquidez do book com slippage, estrutura, derivativos,
padrões gráficos, plano de trade e o score componente por componente.
Auto-refresh a cada 30s; API JSON em `/api/analyze?symbol=BTCUSDT&tf=1h&equity=10000`
com cache de 25s (`X-Cache: HIT/MISS`).

## Como o veredito é montado

Pesos do score de confluência:

| Componente      | Peso | O que mede |
|-----------------|------|------------|
| Tendência MTF   | 18   | 1d (0.5) + 4h (0.3) + base (0.2), via EMA20/EMA50 |
| Estrutura       | 16   | HH/HL/LH/LL, BOS, CHoCH, sweep de liquidez |
| Fluxo agressor  | 15   | CVD, delta, divergência preço×fluxo |
| Volume profile  | 12   | posição vs POC/VAH/VAL **operacional**, HVN/LVN |
| Momentum        | 11   | RSI, MACD, ADX |
| Derivativos     | 10   | funding, basis, variação de OI |
| Volume          | 10   | volume relativo à média, expansão/clímax |
| Liquidez/Book   | 8    | spread, profundidade, desequilíbrio |
| Padrões         | 7    | duplo topo/fundo, OCO, triângulo, cunha, canal, bandeira, retângulo, breakout |

Convicção = soma ponderada normalizada para 0-100 na direção dominante.
Gates de risco rebaixam o status quando há conflito (ex.: fluxo contra a estrutura,
funding extremo, spread anormal, R:R abaixo do mínimo).

O plano ajusta a entrada: se o preço está esticado longe do VWAP, a entrada vira
pullback em vez de mercado. Stop combina estrutura + ATR. Tamanho sai do risco em %
do equity.

## Limitações honestas

- **Volume profile e estrutura vêm de candles**, não de tick data. É uma aproximação
  boa para swing/intradiário, não substitui footprint de verdade.
- **"Prints" são aggTrades agregados** pela exchange: o ticket médio subestima ordens
  institucionais fatiadas por execução algorítmica. O sinal útil é o **p99 e o viés
  dos grandes**, não a média.
- **Delta agressor por candle** usa `taker buy quote volume` da Binance — é o padrão
  do mercado, mas em spot não revela ordem passiva.
- Book é snapshot do momento: paredes podem ser spoofing.
- `journal --evaluate` assume **stop antes de alvo** no mesmo candle (conservador).
- Sem backtest histórico de portfólio. O histórico que existe é o do seu próprio
  journal de sinais — comece a salvar (`--save`) para ter estatística real.

## Não é recomendação de investimento

Ferramenta de leitura de mercado. Decisão e risco são seus.
