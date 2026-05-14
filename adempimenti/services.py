"""Servizi applicativi degli adempimenti.

Logica di dominio condivisa tra management command e view HTTP.
Nessuna dipendenza da request/HTTP qui dentro: si testa da shell e si
chiama da entrambi i lati.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from django.db import transaction

from anagrafica.models import Anagrafica

from .models import (
    Adempimento,
    STATI_LAVORABILI,
    StatoAdempimento,
    TipoAdempimentoCatalogo,
)


@dataclass
class RisultatoSync:
    """Esito di una sincronizzazione adempimenti."""

    tipo: TipoAdempimentoCatalogo
    anno: int
    periodi: list[int | None] = field(default_factory=list)
    creati: int = 0
    gia_esistenti: int = 0
    # Righe gia' presenti per clienti che oggi NON sarebbero piu' applicabili.
    # Solo quelle in stati "lavorabili" (DA_FARE / IN_CORSO / CHIUSA): le altre
    # (INVIATO, FANNO_LORO, NO_DATI) sono gia' state gestite e non vanno
    # rimesse in discussione.
    obsoleti_pks: list[int] = field(default_factory=list)
    # Numero di clienti applicabili (utile per debug/log).
    clienti_applicabili: int = 0


def _clienti_applicabili_oggi(
    tipo: TipoAdempimentoCatalogo,
    includi_non_attivi: bool = False,
) -> tuple[list[Anagrafica], list[int]]:
    """Calcola, in base ai valori CORRENTI dell'anagrafica, l'insieme dei
    clienti applicabili per `tipo`.

    Ritorna `(applicabili, non_applicabili_ids)`.

    NB: la storicizzazione del profilo fiscale e' rimandata; per ora si
    valutano le regole sui valori scalari del record Anagrafica.
    """
    regole = [r for r in tipo.regole.all() if r.attiva]
    if not regole:
        return [], []

    anagrafiche = Anagrafica.objects.filter(is_deleted=False).prefetch_related(
        "categorie"
    )
    if not includi_non_attivi:
        anagrafiche = anagrafiche.filter(stato="attivo")

    applicabili: list[Anagrafica] = []
    non_applicabili_ids: list[int] = []
    for anag in anagrafiche:
        if all(r.valuta(anag) for r in regole):
            applicabili.append(anag)
        else:
            non_applicabili_ids.append(anag.pk)
    return applicabili, non_applicabili_ids


def _periodi_target(
    tipo: TipoAdempimentoCatalogo, solo_periodo: int | None
) -> list[tuple[int | None, object | None]]:
    """Lista di tuple (periodo_int_o_None, scadenza_obj_o_None) da generare.

    - Tipi annuali / una_tantum: una sola tupla `(None, scadenza_periodo_1_o_None)`.
    - Tipi trimestrali/mensili: una tupla per ciascuna ScadenzaPeriodo del tipo,
      filtrate per `solo_periodo` se passato.
    """
    scadenze = list(tipo.scadenze.all().order_by("periodo"))
    if not scadenze:
        return [(None, None)]
    if solo_periodo is not None:
        scadenze = [s for s in scadenze if s.periodo == solo_periodo]
    return [(s.periodo, s) for s in scadenze]


def sincronizza_adempimenti(
    tipo: TipoAdempimentoCatalogo,
    anno: int,
    *,
    solo_periodo: int | None = None,
    dry_run: bool = False,
    includi_non_attivi: bool = False,
) -> RisultatoSync:
    """Crea le righe Adempimento mancanti per (tipo, anno[, periodo]).

    Idempotente: `get_or_create` sul unique (anagrafica, tipo, anno, periodo).
    Non tocca, mai, righe esistenti — comprese quelle aggiunte manualmente
    o gia' lavorate. Calcola anche l'insieme "obsoleto": righe in stati
    lavorabili per clienti che oggi non sarebbero piu' applicabili (solo
    segnalazione, l'utente decide cosa fare).
    """
    applicabili, non_applicabili_ids = _clienti_applicabili_oggi(
        tipo, includi_non_attivi=includi_non_attivi
    )
    periodi_target = _periodi_target(tipo, solo_periodo)

    risultato = RisultatoSync(
        tipo=tipo,
        anno=anno,
        periodi=[p for p, _ in periodi_target],
        clienti_applicabili=len(applicabili),
    )

    with transaction.atomic():
        for anag in applicabili:
            for periodo, scad in periodi_target:
                data_scadenza = scad.calcola_data_scadenza(anno) if scad else None
                if dry_run:
                    esiste = Adempimento.objects.filter(
                        anagrafica=anag, tipo=tipo,
                        anno_fiscale=anno, periodo=periodo,
                    ).exists()
                    if esiste:
                        risultato.gia_esistenti += 1
                    else:
                        risultato.creati += 1
                    continue

                _obj, created = Adempimento.objects.get_or_create(
                    anagrafica=anag,
                    tipo=tipo,
                    anno_fiscale=anno,
                    periodo=periodo,
                    defaults={
                        "data_scadenza": data_scadenza,
                        "stato": StatoAdempimento.DA_FARE,
                    },
                )
                if created:
                    risultato.creati += 1
                else:
                    risultato.gia_esistenti += 1

        # Righe obsolete: righe in stati lavorabili che non sarebbero piu'
        # applicabili oggi. Solo per i (anno, periodi) trattati in questo
        # sync — sennò mostreremmo obsoleti di altri periodi.
        if non_applicabili_ids:
            obsoleti_qs = Adempimento.objects.filter(
                is_deleted=False,
                tipo=tipo,
                anno_fiscale=anno,
                anagrafica_id__in=non_applicabili_ids,
                stato__in=list(STATI_LAVORABILI),
            )
            if solo_periodo is not None:
                obsoleti_qs = obsoleti_qs.filter(periodo=solo_periodo)
            elif periodi_target:
                # Tipo annuale: periodo IS NULL; tipo periodico: lista periodi.
                periodi_int = [p for p, _ in periodi_target if p is not None]
                if periodi_int:
                    obsoleti_qs = obsoleti_qs.filter(periodo__in=periodi_int)
                else:
                    obsoleti_qs = obsoleti_qs.filter(periodo__isnull=True)
            risultato.obsoleti_pks = list(obsoleti_qs.values_list("pk", flat=True))

        if dry_run:
            transaction.set_rollback(True)

    return risultato


def conta_obsoleti(
    tipo: TipoAdempimentoCatalogo,
    anno: int,
    periodo: int | None = None,
) -> Iterable[Adempimento]:
    """Ritorna le righe oggi obsolete per (tipo, anno, periodo).

    Usata dalla vista per mostrare il pannello "Non piu' applicabili" senza
    rifare la sync. Funzione "cheap": valuta le regole su una sola passata
    delle anagrafiche con almeno una riga in stato lavorabile.
    """
    regole = [r for r in tipo.regole.all() if r.attiva]
    if not regole:
        return Adempimento.objects.none()

    base = Adempimento.objects.filter(
        is_deleted=False,
        tipo=tipo,
        anno_fiscale=anno,
        stato__in=list(STATI_LAVORABILI),
    ).select_related("anagrafica").prefetch_related("anagrafica__categorie")
    if periodo is not None:
        base = base.filter(periodo=periodo)

    obsoleti = []
    for riga in base:
        if not all(r.valuta(riga.anagrafica) for r in regole):
            obsoleti.append(riga)
    return obsoleti
