#!/usr/bin/env bash
# Bootstrap a fresh dev environment.
# Usage: bash scripts/dev-bootstrap.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "→ Creating .env from .env.example"
  cp .env.example .env
fi

# Generate a JWT secret if it still has the placeholder
if grep -q "change-me-to-a-long-random-string" .env; then
  SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s|change-me-to-a-long-random-string|${SECRET}|" .env
  else
    sed -i "s|change-me-to-a-long-random-string|${SECRET}|" .env
  fi
  echo "→ Generated random JWT_SECRET in .env"
fi

echo "→ Bringing up stack…"
docker compose up --build -d

echo
echo "✔ Stack is up."
echo "  Frontend  : http://localhost:3000"
echo "  API docs  : http://localhost:8000/docs"
echo "  Health    : http://localhost:8000/health"
echo "  Qdrant    : http://localhost:6333/dashboard"
echo
echo "Tail logs with:  make logs"
