from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from anagrafica import choices_labels as _choices_labels
from anagrafica.models import (
    Anagrafica,
    AnagraficaReferenteStudio,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    RuoloReferenteStudio,
)

from . import stati as _stati
from .columns import get_columns_for_tipo
from .models import (
    Adempimento,
    StatoAdempimento,
    StatoAdempimentoTipo,
    TipoAdempimentoCatalogo,
    tipi_applicabili,
)
from .services import conta_obsoleti, sincronizza_adempimenti


def _global_stati_choices() -> list[tuple[str, str]]:
    """Choices (codice, denominazione) per la vista generica adempimenti.

    Deduplica per codice. Usata solo dal dropdown della lista generica
    (non LIPE), che non ha un tipo specifico di riferimento.
    """
    seen: dict[str, str] = {}
    for codice, den in (
        StatoAdempimentoTipo.objects.filter(attivo=True)
        .values_list("codice", "denominazione")
        .order_by("livello", "denominazione")
    ):
        seen.setdefault(codice, den)
    return list(seen.items())


@login_required
def lista_adempimenti(request):
    qs = Adempimento.objects.filter(is_deleted=False).select_related(
        "anagrafica", "responsabile", "tipo"
    )

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(anagrafica__denominazione__icontains=q)
            | Q(anagrafica__codice_interno__icontains=q)
        )

    tipo_id = request.GET.get("tipo", "")
    if tipo_id.isdigit():
        qs = qs.filter(tipo_id=int(tipo_id))

    anno_fiscale = request.GET.get("anno_fiscale", "")
    if anno_fiscale.isdigit():
        qs = qs.filter(anno_fiscale=int(anno_fiscale))

    stato = request.GET.get("stato", "")
    # Filtro stato sulla vista generica: accetta qualsiasi codice presente
    # in almeno un set di tipo (non vincolato a un tipo specifico).
    if stato and StatoAdempimentoTipo.objects.filter(codice=stato).exists():
        qs = qs.filter(stato=stato)

    esecutore = request.GET.get("esecutore", "")
    if esecutore.isdigit():
        qs = qs.filter(responsabile_id=int(esecutore))

    referente_ruolo = request.GET.get("ref_ruolo", "")
    referente_utente = request.GET.get("ref_utente", "")
    if (
        referente_ruolo in RuoloReferenteStudio.values
        and referente_utente.isdigit()
    ):
        sub = AnagraficaReferenteStudio.objects.filter(
            anagrafica=OuterRef("anagrafica"),
            utente_id=int(referente_utente),
            ruolo=referente_ruolo,
            data_inizio__year__lte=OuterRef("anno_fiscale"),
        ).filter(
            Q(data_fine__isnull=True)
            | Q(data_fine__year__gte=OuterRef("anno_fiscale"))
        )
        qs = qs.filter(Exists(sub))

    qs = qs.order_by("data_scadenza", "anagrafica__denominazione")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "adempimenti": page.object_list,
        "q": q,
        "tipo_id": tipo_id,
        "anno_fiscale": anno_fiscale,
        "stato": stato,
        "esecutore": esecutore,
        "tipi": TipoAdempimentoCatalogo.objects.filter(attivo=True),
        # Vista generica: dropdown unione di tutti i codici stato presenti
        # in qualsiasi tipo (deduplicati). Per la lista LIPE dedicata si usa
        # invece il set per-tipo.
        "stati": _global_stati_choices(),
        "ruoli": RuoloReferenteStudio.choices,
        "totale": paginator.count,
    }
    template = (
        "adempimenti/_list_rows.html"
        if request.htmx
        else "adempimenti/list.html"
    )
    return render(request, template, context)


@login_required
def dettaglio_adempimento(request, pk: int):
    adempimento = get_object_or_404(
        Adempimento.objects.select_related("anagrafica", "responsabile", "tipo"),
        pk=pk,
        is_deleted=False,
    )
    steps = adempimento.steps_completati.select_related("step", "completato_da").order_by("step__ordine")
    return render(
        request,
        "adempimenti/detail.html",
        {
            "adempimento": adempimento,
            "steps": steps,
            "addetti": adempimento.referenti_contabilita_cliente,
            "consulenti": adempimento.referenti_consulenza_cliente,
        },
    )


# ---------------------------------------------------------------------------
# Vista dedicata: Liquidazione IVA Trimestrale (LIPE)
# ---------------------------------------------------------------------------
#
# Pattern UI standard (vedi CLAUDE.md):
#  - selettore anno + selettore periodo (Q1..Q4) in alto
#  - paginazione 50/pagina con paginator in alto e in basso
#  - filtri per colonna sotto le intestazioni (whitelistati)
#  - ordinamento per colonna con whitelist server-side
#  - editing inline cella-per-cella su stato/data_invio/protocollo/note
#  - bulk update sullo stato per le righe selezionate
#  - "+ Aggiungi cliente" per inserire manualmente una riga (es. cliente
#    non incluso dalle regole, da marcare "FANNO_LORO")

# Anni proposti nel selettore: corrente +/- 2.
def _anni_disponibili():
    oggi = date.today()
    return [oggi.year + d for d in range(-2, 3)]


PERIODI = [(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4")]


# Whitelist colonne sortabili per la lista LIPE.
LIPE_SORTABLE = {
    "anagrafica__denominazione",
    "anagrafica__codice_interno",
    "anagrafica__codice_multi",
    "anagrafica__contabilita",
    "anagrafica__regime_contabile",
    "anagrafica__periodicita_iva",
    "data_scadenza",
    "stato",
    "data_invio",
    "protocollo_invio",
}

# Campi modificabili inline + bulk per la vista LIPE.
# Lo stato e' un select con choices DINAMICHE dal catalogo del tipo (vedi
# `_tipo_inline_meta`). Sentinelle ammesse per "tipo widget":
#  - "select_stato": dropdown popolato dal catalogo stati del tipo
#  - "date"/"text": campi liberi
LIPE_INLINE_FIELDS = {
    "stato":            ("select_stato", None),
    "data_invio":       ("date",         None),
    "protocollo_invio": ("text",         None),
    "note":             ("text",         None),
}
# Per la bulk update: stato (validato contro il catalogo del tipo a runtime)
# + protocollo_invio (intero salvato come stringa).
LIPE_BULK_FIELDS = {
    "stato": "stato",
    "protocollo_invio": int,
}


def _get_tipo_con_vista(catalogo_id: int):
    """Recupera un tipo del catalogo che abbia la vista dedicata abilitata.

    Identifica il tipo per PK (non per codice) così il codice resta libero
    di essere rinominato dall'utente. Al momento la vista dedicata supporta
    solo periodicità trimestrale (layout Q1..Q4); rifiutiamo qui i tipi che
    sono stati marcati `ha_vista_dedicata` ma con periodicità diversa.
    """
    tipo = get_object_or_404(
        TipoAdempimentoCatalogo,
        pk=catalogo_id,
        ha_vista_dedicata=True,
    )
    if tipo.periodicita != "trimestrale":
        # Guardia: oggi il layout Q1..Q4 è l'unico supportato. Quando verrà
        # generalizzato a mensile/annuale, rimuovere o ampliare questo check.
        return get_object_or_404(
            TipoAdempimentoCatalogo,
            pk=0,  # forza 404
        )
    return tipo


def legacy_lipe_redirect(request):
    """Redirect 301 dei vecchi URL `/adempimenti/liquidazione-iva-trimestrale/`
    al nuovo URL basato su PK.

    Mantiene la compatibilità con bookmark e link salvati. Sceglie il primo
    tipo con `ha_vista_dedicata=True` e periodicità trimestrale (in pratica:
    LIPE). Se non lo trova, 404.
    """
    tipo = TipoAdempimentoCatalogo.objects.filter(
        ha_vista_dedicata=True, periodicita="trimestrale", attivo=True,
    ).order_by("ordine", "denominazione").first()
    if tipo is None:
        return get_object_or_404(TipoAdempimentoCatalogo, pk=0)
    qs = request.META.get("QUERY_STRING", "")
    url = reverse("adempimenti:lista_tipo", args=[tipo.pk])
    if qs:
        url = f"{url}?{qs}"
    return redirect(url, permanent=True)


def _tipo_inline_meta(field: str, tipo_id: int | None = None):
    """Metadati per il form di edit inline di una cella della vista tipo.

    Per `widget == 'select_stato'` la lista di scelte viene popolata
    dinamicamente dal catalogo stati del tipo (richiede `tipo_id`).
    """
    if field not in LIPE_INLINE_FIELDS:
        return None
    widget, _legacy = LIPE_INLINE_FIELDS[field]
    meta = {"name": field, "widget": widget, "choices": []}
    if widget == "select_stato" and tipo_id is not None:
        meta["choices"] = _stati.choices(tipo_id)
    return meta


@login_required
def lista_tipo(request, catalogo_id: int):
    """Lista dedicata per un tipo di adempimento con `ha_vista_dedicata=True`.

    Oggi serve esclusivamente i tipi trimestrali (layout Q1..Q4); il primo
    cliente reale è la Liquidazione IVA Trimestrale (LIPE). L'URL identifica
    il tipo per PK, quindi il codice del catalogo è libero di essere
    rinominato.

    Selettore `anno` (default: anno corrente) e `periodo` (Q1..Q4, default Q1).
    Caso speciale: `periodo=anno` → vista aggregata 1 riga per cliente con
    4 celle Q1..Q4. Vedi `_render_lipe_anno`.
    """
    tipo = _get_tipo_con_vista(catalogo_id)

    oggi = date.today()
    try:
        anno = int(request.GET.get("anno") or oggi.year)
    except ValueError:
        anno = oggi.year

    periodo_raw = request.GET.get("periodo") or "1"
    if periodo_raw == "anno":
        return _render_lipe_anno(request, tipo, anno)

    try:
        periodo = int(periodo_raw)
    except ValueError:
        periodo = 1
    if periodo not in (1, 2, 3, 4):
        periodo = 1

    base_qs = Adempimento.objects.filter(
        is_deleted=False, tipo=tipo, anno_fiscale=anno, periodo=periodo,
    ).select_related("anagrafica", "responsabile")

    qs = base_qs

    # Filtri colonna (whitelist)
    f_denom = (request.GET.get("f_denominazione") or "").strip()
    if f_denom:
        qs = qs.filter(anagrafica__denominazione__icontains=f_denom)

    f_codice = (request.GET.get("f_codice") or "").strip()
    if f_codice:
        qs = qs.filter(anagrafica__codice_interno__icontains=f_codice)

    f_multi = (request.GET.get("f_multi") or "").strip()
    if f_multi:
        qs = qs.filter(anagrafica__codice_multi__icontains=f_multi)

    f_contab = request.GET.get("f_contab") or ""
    if f_contab in _choices_labels.get_values("contabilita", include_inactive=True):
        qs = qs.filter(anagrafica__contabilita=f_contab)

    f_regime = request.GET.get("f_regime") or ""
    if f_regime in _choices_labels.get_values("regime_contabile", include_inactive=True):
        qs = qs.filter(anagrafica__regime_contabile=f_regime)

    f_iva = request.GET.get("f_iva") or ""
    if f_iva in _choices_labels.get_values("periodicita_iva", include_inactive=True):
        qs = qs.filter(anagrafica__periodicita_iva=f_iva)

    f_stato = request.GET.get("f_stato") or ""
    # Validazione contro il catalogo stati del tipo (non piu' enum hardcoded)
    stati_tipo = _stati.stati_di_tipo(tipo.id)
    codici_tipo = {s.codice for s in stati_tipo}
    if f_stato in codici_tipo:
        qs = qs.filter(stato=f_stato)

    f_protocollo = (request.GET.get("f_protocollo") or "").strip()
    if f_protocollo:
        qs = qs.filter(protocollo_invio__icontains=f_protocollo)

    # Ordinamento
    sort = request.GET.get("sort", "anagrafica__denominazione")
    sort_field = sort.lstrip("-")
    if sort_field not in LIPE_SORTABLE:
        sort = "anagrafica__denominazione"
        sort_field = "anagrafica__denominazione"
    qs = qs.order_by(sort, "anagrafica__denominazione")

    # Totali per stato (sull'intero set non filtrato dell'anno/periodo).
    # Itera sul catalogo stati del tipo (non piu' enum hardcoded).
    counts_raw = base_qs.values("stato").annotate(n=Count("id"))
    counts = {row["stato"]: row["n"] for row in counts_raw}
    totali = []
    for s in stati_tipo:
        totali.append({
            "value": s.codice,
            "label": s.denominazione,
            "count": counts.get(s.codice, 0),
            "lavorabile": s.lavorabile,
        })
    totale_lavorabile = sum(c["count"] for c in totali if c["lavorabile"])
    totale_complessivo = sum(c["count"] for c in totali)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))

    # Stato della lista per il bottone "Crea elenco" / "Aggiorna elenco".
    lista_vuota = not base_qs.exists()

    # Scadenza unica del periodo (mostrata nel banner in testa alla pagina:
    # tutte le righe dello stesso (tipo, anno, periodo) hanno la stessa data
    # di scadenza, quindi non serve ripeterla in colonna).
    scad = tipo.scadenze.filter(periodo=periodo).first()
    scadenza_periodo = scad.calcola_data_scadenza(anno) if scad else None

    # Righe oggi obsolete (cliente non piu' applicabile alle regole) — solo
    # in stati lavorabili. Lista breve, niente paginazione: se cresce molto
    # significa che il profilo fiscale dei clienti cambia spesso e va gestito.
    obsoleti = list(conta_obsoleti(tipo, anno, periodo))

    context = {
        "tipo": tipo,
        "anno": anno,
        "periodo": periodo,
        "anni": _anni_disponibili(),
        "periodi": PERIODI,
        "page": page,
        "page_obj": page,
        "righe": page.object_list,
        # filtri (per i widget)
        "f_denominazione": f_denom,
        "f_codice": f_codice,
        "f_multi": f_multi,
        "f_contab": f_contab,
        "f_regime": f_regime,
        "f_iva": f_iva,
        "f_stato": f_stato,
        "f_protocollo": f_protocollo,
        # opzioni dei select
        "stati": [(s.codice, s.denominazione) for s in stati_tipo],
        "regimi": _choices_labels.get_choices("regime_contabile"),
        "periodicita": _choices_labels.get_choices("periodicita_iva"),
        "contabilita_choices": _choices_labels.get_choices("contabilita"),
        # sort
        "sort": sort,
        "sort_field": sort_field,
        "sort_dir": "desc" if sort.startswith("-") else "asc",
        # totali
        "totali": totali,
        "totale_lavorabile": totale_lavorabile,
        "totale_complessivo": totale_complessivo,
        # azioni "Crea/Aggiorna elenco" + segnalazione obsoleti
        "lista_vuota": lista_vuota,
        "obsoleti": obsoleti,
        # scadenza unica del periodo (banner in testa)
        "scadenza_periodo": scadenza_periodo,
    }
    template = (
        "adempimenti/_lipe_rows.html"
        if request.htmx
        else "adempimenti/lipe_list.html"
    )
    return render(request, template, context)


def _apply_column_filter(qs, code: str, raw: str):
    """Applica un filtro sul queryset Adempimento per il codice colonna dato.

    Whitelist dei codici supportati. Codici sconosciuti sono no-op.
    Per i campi a choices, valida `raw` contro i valori ammessi.
    """
    if code == "cliente":
        return qs.filter(anagrafica__denominazione__icontains=raw)
    if code == "codice_interno":
        return qs.filter(anagrafica__codice_interno__icontains=raw)
    if code == "codice_multi":
        return qs.filter(anagrafica__codice_multi__icontains=raw)
    if code == "codice_fiscale":
        return qs.filter(anagrafica__codice_fiscale__icontains=raw)
    if code == "partita_iva":
        return qs.filter(anagrafica__partita_iva__icontains=raw)
    if code == "tipo_soggetto":
        if raw in _choices_labels.get_values("tipo_soggetto", include_inactive=True):
            return qs.filter(anagrafica__tipo_soggetto=raw)
        return qs
    if code == "regime_contabile":
        if raw in _choices_labels.get_values("regime_contabile", include_inactive=True):
            return qs.filter(anagrafica__regime_contabile=raw)
        return qs
    if code == "tipo_contabilita":
        if raw in _choices_labels.get_values("contabilita", include_inactive=True):
            return qs.filter(anagrafica__contabilita=raw)
        return qs
    if code == "periodicita_iva":
        if raw in _choices_labels.get_values("periodicita_iva", include_inactive=True):
            return qs.filter(anagrafica__periodicita_iva=raw)
        return qs
    if code == "referente_contab":
        return qs.filter(
            anagrafica__referenti_studio__ruolo=RuoloReferenteStudio.ADDETTO_CONTABILITA,
            anagrafica__referenti_studio__utente__last_name__icontains=raw,
        ).distinct()
    if code == "referente_consul":
        return qs.filter(
            anagrafica__referenti_studio__ruolo=RuoloReferenteStudio.RESPONSABILE_CONSULENZA,
            anagrafica__referenti_studio__utente__last_name__icontains=raw,
        ).distinct()
    if code == "stato":
        # Validazione "soft": basta che il codice esista in almeno un
        # set per-tipo (la lista generica non e' tipo-specifica).
        if raw and StatoAdempimentoTipo.objects.filter(codice=raw).exists():
            return qs.filter(stato=raw)
        return qs
    if code == "note":
        return qs.filter(note__icontains=raw)
    return qs


def _render_lipe_anno(request, tipo, anno):
    """Vista aggregata anno intero: 1 riga per cliente, 4 celle Q1..Q4.

    Mostra ogni cliente che ha almeno una riga in uno dei trimestri
    dell'anno. Le celle dei trimestri senza riga restano vuote (placeholder
    "—"), senza far pensare che il cliente sia "cessato": e' solo che per
    quel trimestre non risultava applicabile o non e' ancora stata generata
    la riga. Cliccando una cella si va al dettaglio del singolo periodo per
    poterla editare.

    Le colonne anagrafiche mostrate prima delle 4 celle Q1..Q4 sono guidate
    dal sistema standard (vedi `adempimenti.columns`). Le colonne per-periodo
    (`stato`, `note`) sono escluse in questa vista aggregata.
    """
    from django.db.models import Prefetch
    from anagrafica.models import AnagraficaReferenteStudio

    # Referenti dello studio attivi nell'anno: prefetch filtrato.
    refs_qs = (
        AnagraficaReferenteStudio.objects
        .filter(
            data_inizio__lte=date(anno, 12, 31),
        )
        .filter(
            Q(data_fine__isnull=True) | Q(data_fine__gte=date(anno, 1, 1))
        )
        .select_related("utente")
        .order_by("ruolo", "-principale", "data_inizio")
    )

    base_qs = (
        Adempimento.objects.filter(
            is_deleted=False, tipo=tipo, anno_fiscale=anno,
        )
        .select_related("anagrafica", "responsabile")
        .prefetch_related(
            Prefetch("anagrafica__referenti_studio", queryset=refs_qs)
        )
        .order_by("anagrafica__denominazione", "periodo")
    )

    # Colonne standard configurate per la vista anno (sempre senza per-periodo).
    columns = get_columns_for_tipo(tipo, vista="anno", exclude_per_period=True)

    # Filtri applicati dinamicamente in base alle colonne attive.
    # Niente filtro stato qui: una riga annuale aggrega 4 potenziali stati.
    qs = base_qs
    filtri_attivi: dict[str, str] = {}
    for col in columns:
        if not col.filter_param:
            continue
        raw = (request.GET.get(col.filter_param) or "").strip()
        if not raw:
            continue
        filtri_attivi[col.filter_param] = raw
        qs = _apply_column_filter(qs, col.code, raw)

    # Sort whitelist costruita dalle colonne attive (campi sort_field disponibili).
    sortable = {c.sort_field for c in columns if c.sort_field}
    sort_raw = (request.GET.get("sort") or "").strip()
    sort_field = sort_raw.lstrip("-")
    if sort_field in sortable:
        qs = qs.order_by(sort_raw, "anagrafica__denominazione", "periodo")

    # Aggrega per anagrafica: { anagrafica_id: {"anag": <Anagrafica>,
    #                                            "righe": {1: <Adempimento>, 2: ..., 3: ..., 4: ...}}}
    aggregato = {}
    for r in qs:
        slot = aggregato.setdefault(
            r.anagrafica_id,
            {"anag": r.anagrafica, "righe": {}},
        )
        if r.periodo:
            slot["righe"][r.periodo] = r
    clienti_aggregati = sorted(
        aggregato.values(), key=lambda x: x["anag"].denominazione
    )

    # Totali aggregati: somma per ogni stato su tutti i Q dell'anno.
    counts = {}
    for r in base_qs:
        counts[r.stato] = counts.get(r.stato, 0) + 1
    totali = []
    for s in _stati.stati_di_tipo(tipo.id):
        totali.append({
            "value": s.codice,
            "label": s.denominazione,
            "count": counts.get(s.codice, 0),
            "lavorabile": s.lavorabile,
        })
    totale_lavorabile = sum(c["count"] for c in totali if c["lavorabile"])
    totale_complessivo = sum(c["count"] for c in totali)

    paginator = Paginator(clienti_aggregati, 50)
    page = paginator.get_page(request.GET.get("page"))

    lista_vuota = not base_qs.exists()
    # Obsoleti su tutti i periodi dell'anno
    obsoleti = list(conta_obsoleti(tipo, anno, periodo=None))

    return render(
        request,
        "adempimenti/lipe_anno.html",
        {
            "tipo": tipo,
            "anno": anno,
            "anni": _anni_disponibili(),
            "periodi": PERIODI,
            "page": page,
            "page_obj": page,
            "clienti_aggregati": page.object_list,
            # nuovo sistema colonne
            "columns": columns,
            "sort": sort_raw,
            # totali
            "totali": totali,
            "totale_lavorabile": totale_lavorabile,
            "totale_complessivo": totale_complessivo,
            # azioni
            "lista_vuota": lista_vuota,
            "obsoleti": obsoleti,
        },
    )


@login_required
def tipo_inline_edit_form(request, catalogo_id: int, pk: int, field: str):
    riga = get_object_or_404(
        Adempimento.objects.select_related("anagrafica"),
        pk=pk, tipo_id=catalogo_id, is_deleted=False,
    )
    meta = _tipo_inline_meta(field, tipo_id=catalogo_id)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    return render(
        request,
        "adempimenti/_lipe_cell_edit.html",
        {"r": riga, "field": field, "meta": meta, "catalogo_id": catalogo_id},
    )


@login_required
@require_POST
def tipo_inline_save(request, catalogo_id: int, pk: int, field: str):
    riga = get_object_or_404(
        Adempimento.objects.select_related("anagrafica"),
        pk=pk, tipo_id=catalogo_id, is_deleted=False,
    )
    meta = _tipo_inline_meta(field, tipo_id=catalogo_id)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    raw = (request.POST.get("value") or "").strip()

    if meta["widget"] == "select_stato":
        # Valida contro il catalogo stati DEL TIPO della riga, non un enum.
        if raw and _stati.stato_by_codice(riga.tipo_id, raw) is None:
            return HttpResponseBadRequest("Stato non valido per questo tipo.")
    elif meta["widget"] == "date":
        if raw and len(raw) != 10:
            return HttpResponseBadRequest("Data non valida.")

    if field == "data_invio":
        setattr(riga, field, raw or None)
    else:
        setattr(riga, field, raw)
    riga.save(update_fields=[field, "updated_at"])
    return render(
        request,
        "adempimenti/_lipe_cell_display.html",
        {"r": riga, "field": field, "catalogo_id": catalogo_id},
    )


@login_required
@require_POST
def tipo_bulk_update(request, catalogo_id: int):
    tipo = _get_tipo_con_vista(catalogo_id)
    field = request.POST.get("field", "")
    value = (request.POST.get("value") or "").strip()
    ids = request.POST.getlist("ids")

    if field not in LIPE_BULK_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso per la modifica bulk.")

    spec = LIPE_BULK_FIELDS[field]
    # `protocollo_invio`: numero intero non negativo, salvato come stringa
    # nel CharField del modello. `stato` (spec == "stato"): valida contro
    # il catalogo del tipo LIPE.
    if spec is int:
        try:
            n = int(value)
        except ValueError:
            return HttpResponseBadRequest("Numero non valido.")
        if n < 0:
            return HttpResponseBadRequest("Il numero deve essere ≥ 0.")
        db_value = str(n)
        human_value = db_value
    elif spec == "stato":
        stato_obj = _stati.stato_by_codice(tipo.id, value)
        if stato_obj is None:
            return HttpResponseBadRequest("Stato non valido per questo tipo.")
        db_value = value
        human_value = stato_obj.denominazione
    else:
        return HttpResponseBadRequest("Configurazione del campo bulk non valida.")

    back_url = reverse("adempimenti:lista_tipo", args=[tipo.pk])
    if not ids:
        messages.warning(request, "Nessuna riga selezionata.")
        return redirect(back_url + "?" + (request.POST.get("qs") or ""))

    updated = (
        Adempimento.objects.filter(pk__in=ids, tipo=tipo, is_deleted=False)
        .update(**{field: db_value})
    )
    messages.success(
        request,
        f"{updated} righe aggiornate: {field} → {human_value}.",
    )
    qs = request.POST.get("qs", "")
    return redirect(back_url + ("?" + qs if qs else ""))


@login_required
@require_POST
def tipo_aggiungi_cliente(request, catalogo_id: int):
    """Crea manualmente una riga per un cliente (anche non applicabile).

    POST: anagrafica_id, anno, periodo, stato (default da_fare).
    Idempotente sul unique (anagrafica, tipo, anno, periodo).
    """
    tipo = _get_tipo_con_vista(catalogo_id)
    try:
        anagrafica_id = int(request.POST.get("anagrafica_id") or 0)
        anno = int(request.POST.get("anno") or 0)
        periodo = int(request.POST.get("periodo") or 0)
    except ValueError:
        return HttpResponseBadRequest("Parametri non validi.")
    if periodo not in (1, 2, 3, 4):
        return HttpResponseBadRequest("Periodo non valido.")
    stato = request.POST.get("stato") or _stati.stato_default(tipo.id)
    # Valida contro il set per-tipo (catalogo DB).
    stato_obj = _stati.stato_by_codice(tipo.id, stato)
    if stato_obj is None:
        return HttpResponseBadRequest("Stato non valido.")

    anag = get_object_or_404(Anagrafica, pk=anagrafica_id, is_deleted=False)

    scad = tipo.scadenze.filter(periodo=periodo).first()
    data_scadenza = scad.calcola_data_scadenza(anno) if scad else None

    riga, created = Adempimento.objects.get_or_create(
        anagrafica=anag, tipo=tipo, anno_fiscale=anno, periodo=periodo,
        defaults={"data_scadenza": data_scadenza, "stato": stato},
    )
    sigla = tipo.etichetta_breve or tipo.denominazione
    if created:
        messages.success(
            request,
            f"Aggiunta riga {sigla} per {anag.denominazione} "
            f"({anno} Q{periodo}) — stato {stato_obj.denominazione}.",
        )
    else:
        messages.info(
            request,
            f"Riga già presente per {anag.denominazione} ({anno} Q{periodo}).",
        )

    return redirect(
        reverse("adempimenti:lista_tipo", args=[tipo.pk])
        + f"?anno={anno}&periodo={periodo}"
    )


@login_required
def tipo_search_clienti(request, catalogo_id: int):
    """Endpoint HTMX di autocompletamento clienti per il modale di aggiunta."""
    # Il catalogo_id non viene usato per filtrare i clienti (si possono
    # aggiungere anche clienti oggi non applicabili), ma è nel path per
    # coerenza di scoping e per eventuali estensioni future.
    _ = _get_tipo_con_vista(catalogo_id)
    q = (request.GET.get("q") or "").strip()
    risultati = []
    if len(q) >= 2:
        risultati = list(
            Anagrafica.objects.filter(is_deleted=False)
            .filter(
                Q(denominazione__icontains=q)
                | Q(codice_interno__icontains=q)
                | Q(codice_fiscale__icontains=q)
                | Q(partita_iva__icontains=q)
            )
            .order_by("denominazione")[:20]
        )
    return render(
        request,
        "adempimenti/_lipe_search_results.html",
        {"risultati": risultati, "q": q},
    )


@login_required
@require_POST
def tipo_sincronizza(request, catalogo_id: int):
    """Crea / aggiorna l'elenco per (tipo, anno, periodo).

    Stessa funzione usata dal management command `genera_adempimenti`:
    aggiunge le righe mancanti per i clienti oggi applicabili (idempotente).
    Non tocca mai righe esistenti. Mostra un toast con il riepilogo.
    """
    tipo = _get_tipo_con_vista(catalogo_id)
    try:
        anno = int(request.POST.get("anno") or 0)
        # `periodo` opzionale: se vuoto, sincronizza tutti i periodi dell'anno.
        periodo_raw = request.POST.get("periodo") or ""
        solo_periodo = int(periodo_raw) if periodo_raw else None
    except ValueError:
        return HttpResponseBadRequest("Parametri non validi.")

    if solo_periodo is not None and solo_periodo not in (1, 2, 3, 4):
        return HttpResponseBadRequest("Periodo non valido.")

    risultato = sincronizza_adempimenti(
        tipo, anno, solo_periodo=solo_periodo,
    )

    scope = (
        f"{anno} Q{solo_periodo}"
        if solo_periodo is not None
        else f"tutti i periodi {anno}"
    )
    parti = [f"{risultato.creati} aggiunti"]
    if risultato.gia_esistenti:
        parti.append(f"{risultato.gia_esistenti} già presenti")
    if risultato.obsoleti_pks:
        parti.append(f"{len(risultato.obsoleti_pks)} non più applicabili")
    messages.success(
        request, f"Sincronizzazione {scope}: " + ", ".join(parti) + "."
    )

    qs = request.POST.get("qs", "")
    back_url = reverse("adempimenti:lista_tipo", args=[tipo.pk])
    return redirect(back_url + ("?" + qs if qs else ""))


@login_required
@require_POST
def tipo_rimuovi_riga(request, catalogo_id: int, pk: int):
    """Soft-delete di una riga.

    Usata dal pannello "Non più applicabili" per ripulire l'elenco senza
    perdere lo storico (la riga resta in DB con is_deleted=True).
    """
    riga = get_object_or_404(
        Adempimento, pk=pk, tipo_id=catalogo_id, is_deleted=False,
    )
    riga.is_deleted = True
    riga.save(update_fields=["is_deleted", "updated_at"])
    messages.success(
        request,
        f"Riga rimossa: {riga.anagrafica.denominazione} "
        f"({riga.anno_fiscale} Q{riga.periodo or '—'}).",
    )
    qs = request.POST.get("qs", "")
    back_url = reverse("adempimenti:lista_tipo", args=[catalogo_id])
    return redirect(back_url + ("?" + qs if qs else ""))
