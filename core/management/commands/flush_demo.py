"""Rimuove i dati demo (is_demo=True) senza toccare dati reali.

Ordine di cancellazione (rispetta i FK PROTECT):

  1. StepCompletato, ProgressioneContabilita/Log → cascade da Adempimento/Anagrafica
  2. Adempimento con is_demo=True (o su anagrafiche demo)
  3. AnagraficaReferenteStudio, AnagraficaLegame → cascade da Anagrafica
  4. Anagrafica con is_demo=True
  5. (opzionale, --include-users) UtenteStudio con is_demo=True

Preserva SEMPRE:
  - Tutti gli utenti NON marcati demo (personale reale, admin, superuser)
  - AreaAziendale, TipoAdempimentoCatalogo, ScadenzaPeriodo, ChecklistStep,
    RegolaApplicabilita (configurazione)
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from adempimenti.models import Adempimento
from anagrafica.models import Anagrafica

User = get_user_model()


class Command(BaseCommand):
    help = "Rimuove i record is_demo=True. Preserva utenti reali e configurazione."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-users",
            action="store_true",
            help=(
                "Rimuove anche gli utenti demo. "
                "Default: conserva anche gli utenti demo (potresti averli rinominati)."
            ),
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Salta la conferma interattiva.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra solo cosa verrebbe cancellato, non esegue.",
        )

    def handle(self, *args, **opts):
        anagrafiche_qs = Anagrafica.objects.filter(is_demo=True)
        adempimenti_qs = Adempimento.objects.filter(is_demo=True)
        # Adempimenti orfani (anagrafica non demo ma adempimento marcato demo)
        # vengono comunque presi dal filtro sopra.

        utenti_demo_qs = User.objects.filter(is_demo=True)

        n_anag = anagrafiche_qs.count()
        n_adem = adempimenti_qs.count()
        n_user = utenti_demo_qs.count()

        self.stdout.write(self.style.MIGRATE_HEADING("Oggetto della pulizia:"))
        self.stdout.write(f"  Anagrafiche demo:       {n_anag}")
        self.stdout.write(f"  Adempimenti demo:       {n_adem}")
        if opts["include_users"]:
            self.stdout.write(f"  Utenti demo:            {n_user}")
        else:
            self.stdout.write(
                f"  Utenti demo:            {n_user}  (PRESERVATI, usa --include-users)"
            )

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: nessuna modifica."))
            return

        if n_anag + n_adem + (n_user if opts["include_users"] else 0) == 0:
            self.stdout.write(self.style.SUCCESS("Nessun dato demo da rimuovere."))
            return

        if not opts["yes"]:
            conferma = input("Confermi la cancellazione? [y/N] ").strip().lower()
            if conferma not in ("y", "yes", "s", "si", "sì"):
                self.stdout.write("Annullato.")
                return

        with transaction.atomic():
            # 1) Tutti gli adempimenti su anagrafiche demo (anche se non
            # marcati demo loro stessi): Adempimento.anagrafica è PROTECT
            # e senza questo il delete dell'anagrafica fallirebbe.
            Adempimento.objects.filter(anagrafica__is_demo=True).delete()
            # 2) Adempimenti demo su anagrafiche reali (caso limite).
            adempimenti_qs.delete()
            # 3) Anagrafiche demo: cascade porta via referenti e legami.
            anagrafiche_qs.delete()

            if opts["include_users"]:
                # A questo punto non ci sono più FK PROTECT verso questi utenti
                # (referenti e adempimenti demo sono stati rimossi).
                # Se un utente demo è referente di un'anagrafica REALE o
                # responsabile di un adempimento REALE, il delete fallirà:
                # in quel caso è giusto, perché significa che l'utente è stato
                # promosso a "reale" di fatto e non va cancellato.
                try:
                    utenti_demo_qs.delete()
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Impossibile rimuovere tutti gli utenti demo: {e}\n"
                            "Probabilmente alcuni sono referenti/responsabili "
                            "di dati reali. Togli prima il flag is_demo dove serve."
                        )
                    )
                    raise

        self.stdout.write(self.style.SUCCESS("Flush demo completato."))
