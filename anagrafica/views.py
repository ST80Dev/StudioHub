from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseBadRequest

from . import choices_labels as _choices_labels
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.utils.text import slugify

from .forms import AnagraficaForm
from .models import (
    Anagrafica,
    AnagraficaReferenteStudio,
    Categoria,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    RuoloReferenteStudio,
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
    # Prefetch dei referenti attivi (sia contab che consul) per evitare
    # N+1 sulla tabella elenco clienti.
    referenti_attivi_qs = (
        AnagraficaReferenteStudio.objects.filter(data_fine__isnull=True)
        .select_related("utente")
        .order_by("-principale", "utente__last_name", "utente__first_name")
    )
    queryset = (
        Anagrafica.objects.filter(is_deleted=False)
        .prefetch_related(
            Prefetch(
                "referenti_studio",
                queryset=referenti_attivi_qs,
                to_attr="referenti_attivi",
            )
        )
    )

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
    if f_tipo in _choices_labels.get_values("tipo_soggetto", include_inactive=True):
        queryset = queryset.filter(tipo_soggetto=f_tipo)

    f_stato = request.GET.get("f_stato") or request.GET.get("stato") or ""
    if f_stato in _choices_labels.get_values("stato", include_inactive=True):
        queryset = queryset.filter(stato=f_stato)

    f_regime = request.GET.get("f_regime", "")
    if f_regime in _choices_labels.get_values("regime_contabile", include_inactive=True):
        queryset = queryset.filter(regime_contabile=f_regime)

    f_iva = request.GET.get("f_iva", "")
    if f_iva in _choices_labels.get_values("periodicita_iva", include_inactive=True):
        queryset = queryset.filter(periodicita_iva=f_iva)

    f_contab = request.GET.get("f_contab", "")
    if f_contab in _choices_labels.get_values("contabilita", include_inactive=True):
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

    # Filtro per referente di studio (per ruolo). Whitelist su user_id numerico.
    f_ref_contab = (request.GET.get("f_ref_contab") or "").strip()
    if f_ref_contab.isdigit():
        queryset = queryset.filter(
            referenti_studio__utente_id=int(f_ref_contab),
            referenti_studio__ruolo=RuoloReferenteStudio.REFERENTE_CONTABILITA,
            referenti_studio__data_fine__isnull=True,
        ).distinct()
    f_ref_consul = (request.GET.get("f_ref_consul") or "").strip()
    if f_ref_consul.isdigit():
        queryset = queryset.filter(
            referenti_studio__utente_id=int(f_ref_consul),
            referenti_studio__ruolo=RuoloReferenteStudio.REFERENTE_CONSULENZA,
            referenti_studio__data_fine__isnull=True,
        ).distinct()

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
        "f_ref_contab": f_ref_contab,
        "f_ref_consul": f_ref_consul,
        "utenti_disponibili": get_user_model().objects
            .filter(is_active=True)
            .order_by("last_name", "first_name", "username"),
        "ruolo_contab": RuoloReferenteStudio.REFERENTE_CONTABILITA,
        "ruolo_consul": RuoloReferenteStudio.REFERENTE_CONSULENZA,
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


def _referenti_section_context(cliente):
    """Contesto condiviso fra detail page e fragment HTMX della sezione referenti."""
    User = get_user_model()
    attivi = list(
        cliente.referenti_studio.filter(data_fine__isnull=True)
        .select_related("utente")
        .order_by("ruolo", "-principale", "utente__last_name", "utente__first_name")
    )
    ref_contab = [r for r in attivi if r.ruolo == RuoloReferenteStudio.REFERENTE_CONTABILITA]
    ref_consul = [r for r in attivi if r.ruolo == RuoloReferenteStudio.REFERENTE_CONSULENZA]
    utenti = User.objects.filter(is_active=True).order_by(
        "last_name", "first_name", "username"
    )
    return {
        "cliente": cliente,
        "ref_contab": ref_contab,
        "ref_consul": ref_consul,
        "utenti_disponibili": utenti,
        "ruolo_contab": RuoloReferenteStudio.REFERENTE_CONTABILITA,
        "ruolo_consul": RuoloReferenteStudio.REFERENTE_CONSULENZA,
    }


@login_required
def dettaglio_cliente(request, pk: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    ctx = {
        "cliente": cliente,
        "legami": cliente.legami_da.select_related("anagrafica_collegata"),
        "categorie_assegnate": cliente.categorie.filter(attiva=True),
    }
    ctx.update(_referenti_section_context(cliente))
    return render(request, "anagrafica/detail.html", ctx)


@login_required
@require_POST
def referente_aggiungi(request, pk: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    User = get_user_model()
    utente_id = request.POST.get("utente", "")
    ruolo = request.POST.get("ruolo", "")
    principale = request.POST.get("principale") == "on"

    if ruolo not in RuoloReferenteStudio.values:
        return HttpResponseBadRequest("Ruolo non valido.")
    if not utente_id.isdigit():
        return HttpResponseBadRequest("Utente non valido.")
    utente = get_object_or_404(User, pk=int(utente_id), is_active=True)

    # Evita duplicati: stesso utente, stesso ruolo, già attivo per il cliente.
    gia_attivo = AnagraficaReferenteStudio.objects.filter(
        anagrafica=cliente,
        utente=utente,
        ruolo=ruolo,
        data_fine__isnull=True,
    ).exists()
    if not gia_attivo:
        if principale:
            # Se il nuovo è principale, togli il flag agli altri attivi dello stesso ruolo.
            AnagraficaReferenteStudio.objects.filter(
                anagrafica=cliente, ruolo=ruolo, data_fine__isnull=True,
            ).update(principale=False)
        AnagraficaReferenteStudio.objects.create(
            anagrafica=cliente,
            utente=utente,
            ruolo=ruolo,
            principale=principale,
            data_inizio=date.today(),
        )

    return render(
        request,
        "anagrafica/_referenti_section.html",
        _referenti_section_context(cliente),
    )


@login_required
@require_POST
def referente_chiudi(request, pk: int, rid: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    ref = get_object_or_404(
        AnagraficaReferenteStudio, pk=rid, anagrafica=cliente, data_fine__isnull=True
    )
    ref.data_fine = date.today()
    ref.principale = False
    ref.save(update_fields=["data_fine", "principale"])
    return render(
        request,
        "anagrafica/_referenti_section.html",
        _referenti_section_context(cliente),
    )


@login_required
@require_POST
def referente_associa(request, pk: int, rid: int):
    """Associa un utente reale a un referente "non collegato" (raw),
    cioe' con `utente=None` e `nome_grezzo` valorizzato.

    Tipicamente quei referenti vengono dagli import quando il nome
    dell'addetto nell'Excel non corrispondeva a nessun UtenteStudio
    esistente. Una volta creato l'utente in admin, da qui lo si aggancia
    al referente preservando data_inizio e ruolo. `nome_grezzo` viene
    svuotato.
    """
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    ref = get_object_or_404(
        AnagraficaReferenteStudio,
        pk=rid, anagrafica=cliente,
        utente__isnull=True, data_fine__isnull=True,
    )
    utente_id = (request.POST.get("utente") or "").strip()
    if not utente_id.isdigit():
        return HttpResponseBadRequest("Utente non valido.")
    User = get_user_model()
    utente = get_object_or_404(User, pk=int(utente_id), is_active=True)

    # Se c'e' gia' un referente attivo per stesso (anagrafica, utente, ruolo),
    # chiudo la riga raw invece di duplicare: la riga "vera" ha precedenza.
    duplicato = AnagraficaReferenteStudio.objects.filter(
        anagrafica=cliente, utente=utente, ruolo=ref.ruolo,
        data_fine__isnull=True,
    ).exclude(pk=ref.pk).exists()
    if duplicato:
        ref.data_fine = date.today()
        ref.save(update_fields=["data_fine"])
        messages.info(
            request,
            f"{utente} era gia' referente attivo: la riga importata e' stata chiusa.",
        )
    else:
        ref.utente = utente
        ref.nome_grezzo = ""
        ref.save(update_fields=["utente", "nome_grezzo"])

    return render(
        request,
        "anagrafica/_referenti_section.html",
        _referenti_section_context(cliente),
    )


@login_required
@require_POST
def referente_principale(request, pk: int, rid: int):
    """Promuove il referente a `principale` (gli altri attivi dello stesso ruolo
    perdono il flag). Se è già principale, lo toglie."""
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    ref = get_object_or_404(
        AnagraficaReferenteStudio, pk=rid, anagrafica=cliente, data_fine__isnull=True
    )
    if ref.principale:
        ref.principale = False
        ref.save(update_fields=["principale"])
    else:
        AnagraficaReferenteStudio.objects.filter(
            anagrafica=cliente, ruolo=ref.ruolo, data_fine__isnull=True,
        ).exclude(pk=ref.pk).update(principale=False)
        ref.principale = True
        ref.save(update_fields=["principale"])
    return render(
        request,
        "anagrafica/_referenti_section.html",
        _referenti_section_context(cliente),
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
# Campi su cui e' permessa la modifica bulk dalla lista. Solo i 5 campi
# data-driven (gestiti via TextChoiceLabel): evita inserimento di valori
# arbitrari da textbox.
_BULK_FIELDS = {
    "tipo_soggetto": "Tipo soggetto",
    "stato": "Stato",
    "regime_contabile": "Regime contabile",
    "periodicita_iva": "Periodicità IVA",
    "contabilita": "Tenuta contabilità",
}


@login_required
@require_POST
def bulk_update(request):
    """Aggiorna in massa un singolo campo per N anagrafiche selezionate.

    POST atteso:
      - ids: lista di pk (multipla)
      - field: nome del campo (deve essere in _BULK_FIELDS)
      - value: valore da impostare (deve essere fra i valori ATTIVI gestiti
        da TextChoiceLabel)
    """
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    ids = request.POST.getlist("ids")

    if field not in _BULK_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso per la modifica bulk.")
    if value not in _choices_labels.get_values(field):
        return HttpResponseBadRequest("Valore non ammesso per il campo selezionato.")
    if not ids:
        messages.warning(request, "Nessuna anagrafica selezionata.")
        return redirect(reverse("anagrafica:list") + "?" + request.POST.get("qs", ""))

    updated = (
        Anagrafica.objects.filter(pk__in=ids, is_deleted=False)
        .update(**{field: value})
    )

    label = _choices_labels.get_label(field, value)
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
# Mappa nome_campo -> (widget, lookup_field_label).
# Per widget "select" il secondo elemento e' la chiave di TextChoiceLabel
# (es. "tipo_soggetto") usata per leggere i valori ammessi via choices_labels.
_INLINE_FIELDS = {
    "codice_interno":    ("text",   None),
    "codice_cli":        ("text",   None),
    "codice_multi":      ("text",   None),
    "codice_gstudio":    ("text",   None),
    "codice_fiscale":    ("text",   None),
    "partita_iva":       ("text",   None),
    "email":             ("text",   None),
    "tipo_soggetto":     ("select", "tipo_soggetto"),
    "stato":             ("select", "stato"),
    "regime_contabile":  ("select", "regime_contabile"),
    "periodicita_iva":   ("select", "periodicita_iva"),
    "contabilita":       ("select", "contabilita"),
    "data_inizio_mandato": ("date", None),
    "data_fine_mandato":   ("date", None),
}


def _inline_field_meta(field: str):
    if field not in _INLINE_FIELDS:
        return None
    widget, choices_field = _INLINE_FIELDS[field]
    choices = (
        _choices_labels.get_choices(choices_field) if widget == "select" else None
    )
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
        choices = meta["choices"] or []
        valid = {c for c, _ in choices}
        if raw and raw not in valid:
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
# `_INLINE_FIELDS` per coerenza. I valori "canonici" sono quelli ATTIVI
# in TextChoiceLabel (i codici disattivati sono considerati orfani da
# rimappare).
_DIAG_FIELDS = {
    "tipo_soggetto":   "Tipo soggetto",
    "stato":           "Stato",
    "regime_contabile":"Regime contabile",
    "periodicita_iva": "Periodicità IVA",
    "contabilita":     "Tenuta contabilità",
}


def _staff_required(view):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view)


def _diagnose_field(field: str):
    """Restituisce la lista [(valore, count, is_canonico), ...] ordinata
    per count decrescente; i `null` vengono trattati come '' (mai distinti
    sulle CharField del nostro modello). Canonico = codice ATTIVO."""
    valid = set(_choices_labels.get_values(field))
    rows = (
        Anagrafica.objects.filter(is_deleted=False)
        .values(field).annotate(n=Count("id")).order_by("-n")
    )
    out = []
    for r in rows:
        v = r[field] if r[field] is not None else ""
        out.append({
            "value": v,
            "label": _choices_labels.get_label(field, v) if v else "",
            "count": r["n"],
            "canonico": v in valid,
        })
    return out


@login_required
@_staff_required
def diagnostica(request):
    """Pagina di audit dei campi a choices dell'anagrafica."""
    sezioni = []
    for field, label in _DIAG_FIELDS.items():
        sezioni.append({
            "field": field,
            "label": label,
            "choices": _choices_labels.get_choices(field),
            "rows": _diagnose_field(field),
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
    deve essere fra i valori canonici (attivi) di TextChoiceLabel.
    """
    field = request.POST.get("field", "")
    from_value = request.POST.get("from_value", "")
    to_value = request.POST.get("to_value", "")

    if field not in _DIAG_FIELDS:
        return HttpResponseBadRequest("Campo non ammesso.")
    if to_value not in _choices_labels.get_values(field):
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
