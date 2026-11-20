#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HOME}/.local/bin"
PY="$(command -v python3)"

mkdir -p "$BIN"
cat > "$BIN/finagent" <<EOF
#!${PY}
import sys
sys.path.insert(0, "${DIR}")
from finagent.cli import main
raise SystemExit(main())
EOF
chmod +x "$BIN/finagent"

echo "instalado: $BIN/finagent"
case ":$PATH:" in
  *":$BIN:"*) echo "PATH ok. Teste: finagent analyze BTCUSDT" ;;
  *) echo "AVISO: $BIN nao esta no PATH. Adicione ao ~/.bashrc:"
     echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
