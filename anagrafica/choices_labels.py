"""Override delle label dei TextChoices via `TextChoiceLabel` (Fase 1).

L'utente puo' modificare le label da Django admin
(/admin/anagrafica/textchoicelabel/). Questo modulo espone:

- `get_label(field, codice)`: label override-aware con fallback al default
   delle TextChoices del modello Anagrafica
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


_cache: dict[str, list[tuple[str, str]]] = {}
_cache_lock = Lock()


def _build_cache(field: str) -> list[tuple[str, str]]:
    """Costruisce la lista [(codice, label), ...] per il campo dato.

    1. Parte dai valori canonici delle TextChoices del modello (fallback).
    2. Sovrascrive le label con quelle di TextChoiceLabel se presenti.
    3. Aggiunge eventuali valori "extra" di TextChoiceLabel non presenti
       nelle TextChoices canoniche (utili in futuro per nuovi tipi).
    Risultato ordinato per `ordine` di TextChoiceLabel (default 0), poi
    per label asc.
    """
    from .models import TextChoiceLabel

    tc = _get_textchoices(field)
    base = list(tc.choices) if tc else []  # [(codice, default_label), ...]
    by_codice = {c: lbl for c, lbl in base}

    overrides = (
        TextChoiceLabel.objects.filter(field=field)
        .order_by("ordine", "label")
        .values_list("codice", "label", "ordine")
    )
    ordered: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for codice, label, ordine in overrides:
        by_codice[codice] = label  # override del default
        ordered.append((codice, label, ordine))
        seen.add(codice)

    # Codici canonici non ancora visti (nessun override): in coda con ordine 999
    for codice, default_label in base:
        if codice in seen:
            continue
        ordered.append((codice, default_label, 999))

    # Sort finale per (ordine, label) e ritorna solo (codice, label)
    ordered.sort(key=lambda r: (r[2], r[1]))
    return [(c, l) for c, l, _ in ordered]


def _cached(field: str) -> list[tuple[str, str]]:
    with _cache_lock:
        if field not in _cache:
            _cache[field] = _build_cache(field)
        return _cache[field]


def get_label(field: str, codice: str | None) -> str:
    if not codice:
        return ""
    for c, lbl in _cached(field):
        if c == codice:
            return lbl
    return codice  # fallback: codice raw se non riconosciuto


def get_choices(field: str) -> list[tuple[str, str]]:
    return list(_cached(field))


def get_values(field: str) -> list[str]:
    return [c for c, _ in _cached(field)]


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
