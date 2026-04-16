#!/usr/bin/env bash
# Installazione iniziale di StudioHub sul server Linux.
# Esegui UNA SOLA VOLTA, da un utente con sudo (es. db_admin).
# Non eseguire come root diretto.
#
# Cosa fa:
#   1) crea l'utente di servizio "studiohub-deploy" (no sudo, solo gruppo docker)
#   2) crea la cartella /opt/studiohub di proprieta di quell'utente
#   3) clona il repo dentro /opt/studiohub (branch main)
#   4) prepara .env da .env.prod.example (da valorizzare a mano dopo)
#   5) prepara la cartella di log di Caddy
#
# Dopo questo script, seguire le istruzioni a schermo per:
#   - compilare /opt/studiohub/.env
#   - primo docker compose up
#   - registrare il GitHub Actions self-hosted runner
#   - appendere il site block al Caddyfile
set -euo pipefail

APP_USER="studiohub-deploy"
APP_DIR="/opt/studiohub"
REPO_URL="${REPO_URL:-https://github.com/st80dev/studiohub.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

if [ "$(id -u)" -eq 0 ]; then
    echo "Non eseguire come root. Usa un utente con sudo (es. db_admin)."
    exit 1
fi

echo "==> 1/5 Creazione utente $APP_USER"
if ! id "$APP_USER" >/dev/null 2>&1; then
    sudo adduser --disabled-password --gecos "" --home "/home/$APP_USER" "$APP_USER"
else
    echo "   $APP_USER gia esistente"
fi
sudo usermod -aG docker "$APP_USER"

echo "==> 2/5 Creazione $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> 3/5 Clone repo in $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
    sudo -u "$APP_USER" git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
else
    echo "   repo gia clonato, aggiorno"
    sudo -u "$APP_USER" git -C "$APP_DIR" fetch --all --prune
    sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/$REPO_BRANCH"
fi

echo "==> 4/5 Preparazione .env"
if [ ! -f "$APP_DIR/.env" ]; then
    sudo -u "$APP_USER" cp "$APP_DIR/.env.prod.example" "$APP_DIR/.env"
    sudo chmod 600 "$APP_DIR/.env"
    echo "   .env creato da template. DA COMPILARE prima del primo avvio."
else
    echo "   .env gia presente, lascio stare."
fi

echo "==> 5/5 Cartella log Caddy"
sudo mkdir -p /var/log/caddy
sudo chown caddy:caddy /var/log/caddy 2>/dev/null || true

cat <<EOF

==========================================================================
Setup iniziale completato.

PROSSIMI PASSI (esegui nell'ordine):

[1] Compila il file .env con valori reali:
    sudo -u $APP_USER nano $APP_DIR/.env

    Genera una DJANGO_SECRET_KEY robusta:
      python3 -c "import secrets; print(secrets.token_urlsafe(64))"

    Genera una POSTGRES_PASSWORD robusta:
      python3 -c "import secrets; print(secrets.token_urlsafe(32))"

    Verifica che DJANGO_ALLOWED_HOSTS e DJANGO_CSRF_TRUSTED_ORIGINS
    contengano il sottodominio studiohub.VOSTRO-DOMINIO.TLD reale.

[2] Primo avvio dello stack (come utente $APP_USER):
    sudo -u $APP_USER bash -c \\
      "cd $APP_DIR && docker compose -f docker-compose.prod.yml up -d --build"

[3] Crea il primo superuser Django:
    sudo -u $APP_USER bash -c \\
      "cd $APP_DIR && docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser"

[4] Appendi il site block al Caddyfile esistente e ricarica:
    # 1) prima sostituisci VOSTRO-DOMINIO.TLD in $APP_DIR/deploy/Caddyfile.snippet
    # 2) poi:
    sudo bash -c 'cat $APP_DIR/deploy/Caddyfile.snippet >> /etc/caddy/Caddyfile'
    sudo caddy validate --config /etc/caddy/Caddyfile
    sudo systemctl reload caddy

[5] Registra il runner self-hosted di GitHub Actions come utente $APP_USER:
    Vai su GitHub: Repo -> Settings -> Actions -> Runners -> New self-hosted runner (Linux x64)
    GitHub mostrera 3 comandi: DOWNLOAD, CONFIG, RUN.

    Sul server lanciali COME $APP_USER:
      sudo -u $APP_USER -i
      mkdir actions-runner && cd actions-runner
      # poi incolla i 3 comandi che ti mostra GitHub.
      # Al config aggiungi la label "studiohub":
      #   ./config.sh --url https://github.com/st80dev/studiohub --token XXXXX --labels studiohub

    Installa come servizio persistente (torna con un utente sudoer):
      cd /home/$APP_USER/actions-runner
      sudo ./svc.sh install $APP_USER
      sudo ./svc.sh start
      sudo ./svc.sh status

[6] Verifica porta 443 sul router/firewall: deve inoltrare a 192.168.1.16:443.
    Verifica DNS: studiohub.VOSTRO-DOMINIO.TLD -> IP pubblico fisso dello studio.

[7] Test finale: apri https://studiohub.VOSTRO-DOMINIO.TLD dal browser.
    Caddy emettera il certificato Let's Encrypt al primo accesso (~10 sec).
==========================================================================
EOF
