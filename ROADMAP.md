# StudioHub — Roadmap di sviluppo

Documento di riferimento per l'ampliamento della piattaforma. Vive con il codice:
va aggiornato quando una fase si chiude o quando cambiano le priorità.

## Stato attuale (fase 0 completata)

- Scaffolding Django 5.1 + HTMX + Tailwind + Postgres 16
- Deploy produzione on-prem: Compose + Caddy + runner self-hosted GitHub Actions
- Modelli base:
  - `accounts.UtenteStudio`, `accounts.AreaAziendale`
  - `anagrafica.Anagrafica`, `AnagraficaReferenteStudio` (storicizzato),
    `AnagraficaLegame`
  - `adempimenti.Adempimento` + figlia 1:1 `AdempimentoBilancioUE` (unico tipo
    implementato finora)
- Viste base: lista + dettaglio anagrafiche e adempimenti, con filtri.

## Fasi previste

### Fase 1 — Seed demo e policy dati test/produzione (IN CORSO)

**Obiettivo**: poter popolare il DB con dati di test realistici, lavorarci, e
poi ripulire senza distruggere ciò che è già "reale".

Implementazione:
- Campo `is_demo: bool` sui modelli radice (`UtenteStudio`, `Anagrafica`,
  `Adempimento`).
- Factory riproducibili (`factory-boy` + `Faker`) per ogni app.
- Management command `seed_demo` — idempotente, con seed deterministico.
- Management command `flush_demo` — rimuove solo i record marcati `is_demo`,
  con flag opzionali per escludere o includere gli utenti.

Vedi sezione "Policy dati demo vs reali" più sotto.

### Fase 2 — CRUD completo e UX

- Form di creazione/modifica anagrafica (tipo-specifici: PF/PG/Ente).
- Gestione referenti dello studio da UI (apertura/chiusura righe storicizzate).
- Gestione legami PF↔PG da UI.
- Validazioni: CF, P.IVA, coerenza `tipo_soggetto` vs campi PF,
  regime contabile vs periodicità IVA.
- Soft delete coerente (oggi il flag `is_deleted` c'è ma non è esposto in UI).

### Fase 3 — Catalogo adempimenti esteso

Oggi esiste solo `BILANCIO_UE`. Da aggiungere (pattern: riga padre `Adempimento`
+ figlia 1:1 con i timestamp che derivano lo stato):

- LIPE trimestrali
- Dichiarazione IVA annuale
- CU (Certificazione Unica)
- 770
- Redditi PF / SP / SC
- IRAP
- IMU
- Intrastat / Esterometro (se necessario)
- F24 periodici
- Deposito bilancio al Registro Imprese (distinto dal bilancio UE)
- Visura camerale annuale / comunicazione unica

### Fase 4 — Scadenzario e dashboard operativa

- Vista "in scadenza / in ritardo" per utente, area, anno.
- Dashboard per addetto contabilità e responsabile consulenza
  (solo i clienti di cui sono referente nel periodo).
- Export CSV/Excel dei report operativi.

### Fase 5 — Permessi e audit

- Ruoli applicativi: admin, responsabile, addetto, sola-lettura.
- Audit log sulle modifiche a modelli sensibili (es. `django-simple-history`).
- Limitazione applicativa: vedi solo i clienti di cui sei referente (opzionale).

### Fase 6 — Integrazioni

- Import massivo clienti (CSV/Excel dal gestionale attuale).
- Possibili integrazioni future: PEC, SDI, Registro Imprese, ADE.

### Fase 7 — Hardening produzione

- Backup Postgres automatici (`pg_dump` schedulato) + test di restore.
- Monitoring: healthcheck, log Caddy strutturati, Sentry opzionale.
- Decisione finale sulla porta pubblica (80/443 già usate da NethServer).
- Rotazione log, limiti di upload, rate limiting login.

---

## Policy dati demo vs reali

Principio: in un qualunque momento il DB può contenere **dati demo e dati reali
mescolati** e devono essere distinguibili e rimuovibili in modo chirurgico,
senza dover droppare l'intero DB.

### Come si distinguono

Flag booleano `is_demo` (default `False`) sulle **tabelle radice** del dominio:

| Modello                       | Ha `is_demo` | Motivo                                                                 |
|-------------------------------|--------------|------------------------------------------------------------------------|
| `accounts.UtenteStudio`       | sì           | Si possono creare utenti di test accanto a quelli reali del personale |
| `anagrafica.Anagrafica`       | sì           | Clienti di test vs clienti reali                                      |
| `adempimenti.Adempimento`     | sì           | Ereditato di norma dall'anagrafica, ma tracciato autonomamente        |

I modelli **dipendenti** non hanno il flag perché vengono eliminati via cascade
della radice (o via OneToOne):

- `AnagraficaReferenteStudio` → cascade da `Anagrafica`
- `AnagraficaLegame` → cascade da `Anagrafica`
- `AdempimentoBilancioUE` (e future figlie 1:1) → cascade da `Adempimento`

### Tabelle mai toccate da `flush_demo`

Sono dati **di configurazione / anagrafica di riferimento**, non dati operativi.
Anche in caso di wipe totale dei dati di test vanno preservati:

| Tabella attuale               | Perché si conserva                                              |
|-------------------------------|-----------------------------------------------------------------|
| `accounts.AreaAziendale`      | Struttura organizzativa dello studio, non dipende dai clienti  |
| `django_migrations`           | Storico migrazioni, mai toccare                                |
| `auth_permission`, `content_type` | Infrastruttura Django                                      |
| `django_session`              | Sessioni utente correnti                                       |
| `django_q_*`                  | Code task scheduler                                            |

### Tabelle "referenziali" da pianificare (future)

Quando verranno introdotte avranno lo stesso trattamento: configurazione, non
dati operativi; mai pulite da `flush_demo`:

- **Comuni / Province / CAP** — tabelle ISTAT per validazione indirizzi e CF.
- **Festività nazionali** — per calcolo scadenze operative.
- **Calendario scadenze fiscali** — regole ricorrenti (es. "IVA trimestrale: 16
  del secondo mese successivo"). Alimenta il generatore di `Adempimento`.
- **Codici tributo F24** — lookup per pagamenti.
- **Codici ATECO** — classificazione attività.
- **Aliquote IVA / cassazioni / addizionali** — se servirà modellarle.
- **Configurazione studio** (record singolo): dati dello studio stesso
  (ragione sociale, P.IVA, sede, PEC) — una sola riga, mai demo.
- **Template documenti / checklist per tipo adempimento** — procedure interne.
- **Audit log** — per natura sempre storico, mai cancellato con `flush_demo`.

### Flusso tipico go-live

Lo scenario "prima testo, poi passo al reale" si svolge così:

1. Popolo con `python manage.py seed_demo` (in dev o in prod provvisoria).
2. Uso e collaudo la piattaforma.
3. Quando arrivano i dati reali, **prima** di caricarli:

   ```bash
   # preservando gli utenti (nomi reali già inseriti) e la configurazione:
   python manage.py flush_demo

   # oppure wipe incluso utenti demo (mantiene comunque aree, config, utenti reali):
   python manage.py flush_demo --include-users
   ```

4. Carico i dati reali (via import o via UI).
5. Eventuale backup `pg_dump` prima del cambio di passo — consigliato sempre.

In caso di reset totale vero (raro, solo se il DB ha cicatrici gravi):

```bash
docker compose -f docker-compose.prod.yml down
docker volume rm studiohub_pgdata
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

Questo perde **tutto**, comprese aree e utenti reali. Usare solo come
ultima risorsa e solo con backup disponibile.

---

## Convenzioni di sviluppo

- **Branch**: feature su `claude/<nome-feature>`, merge via PR su `main`.
- **Migrazioni**: una per PR, nomi parlanti.
- **Stile**: Python 3.12, Django 5.1, HTMX per interattività, Tailwind per UI.
- **Lingua**: codice e commenti in italiano per il dominio (adempimenti,
  anagrafiche, referenti); inglese solo per termini tecnici.
- **Testing**: ogni feature porta con sé i propri test (fase 2 in poi).
