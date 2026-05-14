"""Context processor per la sidebar: lista dei tipi adempimento con vista dedicata.

Espone `tipi_dedicati` (queryset/list) ai template, così la sidebar può
mostrare un link per ciascun tipo marcato `ha_vista_dedicata=True` senza
hardcodare nomi di URL o codici.
"""
from .models import TipoAdempimentoCatalogo


def tipi_dedicati(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {"tipi_dedicati": []}
    return {
        "tipi_dedicati": list(
            TipoAdempimentoCatalogo.objects
            .filter(ha_vista_dedicata=True, attivo=True)
            .order_by("ordine", "denominazione")
            .only("pk", "denominazione", "abbreviazione", "colore")
        ),
    }
