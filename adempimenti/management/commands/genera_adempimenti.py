"""Genera in massa righe Adempimento per un tipo + anno fiscale.

Wrapper CLI sopra `adempimenti.services.sincronizza_adempimenti`. Stessa
logica usata anche dal bottone "Crea elenco" / "Aggiorna elenco" nella
vista LIPE, cosi' i due ingressi non possono divergere nel tempo.

Esempi:

    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026
    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026 --solo-periodo 1
    python manage.py genera_adempimenti --tipo liquidazione-iva-trimestrale --anno 2026 --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from adempimenti.models import TipoAdempimentoCatalogo
from adempimenti.services import sincronizza_adempimenti


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
        try:
            tipo = TipoAdempimentoCatalogo.objects.prefetch_related(
                "regole", "scadenze",
            ).get(codice=codice)
        except TipoAdempimentoCatalogo.DoesNotExist:
            raise CommandError(f"Tipo adempimento '{codice}' non trovato.")

        regole_attive = [r for r in tipo.regole.all() if r.attiva]
        if not regole_attive:
            raise CommandError(
                f"Tipo '{codice}' senza regole attive: nessun cliente verrebbe selezionato."
            )

        risultato = sincronizza_adempimenti(
            tipo,
            opts["anno"],
            solo_periodo=opts["solo_periodo"],
            dry_run=opts["dry_run"],
            includi_non_attivi=opts["includi_non_attivi"],
        )

        prefix = "[DRY-RUN] " if opts["dry_run"] else ""
        self.stdout.write(self.style.NOTICE(
            f"Tipo: {tipo.denominazione} · anno {risultato.anno} · "
            f"{risultato.clienti_applicabili} clienti applicabili · "
            f"{len(risultato.periodi)} periodo/i"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Creati: {risultato.creati} · "
            f"Già esistenti: {risultato.gia_esistenti} · "
            f"Obsoleti: {len(risultato.obsoleti_pks)}"
        ))
