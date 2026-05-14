"""Override delle label dei TextChoices via `TextChoiceLabel` (Fase 1).

L'utente puo' modificare le label da Django admin
(/admin/anagrafica/textchoicelabel/). Questo modulo espone:

- `get_label(field, codice)`: label estesa override-aware con fallback al
   default delle TextChoices del modello Anagrafica
- `get_micro_label(field, codice)`: sigla 3 char per celle/badge densi.
   Fallback automatico: prime 3 lettere upper della label.
- `get_choices(field)`: lista `[(codice, label), ...]` ordinata per `ordine`
   override-aware. Sostituisce `<TextChoices>.choices` nei contesti dei
   template/form.
- `get_values(field)`: lista `[codice, ...]` da usare per validazione.
- `invalidate_cache()`: forza il refresh in-memory; chiamato via signal
   post_save/post_delete su TextChoiceLabel.

La cache e' un semplice dict module-level. Si ricarica al primo accesso
dopo invalidate. Footprint trascurabile (~21 record canonici).
"""

from __future__ import annotations

from threading import Lock

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


# Map dei TextChoices del modello Anagrafica usati per fallback.
# Lazy import per evitare circular dependency con anagrafica.models.
def _get_textchoices(field: str):
    from . import models
    return {
        "tipo_soggetto": models.TipoSoggetto,
        "stato": models.StatoAnagrafica,
        "regime_contabile": models.RegimeContabile,
        "periodicita_iva": models.PeriodicitaIVA,
        "contabilita": models.GestioneContabilita,
    }.get(field)


# Entry della cache: una tripla (codice, label, label_micro). Il micro
# puo' essere "" — in quel caso `get_micro_label` calcola il fallback.
_cache: dict[str, list[tuple[str, str, str]]] = {}
_cache_lock = Lock()


def _micro_fallback(label: str) -> str:
    """Sigla 3 char dalle prime 3 lettere alfanumeriche di `label`."""
    if not label:
        return ""
    pulito = "".join(ch for ch in label if ch.isalnum())
    return pulito[:3].upper()


def _build_cache(field: str) -> list[tuple[str, str, str]]:
    """Costruisce la lista [(codice, label, label_micro), ...] per il campo.

    1. Parte dai valori canonici delle TextChoices del modello (fallback).
    2. Sovrascrive label/micro con quelle di TextChoiceLabel se presenti.
    3. Aggiunge eventuali valori "extra" di TextChoiceLabel non presenti
       nelle TextChoices canoniche.
    Risultato ordinato per `ordine` di TextChoiceLabel (default 0), poi
    per label asc.
    """
    from .models import TextChoiceLabel

    tc = _get_textchoices(field)
    base = list(tc.choices) if tc else []  # [(codice, default_label), ...]

    overrides = (
        TextChoiceLabel.objects.filter(field=field)
        .order_by("ordine", "label")
        .values_list("codice", "label", "label_micro", "ordine")
    )
    ordered: list[tuple[str, str, str, int]] = []
    seen: set[str] = set()
    for codice, label, label_micro, ordine in overrides:
        ordered.append((codice, label, label_micro, ordine))
        seen.add(codice)

    # Codici canonici non ancora visti (nessun override): in coda con ordine 999
    for codice, default_label in base:
        if codice in seen:
            continue
        ordered.append((codice, default_label, "", 999))

    ordered.sort(key=lambda r: (r[3], r[1]))
    return [(c, l, m) for c, l, m, _ in ordered]


def _cached(field: str) -> list[tuple[str, str, str]]:
    with _cache_lock:
        if field not in _cache:
            _cache[field] = _build_cache(field)
        return _cache[field]


def get_label(field: str, codice: str | None) -> str:
    if not codice:
        return ""
    for c, lbl, _ in _cached(field):
        if c == codice:
            return lbl
    return codice  # fallback: codice raw se non riconosciuto


def get_micro_label(field: str, codice: str | None) -> str:
    """Sigla 3 char per `codice`. Fallback su prime 3 lettere di `label`."""
    if not codice:
        return ""
    for c, lbl, micro in _cached(field):
        if c == codice:
            return micro or _micro_fallback(lbl)
    return codice[:3].upper()


def get_choices(field: str) -> list[tuple[str, str]]:
    return [(c, l) for c, l, _ in _cached(field)]


def get_choices_micro(field: str) -> list[tuple[str, str]]:
    """Come `get_choices` ma con la sigla micro al posto della label estesa."""
    return [(c, m or _micro_fallback(l)) for c, l, m in _cached(field)]


def get_values(field: str) -> list[str]:
    return [c for c, _, _ in _cached(field)]


def invalidate_cache(field: str | None = None) -> None:
    with _cache_lock:
        if field is None:
            _cache.clear()
        else:
            _cache.pop(field, None)


# Signal: invalidate quando TextChoiceLabel cambia
def _connect_signals():
    from .models import TextChoiceLabel

    @receiver(post_save, sender=TextChoiceLabel, dispatch_uid="cl_invalidate_save")
    def _on_save(sender, instance, **kwargs):
        invalidate_cache(instance.field)

    @receiver(post_delete, sender=TextChoiceLabel, dispatch_uid="cl_invalidate_delete")
    def _on_delete(sender, instance, **kwargs):
        invalidate_cache(instance.field)
