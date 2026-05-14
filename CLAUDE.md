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

## Convenzione codici TextChoices

Regola: **i codici nel DB sono sempre in minuscolo, senza spazi**
(es. `interna`, `ordinario`, `srl`, `profex`). Sono identificatori
semantici stabili, *non* etichette: l'aspetto visivo si gestisce
con le label, non rinominando i codici.

3 livelli di etichetta su `TextChoiceLabel` (modificabili da admin a
`/admin/anagrafica/textchoicelabel/`):

1. **`codice`** — identificativo stabile per DB, URL, regole
   (`regime_contabile = 'forfettario'`). Non rinominare salvo migration.
2. **`label_micro`** — sigla 3 char per celle dense / badge
   (`INT`, `EST`, `SRL`). Configurabile; fallback automatico alle prime 3
   lettere upper di `label` se vuoto. Uso template:
   `{{ codice|micro_label:'<field>' }}`.
3. **`label`** — etichetta estesa per form e dropdown filtri
   (`Interna (tenuta dallo studio)`). Uso template (statico):
   `{{ obj.get_<field>_display }}`, oppure (dinamico):
   `{{ codice|label_for:'<field>' }}`.

Helper Python: `anagrafica.choices_labels.get_label(field, codice)`,
`get_micro_label(field, codice)`, `get_choices(field)`,
`get_choices_micro(field)`.

Quando si aggiunge un nuovo campo TextChoices al modello:
- definirlo con codici minuscoli;
- aggiungerlo a `_get_textchoices()` in `anagrafica/choices_labels.py`;
- aggiungere una migration RunPython che popola `TextChoiceLabel` con
  `(field, codice, label, label_micro, ordine)` per ciascun valore;
- aggiungerlo a `TextChoiceLabel.FIELD_CHOICES` in `models.py`.

## Stati adempimento (catalogo per-tipo)

Ogni `TipoAdempimentoCatalogo` ha il SUO set di stati di avanzamento
(tabella `StatoAdempimentoTipo`). Non sono piu' un TextChoices fisso. Il
set iniziale viene copiato da uno **Standard globale**
(`StatoAdempimentoStandard`, editabile da admin Django) alla creazione del
tipo (via signal `post_save`).

Tre proprietà chiave per ogni stato:

- **`lavorabile`** (bool) — se True, l'adempimento conta nel "lavoro
  residuo". Cambiarlo permette di marcare nuovi stati terminali (es.
  "archiviato") senza modifiche al codice.
- **`livello`** (0..100) — progressione. 0 = non in scope (es. fanno_loro,
  no_dati), 100 = completato (inviato). Usato anche come sort.
- **`iniziale_default`** (bool) — uno solo a True per set: stato di
  partenza per nuovi adempimenti di quel tipo.

Stati copiati dallo Standard hanno `e_predefinito=True` e **non si
possono eliminare** (modificabili sì). Per "nasconderli" si usa il
flag `attivo=False`. Stati custom aggiunti dopo (e_predefinito=False)
sono eliminabili se nessun adempimento li referenzia.

Helper Python: `adempimenti.stati.stati_di_tipo(tipo_id)`,
`stato_by_codice(tipo_id, codice)`, `codici_lavorabili(tipo_id)`,
`stato_default(tipo_id)`, `choices(tipo_id)`. Cache module-level
invalidata via signal su save/delete.

Template tag per il badge: `{% load adempimenti_extras %}` poi
`{% stato_badge adempimento %}` (preferito) o
`{% stato_badge_by_codice tipo_id codice %}`. Il render legge
denominazione + colore dal catalogo per-tipo: niente più
if/elif hardcoded per codice in `_stato_badge.html`.

Editabile da:
- admin Django: `/admin/adempimenti/statoadempimentostandard/` per il set
  globale, e inline "Stati (per tipo)" sul `TipoAdempimentoCatalogo`;
- UI dedicata: `/configurazione/tipi/<id>/?tab=stati`.

NB: modificare lo Standard **non** propaga retroattivamente sugli stati
gia' copiati nei tipi (per non sovrascrivere personalizzazioni). Impatta
solo le copie alla creazione di un nuovo tipo.

## Pattern UI per liste/tabelle

Quando si costruisce una nuova lista/tabella di record (clienti,
adempimenti, scadenze, sessioni di import, ecc.) seguire **sempre** questi
pattern standard, già implementati su `anagrafica/lista_clienti` come
riferimento:

### Paginazione (obbligatoria)
- 50 record/pagina di default, `django.core.paginator.Paginator`.
- Render con `{% include "partials/_paginator.html" with page_obj=page_obj %}`
  (il partial è generico, preserva tutti i query param correnti e supporta
  prev/next + salto rapido a pagina N).
- **Sempre due posizionamenti**: in alto a destra (accanto al titolo o alle
  azioni primarie tipo "+ Nuovo") e in fondo alla tabella. Così l'utente
  non deve scorrere a fine pagina per cambiare pagina.
- La view deve passare `page_obj` (alias di `page`) al contesto.

### Filtri per colonna (sotto le intestazioni)
- Riga di filtri sotto l'header della tabella, con `<input>` testo per i
  campi liberi e `<select>` per i campi a choices.
- Tutti gli input hanno attributo `form="filters-form"` e puntano a un
  `<form method="get" id="filters-form">` posto sopra la tabella (così la
  riga filtri non deve stare DENTRO la tabella e si evitano problemi di
  nesting `<form>` con il form bulk).
- I `<select>` di filtro hanno `onchange="this.form.submit()"` per submit
  automatico; gli `<input>` testuali si confermano con Invio.
- Convenzione query string: `?f_<campo>=<valore>`. Lato view, mappa
  esplicita di whitelist (vedi `lista_clienti.filter_text`).

### Ordinamento per colonna (header sortabili)
- Header come link, partial riusabile `anagrafica/_sort_header.html`
  (parametri: `label`, `field`).
- Query string: `?sort=<field>` (asc) o `?sort=-<field>` (desc); click sulla
  stessa colonna toggla la direzione.
- **Whitelist server-side obbligatoria**: `SORTABLE = {...}` nella view per
  prevenire ORM injection su campi non previsti.
- Indicatore visivo: ↑ / ↓ sulla colonna attiva, ↕ neutro sulle altre.

### Editing inline cella-per-cella
- Pattern click-to-edit con HTMX: il `<td>` in display ha
  `hx-get` → fragment edit; il form in edit ha `hx-post` → fragment display.
- Whitelist server-side dei campi modificabili (in `anagrafica.views`:
  `_INLINE_FIELDS`).
- Partial riusabili: `_cell_display.html` + `_cell_edit.html`. Per applicare
  lo stesso pattern a un altro modello, replicare: una whitelist, 2 view
  (form GET + save POST), 2 partial parametrizzati su `c` + `field`.
- I campi a choices Django **devono** essere `<select>` chiusi (mai input
  testuali), per evitare la persistenza di valori non validi.

### Modifica di massa (bulk)
- Selezione multipla con checkbox per riga, "seleziona tutto" nell'header.
- Pattern: `<form method="post">` esterno che wrappa la tabella, barra
  azione con `<select campo> + <select valore> + bottone "Applica a N"`.
- **Solo campi a choices** sono ammessi alla modifica bulk (no free-text).
- View con whitelist `_BULK_FIELDS` mappata a `TextChoices` Django.
- Preservare i filtri correnti al ritorno: campo hidden `qs` con
  `{{ request.GET.urlencode }}`, redirect a `?<qs>` dopo l'update.

### Header e dipendenze già pronte
- `htmx.org@1.9.12` e `alpinejs@3.14.1` sono caricati globalmente in
  `templates/base.html`. Non serve re-includerli.
- Template tag `get_attr` (`anagrafica.templatetags.anagrafica_extras`) per
  accesso dinamico ad attributi nei template (usato dai partial inline).
