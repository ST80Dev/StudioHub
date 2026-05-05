# StudioHub — Roadmap di sviluppo

Documento di riferimento per l'ampliamento della piattaforma. Vive con il codice:
va aggiornato quando una fase si chiude o quando cambiano le priorità.

---

## Decisioni architetturali (aprile 2025)

Queste decisioni sono state prese nella sessione di progettazione iniziale e
guidano l'intera implementazione.

### Principio guida: configurabilità da UI

Le regole di business (scadenze, regole di applicabilità, checklist, assegnazioni
di default) **non vanno hardcoded nel codice**. Devono vivere in tabelle di
configurazione editabili dall'utente via interfaccia.

Motivazione: lo studio ha molta differenziazione di casi e le regole possono
cambiare (proroghe, nuovi adempimenti, eccezioni clienti). Se la regola è nel
codice serve un deploy; se è nel DB basta un click.

### Architettura adempimenti: catalogo-driven

**NON** si usa il pattern tabella-per-tipo (una classe Python per ogni tipo di
adempimento, come era `AdempimentoBilancioUE`). Questo pattern richiederebbe
una migrazione per ogni nuovo tipo.

Si usa invece un **catalogo configurabile**:
- `TipoAdempimentoCatalogo` — riga per tipo, editabile da UI
- `ScadenzaPeriodo` — scadenze per periodo per tipo (supporta adempimenti
  con N scadenze/anno: LIPE ha 4, F24 ha 12, Bilancio UE ha 1)
- `ChecklistStep` — step ordinati per tipo, editabili
- `RegolaApplicabilita` — condizioni su campi del profilo fiscale del cliente
  che determinano quali adempimenti gli competono
- `Adempimento` — un solo modello per tutti i tipi, con FK al catalogo

### Derivazione adempimenti dal profilo fiscale del cliente

Non si selezionano manualmente i tipi di adempimento per ogni cliente.
Si configurano regole del tipo:
- "Se tipo_soggetto IN (SRL, SPA) → Bilancio UE"
- "Se sostituto_imposta = True → CU, 770"
- "Se categoria_professione = sanitaria → STS"

Le regole sono in DB (`RegolaApplicabilita`), editabili da UI. Quando l'utente
modifica il profilo fiscale di un cliente, la piattaforma ricalcola e propone
attivazione/disattivazione degli adempimenti (sempre con conferma utente).

### Approccio incrementale per adempimento

I tipi vengono implementati uno alla volta (uno per PR), ognuno con le sue
scadenze, regole, checklist. Campi comuni tra tutti i tipi definiti una volta
sola nel modello `Adempimento`.

### Vista per tipo in sidebar

Ogni tipo adempimento ha la sua voce nella sidebar (non una vista unica).
Per tipi periodici (LIPE, F24) la vista è una **matrice**: righe = clienti,
colonne = periodi, celle = stato. Per tipi annuali la matrice ha una sola
colonna — si degrada naturalmente.

### 4 stati standard per tutti gli adempimenti

`DA_FARE` → `IN_CORSO` → `CONTROLLATO` → `INVIATO`

Lo stato è un campo flat, non derivato da timestamp. Checklist e date vivono
come dati aggiuntivi, non come driver dello stato.

---

## Modelli: schema target

### Modelli di dominio

#### `adempimenti.TipoAdempimentoCatalogo`
Catalogo tipi adempimento, editabile da UI.
- `codice` (slug, unique)
- `denominazione` (string)
- `periodicita` (choice: annuale/trimestrale/mensile/una_tantum)
- `colore` (string, null — per UI)
- `attivo` (bool)
- `note_regole` (text — appunti per chi configura)

#### `adempimenti.ScadenzaPeriodo`
Scadenze per periodo per tipo. Supporta N scadenze/anno.
- `tipo_adempimento` (FK → TipoAdempimentoCatalogo)
- `periodo` (int: 1 per annuale, 1-4 per trimestrale, 1-12 per mensile)
- `mese_scadenza` (int 1-12)
- `giorno_scadenza` (int 1-31)
- `anno_offset` (int: 0 = stesso anno fiscale, 1 = anno successivo)
- `etichetta` (string: "Q1", "Gennaio", "Annuale", ecc.)

#### `adempimenti.ChecklistStep`
Step configurabili per tipo, editabili da UI.
- `tipo_adempimento` (FK)
- `ordine` (int)
- `denominazione` (string)

#### `adempimenti.RegolaApplicabilita`
Regole "se X allora questo adempimento compete al cliente".
- `tipo_adempimento` (FK)
- `campo_condizione` (choice: tipo_soggetto, regime_contabile, periodicita_iva,
  sostituto_imposta, iscritto_cciaa, contabilita, categoria_professione)
- `operatore` (choice: uguale, in_lista, vero, falso)
- `valore` (string: es. "SRL,SPA")
- `attiva` (bool)
- `ordine` (int)

Logica: per un dato tipo, TUTTE le regole attive devono essere soddisfatte
(AND). Se 0 regole → il tipo non si applica a nessuno automaticamente.

#### `adempimenti.Adempimento`
Record singolo. Campi comuni a tutti i tipi.
- `anagrafica` (FK → Anagrafica, PROTECT)
- `tipo` (FK → TipoAdempimentoCatalogo, PROTECT)
- `anno_fiscale` (int)
- `periodo` (int, null — 1-12 per mensile, 1-4 per trim., null per annuale)
- `data_scadenza` (date — calcolata da ScadenzaPeriodo, sovrascrivibile)
- `stato` (choice: DA_FARE / IN_CORSO / CONTROLLATO / INVIATO)
- `responsabile` (FK → UtenteStudio, null — pre-assegnabile da regola tipo)
- `note` (text)
- `is_deleted` (bool)
- `is_demo` (bool)
- UNIQUE `(anagrafica, tipo, anno_fiscale, periodo)`

#### `adempimenti.StepCompletato`
Completamento checklist per singolo adempimento.
- `adempimento` (FK)
- `step` (FK → ChecklistStep)
- `completato` (bool)
- `data_completamento` (date, null)
- `completato_da` (FK → UtenteStudio, null)

#### Sezione sidebar "Avanzamento operativo" — controllo "Avanzamento contabilità"

"Avanzamento operativo" è una sezione di sidebar **separata** dal catalogo
`Adempimento`, contenitore di più controlli su lavorazioni che non vanno
modellate come adempimenti veri e propri. Il primo controllo è
**Avanzamento contabilità** (tenuta contabilità interna).

Modelli del primo controllo: `AvanzamentoMensile` + `AvanzamentoSnapshot` +
`AvanzamentoSnapshotRiga`. Per ogni mese si tracciano tre flag (PN / RA / RV)
+ data VB (incontro col cliente e visione bilancio del mese). La
cristallizzazione è manuale on-demand (snapshot etichettato, immutabile). Il
calcolo % avanzamento ponderato usa solo PN:
`% = Σ(peso × mesi_PN) / Σ(peso × 12) × 100`.

Design completo, modello dati e UI: vedi
[`docs/sezioni/avanzamento-contabilita.md`](docs/sezioni/avanzamento-contabilita.md).

> Nota: i precedenti `ProgressioneContabilita` / `ProgressioneContabilitaLog`
> sono stati **superati** da questo design (singolo `mese_ultimo_registrato`
> non bastava: servono tre flag separati per registro + data VB).

### Campi aggiunti su `anagrafica.Anagrafica` (profilo fiscale)

| Campo                          | Tipo              | Default                        |
|--------------------------------|-------------------|--------------------------------|
| `contabilita`                  | choice INT/EST    | ESTERNA                        |
| `peso_contabilita`             | int 1-6, null     | null = non classificato        |
| `sostituto_imposta`            | bool              | False                          |
| `iscritto_cciaa`               | bool              | False                          |
| `data_fine_esercizio`          | CharField "MM-DD" | "12-31"                        |
| `categoria_professione`        | CharField, blank  | "" (per STS e simili futuri)   |

### Tabelle preservate (aggiornamento)

Oltre a quelle già elencate, le nuove tabelle di configurazione non vengono
mai toccate da `flush_demo`:
- `TipoAdempimentoCatalogo`
- `ScadenzaPeriodo`
- `ChecklistStep`
- `RegolaApplicabilita`

---

## Tipi adempimento MVP (da implementare uno alla volta)

1. BILANCIO_UE (include deposito CCIAA)
2. DICH_IVA (dichiarazione IVA annuale)
3. LIQ_IVA (liquidazione IVA periodica — trimestrale o mensile)
4. DICH_REDDITI_PF
5. DICH_REDDITI_SP
6. DICH_REDDITI_SC
7. CU (Certificazione Unica)
8. MOD_770
9. F24 (versamenti periodici)
10. IMU

Ogni tipo porta con sé: regole scadenza, regole applicabilità, checklist
standard pre-seedata. Implementazione incrementale.

---

## Stato attuale (fase 0 completata)

- Scaffolding Django 5.1 + HTMX + Tailwind + Postgres 16
- Deploy produzione on-prem: manuale da terminale server (vedi CLAUDE.md)
- Modelli base implementati (in refactoring verso schema target)
- Seed demo con `is_demo` e factory riproducibili

## Fasi previste

### Fase 1 — Infrastruttura modelli (IN CORSO)

Refactoring da architettura "tabella-per-tipo" a "catalogo-driven":
- Rimozione `AdempimentoBilancioUE` (figlia 1:1)
- Implementazione modelli catalogo (TipoAdempimentoCatalogo, ScadenzaPeriodo,
  ChecklistStep, RegolaApplicabilita, StepCompletato)
- Profilo fiscale arricchito su Anagrafica
- Progressione contabilità mensile + log storico
- Seed demo e policy dati test/produzione
- Management commands `seed_demo` / `flush_demo`

### Fase 2 — Primo adempimento: Bilancio UE + UI

- Seed configurazione Bilancio UE (regole, checklist, scadenze)
- Vista matrice per tipo in sidebar
- Scheda cliente con tab adempimenti
- Home = scadenzario personale

### Fase 2-bis (in parallelo) — Avanzamento contabilità

Primo controllo della futura sezione sidebar "Avanzamento operativo", fuori
dal catalogo adempimenti. Da sviluppare subito perché sblocca un'attività
operativa quotidiana (controllo dello stato di tenuta contabilità interna).
Dettaglio in
[`docs/sezioni/avanzamento-contabilita.md`](docs/sezioni/avanzamento-contabilita.md).

- Migrazione `peso_contabilita` a int 1-6
- Modelli `AvanzamentoMensile` + snapshot
- Vista matrice mensile (PN/RA/RV/VB) con HTMX
- Cristallizzazione manuale on-demand
- Selettori anno + snapshot, % ponderata in header

### Fase 3 — Adempimenti successivi (uno per PR)

Tipi 2-10 della lista MVP, ognuno con le sue regole specifiche. Discussione
e implementazione incrementale.

### Fase 4 — CRUD completo e UX

- Form di creazione/modifica anagrafica (tipo-specifici: PF/PG/Ente)
- Gestione referenti dello studio da UI (apertura/chiusura righe storicizzate)
- Gestione legami PF↔PG da UI
- Validazioni: CF, P.IVA, coerenza tipo_soggetto vs campi PF
- Pannello configurazione: tipi adempimento, regole, checklist, scadenze

### Fase 5 — Permessi e audit

- Ruoli applicativi: admin, responsabile, addetto, sola-lettura
- Audit log su modifiche critiche (es. django-simple-history)
- Limitazione applicativa opzionale

### Fase 6 — Integrazioni

- Import massivo clienti (CSV/Excel)
- Export CSV/Excel dei report operativi
- Possibili integrazioni future: PEC, SDI, ADE

### Fase 7 — Hardening produzione

- Backup Postgres automatici + test restore
- Monitoring, log, Sentry opzionale
- Porta pubblica (deferred: 80/443 usate da NethServer)

### Fase avanzata (eventuale)

- Documenti allegati (upload ricevute, attestati, F24 quietanzati)
- Timeline attività / log per adempimento
- Dipendenze tra adempimenti
- Notifiche in-app / email su scadenze
- Calendario visuale mese/settimana

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
della radice:

- `AnagraficaReferenteStudio` → cascade da `Anagrafica`
- `AnagraficaLegame` → cascade da `Anagrafica`
- `StepCompletato` → cascade da `Adempimento`
- `AvanzamentoMensile` → cascade da `Anagrafica`
- `AvanzamentoSnapshotRiga` → cascade dallo `Snapshot`; protect su `Anagrafica`

### Tabelle mai toccate da `flush_demo`

Dati di configurazione / anagrafica di riferimento:

- `accounts.AreaAziendale`
- `adempimenti.TipoAdempimentoCatalogo` + `ScadenzaPeriodo` + `ChecklistStep`
  + `RegolaApplicabilita`
- `django_migrations`, `auth_permission`, `content_type`
- `django_session`, `django_q_*`

### Flusso tipico go-live

1. Popolo con `python manage.py seed_demo` (in dev o in prod provvisoria).
2. Uso e collaudo la piattaforma.
3. Quando arrivano i dati reali:

   ```bash
   python manage.py flush_demo                   # preserva utenti
   python manage.py flush_demo --include-users    # oppure wipe completo demo
   ```

4. Carico i dati reali (via import o via UI).
5. Backup `pg_dump` prima del cambio di passo — consigliato sempre.

---

## Convenzioni di sviluppo

- **Branch**: feature su `claude/<nome-feature>`, merge via PR su `main`.
- **Migrazioni**: nomi parlanti.
- **Stile**: Python 3.12, Django 5.1, HTMX per interattività, Tailwind per UI.
- **Lingua**: codice e commenti in italiano per il dominio; inglese per termini
  tecnici.
- **Adempimenti**: un tipo alla volta, discusso e implementato incrementalmente.
