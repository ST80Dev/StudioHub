"""Helpers per il lookup degli stati di un adempimento, con cache.

Gli stati validi per un `Adempimento` non sono piu' hardcoded come
TextChoices: vivono nella tabella `StatoAdempimentoTipo` (per-tipo). Per
evitare di fare una query ad ogni render di lista (50 righe → 50 query
sul catalogo stati), questo modulo mantiene una cache module-level
per-tipo, invalidata via signal su save/delete.

API principali:

- `stati_di_tipo(tipo_id)` → lista degli stati attivi del tipo, ordinati
  per `livello`.
- `stato_by_codice(tipo_id, codice)` → singolo stato o None.
- `codici_validi(tipo_id)` → set di codici utilizzabili per quel tipo.
- `codici_lavorabili(tipo_id)` → sottoinsieme con `lavorabile=True`.
- `stato_default(tipo_id)` → codice dello stato `iniziale_default` (con
  fallback al primo per livello).
- `choices(tipo_id)` → lista `[(codice, denominazione), ...]` per dropdown.

`_connect_signals()` deve essere chiamato una volta a startup (vedi
`adempimenti/apps.py`).
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


if TYPE_CHECKING:
    from .models import StatoAdempimentoTipo


# Cache: { tipo_id: list[StatoAdempimentoTipo] } ordinata per livello.
_tipo_cache: dict[int, list["StatoAdempimentoTipo"]] = {}
_lock = Lock()


def stati_di_tipo(tipo_id: int) -> list["StatoAdempimentoTipo"]:
    """Stati attivi del tipo, ordinati per `livello` asc."""
    if tipo_id is None:
        return []
    with _lock:
        cached = _tipo_cache.get(tipo_id)
        if cached is not None:
            return cached
        from .models import StatoAdempimentoTipo
        loaded = list(
            StatoAdempimentoTipo.objects.filter(
                tipo_adempimento_id=tipo_id, attivo=True,
            ).order_by("livello", "denominazione")
        )
        _tipo_cache[tipo_id] = loaded
        return loaded


def stato_by_codice(tipo_id: int, codice: str) -> "StatoAdempimentoTipo | None":
    if not codice or tipo_id is None:
        return None
    for s in stati_di_tipo(tipo_id):
        if s.codice == codice:
            return s
    return None


def codici_validi(tipo_id: int) -> set[str]:
    return {s.codice for s in stati_di_tipo(tipo_id)}


def codici_lavorabili(tipo_id: int) -> set[str]:
    return {s.codice for s in stati_di_tipo(tipo_id) if s.lavorabile}


def codici_non_lavorabili(tipo_id: int) -> set[str]:
    return {s.codice for s in stati_di_tipo(tipo_id) if not s.lavorabile}


def stato_default(tipo_id: int) -> str:
    """Codice dello stato iniziale per nuovi adempimenti.

    1. Il primo `iniziale_default=True` se presente.
    2. Altrimenti il primo per `livello` asc.
    3. Fallback finale: 'da_fare' (codice canonico).
    """
    stati = stati_di_tipo(tipo_id)
    for s in stati:
        if s.iniziale_default:
            return s.codice
    if stati:
        return stati[0].codice
    return "da_fare"


def choices(tipo_id: int) -> list[tuple[str, str]]:
    """Lista `[(codice, denominazione), ...]` per dropdown/filtri."""
    return [(s.codice, s.denominazione) for s in stati_di_tipo(tipo_id)]


def label(tipo_id: int, codice: str) -> str:
    """Denominazione dello stato, fallback al codice se non riconosciuto."""
    s = stato_by_codice(tipo_id, codice)
    return s.denominazione if s else (codice or "")


def invalidate(tipo_id: int | None = None) -> None:
    """Svuota la cache (per tutto o per un tipo specifico)."""
    with _lock:
        if tipo_id is None:
            _tipo_cache.clear()
        else:
            _tipo_cache.pop(tipo_id, None)


# ---------------------------------------------------------------------------
# Signal: invalidazione cache + auto-copia Standard → Tipo
# ---------------------------------------------------------------------------

def _connect_signals() -> None:
    """Registra i signal. Chiamato da `AdempimentiConfig.ready()`."""
    from .models import (
        StatoAdempimentoStandard,
        StatoAdempimentoTipo,
        TipoAdempimentoCatalogo,
    )

    @receiver(post_save, sender=StatoAdempimentoTipo, dispatch_uid="stati_tipo_save")
    def _on_save(sender, instance, **kwargs):
        invalidate(instance.tipo_adempimento_id)

    @receiver(post_delete, sender=StatoAdempimentoTipo, dispatch_uid="stati_tipo_del")
    def _on_delete(sender, instance, **kwargs):
        invalidate(instance.tipo_adempimento_id)

    @receiver(post_save, sender=StatoAdempimentoStandard, dispatch_uid="stati_std_save")
    def _on_std_save(sender, instance, **kwargs):
        # Lo Standard non influenza tipi esistenti, ma puliamo la cache
        # per coerenza (nel caso futuro di una "re-apply standard").
        invalidate(None)

    @receiver(
        post_save, sender=TipoAdempimentoCatalogo,
        dispatch_uid="stati_copy_std_on_tipo_create",
    )
    def _copy_std_on_new_tipo(sender, instance, created, **kwargs):
        """Quando si crea un nuovo TipoAdempimento, copia gli stati Standard.

        Idempotente: se per qualche ragione il tipo ha gia' stati, non
        sovrascrive nulla (skip silente sui codici gia' presenti).
        """
        if not created:
            return
        from .models import StatoAdempimentoTipo as STT

        per_tipo_codici = set(
            STT.objects.filter(tipo_adempimento=instance)
            .values_list("codice", flat=True)
        )
        nuovi = []
        for std in StatoAdempimentoStandard.objects.filter(attivo=True):
            if std.codice in per_tipo_codici:
                continue
            nuovi.append(STT(
                tipo_adempimento=instance,
                codice=std.codice,
                denominazione=std.denominazione,
                sigla=std.sigla,
                colore=std.colore,
                lavorabile=std.lavorabile,
                livello=std.livello,
                iniziale_default=std.iniziale_default,
                attivo=True,
                e_predefinito=True,
            ))
        if nuovi:
            STT.objects.bulk_create(nuovi)
        invalidate(instance.id)
