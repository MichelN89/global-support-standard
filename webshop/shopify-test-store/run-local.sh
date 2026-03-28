#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.example first."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"

exec python3 -m uvicorn gss_webshop_shopify.app:app --host "${GSS_PROVIDER_HOST}" --port "${GSS_PROVIDER_PORT}"
