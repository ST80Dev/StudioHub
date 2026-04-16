# Istruzioni per Claude

## Stile di risposta

- **Operazioni pratiche** (comandi da eseguire, modifiche puntuali, passaggi
  già decisi): rispondere in modo **sintetico**. Idealmente il comando da
  copiare e incollare, una verifica, via. Niente alternative multiple se
  non richieste.
- **Pianificazione e scelte architetturali**: va bene presentare alternative
  con pro e contro, approfondire, confrontare. È questo il momento per i
  dettagli.

## Contesto del progetto

- Studio di commercialisti, server Linux on-prem Ubuntu 24.04 (VM VMware,
  `192.168.1.16`, hostname `ubuntu-db`).
- Stack: Django 5.1 + HTMX + Tailwind + PostgreSQL 16 + Caddy nativo.
- Deploy in questa fase: **manuale da terminale server**. Dopo aver mergiato
  la PR su `main`, eseguire sul server:

      sudo -u studiohub-deploy bash /opt/studiohub/scripts/deploy.sh

  Il workflow `.github/workflows/deploy.yml` esiste già ma non è attivo: manca
  l'installazione del runner self-hosted (strategia C). Il runner si potrà
  attivare in futuro con `scripts/install-server.sh`. Quando verrà attivato,
  basterà il merge su main per triggerare il deploy, senza comando manuale.
- Utente di servizio dedicato: `studiohub-deploy` (no sudo, gruppo docker).
- Path applicazione: `/opt/studiohub`.
- Postgres dedicato nello stack Compose (non condiviso con altri stack già
  presenti sul server: Mattermost, pgsql_docker).
- Porte pubbliche 80/443 già occupate da NethServer (replica server
  documentale) → decisione deferred su porta esterna per StudioHub.
