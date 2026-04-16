"""Popola il database con dati di test riproducibili.

Tutti i record creati vengono marcati con `is_demo=True` sulle tabelle
radice (UtenteStudio, Anagrafica, Adempimento) e possono essere rimossi
in modo chirurgico con `flush_demo` senza toccare i dati reali.

Esempi d'uso:

    # Scenario tipico: riusa utenti già presenti, crea 30 clienti e adempimenti.
    python manage.py seed_demo

    # Crea anche 6 utenti demo (oltre a usare quelli reali se ci sono).
    python manage.py seed_demo --create-users

    # Ripartenza pulita: cancella prima i dati demo esistenti.
    python manage.py seed_demo --reset-demo

    # Parametri di volume.
    python manage.py seed_demo --clienti 50 --adempimenti-per-cliente 3
"""
from __future__ import annotations

import random
from datetime import date

import factory
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.factories import UtenteDemoFactory
from adempimenti.factories import AdempimentoBilancioUEFactory
from anagrafica.factories import (
    AnagraficaEntitaFactory,
    AnagraficaPFFactory,
    LegameFactory,
    ReferenteStudioFactory,
    _fake_codice_interno,
)
from anagrafica.models import (
    Anagrafica,
    RuoloReferenteStudio,
    TIPI_ENTITA,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Popola il DB con dati demo riproducibili (marcati is_demo=True)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clienti",
            type=int,
            default=30,
            help="Numero di anagrafiche demo da creare (default: 30).",
        )
        parser.add_argument(
            "--adempimenti-per-cliente",
            type=int,
            default=2,
            help="Adempimenti medi per cliente entità (default: 2).",
        )
        parser.add_argument(
            "--anno-inizio",
            type=int,
            default=2024,
            help="Primo anno fiscale da coprire (default: 2024).",
        )
        parser.add_argument(
            "--anno-fine",
            type=int,
            default=2025,
            help="Ultimo anno fiscale da coprire (default: 2025).",
        )
        parser.add_argument(
            "--create-users",
            action="store_true",
            help="Crea utenti demo oltre a riusare quelli esistenti.",
        )
        parser.add_argument(
            "--num-users",
            type=int,
            default=6,
            help="Utenti demo da creare se --create-users (default: 6).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Seed deterministico per la generazione (default: 42).",
        )
        parser.add_argument(
            "--reset-demo",
            action="store_true",
            help="Cancella i dati demo esistenti prima di popolare.",
        )

    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        factory.random.reseed_random(opts["seed"])

        if opts["reset_demo"]:
            self.stdout.write(self.style.WARNING("Reset dati demo in corso..."))
            from django.core.management import call_command

            call_command("flush_demo", "--yes", "--include-users")

        with transaction.atomic():
            utenti = self._ensure_users(
                create_new=opts["create_users"], n_new=opts["num_users"]
            )
            if not utenti:
                self.stdout.write(
                    self.style.ERROR(
                        "Nessun utente disponibile. Rilancia con --create-users "
                        "oppure crea prima utenti reali da admin."
                    )
                )
                return

            clienti = self._create_clienti(
                n=opts["clienti"], utenti=utenti
            )
            self._create_legami(clienti)
            self._create_adempimenti(
                clienti=clienti,
                utenti=utenti,
                media_per_cliente=opts["adempimenti_per_cliente"],
                anno_inizio=opts["anno_inizio"],
                anno_fine=opts["anno_fine"],
            )

        self.stdout.write(self.style.SUCCESS("Seed demo completato."))
        self._print_riepilogo()

    # ------------------------------------------------------------------ users

    def _ensure_users(self, *, create_new: bool, n_new: int):
        """Restituisce la lista di utenti usabili come referenti/responsabili.

        Riusa sempre gli utenti esistenti (demo o reali, non superuser).
        Se richiesto, aggiunge nuovi utenti demo.
        """
        esistenti = list(
            User.objects.filter(is_active=True).exclude(is_superuser=True)
        )
        creati = []
        if create_new:
            for _ in range(n_new):
                creati.append(UtenteDemoFactory())
            self.stdout.write(f"Creati {len(creati)} utenti demo.")
        utenti = esistenti + creati
        self.stdout.write(f"Utenti disponibili per il seed: {len(utenti)}.")
        return utenti

    # --------------------------------------------------------------- clienti

    def _create_clienti(self, *, n: int, utenti):
        clienti: list[Anagrafica] = []
        start_idx = self._next_codice_interno_idx()
        for i in range(n):
            codice = _fake_codice_interno(start_idx + i)
            # Mix: ~60% entità, ~40% persone fisiche.
            if random.random() < 0.6:
                cli = AnagraficaEntitaFactory(codice_interno=codice)
            else:
                cli = AnagraficaPFFactory(codice_interno=codice)
            self._assegna_referenti(cli, utenti)
            clienti.append(cli)
        self.stdout.write(f"Create {len(clienti)} anagrafiche demo.")
        return clienti

    def _next_codice_interno_idx(self) -> int:
        """Prossimo indice libero per il prefisso DEMO-NNNNN."""
        existing = Anagrafica.objects.filter(
            codice_interno__startswith="DEMO-"
        ).values_list("codice_interno", flat=True)
        max_idx = 0
        for cod in existing:
            try:
                idx = int(cod.split("-", 1)[1])
                max_idx = max(max_idx, idx)
            except (ValueError, IndexError):
                continue
        return max_idx + 1

    def _assegna_referenti(self, cli: Anagrafica, utenti):
        """Assegna un addetto contabilità e un responsabile consulenza."""
        for ruolo in (
            RuoloReferenteStudio.ADDETTO_CONTABILITA,
            RuoloReferenteStudio.RESPONSABILE_CONSULENZA,
        ):
            utente = random.choice(utenti)
            ReferenteStudioFactory(
                anagrafica=cli,
                utente=utente,
                ruolo=ruolo,
                principale=True,
            )

    # ---------------------------------------------------------------- legami

    def _create_legami(self, clienti):
        """Crea legami PF↔entità plausibili: per ciascuna entità aggancia
        1-2 PF come socio/amministratore/legale rappr.
        """
        entita = [c for c in clienti if c.tipo_soggetto in TIPI_ENTITA]
        pf = [c for c in clienti if c.tipo_soggetto not in TIPI_ENTITA]
        if not pf:
            return
        created = 0
        for ent in entita:
            k = random.choice([1, 1, 2])
            for persona in random.sample(pf, min(k, len(pf))):
                try:
                    LegameFactory(
                        anagrafica=ent,
                        anagrafica_collegata=persona,
                    )
                    created += 1
                except Exception:  # vincolo unique → skip
                    continue
        self.stdout.write(f"Creati {created} legami anagrafici.")

    # ----------------------------------------------------------- adempimenti

    def _create_adempimenti(
        self,
        *,
        clienti,
        utenti,
        media_per_cliente: int,
        anno_inizio: int,
        anno_fine: int,
    ):
        """Solo le SRL/SPA hanno Bilancio UE; gli altri tipi avranno adempimenti
        specifici quando saranno implementati (Fase 3 della roadmap).
        """
        from anagrafica.models import TIPI_BILANCIO_UE

        count = 0
        for cli in clienti:
            if cli.tipo_soggetto not in TIPI_BILANCIO_UE:
                continue
            anni = list(range(anno_inizio, anno_fine + 1))
            # Media targhettata: 1 riga per anno coperto, clamped a media_per_cliente.
            n = min(len(anni), max(1, media_per_cliente))
            for anno_fiscale in random.sample(anni, n):
                AdempimentoBilancioUEFactory(
                    anagrafica=cli,
                    anno_fiscale=anno_fiscale,
                    anno_esecuzione=anno_fiscale + 1,
                    responsabile=random.choice(utenti),
                )
                count += 1
        self.stdout.write(f"Creati {count} adempimenti Bilancio UE.")

    # ------------------------------------------------------------- riepilogo

    def _print_riepilogo(self):
        from adempimenti.models import Adempimento

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Stato attuale del DB:"))
        self.stdout.write(
            f"  Utenti totali:          {User.objects.count()} "
            f"(di cui demo: {User.objects.filter(is_demo=True).count()})"
        )
        self.stdout.write(
            f"  Anagrafiche totali:     {Anagrafica.objects.count()} "
            f"(di cui demo: {Anagrafica.objects.filter(is_demo=True).count()})"
        )
        self.stdout.write(
            f"  Adempimenti totali:     {Adempimento.objects.count()} "
            f"(di cui demo: {Adempimento.objects.filter(is_demo=True).count()})"
        )
