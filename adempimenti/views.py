from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from anagrafica.models import (
    Anagrafica,
    AnagraficaReferenteStudio,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    RuoloReferenteStudio,
)

from .models import (
    Adempimento,
    STATI_LAVORABILI,
    STATI_NON_LAVORABILI,
    StatoAdempimento,
    TipoAdempimentoCatalogo,
    tipi_applicabili,
)


# Codice del tipo "Liquidazione IVA Trimestrale" (seed migration 0006).
CODICE_LIPE = "liquidazione-iva-trimestrale"


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
    if stato in StatoAdempimento.values:
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
        "stati": StatoAdempimento.choices,
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
            "addetti": adempimento.addetti_contabilita_cliente,
            "consulenti": adempimento.responsabili_consulenza_cliente,
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
LIPE_INLINE_FIELDS = {
    "stato":            ("select", StatoAdempimento),
    "data_invio":       ("date",   None),
    "protocollo_invio": ("text",   None),
    "note":             ("text",   None),
}
LIPE_BULK_FIELDS = {
    "stato": StatoAdempimento,
}


def _get_tipo_lipe():
    return get_object_or_404(TipoAdempimentoCatalogo, codice=CODICE_LIPE)


def _lipe_inline_meta(field: str):
    if field not in LIPE_INLINE_FIELDS:
        return None
    widget, choices = LIPE_INLINE_FIELDS[field]
    return {"name": field, "widget": widget, "choices": choices}


@login_required
def lista_lipe(request):
    """Lista dedicata alla Liquidazione IVA Trimestrale.

    Filtra implicitamente per `tipo=liquidazione-iva-trimestrale`. Selettore
    `anno` (default: anno corrente) e `periodo` (Q1..Q4, default Q1).
    """
    tipo = _get_tipo_lipe()

    oggi = date.today()
    try:
        anno = int(request.GET.get("anno") or oggi.year)
    except ValueError:
        anno = oggi.year
    try:
        periodo = int(request.GET.get("periodo") or 1)
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
    if f_contab in GestioneContabilita.values:
        qs = qs.filter(anagrafica__contabilita=f_contab)

    f_regime = request.GET.get("f_regime") or ""
    if f_regime in RegimeContabile.values:
        qs = qs.filter(anagrafica__regime_contabile=f_regime)

    f_iva = request.GET.get("f_iva") or ""
    if f_iva in PeriodicitaIVA.values:
        qs = qs.filter(anagrafica__periodicita_iva=f_iva)

    f_stato = request.GET.get("f_stato") or ""
    if f_stato in StatoAdempimento.values:
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

    # Totali per stato (sull'intero set non filtrato dell'anno/periodo)
    counts_raw = (
        base_qs.values("stato").annotate(n=Count("id"))
    )
    counts = {row["stato"]: row["n"] for row in counts_raw}
    totali = []
    for val, label in StatoAdempimento.choices:
        totali.append({
            "value": val,
            "label": label,
            "count": counts.get(val, 0),
            "lavorabile": val in STATI_LAVORABILI,
        })
    totale_lavorabile = sum(
        c["count"] for c in totali if c["lavorabile"]
    )
    totale_complessivo = sum(c["count"] for c in totali)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))

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
        "stati": StatoAdempimento.choices,
        "regimi": RegimeContabile.choices,
        "periodicita": PeriodicitaIVA.choices,
        "contabilita_choices": GestioneContabilita.choices,
        # sort
        "sort": sort,
        "sort_field": sort_field,
        "sort_dir": "desc" if sort.startswith("-") else "asc",
        # totali
        "totali": totali,
        "totale_lavorabile": totale_lavorabile,
        "totale_complessivo": totale_complessivo,
    }
    template = (
        "adempimenti/_lipe_rows.html"
        if request.htmx
        else "adempimenti/lipe_list.html"
    )
    return render(request, template, context)


@login_required
def lipe_inline_edit_form(request, pk: int, field: str):
    meta = _lipe_inline_meta(field)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    riga = get_object_or_404(
        Adempimento.objects.select_related("anagrafica"),
        pk=pk, is_deleted=False,
    )
    return render(
        request,
        "adempimenti/_lipe_cell_edit.html",
        {"r": riga, "field": field, "meta": meta},
    )


@login_required
@require_POST
def lipe_inline_save(request, pk: int, field: str):
    meta = _lipe_inline_meta(field)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    riga = get_object_or_404(
        Adempimento.objects.select_related("anagrafica"),
        pk=pk, is_deleted=False,
    )
    raw = (request.POST.get("value") or "").strip()

    if meta["widget"] == "select":
        choices = meta["choices"]
        if raw and raw not in choices.values:
            return HttpResponseBadRequest("Valore non ammesso per il campo.")
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
        {"r": riga, "field": field},
    )


@login_required
@require_POST
def lipe_bulk_update(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    ids = request.POST.getlist("ids")

    if field not in LIPE_BULK_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso per la modifica bulk.")
    choices_cls = LIPE_BULK_FIELDS[field]
    if value not in choices_cls.values:
        return HttpResponseBadRequest("Valore non ammesso per il campo.")
    if not ids:
        messages.warning(request, "Nessuna riga selezionata.")
        return redirect(reverse("adempimenti:lipe") + "?" + (request.POST.get("qs") or ""))

    updated = (
        Adempimento.objects.filter(pk__in=ids, is_deleted=False)
        .update(**{field: value})
    )
    messages.success(
        request,
        f"{updated} righe aggiornate: {field} → {choices_cls(value).label}.",
    )
    qs = request.POST.get("qs", "")
    return redirect(reverse("adempimenti:lipe") + ("?" + qs if qs else ""))


@login_required
@require_POST
def lipe_aggiungi_cliente(request):
    """Crea manualmente una riga LIPE per un cliente (anche non applicabile).

    POST: anagrafica_id, anno, periodo, stato (default da_fare).
    Idempotente sul unique (anagrafica, tipo, anno, periodo).
    """
    tipo = _get_tipo_lipe()
    try:
        anagrafica_id = int(request.POST.get("anagrafica_id") or 0)
        anno = int(request.POST.get("anno") or 0)
        periodo = int(request.POST.get("periodo") or 0)
    except ValueError:
        return HttpResponseBadRequest("Parametri non validi.")
    if periodo not in (1, 2, 3, 4):
        return HttpResponseBadRequest("Periodo non valido.")
    stato = request.POST.get("stato") or StatoAdempimento.DA_FARE
    if stato not in StatoAdempimento.values:
        return HttpResponseBadRequest("Stato non valido.")

    anag = get_object_or_404(Anagrafica, pk=anagrafica_id, is_deleted=False)

    scad = tipo.scadenze.filter(periodo=periodo).first()
    data_scadenza = scad.calcola_data_scadenza(anno) if scad else None

    riga, created = Adempimento.objects.get_or_create(
        anagrafica=anag, tipo=tipo, anno_fiscale=anno, periodo=periodo,
        defaults={"data_scadenza": data_scadenza, "stato": stato},
    )
    if created:
        messages.success(
            request,
            f"Aggiunta riga LIPE per {anag.denominazione} "
            f"({anno} Q{periodo}) — stato {StatoAdempimento(stato).label}.",
        )
    else:
        messages.info(
            request,
            f"Riga già presente per {anag.denominazione} ({anno} Q{periodo}).",
        )

    return redirect(
        reverse("adempimenti:lipe") + f"?anno={anno}&periodo={periodo}"
    )


@login_required
def lipe_search_clienti(request):
    """Endpoint HTMX di autocompletamento clienti per il modale di aggiunta."""
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
