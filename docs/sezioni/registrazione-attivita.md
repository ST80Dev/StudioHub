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

Voce del catalogo attività registrabili. **Gerarchia a tre livelli**:
`AreaAziendale` (top) → `Attivita` padre → `Attivita` figlia
(sub-attività, opzionale, **massimo 1 livello di figli**).

Le sub-attività sono uno strato di dettaglio opzionale che l'utente può
sfruttare per puntualizzare meglio cosa ha fatto (tipicamente
corrispondono alle **fasi di una checklist** del relativo adempimento,
quando esiste). Sono sempre opzionali: la `RegistrazioneAttivita` può
puntare al padre (utente non vuole dettagliare) o a una figlia (utente
vuole il dettaglio).

Esempi (indicativi, da affinare con l'utente):

- Area **Contabilità**:
  - "Registrazione FE" → figlie: "FE ricevute", "FE emesse",
    "FE corrispettivi".
  - "Quadratura banche" (senza figlie).
- Area **Consulenza Ordinaria**:
  - "Predisposizione LIPE" → figlie: "Estrazione dati", "Controllo
    coerenza", "Invio telematico".
  - "Consulenza fiscale telefonica" (senza figlie).
- Area **Consulenza Straordinaria**:
  - "Operazione straordinaria" → figlie: "Analisi preliminare",
    "Predisposizione atti", "Adempimenti post".
- Area **Attività Interne**:
  - "Formazione", "Riunione studio" (tipicamente senza figlie).

**Costo/tariffa**: NON sono campi di `Attivita`, vengono presi
dall'`area` di appartenenza al momento della registrazione (vedi
snapshot in `RegistrazioneAttivita`). I figli **ereditano l'area del
padre** (vincolo): non si può cambiare area su una sub-attività.

| Campo | Tipo | Note |
|---|---|---|
| `codice` | slug lowercase | identificativo stabile |
| `parent` | FK self Attivita PROTECT nullable | NULL = attività padre (livello 1); valorizzato = sub-attività (livello 2) |
| `area` | FK AreaAziendale PROTECT | per i figli: deve essere = `parent.area` |
| `denominazione` | string | label estesa |
| `abbreviazione` | string max 8 blank | per badge/report compatti |
| `richiede_cliente` | bool default True | False per attività interne; sui figli si eredita di default ma override consentito |
| `attivo` | bool default True | per dismettere senza eliminare |
| `ordine` | int | ordinamento all'interno del livello (fra padri di un'area, o fra figli di un padre) |

Vincoli:

- **Profondità max 2**: se `parent` è valorizzato, allora
  `parent.parent IS NULL` (un figlio non può avere a sua volta figli).
- Se `parent` valorizzato, `area == parent.area`.
- Unique consigliato: `(area, parent, codice)` o `(area, codice)` se
  vogliamo `codice` unico tra padre+figli della stessa area.

Editabile da admin Django e da UI Configurazione (`/configurazione/
attivita/catalogo`) con vista ad albero raggruppata per area.

**OPEN** — `codice` univoco globale, per area, o per (area, parent)?
Suggerito: `(area, codice)` unique a livello di area (padri e figli non
si chiamano mai uguale dentro la stessa area).

**OPEN — collegamento a `ChecklistStep`** (fase 2): le sub-attività
spesso replicano la struttura dei `ChecklistStep` per tipo adempimento.
Si potrebbe aggiungere una FK opzionale `checklist_step` per mappare la
sub-attività a uno step di un tipo adempimento, così che registrare ore
sulla sub-attività possa anche "spuntare" lo step della checklist
sull'adempimento collegato. Per la v1 non si fa: si parte solo con
gerarchia padre/figlio libera, l'integrazione con la checklist arriva
dopo se serve.

#### `attivita.RegistrazioneAttivita`

La riga di timesheet vera e propria. Una per ogni "blocco" di lavoro
registrato.

| Campo | Tipo | Note |
|---|---|---|
| `utente` | FK UtenteStudio PROTECT | autore (chi ha svolto l'attività) |
| `attivita` | FK Attivita PROTECT | l'attività svolta; può essere un padre (livello 1) o una sub-attività (livello 2), a scelta dell'utente |
| `area_valorizzazione` | FK AreaAziendale PROTECT | snapshot: **= attivita.area al momento del save** (uguale per padre e figlia), NON area dell'utente |
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
- L'utente NON sceglie l'area dell'attività: viene derivata dall'attività
  selezionata. Mostrato in form come label info ("Area di valorizzazione:
  Consulenza Ordinaria — 50€/h costo, 75€/h tariffa") per chiarezza.
- **Selezione attività con sub-attività opzionale**: il form mostra un
  primo select con le attività padre (raggruppate per area). Se
  l'attività scelta ha figli, compare un secondo select opzionale con le
  sub-attività ("nessun dettaglio" come opzione di default). L'utente
  può lasciare il livello padre o scendere alla sub a sua scelta.

---

## Reportistica (priorità per release)

DEC v1: **scheda addetto / timesheet personale**.

**Aggregazione sub-attività**: tutti i report di default aggregano al
livello **attività padre** (livello 1). Il dettaglio per sub-attività
compare solo in viste esplicitamente richieste tramite un toggle / link
"mostra dettaglio sub-attività" o in report dedicati. Logica
implementativa: per ogni `RegistrazioneAttivita` si guarda
`attivita.parent or attivita` per ricondurre al padre quando serve
aggregare.

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

- Modello `Attivita` (con `parent` self-FK, max 2 livelli) +
  `RegistrazioneAttivita`.
- UI di configurazione catalogo attività ad albero (per area).
- Modale globale di inserimento (1), con select padre + select sub
  opzionale.
- Pagina diario giornaliero (2).
- Pagina "le mie attività" con paginazione e filtri (pattern
  `lista_clienti`); aggregazione default al livello padre + toggle
  "mostra sub-attività".

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
5. **Vincolo `Attivita` ↔ tipo adempimento**: warning soft o nulla
   nell'autocomplete adempimento in base all'attività scelta?
6. **Parser durata**: input tollerante a "1.5" / "1,5". Altri formati
   ammessi (es. "90m", "1h30")? Default no.
7. **Granularità budget livello 2**: addetto×area (proposto) vs
   addetto×Attivita. Da decidere nella sessione dedicata al budget.
8. **Link sub-Attivita ↔ ChecklistStep**: in fase 2 mappare le
   sub-attività ai checklist step dei tipi adempimento, per spuntare
   automaticamente lo step quando si registrano ore? Forma del mapping
   (1:1, 1:N, M:N)?
9. **Codice Attivita**: unique per `(area, codice)` o solo `(codice)`
   globale?
10. **Adempimenti collegati**: filtraggio nell'autocomplete per cliente
    + periodo corrente è sufficiente, o serve anche per "scaduti" /
    "futuri"?
11. **Eliminazione**: solo soft-delete (flag) o hard delete? Audit richiede
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
