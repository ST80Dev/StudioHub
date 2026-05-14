from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest

from . import choices_labels as _choices_labels
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.utils.text import slugify

from .forms import AnagraficaForm
from .models import (
    Anagrafica,
    Categoria,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    StatoAnagrafica,
    TipoSoggetto,
)


@login_required
def lista_clienti(request):
    """Lista densa dei clienti, con ricerca libera, filtri per colonna,
    ordinamento per colonna e paginazione.

    Pattern UI standard (vedi CLAUDE.md "Pattern UI per liste/tabelle"):
    - paginazione server-side (50/pagina) con partial `_paginator.html`
    - filtri per colonna come query string GET (whitelistati)
    - ordinamento `?sort=<field>` o `?sort=-<field>` con whitelist server-side
    """
    queryset = Anagrafica.objects.filter(is_deleted=False)

    # Ricerca libera generale (resta per retrocompatibilità: dal pulsante "Filtra")
    q = request.GET.get("q", "").strip()
    if q:
        queryset = queryset.filter(
            Q(denominazione__icontains=q)
            | Q(codice_interno__icontains=q)
            | Q(codice_fiscale__icontains=q)
            | Q(partita_iva__icontains=q)
        )

    # Filtri per colonna. Mappa nome_query -> (lookup ORM, tipo).
    # tipo: "text" -> icontains; "exact" -> exact (per choices/select).
    filter_text = {
        "f_codice": "codice_interno__icontains",
        "f_denominazione": "denominazione__icontains",
        "f_cf": "codice_fiscale__icontains",
        "f_piva": "partita_iva__icontains",
    }
    for qkey, lookup in filter_text.items():
        v = (request.GET.get(qkey) or "").strip()
        if v:
            queryset = queryset.filter(**{lookup: v})

    # Filtri per choices: usano la query-key del campo direttamente (back-compat con `tipo`/`stato`).
    f_tipo = request.GET.get("f_tipo") or request.GET.get("tipo") or ""
    if f_tipo in TipoSoggetto.values:
        queryset = queryset.filter(tipo_soggetto=f_tipo)

    f_stato = request.GET.get("f_stato") or request.GET.get("stato") or ""
    if f_stato in StatoAnagrafica.values:
        queryset = queryset.filter(stato=f_stato)

    f_regime = request.GET.get("f_regime", "")
    if f_regime in RegimeContabile.values:
        queryset = queryset.filter(regime_contabile=f_regime)

    f_iva = request.GET.get("f_iva", "")
    if f_iva in PeriodicitaIVA.values:
        queryset = queryset.filter(periodicita_iva=f_iva)

    f_contab = request.GET.get("f_contab", "")
    if f_contab in GestioneContabilita.values:
        queryset = queryset.filter(contabilita=f_contab)

    # Filtro "Da completare": anagrafiche con denominazione o tipo_soggetto
    # vuoti (tipicamente create da import permissivo). Utile per identificare
    # in fretta cosa va sistemato.
    f_incompleto = request.GET.get("f_incompleto", "")
    if f_incompleto == "1":
        queryset = queryset.filter(Q(denominazione="") | Q(tipo_soggetto=""))

    # Conteggio anagrafiche incomplete (sempre disponibile per il chip).
    n_incomplete = (
        Anagrafica.objects.filter(is_deleted=False)
        .filter(Q(denominazione="") | Q(tipo_soggetto=""))
        .count()
    )

    # Ordinamento. Whitelist dei campi sortabili (sicurezza: no order_by
    # su qualsiasi attributo, evita raw SQL injection di lookup esotici).
    SORTABLE = {
        "codice_interno", "denominazione", "tipo_soggetto",
        "codice_fiscale", "partita_iva", "regime_contabile",
        "periodicita_iva", "contabilita", "stato",
    }
    sort = request.GET.get("sort", "denominazione")
    sort_field = sort.lstrip("-")
    if sort_field not in SORTABLE:
        sort = "denominazione"
        sort_field = "denominazione"

    paginator = Paginator(queryset.order_by(sort, "denominazione"), 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "page_obj": page,  # alias per il partial _paginator.html
        "clienti": page.object_list,
        "q": q,
        # filtri correnti (per i widget di header)
        "f_codice": request.GET.get("f_codice", ""),
        "f_denominazione": request.GET.get("f_denominazione", ""),
        "f_cf": request.GET.get("f_cf", ""),
        "f_piva": request.GET.get("f_piva", ""),
        "f_tipo": f_tipo,
        "f_stato": f_stato,
        "f_regime": f_regime,
        "f_iva": f_iva,
        "f_contab": f_contab,
        "f_incompleto": f_incompleto,
        "n_incomplete": n_incomplete,
        # back-compat (sidebar/altri callers che ancora usano i nomi vecchi)
        "tipo": f_tipo,
        "stato": f_stato,
        # opzioni dei select
        # Choices override-aware (label modificabili da admin via TextChoiceLabel)
        "tipi_soggetto": _choices_labels.get_choices("tipo_soggetto"),
        "stati": _choices_labels.get_choices("stato"),
        "regimi": _choices_labels.get_choices("regime_contabile"),
        "periodicita": _choices_labels.get_choices("periodicita_iva"),
        "contabilita_choices": _choices_labels.get_choices("contabilita"),
        "totale": paginator.count,
        # sort corrente per indicatori UI
        "sort": sort,
        "sort_field": sort_field,
        "sort_dir": "desc" if sort.startswith("-") else "asc",
    }
    template = (
        "anagrafica/_list_rows.html" if request.htmx else "anagrafica/list.html"
    )
    return render(request, template, context)


@login_required
def dettaglio_cliente(request, pk: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    return render(
        request,
        "anagrafica/detail.html",
        {
            "cliente": cliente,
            "referenti_attivi": cliente.referenti_studio.filter(
                data_fine__isnull=True
            ).select_related("utente"),
            "legami": cliente.legami_da.select_related("anagrafica_collegata"),
            "categorie_assegnate": cliente.categorie.filter(attiva=True),
        },
    )


# ---------------------------------------------------------------------------
# Categorie (tag) sull'anagrafica
# ---------------------------------------------------------------------------
#
# UI a chip con autocompletamento HTMX. L'utente digita; mostriamo le categorie
# esistenti che fanno match (auto-proposizione dei valori già usati) + opzione
# "crea nuova" se nessun match esatto. Click → assegna al cliente. La rimozione
# è il click sulla X del chip già presente.

def _render_categorie_box(request, cliente: Anagrafica):
    return render(
        request,
        "anagrafica/_categorie_box.html",
        {"cliente": cliente, "categorie_assegnate": cliente.categorie.filter(attiva=True)},
    )


@login_required
def categorie_search(request, pk: int):
    """Suggerimenti di categorie per autocompletamento sull'anagrafica."""
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    q = (request.GET.get("q") or "").strip()
    suggerimenti = []
    esatto = None
    if q:
        gia_assegnate_ids = list(cliente.categorie.values_list("pk", flat=True))
        suggerimenti = list(
            Categoria.objects.filter(attiva=True)
            .filter(
                Q(denominazione__icontains=q) | Q(slug__icontains=slugify(q))
            )
            .exclude(pk__in=gia_assegnate_ids)
            .order_by("denominazione")[:15]
        )
        esatto = Categoria.objects.filter(
            slug=slugify(q)
        ).first()
    return render(
        request,
        "anagrafica/_categorie_suggest.html",
        {
            "cliente": cliente,
            "q": q,
            "suggerimenti": suggerimenti,
            "esatto": esatto,
        },
    )


@login_required
@require_POST
def categorie_assegna(request, pk: int):
    """Assegna una categoria al cliente. Crea nuova se 'q' non matcha alcun slug."""
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    cat_id = request.POST.get("categoria_id")
    nuovo_nome = (request.POST.get("nuovo_nome") or "").strip()

    cat = None
    if cat_id and cat_id.isdigit():
        cat = Categoria.objects.filter(pk=int(cat_id), attiva=True).first()
    elif nuovo_nome:
        slug = slugify(nuovo_nome)[:40]
        if not slug:
            return HttpResponseBadRequest("Nome categoria non valido.")
        cat, _created = Categoria.objects.get_or_create(
            slug=slug,
            defaults={"denominazione": nuovo_nome[:80]},
        )

    if not cat:
        return HttpResponseBadRequest("Categoria non specificata.")

    cliente.categorie.add(cat)
    return _render_categorie_box(request, cliente)


@login_required
@require_POST
def categorie_rimuovi(request, pk: int, cat_pk: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    cat = get_object_or_404(Categoria, pk=cat_pk)
    cliente.categorie.remove(cat)
    return _render_categorie_box(request, cliente)


@login_required
def modifica_cliente(request, pk: int):
    """Form di modifica completa di un'anagrafica."""
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    if request.method == "POST":
        form = AnagraficaForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, f"Anagrafica '{cliente.denominazione}' aggiornata.")
            return redirect("anagrafica:detail", pk=cliente.pk)
    else:
        form = AnagraficaForm(instance=cliente)
    return render(
        request,
        "anagrafica/form.html",
        {"form": form, "cliente": cliente},
    )


# Campi su cui è permessa la modifica bulk dalla lista.
# Solo campi a choices: evita inserimento di valori arbitrari da textbox.
_BULK_FIELDS = {
    "tipo_soggetto": TipoSoggetto,
    "stato": StatoAnagrafica,
    "regime_contabile": RegimeContabile,
    "periodicita_iva": PeriodicitaIVA,
    "contabilita": GestioneContabilita,
}


@login_required
@require_POST
def bulk_update(request):
    """Aggiorna in massa un singolo campo per N anagrafiche selezionate.

    POST atteso:
      - ids: lista di pk (multipla)
      - field: nome del campo (deve essere in _BULK_FIELDS)
      - value: valore da impostare (deve essere fra i choices.values del campo)
    """
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    ids = request.POST.getlist("ids")

    if field not in _BULK_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso per la modifica bulk.")
    choices_cls = _BULK_FIELDS[field]
    if value not in choices_cls.values:
        return HttpResponseBadRequest("Valore non ammesso per il campo selezionato.")
    if not ids:
        messages.warning(request, "Nessuna anagrafica selezionata.")
        return redirect(reverse("anagrafica:list") + "?" + request.POST.get("qs", ""))

    updated = (
        Anagrafica.objects.filter(pk__in=ids, is_deleted=False)
        .update(**{field: value})
    )

    label = choices_cls(value).label
    field_label = {
        "tipo_soggetto": "Tipo soggetto",
        "stato": "Stato",
        "regime_contabile": "Regime contabile",
        "periodicita_iva": "Periodicità IVA",
        "contabilita": "Tenuta contabilità",
    }.get(field, field)
    messages.success(
        request,
        f"{updated} anagrafiche aggiornate: {field_label} → {label}.",
    )
    # Ritorna alla lista preservando filtri/ricerca correnti.
    qs = request.POST.get("qs", "")
    return redirect(reverse("anagrafica:list") + ("?" + qs if qs else ""))


# ---------------------------------------------------------------------------
# Inline edit (cella per cella) dalla tabella
# ---------------------------------------------------------------------------
#
# Pattern click-to-edit con HTMX:
#  1. il <td> in modalità display ha hx-get verso `inline_edit_form` con
#     trigger=click. Restituisce il <td> in modalità "edit".
#  2. il form in modalità edit ha hx-post verso `inline_save` con
#     trigger=change. Salva e restituisce il <td> tornato in modalità display.
#  3. l'utente puo' premere Esc per annullare (gestito client-side: il piccolo
#     listener globale rimette il valore originale).
#
# Whitelist `_INLINE_FIELDS` controlla quali campi sono modificabili e con
# quale widget. Aggiungere/togliere campi qui basta a estendere o restringere
# la feature, senza toccare il template.

# Tipo widget per campo. "select" usa le choices Django; "text" usa <input
# type=text>; "date" usa <input type=date>; "number" usa <input type=number>.
_INLINE_FIELDS = {
    "codice_interno":    ("text",   None),
    "codice_cli":        ("text",   None),
    "codice_multi":      ("text",   None),
    "codice_gstudio":    ("text",   None),
    "codice_fiscale":    ("text",   None),
    "partita_iva":       ("text",   None),
    "email":             ("text",   None),
    "tipo_soggetto":     ("select", TipoSoggetto),
    "stato":             ("select", StatoAnagrafica),
    "regime_contabile":  ("select", RegimeContabile),
    "periodicita_iva":   ("select", PeriodicitaIVA),
    "contabilita":       ("select", GestioneContabilita),
    "data_inizio_mandato": ("date", None),
    "data_fine_mandato":   ("date", None),
}


def _inline_field_meta(field: str):
    if field not in _INLINE_FIELDS:
        return None
    widget, choices = _INLINE_FIELDS[field]
    return {"name": field, "widget": widget, "choices": choices}


def _render_cell_display(request, cliente, field: str):
    return render(
        request,
        "anagrafica/_cell_display.html",
        {"c": cliente, "field": field},
    )


@login_required
def inline_edit_form(request, pk: int, field: str):
    """GET: ritorna il <td> in modalità edit (input/select) per il campo."""
    meta = _inline_field_meta(field)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    return render(
        request,
        "anagrafica/_cell_edit.html",
        {"c": cliente, "field": field, "meta": meta},
    )


@login_required
@require_POST
def inline_save(request, pk: int, field: str):
    """POST: salva il nuovo valore e ritorna il <td> in modalità display."""
    meta = _inline_field_meta(field)
    if not meta:
        return HttpResponseBadRequest("Campo non ammesso per l'edit inline.")
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    raw = (request.POST.get("value") or "").strip()

    # Normalizzazione e validazione minima per widget.
    if meta["widget"] == "select":
        choices = meta["choices"]
        if raw and raw not in choices.values:
            return HttpResponseBadRequest("Valore non ammesso per il campo.")
    elif meta["widget"] == "date":
        # accetta input HTML5 type=date (YYYY-MM-DD) o vuoto
        if raw and len(raw) != 10:
            return HttpResponseBadRequest("Data non valida.")

    # Campi speciali: normalizzazione coerente con il form
    if field == "codice_fiscale":
        raw = raw.upper()

    # Per campi unique (codice_cli) controlliamo i conflitti per evitare 500.
    if field == "codice_cli" and raw:
        conflict = Anagrafica.objects.filter(codice_cli=raw).exclude(pk=cliente.pk).exists()
        if conflict:
            return HttpResponseBadRequest("Codice CLI già usato da un'altra anagrafica.")

    # `null=True` solo su codice_cli; gli altri sono `blank=True` senza null.
    if field == "codice_cli" and raw == "":
        setattr(cliente, field, None)
    else:
        setattr(cliente, field, raw)
    cliente.save(update_fields=[field, "updated_at"])
    return _render_cell_display(request, cliente, field)


# ---------------------------------------------------------------------------
# Diagnostica anagrafica (staff-only)
# ---------------------------------------------------------------------------
#
# Pagina di analisi che mostra, per ogni campo a choices, la distribuzione
# dei valori effettivamente presenti nel DB. Evidenzia i valori non canonici
# (es. residui da import, errori passati) e permette di rimapparli in massa
# verso un valore canonico. Riusabile per audit periodici dopo nuovi import.

# Whitelist dei campi su cui si può remap. Allineata a `_BULK_FIELDS` /
# `_INLINE_FIELDS` per coerenza.
_DIAG_FIELDS = {
    "tipo_soggetto":   ("Tipo soggetto",       TipoSoggetto),
    "stato":           ("Stato",               StatoAnagrafica),
    "regime_contabile":("Regime contabile",    RegimeContabile),
    "periodicita_iva": ("Periodicità IVA",     PeriodicitaIVA),
    "contabilita":     ("Tenuta contabilità",  GestioneContabilita),
}


def _staff_required(view):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view)


def _diagnose_field(field: str, choices_cls):
    """Restituisce la lista [(valore, count, is_canonico), ...] ordinata
    per count decrescente; i `null` vengono trattati come '' (mai distinti
    sulle CharField del nostro modello)."""
    valid = set(choices_cls.values)
    rows = (
        Anagrafica.objects.filter(is_deleted=False)
        .values(field).annotate(n=Count("id")).order_by("-n")
    )
    out = []
    for r in rows:
        v = r[field] if r[field] is not None else ""
        out.append({
            "value": v,
            "label": choices_cls(v).label if v in valid else v,
            "count": r["n"],
            "canonico": v in valid,
        })
    return out


@login_required
@_staff_required
def diagnostica(request):
    """Pagina di audit dei campi a choices dell'anagrafica."""
    sezioni = []
    for field, (label, cls) in _DIAG_FIELDS.items():
        sezioni.append({
            "field": field,
            "label": label,
            "choices": cls.choices,
            "rows": _diagnose_field(field, cls),
        })
    totale = Anagrafica.objects.filter(is_deleted=False).count()
    return render(
        request,
        "anagrafica/diagnostica.html",
        {"sezioni": sezioni, "totale": totale},
    )


@login_required
@_staff_required
@require_POST
def diagnostica_remap(request):
    """Rimappa tutti i record con valore_orfano del campo verso valore_target.

    POST: field, from_value, to_value. Solo campi nella whitelist, e to_value
    deve essere fra i valori canonici delle choices.
    """
    field = request.POST.get("field", "")
    from_value = request.POST.get("from_value", "")
    to_value = request.POST.get("to_value", "")

    if field not in _DIAG_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso.")
    _, choices_cls = _DIAG_FIELDS[field]
    if to_value not in choices_cls.values:
        return HttpResponseBadRequest("Valore target non canonico.")

    # Confronto su stringa esatta: `from_value` può essere "" per rimappare i blank.
    updated = (
        Anagrafica.objects.filter(is_deleted=False, **{field: from_value})
        .update(**{field: to_value})
    )
    messages.success(
        request,
        f"Rimappati {updated} record: {field} '{from_value or '(vuoto)'}' → '{to_value}'.",
    )
    return redirect("anagrafica:diagnostica")
