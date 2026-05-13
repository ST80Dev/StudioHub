from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import AnagraficaForm
from .models import (
    Anagrafica,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    StatoAnagrafica,
    TipoSoggetto,
)


@login_required
def lista_clienti(request):
    """Lista densa dei clienti, con ricerca libera e filtri rapidi."""
    queryset = Anagrafica.objects.filter(is_deleted=False)

    q = request.GET.get("q", "").strip()
    if q:
        queryset = queryset.filter(
            Q(denominazione__icontains=q)
            | Q(codice_interno__icontains=q)
            | Q(codice_fiscale__icontains=q)
            | Q(partita_iva__icontains=q)
        )

    tipo = request.GET.get("tipo", "")
    if tipo in TipoSoggetto.values:
        queryset = queryset.filter(tipo_soggetto=tipo)

    stato = request.GET.get("stato", "")
    if stato in StatoAnagrafica.values:
        queryset = queryset.filter(stato=stato)

    paginator = Paginator(queryset.order_by("denominazione"), 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "clienti": page.object_list,
        "q": q,
        "tipo": tipo,
        "stato": stato,
        "tipi_soggetto": TipoSoggetto.choices,
        "stati": StatoAnagrafica.choices,
        "regimi": RegimeContabile.choices,
        "periodicita": PeriodicitaIVA.choices,
        "contabilita_choices": GestioneContabilita.choices,
        "totale": paginator.count,
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
        },
    )


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
