"""Factory per generare adempimenti demo sul nuovo schema catalogo-driven.

Usate solo dal management command `seed_demo`. Non importare in runtime.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .models import Adempimento, StatoAdempimento, TipoAdempimentoCatalogo


def crea_adempimento_demo(
    anagrafica,
    tipo: TipoAdempimentoCatalogo,
    anno_fiscale: int,
    responsabile=None,
) -> list[Adempimento]:
    """Crea gli adempimenti per un tipo/anno (uno per periodo).

    Restituisce la lista di record creati.
    """
    scadenze = tipo.scadenze.all()
    if not scadenze.exists():
        scadenze = [None]

    stati_pesati = [
        StatoAdempimento.DA_FARE,
        StatoAdempimento.IN_CORSO,
        StatoAdempimento.IN_CORSO,
        StatoAdempimento.CHIUSA,
        StatoAdempimento.CHIUSA,
        StatoAdempimento.INVIATO,
        StatoAdempimento.INVIATO,
        StatoAdempimento.INVIATO,
    ]

    creati = []
    for scad in scadenze:
        periodo = scad.periodo if scad else None
        data_scadenza = scad.calcola_data_scadenza(anno_fiscale) if scad else None

        adempimento, created = Adempimento.objects.get_or_create(
            anagrafica=anagrafica,
            tipo=tipo,
            anno_fiscale=anno_fiscale,
            periodo=periodo,
            defaults={
                "data_scadenza": data_scadenza,
                "stato": random.choice(stati_pesati),
                "responsabile": responsabile,
                "is_demo": True,
            },
        )
        if created:
            creati.append(adempimento)
    return creati
