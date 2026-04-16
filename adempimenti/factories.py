"""Factory per generare adempimenti demo.

Usate solo dal management command `seed_demo`. Non importare in runtime.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import factory
from factory.django import DjangoModelFactory

from .models import Adempimento, AdempimentoBilancioUE, TipoAdempimento


class AdempimentoBilancioUEFactory(DjangoModelFactory):
    """Adempimento padre + figlia BilancioUE, con stato realistico.

    Il chiamante passa `anagrafica`, `anno_fiscale`, `anno_esecuzione`,
    `responsabile`. La progressione dello stato è randomizzata ma coerente
    coi timestamp.
    """

    class Meta:
        model = Adempimento

    is_demo = True
    tipo = TipoAdempimento.BILANCIO_UE
    note = ""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        adempimento = super()._create(model_class, *args, **kwargs)
        _popola_figlia_bilancio_ue(adempimento)
        return adempimento


def _popola_figlia_bilancio_ue(adempimento: Adempimento) -> AdempimentoBilancioUE:
    """Crea la figlia 1:1 con timestamp coerenti tra loro.

    Distribuzione degli stati (peso):
      - da_iniziare: 15%
      - da_compilare: 25%
      - da_inviare: 25%
      - completato: 35%
    """
    chiusura = compilazione = invio = None
    stato = random.choices(
        ["da_iniziare", "da_compilare", "da_inviare", "completato"],
        weights=[15, 25, 25, 35],
        k=1,
    )[0]

    if stato in ("da_compilare", "da_inviare", "completato"):
        # Chiusura di bilancio: tipicamente entro il 30/4 dell'anno successivo.
        chiusura = date(adempimento.anno_esecuzione, 4, 30) - timedelta(
            days=random.randint(0, 120)
        )
    if stato in ("da_inviare", "completato"):
        compilazione = chiusura + timedelta(days=random.randint(5, 45))
    if stato == "completato":
        invio = compilazione + timedelta(days=random.randint(1, 30))

    return AdempimentoBilancioUE.objects.create(
        adempimento=adempimento,
        data_chiusura_bilancio=chiusura,
        data_compilazione=compilazione,
        data_invio_pratica=invio,
    )
