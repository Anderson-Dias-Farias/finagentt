# Deploy no Easypanel — imagem única, SQLite persistente

Resposta curta para "iremos perder algo do sqlite?": **sem volume, sim — tudo. Com
volume em `/data`, não se perde nada em rebuild nem em redeploy.** Testado neste
repositório: sinal gravado no container A apareceu no container B (novo, mesmo volume) e
sumiu no container C (novo, sem volume).

## Por que

Todo container tem filesystem próprio e efêmero. O `journal.db` nasce dentro da
camada de escrita do container; quando o Easypanel rebuilda a imagem e sobe um container
novo, essa camada é descartada. Volume é a única coisa que sobrevive — o build (push →
nova imagem) nunca toca no volume.

| Item | Onde vive | Sobrevive a redeploy? |
| --- | --- | --- |
| `journal.db` + `-wal` + `-shm` | `/data` (volume) | sim |
| `state.json` (último veredito por símbolo) | `/data` (volume) | sim |
| `backups/journal-*.db` | `/data/backups` (volume) | sim |
| código, `web/`, imagem | imagem Docker | sempre recriado (é o esperado) |
| cache de análise em memória (TTL 25s) | RAM | não (irrelevante) |

`.gitignore`/`.dockerignore` já bloqueiam `*.db`, então o banco de desenvolvimento nunca
entra na imagem. Bom: um `COPY` distraído não sobrescreve o volume.

## Passo 0 — o push precisa existir

Hoje o repositório local **não tem remote**: `git remote -v` está vazio. "A cada push ele
instala automático" só passa a valer depois de:

```bash
cd /home/anderson/Projetos/finagent
git remote add origin git@github.com:<usuario>/finagent.git
git push -u origin master
```

## Opção A — App (recomendado, é o fluxo "push → deploy")

No Easypanel: **Create Service → App**

- **Source**: GitHub → repositório `finagent`, branch `master`
- **Build**: Dockerfile (caminho `Dockerfile`, contexto `/`)
- **Auto Deploy**: ligado (o Easypanel registra o webhook; cada push em `master` rebuilda)
- **Port**: `3000` ← o padrão do Easypanel é 80, e 502 "Service is not reachable" é quase
  sempre isso
- **Volume**: mount path `/data` (nomeie `finagent-data`)
- **Deploy**: salvar

Variáveis de ambiente (opcionais, todas têm default):

```
FINAGENT_EVAL_INTERVAL=600        # resolve sinais abertos a cada 10 min
FINAGENT_BACKUP_INTERVAL=21600    # backup consistente a cada 6h
FINAGENT_BACKUP_KEEP=14           # mantém 14 cópias
TELEGRAM_BOT_TOKEN=               # alerta de mudança de veredito
TELEGRAM_CHAT_ID=
```

Se o `TELEGRAM_*` estiver preenchido, use "Secret" no Easypanel para que não apareça no
painel nem em log. Nada de credencial no código.

## Opção B — Stack Compose

**Create Service → Compose**, cole o `docker-compose.yml` do repo. O volume nomeado
`finagent-data` já está declarado; `ports: 3000` cria o proxy do Easypanel.

## Verificação depois do deploy

```bash
curl -s https://<dominio>/api/health   # {"ok":true,...,"signals":N,"open":M}
curl -s https://<dominio>/api/state    # db, tamanho, contadores, último monitor
curl -s https://<dominio>/api/report   # expectativa por setup / TF / convicção
```

`/api/health` responde **503** se o banco não existir ou o diretório não for gravável — é
o healthcheck do container, então um volume mal montado aparece como `unhealthy`, não como
"funcionando vazio".

## Backup e restauração

- Automático: a cada 6h em `/data/backups/journal-<timestamp>.db`, via `sqlite3 backup`
  (consistente mesmo com o monitor escrevendo; não é `cp`).
- Manual: `docker exec <container> python finagent.py backup`
- Baixar: `docker cp <container>:/data/backups/ .`
- Restaurar: pare o serviço, substitua `/data/journal.db` pelo arquivo, remova
  `journal.db-wal`/`-shm` antigos, suba de novo.
- Migração de schema: `journal.init()` é idempotente (`CREATE TABLE IF NOT EXISTS` +
  `ALTER TABLE ADD COLUMN` guardado). Nunca há `DROP` nem recriação — subir versão nova
  sobre banco antigo preserva os sinais.

## Permissão do volume (o erro clássico)

A imagem roda com uid `10001`. Se o volume for **bind mount** de um diretório do host
criado antes, o container não escreve e o healthcheck fica `unhealthy`:

```bash
chown -R 10001:10001 /caminho/no/host
```

Com volume nomeado do Docker (caso do Easypanel), as permissões da imagem são herdadas e
isso não é necessário.

## Monitoramento remoto (como eu acompanho daqui)

Sem expor nada na internet e sem abrir porta: você me dá uma chave restrita e eu puxo o
banco.

```bash
# no servidor: usuário só-leitura + authorized_keys com command restrito
# na minha ponta:
rsync -av vps:/var/lib/docker/volumes/finagent-data/_data/journal.db /tmp/journal.db
sqlite3 /tmp/journal.db "select setup, count(*), round(avg(r_multiple),2) from signals where outcome!='OPEN' group by 1 order by 2 desc;"
```

Alternativa ao vivo: `ssh -L 3000:127.0.0.1:3000 vps` e eu leio `/api/state` no
localhost, sem publicar o serviço.

## O que ainda não está pronto

- Auto-deploy só existe depois do remote (Passo 0).
- `scripts/fetch_data.py` (histórico `data.binance.vision`) ainda não foi escrito — sem
  ele o backtest continua sem corpus.
- Pesos do score continuam sem calibração; `/api/report` agora mede, mas ainda não decide.
