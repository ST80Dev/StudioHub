"""Genera in massa righe Adempimento per un tipo + anno fiscale.

Itera su tutte le anagrafiche attive non cancellate, valuta le regole di
applicabilità del tipo richiesto, e crea (idempotente, get_or_create per
tupla unique) una riga per ogni periodo previsto dal tipo.

Esempi:

    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026
    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026 --solo-periodo 1
    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026 --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from adempimenti.models import (
    Adempimento,
    StatoAdempimento,
    TipoAdempimentoCatalogo,
)
from anagrafica.models import Anagrafica


class Command(BaseCommand):
    help = "Genera Adempimento per il tipo/anno indicato sui clienti applicabili."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tipo", required=True,
            help="Codice (slug) del TipoAdempimentoCatalogo (es. liquidazione-iva-trimestrale).",
        )
        parser.add_argument(
            "--anno", required=True, type=int,
            help="Anno fiscale di competenza (es. 2026).",
        )
        parser.add_argument(
            "--solo-periodo", type=int, default=None,
            help="Limita a un singolo periodo (es. 1 per Q1). Default: tutti i periodi del tipo.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Non scrive nulla, mostra solo cosa farebbe.",
        )
        parser.add_argument(
            "--includi-non-attivi", action="store_true",
            help="Include anche anagrafiche con stato sospeso/cessato.",
        )

    def handle(self, *args, **opts):
        codice = opts["tipo"]
        anno = opts["anno"]
        solo_periodo = opts["solo_periodo"]
        dry_run = opts["dry_run"]
        includi_non_attivi = opts["includi_non_attivi"]

        try:
            tipo = TipoAdempimentoCatalogo.objects.prefetch_related(
                "regole", "scadenze",
            ).get(codice=codice)
        except TipoAdempimentoCatalogo.DoesNotExist:
            raise CommandError(f"Tipo adempimento '{codice}' non trovato.")

        regole = [r for r in tipo.regole.all() if r.attiva]
        if not regole:
            raise CommandError(
                f"Tipo '{codice}' senza regole attive: nessun cliente verrebbe selezionato."
            )

        scadenze = list(tipo.scadenze.all())
        if solo_periodo is not None:
            scadenze = [s for s in scadenze if s.periodo == solo_periodo]
            if not scadenze:
                raise CommandError(
                    f"Nessuna scadenza definita per il periodo {solo_periodo} sul tipo '{codice}'."
                )

        anagrafiche = Anagrafica.objects.filter(is_deleted=False).prefetch_related(
            "categorie"
        )
        if not includi_non_attivi:
            anagrafiche = anagrafiche.filter(stato="attivo")

        applicabili = []
        for anag in anagrafiche:
            if all(r.valuta(anag) for r in regole):
                applicabili.append(anag)

        self.stdout.write(
            self.style.NOTICE(
                f"Tipo: {tipo.denominazione} · anno {anno} · "
                f"{len(applicabili)} clienti applicabili · "
                f"{len(scadenze)} periodo/i"
            )
        )

        creati = 0
        gia_esistenti = 0
        with transaction.atomic():
            for anag in applicabili:
                for scad in scadenze:
                    data_scadenza = scad.calcola_data_scadenza(anno)
                    if dry_run:
                        if Adempimento.objects.filter(
                            anagrafica=anag, tipo=tipo,
                            anno_fiscale=anno, periodo=scad.periodo,
                        ).exists():
                            gia_esistenti += 1
                        else:
                            creati += 1
                        continue

                    _obj, created = Adempimento.objects.get_or_create(
                        anagrafica=anag,
                        tipo=tipo,
                        anno_fiscale=anno,
                        periodo=scad.periodo,
                        defaults={
                            "data_scadenza": data_scadenza,
                            "stato": StatoAdempimento.DA_FARE,
                        },
                    )
                    if created:
                        creati += 1
                    else:
                        gia_esistenti += 1

            if dry_run:
                # Annulla qualunque effetto collaterale (per sicurezza, anche
                # se qui non scriviamo).
                transaction.set_rollback(True)

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Creati: {creati} · Già esistenti: {gia_esistenti}"
        ))
