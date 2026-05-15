# Sezione "Registrazione attività" — timesheet operativo dello studio

Sezione dedicata in sidebar, **separata** sia dal catalogo `Adempimento` sia
da "Avanzamento operativo". Ogni addetto dello studio registra le proprie
attività quotidiane (cliente, attività, durata, descrizione). Le ore
alimentano analisi di carico, marginalità per cliente e timesheet personale.

> File di lavoro / note di progettazione. Le scelte già confermate sono
> indicate come **DEC**; quelle ancora aperte come **OPEN**.

---

## Scopo (cosa serve)

- **Rendicontazione interna**: chi ha fatto cosa, quanto, su quale cliente
  o attività trasversale.
- **Marginalità per cliente**: il cliente ha un **budget orario** annuo;
  confrontiamo consumo reale vs budget e ne ricaviamo valore economico
  via costo/tariffa oraria. **I parametri costo/tariffa sono quelli
  dell'AREA cui appartiene l'ATTIVITÀ svolta**, non quelli dell'area di
  appartenenza dell'addetto. Esempio: un addetto di Contabilità (costo
  30€ / tariffa 45€) che svolge un'attività dell'area Consulenza
  Ordinaria (costo 50€ / tariffa 75€) viene valorizzato con i parametri
  della Consulenza Ordinaria, non della Contabilità.
- **Avanzamento adempimenti (solo informativo)**: ogni attività può essere
  agganciata a un adempimento specifico. **Non c'è automatismo di
  cambio stato**: lo stato dell'adempimento si gestisce come oggi, le ore
  si accumulano come dato analitico.
- **Fatturazione effettiva**: fuori scope (avviene con altro software). Da
  StudioHub esce solo l'analisi di consuntivo e marginalità per uso
  decisionale interno.

DEC: nessun lock di periodo (modificabile sempre da autore e admin).

---

## Modello dati

> Nuova app Django: `attivita/`. Convenzione: tutti i nomi minuscoli stile
> TextChoices (cfr. `CLAUDE.md`).

### Entità esistenti da estendere

#### `accounts.UtenteStudio`

Oggi: `aree = M2M(AreaAziendale)`.

**DEC** — l'utente ha **una sola area di appartenenza** (informazione di
organigramma). Refactor proposto:

- aggiungere `area_appartenenza` = FK `AreaAziendale` (nullable in
  transitorio).
- la M2M `aree` esistente può restare come dato secondario (insieme di
  aree in cui l'utente "può lavorare") oppure essere dismessa: per la
  valorizzazione delle attività **non viene usata**.

**Importante**: l'area di appartenenza dell'utente NON entra nel calcolo
costo/tariffa dell'attività registrata. Serve solo per organigramma,
filtri report ("registrazioni svolte da addetti dell'area Contabilità"),
ecc. La valorizzazione economica usa sempre l'area dell'**Attività**
svolta (vedi `Attivita` e `RegistrazioneAttivita` sotto).

#### `anagrafica.AreaAziendale`

Aggiungere:

- `costo_orario` (Decimal) — costo interno (lordo azienda).
- `tariffa_oraria` (Decimal) — tariffa di studio applicata al cliente.

**OPEN** — storicizzazione tariffe (validità da/a):
- Opzione A: campo singolo, modificabile, niente storia.
- Opzione B: tabella `AreaAziendaleTariffa` con `(area, valida_da)` per
  avere il costo corretto al momento dell'attività.

Decisione raccomandata: B se vogliamo dati di marginalità storici
attendibili anche dopo aumenti di tariffa. A se accettiamo di
"riscrivere" la marginalità con valori correnti.

#### `anagrafica.Anagrafica` (cliente)

Aggiungere:

- `compenso_annuo` (Decimal, per anno fiscale) — solo informativo per la
  marginalità (non sostituisce la fattura emessa da altro software).
- **OPEN**: se va per anno (allora serve tabella `CompensoAnnuoCliente`
  con `(cliente, anno, importo)`) o se basta un valore unico "corrente".

Il **referente** del cliente esiste già (`RiferimentoCliente` con ruoli
`referente_contabilita` e `referente_consulenza`). Lo usiamo a scopo
informativo nei report ("il referente di questo cliente sta sforando il
budget") ma **non** vincola chi può registrare attività: chiunque dello
studio può registrare su qualunque cliente (**DEC**).

### Nuove entità

#### `attivita.Attivita`

Voce specifica del catalogo attività registrabili. **Gerarchia a due
livelli**: `AreaAziendale` (top) → `Attivita` (specifica). Ogni area ha
il proprio elenco di attività dedicate.

Esempi (indicativi, da affinare con l'utente):

- Area **Contabilità**: "Registrazione FE", "Registrazione FA",
  "Quadratura banche", "Liquidazione IVA", "Gestione cespiti".
- Area **Consulenza Ordinaria**: "Consulenza fiscale telefonica",
  "Risposta interpello", "Predisposizione F24", "Predisposizione
  dichiarativi".
- Area **Consulenza Straordinaria**: "Operazione straordinaria",
  "Perizia", "Due diligence", "Contenzioso tributario".
- Area **Attività Interne**: "Formazione", "Riunione studio",
  "Aggiornamento normativo", "Gestione organizzativa".

**Costo/tariffa**: NON sono campi di `Attivita`, vengono presi
dall'`area` di appartenenza al momento della registrazione (vedi
snapshot in `RegistrazioneAttivita`). Quindi se l'utente cambia il
costo/tariffa dell'area "Consulenza Ordinaria", da quel momento in poi
le nuove registrazioni di tutte le attività di quell'area si valorizzano
al nuovo importo.

Distinta da `TipoAdempimentoCatalogo`: l'`Attivita` è la dimensione
analitica del lavoro svolto; il tipo adempimento è il "pezzo formale"
su cui eventualmente si lavora. Si possono collegare nella registrazione
ma sono indipendenti.

| Campo | Tipo | Note |
|---|---|---|
| `codice` | slug lowercase | identificativo stabile (univoco globale o per area, vedi OPEN) |
| `area` | FK AreaAziendale PROTECT | determina costo/tariffa di valorizzazione |
| `denominazione` | string | label estesa |
| `abbreviazione` | string max 8 blank | per badge/report compatti, opzionale |
| `richiede_cliente` | bool default True | False per attività interne (formazione, riunioni studio) |
| `attivo` | bool default True | per dismettere senza eliminare |
| `ordine` | int | per ordinamento all'interno dell'area |

Editabile da admin Django e da UI Configurazione (`/configurazione/
attivita/catalogo` con vista raggruppata per area).

**OPEN** — `codice` univoco globale o solo `(area, codice)`? Il secondo
permette di avere "registrazione" sia in Contabilità che in altre aree
senza conflitti, ma rende meno utile il codice come identificativo
parlante. Suggerito: `(area, codice)` unique.

#### `attivita.RegistrazioneAttivita`

La riga di timesheet vera e propria. Una per ogni "blocco" di lavoro
registrato.

| Campo | Tipo | Note |
|---|---|---|
| `utente` | FK UtenteStudio PROTECT | autore (chi ha svolto l'attività) |
| `attivita` | FK Attivita PROTECT | l'attività svolta; porta con sé l'area di valorizzazione |
| `area_valorizzazione` | FK AreaAziendale PROTECT | snapshot: **= attivita.area al momento del save**, NON area dell'utente |
| `data` | date | giorno dell'attività |
| `durata_ore` | Decimal(5,2) positivo | granularità: decimali di ora (es. `1.50`, `0.25`, `2.75`) |
| `cliente` | FK Anagrafica PROTECT nullable | obbligatorio se `attivita.richiede_cliente=True` |
| `adempimento` | FK adempimenti.Adempimento PROTECT nullable | aggancio opzionale a un adempimento specifico |
| `descrizione` | text | descrizione libera di cosa è stato fatto |
| `costo_orario_snapshot` | Decimal | costo/h dell'`area_valorizzazione` al momento dell'inserimento |
| `tariffa_oraria_snapshot` | Decimal | tariffa/h dell'`area_valorizzazione` al momento dell'inserimento |
| `costo_valorizzato` | Decimal calcolato | `durata_ore × costo_orario_snapshot` |
| `valore_valorizzato` | Decimal calcolato | `durata_ore × tariffa_oraria_snapshot` |
| `created_at` / `updated_at` | auto | |
| `updated_by` | FK UtenteStudio nullable | per audit |

Indici: `(utente, data)`, `(cliente, data)`, `(attivita, data)`,
`(adempimento)`, `(area_valorizzazione, data)`.

Vincoli:
- `durata_ore > 0`.
- Se `attivita.richiede_cliente`, allora `cliente NOT NULL`.
- Se `adempimento` non nullo, allora `adempimento.anagrafica == cliente`.

**Snapshot di area + costo + tariffa al save**: ad ogni save (create o
update) si rileggono `attivita.area` e i valori correnti di
`costo_orario`/`tariffa_oraria` di quell'area, e si scrivono nei tre
campi snapshot. Così la valorizzazione resta stabile anche se in
seguito si cambia l'area di un'`Attivita` o si modificano le tariffe
di un'area. Se si adotta la storicizzazione tariffe (Opzione B in
`AreaAziendale`), si legge la tariffa valida alla `data` dell'attività
e gli snapshot diventano ridondanti (vedi decisioni aperte).

#### `attivita.BudgetAddetto`

> **Preliminare** — la modellazione del budget verrà approfondita in una
> sessione dedicata. Quanto segue è una bozza coerente con le decisioni
> fin qui prese, non un design finale.

Monte ore preventivato annualmente. **DEC**: due livelli alternativi
(mutualmente esclusivi per riga), entrambi sempre **per addetto**:

1. **addetto × cliente** — "Mario farà 40h sul cliente Rossi nel 2026"
   (sappiamo a priori a quale cliente quelle ore saranno dedicate).
2. **addetto × area** — "Mario farà 200h sull'area Consulenza Ordinaria
   nel 2026" (sappiamo che farà quelle ore in quell'area, ma non
   sappiamo ancora la ripartizione per cliente).

| Campo | Tipo | Note |
|---|---|---|
| `utente` | FK UtenteStudio PROTECT | obbligatorio |
| `anno` | int | anno solare/fiscale |
| `cliente` | FK Anagrafica PROTECT nullable | valorizzato per livello 1, NULL per livello 2 |
| `area` | FK AreaAziendale PROTECT nullable | valorizzato per livello 2, NULL per livello 1 |
| `ore` | Decimal(7,2) | ore preventivate nell'anno |
| `note` | text blank | |

Vincoli:
- esattamente uno fra `cliente` e `area` valorizzato (XOR).
- Unique: `(utente, anno, cliente, area)` con NULL distinti.

Confronto con consuntivo:

- **Livello 1 (addetto×cliente)**: budget Mario su Rossi vs somma
  `durata_ore` di `RegistrazioneAttivita` con `utente=Mario,
  cliente=Rossi, anno(data)=2026` (su tutte le attività, di qualunque
  area).
- **Livello 2 (addetto×area)**: budget Mario sull'area Consulenza
  Ordinaria vs somma `durata_ore` di `RegistrazioneAttivita` con
  `utente=Mario, area_valorizzazione=Consulenza Ord., anno(data)=2026`
  (su tutti i clienti, incluse attività senza cliente).

Conversione in € a runtime:
- Livello 2: `ore × tariffa_oraria` dell'area budgetata (deterministico).
- Livello 1: ambigua perché non sappiamo a priori in che mix di aree
  quelle ore saranno spese (vedi OPEN sotto).

**OPEN** — granularità del livello 2: si budgetta per area
(`addetto × area`) o anche per singola `Attivita` (`addetto × attivita`)?
Per ora propendo per area, più gestibile come pianificazione macro;
l'attività singola sarebbe troppa granularità per un budget annuo.
Da confermare nella sessione di approfondimento dedicata al budget.

**OPEN** — per il livello 1 (addetto×cliente) la valorizzazione
economica del budget è ambigua perché non sappiamo a priori in che mix
di aree quelle ore saranno spese. Possibili approcci:
- (a) si usa la tariffa dell'area di appartenenza dell'utente come proxy;
- (b) si valorizza solo in ore (no €) per il livello 1 e si lascia che
  la marginalità in € emerga solo a consuntivo;
- (c) ogni cliente ha una "tariffa di riferimento" configurabile che
  proietta il budget orario in un valore atteso.

L'opzione (b) è la più onesta dato il modello scelto.

#### `attivita.ConsumoAtteso` (opzionale, fase 2)

Per la **curva attesa** intra-anno. Se ci spostiamo dalla v1 lineare, una
tabella di "ore previste per (cliente, mese)" generata da un job:

- input: scadenze adempimenti previste per il cliente nell'anno + tipo
  soggetto + regime contabile → peso del mese;
- distribuisce il budget annuo del cliente sui mesi con un profilo non
  uniforme;
- in v1 può essere semplicemente un calcolo on-the-fly senza tabella.

**OPEN** — vale la pena precalcolare e cachare o si fa on-demand al
render del report?

---

## Attività vs tipo adempimento

Sono concetti diversi e tutti e due servono. Mapping logico:

- **Attivita** (con la sua area) è la dimensione di analisi del lavoro
  svolto: cosa stiamo facendo concretamente, in quale area aziendale.
- **TipoAdempimentoCatalogo** è il "pezzo formale" su cui si lavora
  (LIPE, Bilancio UE, F24).

Una `RegistrazioneAttivita` ha sempre un'`Attivita` e — facoltativamente
— un `Adempimento` collegato. Esempi:

- "1h sul cliente Rossi, registrazione FE generica" →
  attivita="Registrazione FE" (area Contabilità), cliente=Rossi,
  adempimento=NULL.
- "0.5h sul cliente Rossi, predisposizione F24 per LIPE Q2 2026" →
  attivita="Predisposizione F24" (area Consulenza Ordinaria),
  cliente=Rossi, adempimento=Adempimento(tipo=LIPE, Q2 2026).
- "2h di Formazione interna" → attivita="Formazione" (area Attività
  Interne), cliente=NULL, adempimento=NULL.

**OPEN** — vincolo soft fra `Attivita` e tipi di adempimento? Es.
"Attività 'Predisposizione F24' è coerente con adempimenti di tipo F24,
LIPE", solo come filtro/warning nell'autocomplete adempimento. Per la
v1 si può rinviare.

---

## UI / UX

DEC: tutte e tre le modalità di inserimento coesistono.

### 1. Modale globale (sempre accessibile)

- Bottone "Registra attività" in topbar, presente su tutte le pagine.
- HTMX modal con campi: data (default oggi), durata, cliente
  (autocomplete), categoria, adempimento (autocomplete filtrato sul
  cliente quando selezionato), descrizione, area (default = principale,
  modificabile).
- Su pagine "scheda cliente" o "scheda adempimento", il bottone
  precompila il campo relativo.

### 2. Diario giornaliero

- Pagina `/attivita/oggi` (o `/attivita/<data>`): lista delle
  registrazioni del giorno dell'utente loggato, totale ore in basso.
- Form di aggiunta rapida in cima (stessi campi del modale).
- Click su una riga → modifica inline (pattern editing inline di
  `lista_clienti`).

### 3. Timesheet settimanale a griglia

- Pagina `/attivita/settimana?w=YYYY-Www`: griglia con righe =
  (cliente|categoria|adempimento) usati nella settimana, colonne = i 7
  giorni, celle = ore (Decimal).
- Lettura: somma `durata_minuti` aggregata per chiave riga.
- Modifica inline cella: apre form dei record contenuti (o ne crea uno
  nuovo se vuota).
- Totali a fine riga (per chiave) e a fondo colonna (per giorno).

### Comportamenti comuni

- Durata sempre in **decimali di ora** (es. `1.5`, `0.25`, `2.75`).
  Input tollerante alla virgola italiana (`1,5` → `1.5`); validazione
  lato server: `> 0`, max 2 decimali.
- Salvataggio HTMX, conferma toast inline, ritorno alla vista corrente
  con stato preservato.
- L'utente NON sceglie l'area dell'attività: viene derivata dalla
  categoria selezionata. Mostrato in form come label info ("Area di
  valorizzazione: Consulenza Ordinaria — 50€/h costo, 75€/h tariffa")
  per chiarezza.

---

## Reportistica (priorità per release)

DEC v1: **scheda addetto / timesheet personale**.

### v1 — Timesheet addetto

`/attivita/utente/<id>` (admin) oppure `/attivita/mio` (utente loggato):

- Header con range periodo (default = mese corrente) + filtri:
  cliente, categoria, adempimento.
- Tabella registrazioni paginata (50/pag, pattern `lista_clienti`):
  data, durata, cliente, categoria, adempimento, area, descrizione.
- Totali per periodo: ore totali, ore per categoria, ore per cliente.
- Confronto vs budget personale: somma budget addetto×cliente di tutti i
  clienti dell'utente + budget addetto×categoria trasversali → ore attese
  vs consumate.

### v2 — Scheda cliente con consumo

Sezione nella scheda cliente:
- Budget totale (annuo) per anno corrente vs consumo.
- Dettaglio per categoria (consuntivo: ore consumate raggruppate per
  categoria sul cliente).
- Dettaglio per addetto (chi ha lavorato quanto su questo cliente).
- Curva atteso vs reale nel tempo.
- Marginalità: `compenso_annuo − somma costo_valorizzato`.
- Valore prodotto: `somma valore_valorizzato`.

### v3 — Dashboard alert sforamenti

- Clienti con consumo > X% del budget annuo.
- Addetti molto sotto/molto sopra le ore attese.
- Marginalità negativa o sotto soglia configurabile.

### v4 — Export Excel/CSV

- Export registrazioni grezze filtrate.
- Export pivot (cliente × addetto × mese, in ore ed €).

---

## Permessi e visibilità

DEC: **tutti vedono tutto**.

Lettura:
- Ogni `UtenteStudio` autenticato può vedere tutte le registrazioni di
  tutti.
- Pagina `/attivita/mio` filtra di default sull'utente loggato per
  comodità, ma la pagina addetto-specifica è accessibile per chiunque.

Scrittura:
- Inserimento: ognuno solo per sé (campo `utente` non modificabile da UI,
  fisso = `request.user`; admin può cambiarlo da admin Django se serve
  inserire per conto terzi).
- Modifica/eliminazione: autore + utenti con flag admin (DEC: nessun
  lock di periodo, modificabile sempre).

---

## Curva attesa di consumo

DEC: "ragionata sulle scadenze adempimenti del cliente + tipo soggetto +
regime contabile". V1: parto lineare, v2 smart.

### v1 — Lineare

`atteso(data) = budget_annuo × (giorno_dell_anno / 365)`.

Semplice, rende il confronto immediato anche se non realistico per
clienti con stagionalità marcata.

### v2 — Pesata su scadenze

Algoritmo proposto:

1. Per cliente nell'anno, raccogli le scadenze previste dei suoi
   adempimenti attivi (via `ScadenzaPeriodo` filtrato per applicabilità).
2. Per ogni mese, conta le scadenze "che cadono in quel mese" (o nei
   30gg precedenti, se l'attività di preparazione anticipa la scadenza —
   parametrizzabile per tipo adempimento).
3. Aggiungi un fattore base "contabilità ricorrente mensile" se il
   regime contabile è interno/ordinario/semplificato (peso fisso per
   mese su contabilità periodica).
4. Pesi mese per mese normalizzati → distribuisci il `budget_annuo`
   secondo i pesi → `atteso(mese_i)`.

Da affinare iterando sui dati reali: probabilmente serve un parametro per
tipo adempimento "anticipo medio lavorazione" (giorni prima della
scadenza in cui si fa il grosso del lavoro).

---

## Integrazione con il resto del sistema

### Anagrafica clienti

- Scheda cliente: nuova tab "Attività" con riepilogo consuntivo
  (categoria → ore → €) + lista cronologica delle ultime registrazioni
  + grafico budget vs consumo (v2).
- Campo `compenso_annuo` nella tab profilo fiscale o in una nuova tab
  "Economico".

### Adempimenti

- Scheda adempimento: pannello "Attività su questo adempimento" con
  somma ore e dettaglio per addetto (read-only).
- Nessuna automazione sullo stato (DEC).

### Sidebar

- Nuova voce "Attività" (livello primo) con sotto-voci:
  - "Oggi" → `/attivita/oggi`
  - "Settimana" → `/attivita/settimana`
  - "Le mie attività" → `/attivita/mio`
  - "Configurazione" → catalogo categorie + budget (solo per admin).

### Configurazione

- `/configurazione/attivita/categorie` — CRUD categorie.
- `/configurazione/attivita/aree` — gestione costo/tariffa per area (oggi
  esistono solo le denominazioni).
- `/configurazione/attivita/budget` — impostazione budget addetto: per
  ogni utente e anno, riga per ogni cliente assegnato (livello
  addetto×cliente) e riga per ogni categoria con monte ore trasversale
  (livello addetto×categoria).

---

## Fasi di sviluppo proposte

### Fase 0 — Scaffolding

- App `attivita` + migrazioni base.
- Estensione `AreaAziendale` (`costo_orario`, `tariffa_oraria`).
- Estensione `UtenteStudio.area_principale`.
- Seed minimo: 3-4 categorie base.

### Fase 1 — Inserimento

- Modello `Attivita` + `RegistrazioneAttivita`.
- Modale globale di inserimento (1).
- Pagina diario giornaliero (2).
- Pagina "le mie attività" con paginazione e filtri (pattern
  `lista_clienti`).

### Fase 2 — Budget e timesheet

- Modello `BudgetAddetto` + UI configurazione.
- Timesheet settimanale a griglia (3).
- Confronto consumato vs atteso lineare nello scheda addetto.

### Fase 3 — Reportistica cliente

- Scheda cliente tab "Attività".
- Marginalità (compenso annuo − costi valorizzati).
- Curva attesa v1 (lineare).

### Fase 4 — Smart & dashboard

- Curva attesa v2 (pesata su scadenze).
- Dashboard alert sforamenti.
- Export.

---

## Decisioni aperte (riepilogo)

1. **Storicizzazione tariffe/costi per area**: tabella storica vs valore
   unico (preferito: tabella storica, vedi sopra).
2. **Compenso annuo cliente**: tabella per-anno o valore unico
   "corrente"?
3. **Snapshot tariffa nel record** vs lookup storico al momento del
   render: se andiamo su tabella storica delle tariffe, lo snapshot in
   colonna diventa ridondante.
4. **Tabella ConsumoAtteso pre-calcolata** vs calcolo on-the-fly?
5. **Vincolo categoria ↔ tipo adempimento**: warning soft o nulla?
6. **Parser durata**: quale formato canonico in UI (es. consentire
   "1.5", "1,5", "1:30", "90m")?
7. **Adempimenti collegati**: filtraggio nell'autocomplete per cliente
   + periodo corrente è sufficiente, o serve anche per "scaduti" /
   "futuri"?
8. **Eliminazione**: solo soft-delete (flag) o hard delete? Audit richiede
   soft, semplicità richiede hard.

---

## Note tecniche

- App Django: `attivita/` (nuova).
- Convenzione codici minuscoli (cfr. `CLAUDE.md`).
- Pattern UI standard per liste/tabelle (`CLAUDE.md` → paginazione 50,
  filtri sotto header, ordinamento server-side con whitelist).
- Editing inline con HTMX (pattern `_cell_display.html` / `_cell_edit.html`
  di `anagrafica`).
- Test factory in `attivita/factories.py` allineato allo stile esistente.
