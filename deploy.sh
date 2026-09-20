#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Edit MYSQL_PASSWORD and service URLs, then rerun."
  exit 1
fi

python -m compileall app
echo "Build/compile OK."
echo "Start with:"
echo "  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090"
