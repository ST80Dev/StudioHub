#!/usr/bin/env bash
# Chiamato dal workflow GitHub Actions su ogni push su main.
# Lavora nella cartella APP_DIR (default /opt/studiohub) che DEVE essere
# un repo git gia clonato (la prima volta usa scripts/install-server.sh).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/studiohub}"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"

cd "$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
    echo "ERRORE: $APP_DIR non e un repo git."
    echo "Esegui prima scripts/install-server.sh sul server."
    exit 1
fi

if [ ! -f "$APP_DIR/.env" ]; then
    echo "ERRORE: manca $APP_DIR/.env (copia da .env.prod.example e valorizzalo)"
    exit 1
fi

echo "==> [$(date --iso-8601=seconds)] Fetch ultime modifiche da origin/main"
git fetch --all --prune
git reset --hard origin/main

echo "==> Build immagini"
docker compose -f "$COMPOSE_FILE" build

echo "==> Avvio / aggiornamento container"
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo "==> Pulizia immagini dangling"
docker image prune -f >/dev/null || true

echo "==> Stato container"
docker compose -f "$COMPOSE_FILE" ps

echo "==> Deploy completato il $(date --iso-8601=seconds)"
