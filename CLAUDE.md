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
