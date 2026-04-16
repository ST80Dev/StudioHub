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
- Deploy via GitHub Actions self-hosted runner (strategia C).
- Utente di servizio dedicato: `studiohub-deploy` (no sudo, gruppo docker).
- Path applicazione: `/opt/studiohub`.
- Postgres dedicato nello stack Compose (non condiviso con altri stack già
  presenti sul server: Mattermost, pgsql_docker).
- Porte pubbliche 80/443 già occupate da NethServer (replica server
  documentale) → decisione deferred su porta esterna per StudioHub.
