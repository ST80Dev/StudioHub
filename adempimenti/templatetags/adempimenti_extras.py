"""Template tag/filter helper per le tabelle adempimenti.

Espone i filtri necessari ai partial `templates/adempimenti/cells/*` e
un inclusion-tag per renderizzare header/filtri di colonna in modo uniforme.
"""

from __future__ import annotations

from datetime import date

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from anagrafica import choices_labels as _choices_labels

from .. import stati as _stati

register = template.Library()


@register.simple_tag
def stato_badge(adempimento) -> str:
    """Render del badge dello stato per un Adempimento.

    Legge denominazione + colore dal catalogo `StatoAdempimentoTipo` del
    tipo della riga (per-tipo). Niente piu' if/elif hardcoded per codice.
    Fallback per codici non riconosciuti: badge grigio con il codice raw.
    """
    if adempimento is None:
        return ""
    s = _stati.stato_by_codice(adempimento.tipo_id, adempimento.stato)
    if s is None:
        return format_html(
            '<span class="sh-state sh-state-idle">{}</span>',
            adempimento.stato or "—",
        )
    return format_html(
        '<span class="sh-state sh-state-{colore}">{label}</span>',
        colore=s.colore,
        label=s.denominazione,
    )


@register.simple_tag
def stato_badge_by_codice(tipo_id, codice) -> str:
    """Variante di `stato_badge` quando non hai l'oggetto Adempimento.

    Se `tipo_id` non e' fornito (None / 0 / ''), cerca il primo match per
    codice across-tipi (best-effort per template generici come la home).
    """
    if not codice:
        return ""
    s = _stati.stato_by_codice(tipo_id, codice) if tipo_id else None
    if s is None:
        # Fallback "any tipo": prendi la prima voce attiva con quel codice
        # (le denominazioni copiate dallo Standard sono coerenti tra tipi).
        from ..models import StatoAdempimentoTipo
        s = (
            StatoAdempimentoTipo.objects.filter(codice=codice, attivo=True)
            .only("denominazione", "colore")
            .first()
        )
    if s is None:
        return format_html('<span class="sh-state sh-state-idle">{}</span>', codice)
    return format_html(
        '<span class="sh-state sh-state-{colore}">{label}</span>',
        colore=s.colore,
        label=s.denominazione,
    )


@register.filter(name="referenti_studio")
def referenti_studio(anag, ruolo: str):
    """Filtra i referenti di un'anagrafica per ruolo.

    Se l'anagrafica ha `referenti_studio` gia' prefetched, itera in memoria
    (no nuova query). Altrimenti emette una query.
    """
    if anag is None:
        return []
    referenti = getattr(anag, "_prefetched_objects_cache", {}).get(
        "referenti_studio"
    )
    if referenti is not None:
        return [r for r in referenti if r.ruolo == ruolo]
    return list(anag.referenti_studio.filter(ruolo=ruolo).select_related("utente"))


@register.filter(name="attivi_in_anno")
def attivi_in_anno(referenti, anno):
    """Filtra una lista di `AnagraficaReferenteStudio` mantenendo solo quelli
    validi nell'anno (data_inizio <= 31/12/anno, data_fine vuota o >= 1/1/anno).

    Se `anno` e' None, ritorna solo quelli con data_fine vuota (in carica oggi).
    """
    if not referenti:
        return []
    if anno is None:
        return [r for r in referenti if r.data_fine is None]
    inizio = date(int(anno), 1, 1)
    fine = date(int(anno), 12, 31)
    out = []
    for r in referenti:
        if r.data_inizio and r.data_inizio > fine:
            continue
        if r.data_fine is not None and r.data_fine < inizio:
            continue
        out.append(r)
    return out


@register.filter(name="iniziali_utente")
def iniziali_utente(user) -> str:
    """Restituisce le iniziali di un utente (es. 'M.R.' per Mario Rossi).
    Fallback: prime 2 lettere dell'username in maiuscolo.
    """
    if user is None:
        return ""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    if first or last:
        a = first[:1].upper()
        b = last[:1].upper()
        return f"{a}.{b}.".strip(".")
    uname = (getattr(user, "username", "") or "").strip()
    return uname[:2].upper()


@register.simple_tag(takes_context=True)
def column_header(context, column):
    """Header sortabile per una `ColumnSpec`.

    Replica la logica di `anagrafica/_sort_header.html` ma generica:
    se la colonna ha `sort_field`, mostra il link con freccia direzione;
    altrimenti mostra solo l'etichetta.
    """
    request = context["request"]
    current = request.GET.get("sort", "")
    label = column.label

    if not column.sort_field:
        return format_html(
            '<th class="{}">{}</th>',
            column.css_th + " text-left text-[11px] uppercase tracking-wider text-slate-500",
            label,
        )

    field = column.sort_field
    asc = field
    desc = "-" + field
    next_sort = desc if current == asc else asc
    arrow = "↕"
    if current == asc:
        arrow = "↑"
    elif current == desc:
        arrow = "↓"

    params = request.GET.copy()
    params["sort"] = next_sort
    url = "?" + params.urlencode()
    return format_html(
        '<th class="{cls}"><a href="{url}" class="hover:underline">{label} <span class="opacity-50">{arrow}</span></a></th>',
        cls=column.css_th + " text-left text-[11px] uppercase tracking-wider text-slate-500",
        url=url,
        label=label,
        arrow=arrow,
    )


@register.simple_tag(takes_context=True)
def column_filter(context, column):
    """Cella filtro per una `ColumnSpec` (sotto l'header).

    Render input testo o select a seconda di `column.filter_kind`.
    Usa attributo `form="filters-form"` per delegare il submit al form esterno.
    """
    if not column.filter_param or not column.filter_kind:
        return format_html('<th class="{}"></th>', column.css_th)

    request = context["request"]
    value = request.GET.get(column.filter_param, "")
    base_input = (
        "w-full rounded border-slate-300 px-1 py-0.5 text-xs "
        "dark:bg-slate-800 dark:border-slate-700"
    )

    if column.filter_kind == "text":
        return format_html(
            '<th class="px-1 py-1"><input form="filters-form" type="text" '
            'name="{name}" value="{val}" placeholder="filtra" '
            'class="{cls}"></th>',
            name=column.filter_param,
            val=value,
            cls=base_input,
        )

    # select
    if column.filter_choices_key == "_stato_adempimento":
        # Sistema colonne riusabile (non tipo-specifico): unione dei codici
        # stato attivi da tutti i tipi, deduplicati.
        from ..models import StatoAdempimentoTipo
        seen: dict[str, str] = {}
        for cod, den in (
            StatoAdempimentoTipo.objects.filter(attivo=True)
            .values_list("codice", "denominazione")
            .order_by("livello", "denominazione")
        ):
            seen.setdefault(cod, den)
        choices = list(seen.items())
    else:
        choices = _choices_labels.get_choices(column.filter_choices_key)

    opts_parts = [format_html('<option value="">tutti</option>')]
    for val, lbl in choices:
        if value == val:
            opts_parts.append(format_html(
                '<option value="{}" selected>{}</option>', val, lbl,
            ))
        else:
            opts_parts.append(format_html(
                '<option value="{}">{}</option>', val, lbl,
            ))

    return format_html(
        '<th class="px-1 py-1"><select form="filters-form" name="{name}" '
        'onchange="this.form.submit()" class="{cls}">{opts}</select></th>',
        name=column.filter_param,
        cls=base_input,
        opts=mark_safe("".join(opts_parts)),
    )
