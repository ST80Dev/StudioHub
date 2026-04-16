"""Factory per generare anagrafiche demo, referenti e legami.

Usate solo dal management command `seed_demo`. Non importare in runtime.
"""
from __future__ import annotations

import random
import string
from datetime import date

import factory
from faker import Faker
from factory.django import DjangoModelFactory

_fake = Faker("it_IT")

from .models import (
    Anagrafica,
    AnagraficaLegame,
    AnagraficaReferenteStudio,
    PeriodicitaIVA,
    RegimeContabile,
    RuoloReferenteStudio,
    StatoAnagrafica,
    TIPI_ENTITA,
    TIPI_PERSONA_FISICA,
    TipoLegame,
    TipoSoggetto,
)


# ---------------------------------------------------------------------------
# Helper: generatori di CF/PIVA sintatticamente plausibili (non validati).
# ---------------------------------------------------------------------------

def _fake_codice_fiscale_pf() -> str:
    """CF persona fisica: 16 char alfanumerici (finto)."""
    letters = string.ascii_uppercase
    digits = string.digits
    parts = [
        "".join(random.choices(letters, k=6)),
        "".join(random.choices(digits, k=2)),
        random.choice("ABCDEHLMPRST"),
        "".join(random.choices(digits, k=2)),
        random.choice(letters) + "".join(random.choices(digits, k=3)),
        random.choice(letters),
    ]
    return "".join(parts)


def _fake_partita_iva() -> str:
    """P.IVA: 11 cifre (finto, no check-digit ufficiale)."""
    return "".join(random.choices(string.digits, k=11))


def _fake_codice_interno(idx: int) -> str:
    """Prefisso DEMO- per renderlo riconoscibile anche senza `is_demo`."""
    return f"DEMO-{idx:05d}"


# ---------------------------------------------------------------------------
# Factory base: pick del tipo_soggetto a monte per pilotare gli altri campi.
# ---------------------------------------------------------------------------

PROVINCE_IT = [
    "MI", "RM", "TO", "NA", "FI", "BO", "VE", "PA", "CT", "BA", "GE", "PD",
    "VR", "BS", "MO", "PR", "RE", "TS", "CA", "AN",
]


class AnagraficaPFFactory(DjangoModelFactory):
    """Persona fisica (PF / PROFEX / DI)."""

    class Meta:
        model = Anagrafica
        django_get_or_create = ("codice_interno",)

    is_demo = True
    tipo_soggetto = factory.LazyFunction(
        lambda: random.choice(list(TIPI_PERSONA_FISICA))
    )
    cognome = factory.Faker("last_name", locale="it_IT")
    nome = factory.Faker("first_name", locale="it_IT")
    denominazione = factory.LazyAttribute(lambda o: f"{o.cognome} {o.nome}")
    codice_fiscale = factory.LazyFunction(_fake_codice_fiscale_pf)
    partita_iva = factory.LazyAttribute(
        lambda o: _fake_partita_iva() if o.tipo_soggetto != TipoSoggetto.PF else ""
    )
    stato = StatoAnagrafica.ATTIVO
    email = factory.Faker("email")
    indirizzo_via = factory.Faker("street_name", locale="it_IT")
    indirizzo_civico = factory.LazyFunction(lambda: str(random.randint(1, 200)))
    indirizzo_cap = factory.Faker("postcode", locale="it_IT")
    indirizzo_comune = factory.Faker("city", locale="it_IT")
    indirizzo_provincia = factory.LazyFunction(lambda: random.choice(PROVINCE_IT))
    indirizzo_nazione = "Italia"
    regime_contabile = factory.LazyAttribute(
        lambda o: (
            random.choice([RegimeContabile.FORFETTARIO, RegimeContabile.SEMPLIFICATO])
            if o.tipo_soggetto in TIPI_PERSONA_FISICA and o.tipo_soggetto != TipoSoggetto.PF
            else RegimeContabile.NON_APPLICABILE
        )
    )
    periodicita_iva = factory.LazyAttribute(
        lambda o: (
            PeriodicitaIVA.NON_SOGGETTO
            if (
                o.tipo_soggetto == TipoSoggetto.PF
                or o.regime_contabile == RegimeContabile.FORFETTARIO
            )
            else random.choice([PeriodicitaIVA.TRIMESTRALE, PeriodicitaIVA.MENSILE])
        )
    )
    data_inizio_mandato = factory.LazyFunction(
        lambda: date(random.randint(2015, 2024), random.randint(1, 12), 1)
    )


class AnagraficaEntitaFactory(DjangoModelFactory):
    """Entità giuridica (SNC/SAS/SRL/SPA/ASS/FALL)."""

    class Meta:
        model = Anagrafica
        django_get_or_create = ("codice_interno",)

    is_demo = True
    tipo_soggetto = factory.LazyFunction(lambda: random.choice(list(TIPI_ENTITA)))
    denominazione = factory.LazyAttribute(
        lambda o: f"{_fake.last_name()} {o.tipo_soggetto}"
    )
    codice_fiscale = factory.LazyFunction(_fake_partita_iva)
    partita_iva = factory.LazyFunction(_fake_partita_iva)
    stato = StatoAnagrafica.ATTIVO
    email = factory.Faker("company_email")
    indirizzo_via = factory.Faker("street_name", locale="it_IT")
    indirizzo_civico = factory.LazyFunction(lambda: str(random.randint(1, 200)))
    indirizzo_cap = factory.Faker("postcode", locale="it_IT")
    indirizzo_comune = factory.Faker("city", locale="it_IT")
    indirizzo_provincia = factory.LazyFunction(lambda: random.choice(PROVINCE_IT))
    indirizzo_nazione = "Italia"
    regime_contabile = RegimeContabile.ORDINARIO
    periodicita_iva = factory.LazyFunction(
        lambda: random.choice([PeriodicitaIVA.MENSILE, PeriodicitaIVA.TRIMESTRALE])
    )
    data_inizio_mandato = factory.LazyFunction(
        lambda: date(random.randint(2010, 2023), random.randint(1, 12), 1)
    )


class ReferenteStudioFactory(DjangoModelFactory):
    class Meta:
        model = AnagraficaReferenteStudio

    ruolo = factory.LazyFunction(
        lambda: random.choice(list(RuoloReferenteStudio))
    )
    principale = True
    data_inizio = factory.LazyAttribute(
        lambda o: o.anagrafica.data_inizio_mandato or date(2020, 1, 1)
    )


class LegameFactory(DjangoModelFactory):
    class Meta:
        model = AnagraficaLegame

    tipo_legame = factory.LazyFunction(
        lambda: random.choice(
            [TipoLegame.SOCIO, TipoLegame.AMMINISTRATORE, TipoLegame.LEGALE_RAPPR]
        )
    )
