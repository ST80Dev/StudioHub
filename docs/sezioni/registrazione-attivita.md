# Sezione "Registrazione attività" — timesheet operativo dello studio

Sezione dedicata in sidebar, **separata** sia dal catalogo `Adempimento` sia
da "Avanzamento operativo". Ogni addetto dello studio registra le proprie
attività quotidiane (cliente, categoria, durata, descrizione). Le ore
alimentano analisi di carico, marginalità per cliente e timesheet personale.

> File di lavoro / note di progettazione. Le scelte già confermate sono
> indicate come **DEC**; quelle ancora aperte come **OPEN**.

---

## Scopo (cosa serve)

- **Rendicontazione interna**: chi ha fatto cosa, quanto, su quale cliente
  o attività trasversale.
- **Marginalità per cliente**: il cliente ha un **budget orario** annuo
  (totale e/o spalmato per categoria di attività); confrontiamo consumo
  reale vs budget e ne ricaviamo valore economico via costo/tariffa oraria.
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

**DEC** — gli addetti hanno **una sola area principale + override
eventuale** per singola attività. Refactor proposto:

- `area_principale` = FK `AreaAziendale` (nullable in transitorio).
- `aree` resta come M2M ma diventa l'insieme delle aree "compatibili"
  (default = area principale + eventuali aggiuntive utilizzabili come
  override). Vincolo: `area_principale ∈ aree`.

In UI di inserimento attività, il campo **Area** è precompilato con
`area_principale` ma selezionabile fra `aree` quando l'addetto sta facendo
un'attività con un "cappello" diverso (es. addetto di Area B che fa
attività di Area C con costo/tariffa diversi).

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

#### `attivita.CategoriaAttivita`

Macro-categoria di attività registrabile (es. "Contabilità", "Dichiarativi
periodici", "Consulenza", "Bilancio", "Studio interno / formazione").

Distinta da `TipoAdempimentoCatalogo`: una categoria è più ampia di un
singolo tipo e include anche attività che non corrispondono a un
adempimento (consulenza ad hoc, riunioni interne, formazione).

| Campo | Tipo | Note |
|---|---|---|
| `codice` | slug lowercase | identificativo stabile |
| `denominazione` | string | label estesa |
| `abbreviazione` | string max 8 | per badge/sidebar/report compatti |
| `richiede_cliente` | bool | False per "interne studio" (formazione, riunioni) |
| `attivo` | bool | per dismettere senza eliminare |
| `ordine` | int | per ordinamento UI |

Editabile da admin Django e da UI Configurazione.

#### `attivita.RegistrazioneAttivita`

La riga di timesheet vera e propria. Una per ogni "blocco" di lavoro
registrato.

| Campo | Tipo | Note |
|---|---|---|
| `utente` | FK UtenteStudio PROTECT | autore |
| `area` | FK AreaAziendale PROTECT | snapshot dell'area al momento; default = `utente.area_principale`, override consentito fra `utente.aree` |
| `data` | date | giorno dell'attività |
| `durata_minuti` | int positivo | granularità: minuti, UI in formato `H:MM` |
| `cliente` | FK Anagrafica PROTECT nullable | obbligatorio se `categoria.richiede_cliente=True` |
| `categoria` | FK CategoriaAttivita PROTECT | |
| `adempimento` | FK adempimenti.Adempimento PROTECT nullable | aggancio opzionale a un adempimento specifico |
| `descrizione` | text | descrizione libera di cosa è stato fatto |
| `costo_orario_snapshot` | Decimal | valore al momento dell'inserimento (snapshot per marginalità storiche) |
| `tariffa_oraria_snapshot` | Decimal | idem |
| `costo_valorizzato` | Decimal calcolato | `durata × costo_orario_snapshot / 60` |
| `valore_valorizzato` | Decimal calcolato | `durata × tariffa_oraria_snapshot / 60` |
| `created_at` / `updated_at` | auto | |
| `updated_by` | FK UtenteStudio nullable | per audit |

Indici: `(utente, data)`, `(cliente, data)`, `(categoria, data)`,
`(adempimento)`.

Vincoli:
- `durata_minuti > 0`.
- Se `categoria.richiede_cliente`, allora `cliente NOT NULL`.
- Se `adempimento` non nullo, allora `adempimento.anagrafica == cliente`.

Snapshot di costo/tariffa: si fa al **save** (sia create che update), per
mantenere allineato il valore alla configurazione corrente. Se in futuro
si introduce la storicizzazione (Opzione B sopra), si legge dalla tabella
storica per la `data` dell'attività e si elimina lo snapshot in colonna.

#### `attivita.BudgetCliente`

Monte ore preventivato per un cliente in un anno. **DEC**: i tre livelli
coesistono.

| Campo | Tipo | Note |
|---|---|---|
| `cliente` | FK Anagrafica | |
| `anno` | int | anno fiscale |
| `utente` | FK UtenteStudio nullable | NULL = budget aggregato cliente, non per addetto |
| `categoria` | FK CategoriaAttivita nullable | NULL = totale, non per categoria |
| `area` | FK AreaAziendale nullable | per ragionare in € sui livelli che non vincolano l'utente (vedi nota) |
| `ore` | Decimal | ore preventivate |

Unique: `(cliente, anno, utente, categoria)` (con NULL come "qualunque").

Livelli (DEC):

1. **addetto × cliente** (`utente` valorizzato, `categoria` NULL): "Mario
   farà 40h sul cliente Rossi nel 2026".
2. **addetto × cliente × categoria** (entrambi valorizzati): "Mario farà
   30h di Contabilità e 10h di Dichiarativi su Rossi".
3. **addetto × categoria** (`utente` valorizzato, `cliente` NULL,
   `categoria` valorizzato): "Mario farà 200h di Formazione nel 2026"
   (trasversale, non legato a uno specifico cliente).

Convenzione di coerenza: se per un cliente esistono budget a livello 2
(categoria), il budget cliente totale è la somma; lato UI si verifica e
si segnala se il totale "manuale" (livello 1) diverge.

Conversione in € a runtime: `ore × tariffa_oraria` dell'area dell'utente
(se `utente` valorizzato) o dell'area del livello (`area` o quella
prevalente del cliente). Il valore non viene memorizzato per non doverlo
ricalcolare alle modifiche tariffa.

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

## Categoria attività vs tipo adempimento

Sono concetti diversi e tutti e due servono. Mapping logico:

- **CategoriaAttivita** è la dimensione di analisi del lavoro (cosa
  stiamo facendo: contabilità, consulenza, formazione, ecc.).
- **TipoAdempimentoCatalogo** è il "pezzo formale" su cui si lavora (LIPE,
  Bilancio UE, F24).

Una stessa attività può appartenere a una categoria e — facoltativamente
— a uno specifico adempimento. Esempi:
- "1h di Contabilità su Rossi, generica" → categoria=Contabilità,
  cliente=Rossi, adempimento=NULL.
- "0:30 di Contabilità su Rossi, per LIPE Q2 2026" → categoria=Contabilità,
  cliente=Rossi, adempimento=Adempimento(tipo=LIPE, Q2 2026).
- "2h di Formazione interna" → categoria=Formazione, cliente=NULL,
  adempimento=NULL.

**OPEN** — vincolo soft fra categoria e tipi di adempimento? Es.
"Categoria Contabilità è coerente con adempimenti di tipo F24, LIPE, …",
solo come warning UI? Per la v1 si può rinviare.

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

- Durata sempre in formato `H:MM` (input parsabile da "1,5" → 1:30 e
  "90m" → 1:30, oltre al formato canonico "1:30").
- Salvataggio HTMX, conferma toast inline, ritorno alla vista corrente
  con stato preservato.
- Validazione lato server di area ∈ aree dell'utente.

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
- Confronto vs budget personale (somma budget livello 1 dei clienti +
  budget trasversale livello 3): ore attese vs consumate.

### v2 — Scheda cliente con consumo

Sezione nella scheda cliente:
- Budget totale (annuo) per anno corrente vs consumo.
- Dettaglio per categoria (se esistono budget livello 2).
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
- `/configurazione/attivita/budget/<cliente_id>` — impostazione budget
  multi-livello del cliente per l'anno corrente.

---

## Fasi di sviluppo proposte

### Fase 0 — Scaffolding

- App `attivita` + migrazioni base.
- Estensione `AreaAziendale` (`costo_orario`, `tariffa_oraria`).
- Estensione `UtenteStudio.area_principale`.
- Seed minimo: 3-4 categorie base.

### Fase 1 — Inserimento

- Modello `CategoriaAttivita` + `RegistrazioneAttivita`.
- Modale globale di inserimento (1).
- Pagina diario giornaliero (2).
- Pagina "le mie attività" con paginazione e filtri (pattern
  `lista_clienti`).

### Fase 2 — Budget e timesheet

- Modello `BudgetCliente` + UI configurazione.
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
