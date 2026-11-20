"""FinAgent - agente de analise de fluxo, volume, liquidez e estrutura de mercado."""
from .envfile import load as _load_env

__version__ = "1.1.0"

# O .env precisa entrar ANTES de qualquer submodulo ler o ambiente: os caminhos
# (FINAGENT_DB, FINAGENT_DATA, FINAGENT_BACKUP_DIR) e os intervalos sao resolvidos
# no import dos modulos. Aqui roda uma vez, no import do pacote.
# Variavel ja definida no ambiente real (EasyPanel/systemd) tem prioridade.
_load_env()
