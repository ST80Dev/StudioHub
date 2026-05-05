# Avanzamento contabilità — tenuta contabilità interna

Primo controllo della sezione di sidebar **"Avanzamento operativo"**. Traccia
mese per mese lo stato di registrazione contabile dei clienti per cui lo studio
elabora la contabilità internamente. È **separato** dal catalogo `Adempimento`.

> "Avanzamento operativo" è il contenitore in sidebar destinato a raccogliere
> più controlli di avanzamento su lavorazioni che non ha senso modellare come
> adempimenti veri e propri. Questa nota copre il **primo** di quei controlli
> (l'avanzamento contabilità). Altri controlli verranno aggiunti come note
> sorelle in `docs/sezioni/`.

> Sostituisce e raffina il design preliminare di `ProgressioneContabilita` /
> `ProgressioneContabilitaLog` in `ROADMAP.md`. Le tabelle e la formula qui
> riportate sono quelle di riferimento.

---

## Scopo

- Rispondere in qualunque momento a "a che punto siamo con la registrazione
  della prima nota / acquisti / vendite del cliente X?".
- Calcolare un **indice ponderato di avanzamento** dello studio per anno
  fiscale.
- Permettere confronti **anno su anno** allo stesso punto del calendario, via
  snapshot cristallizzati a richiesta dell'utente.
- Tenere nota dell'ultimo incontro col cliente in cui è stato visionato il
  bilancio del mese.

## Clienti inclusi (filtro AND)

- `Anagrafica.contabilita == INTERNA`
- `Anagrafica.regime_contabile IN (semplificata, ordinaria)`
- `Anagrafica.tipo_soggetto IN (ditta_individuale, societa_persone, srl)`

Esclusi di default: contabilità esterna, forfettari (no registri IVA da
tenere), enti, altre forme societarie non gestite internamente. La griglia di
visualizzazione è raggruppata per `tipo_soggetto + regime_contabile` (DI ord,
DI sempl, SP, SRL, …) come nello schema cartaceo storico dello studio.

## Modello dati

### `anagrafica.AvanzamentoMensile`

Stato corrente. Una riga per (cliente, anno, mese). Creazione **lazy**: la
riga nasce alla prima interazione (toggle o data VB).

| Campo            | Tipo                | Note                                |
|------------------|---------------------|-------------------------------------|
| `anagrafica`     | FK Anagrafica PROT. |                                     |
| `anno`           | int                 |                                     |
| `mese`           | int 1-12            |                                     |
| `pn_inserita`    | bool default False  | Prima Nota                          |
| `ra_inserito`    | bool default False  | Reg. Acquisti                       |
| `rv_inserito`    | bool default False  | Reg. Vendite                        |
| `vb_data`        | date null           | data incontro / visione bilancio    |
| `updated_at`     | auto                |                                     |
| `updated_by`     | FK UtenteStudio null|                                     |
| UNIQUE           | (anagrafica, anno, mese) |                                |

### `anagrafica.AvanzamentoSnapshot`

Cristallizzazione manuale on-demand. Una riga per snapshot etichettato.
Immutabile dopo la creazione.

| Campo              | Tipo            | Note                              |
|--------------------|-----------------|-----------------------------------|
| `etichetta`        | string          | default "Chiusura <mese> <anno>"  |
| `creato_il`        | datetime auto   |                                   |
| `creato_da`        | FK UtenteStudio |                                   |
| `anno_riferimento` | int             | anno fiscale fotografato          |
| `note`             | text blank      |                                   |

### `anagrafica.AvanzamentoSnapshotRiga`

Foto di una singola cella matrice all'istante dello snapshot. Lo snapshot
include **tutta la popolazione clienti** che rientrava nei filtri al momento
della cristallizzazione (anche righe vuote), per non falsare i denominatori
del calcolo % al confronto storico.

| Campo                          | Tipo            | Note                          |
|--------------------------------|-----------------|-------------------------------|
| `snapshot`                     | FK AvanzamentoSnapshot CASCADE |                |
| `anagrafica`                   | FK Anagrafica PROTECT |                         |
| `mese`                         | int 1-12        |                               |
| `pn_inserita`                  | bool            |                               |
| `ra_inserito`                  | bool            |                               |
| `rv_inserito`                  | bool            |                               |
| `vb_data`                      | date null       |                               |
| `peso_contabilita_at_snapshot` | int 1-6         | peso congelato all'istante    |
| `denominazione_at_snapshot`    | string          | denormalizzato per storia     |

UNIQUE `(snapshot, anagrafica, mese)`.

## Profilo cliente — campi richiesti / da rivedere

Su `anagrafica.Anagrafica`:

- `peso_contabilita`: **int 1-6** (era `PositiveSmallInt default 0` nel ROADMAP
  originario). Range valido 1-6 per i clienti che rientrano nella sezione,
  `null` o 0 = "non classificato". Migrazione necessaria con validatore di
  range. Rappresenta la **complessità della prima nota** del cliente
  (1 = banale, 6 = molto complessa).

## Calcolo % avanzamento ponderato

Solo l'inserimento di **Prima Nota** entra nella formula. RA, RV e VB sono
tracciati per uso operativo ma **non** pesano sulla %.

```
numeratore   = Σ_clienti ( peso_contabilita × num_mesi_con_pn_inserita )
denominatore = Σ_clienti ( peso_contabilita × 12 )
% avanzamento = numeratore / denominatore × 100
```

- Calcolato per anno fiscale, sull'intera popolazione che rientra nei filtri.
- Se `peso_contabilita` è null o 0, il cliente è escluso dal calcolo (ma resta
  visibile in matrice con badge "peso da assegnare").
- Su uno snapshot la stessa formula gira sui dati congelati (incluso il
  `peso_contabilita_at_snapshot`).

## Cristallizzazione (snapshot)

- **Manuale on-demand**: pulsante "Cristallizza situazione attuale" in testa
  alla matrice. Cadenza tipica attesa: fine mese o entro il 5 del mese
  successivo.
- L'azione crea un `AvanzamentoSnapshot` + N righe `AvanzamentoSnapshotRiga`
  (una per ogni coppia cliente × mese 1-12 della popolazione corrente).
- Etichetta libera, suggerita di default `"Chiusura <mese precedente> <anno>"`.
- Gli snapshot sono **immutabili** in lettura; non si modificano né si
  ricalcolano. Se serve una correzione, si crea un nuovo snapshot.
- Eliminazione consentita solo a un ruolo amministrativo (TBD in fase
  permessi).

## UI matrice — voce "Avanzamento operativo" in sidebar

Layout di riferimento (modello: foglio Excel storico dello studio).

Colonne fisse a sinistra:

- Ragione sociale
- Periodicità IVA (M / T)
- Peso contabilità (1-6) — derivato da anagrafica
- Conteggio mesi PN inseriti / 12 (calcolato live)
- Addetto contabile (derivato da assegnazioni anagrafica)

Colonne mensili (12), per ciascun mese 4 sotto-celle:

- **PN** — checkbox toggle
- **RA** — checkbox toggle
- **RV** — checkbox toggle
- **VB** — input date inline (può restare vuoto)

Comportamento:

- Toggle e date applicati con HTMX patch sul singolo campo, ottimistico.
- Raggruppamento righe per `tipo_soggetto + regime_contabile` con
  intestazioni di sezione (DI ord., DI sempl., SP, SRL, …).
- Selettore **anno** in alto (default = anno corrente).
- Selettore **vista snapshot** (dropdown con elenco snapshot dell'anno
  selezionato, "live" come prima opzione). Quando si guarda uno snapshot la
  matrice è read-only e legge da `AvanzamentoSnapshotRiga`.
- Footer / banner header: % avanzamento ponderata cumulativa della vista
  corrente (live o snapshot).
- Pulsante "Cristallizza situazione attuale" visibile solo in vista live.

## Note operative / vincoli da ricordare

- **Peso contabilità**: caratteristica del cliente, non del mese. Cambia
  raramente; le modifiche impattano i calcoli da quel momento in poi. Gli
  snapshot fotografano il peso al momento della cristallizzazione, quindi
  confronti storici restano coerenti anche se il peso viene successivamente
  rivisto.
- **Forfettari** esclusi (non hanno registri IVA da tenere).
- **Enti** esclusi finché lo studio non gestisce internamente quel caso.
- **Cambio contabilità ESTERNA → INTERNA** in corso d'anno: i mesi precedenti
  restano vuoti (PN/RA/RV false, VB null). Niente back-fill automatico.
- **Cambio INTERNA → ESTERNA** in corso d'anno: il cliente esce dalla matrice
  live, ma le righe pregresse e gli snapshot storici restano consultabili.
- I numeri tipo "PN = mesi×peso" mostrati nel foglio cartaceo storico sono
  calcolati on-the-fly, **non** persistiti.

## TODO implementativi (Fase 2-bis)

- [ ] Migrazione `Anagrafica.peso_contabilita` a `IntegerField` con
      validatore range 1-6, null=True.
- [ ] Modelli `AvanzamentoMensile`, `AvanzamentoSnapshot`,
      `AvanzamentoSnapshotRiga`.
- [ ] Vista matrice live con HTMX patch per toggle PN/RA/RV e input date VB.
- [ ] Vista matrice in modalità snapshot (read-only).
- [ ] Pulsante cristallizzazione + transazione che popola le righe snapshot.
- [ ] Selettore anno e selettore snapshot.
- [ ] Calcolo % ponderata in template tag o context processor.
- [ ] Voce sidebar "Avanzamento operativo" separata dagli adempimenti.
- [ ] Seed demo: alcuni mesi spuntati a campione su clienti `is_demo` con
      `contabilita=INTERNA`.
- [ ] Policy `flush_demo`: `AvanzamentoMensile` e snapshot delle righe demo
      vanno via in cascade dall'`Anagrafica` (radice già flaggata).

## Domande aperte (da rivedere prima dell'implementazione)

- Politica permessi su cristallizzazione ed eliminazione snapshot (decisione
  rinviata a Fase 5 — Permessi e audit).
- Se serva un'esportazione CSV/Excel della matrice (probabile in Fase 6 —
  Integrazioni, niente di urgente).
- Notifica/alert se a fine mese la % rimane sotto soglia configurabile —
  rinviato a fasi successive.
