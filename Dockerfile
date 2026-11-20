# finagent — imagem unica: dashboard (3000) + monitor + evaluate + backup
# Sem dependencias externas: Python stdlib apenas. Nada de pip install = build em ~10s.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo \
    FINAGENT_DATA=/data \
    FINAGENT_DB=/data/journal.db \
    FINAGENT_STATE=/data/state.json \
    FINAGENT_BACKUP_DIR=/data/backups \
    FINAGENT_PORT=3000

# Usuario fixo (uid 10001): o volume do host precisa poder ser escrito por ele.
# Se o volume ja existir com outro dono no servidor: chown -R 10001:10001 <path>
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/backups \
    && chown -R app:app /data

WORKDIR /app

COPY finagent.py server.py ./
COPY finagent/ ./finagent/
COPY web/ ./web/
RUN chown -R app:app /app && chmod -R a+rX /app

USER app

# O banco vive AQUI. Sem este volume, todo redeploy comeca vazio.
VOLUME ["/data"]

EXPOSE 3000

# healthcheck usa o proprio endpoint; /api/health responde 503 se o banco nao for gravavel
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=4).status==200 else 1)"]

CMD ["python", "finagent.py", "serve", "--host", "0.0.0.0", "--port", "3000", "--monitor"]
