"""Risolve i referenti studio rimasti "pending" provando ad associarli a un
UtenteStudio reale.

Sorgenti processate:

1. `AnagraficaReferenteStudio` con `utente IS NULL` (origine principale dopo
   la migrazione 0014/0015 di anagrafica): valorizza `utente` quando il match
   sul `nome_grezzo` riesce e svuota `nome_grezzo`.

2. `DatoImportato` con chiavi legacy `referente_*_pending` o
   `addetto_contabilita` / `addetto_consulenza` (per ambienti che non hanno
   ancora ricevuto la 0015 o che ricevono nuovi import su versioni in fase
   di rollout). Crea/aggiorna il referente corrispondente e rinomina la
   chiave a `<chiave>_risolto` per audit.

Strategia di match: vedi `importazione.apply._match_utente` (username,
"Nome Cognome", solo cognome). Per i casi sporchi si passa un
`--alias-file` JSON `{"nome cosi'": "username o id"}`.

Idempotente: una seconda esecuzione non duplica referenti.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from anagrafica.models import AnagraficaReferenteStudio, RuoloReferenteStudio
from importazione.apply import _match_utente
from importazione.models import DatoImportato


# Mappa chiave DatoImportato legacy -> ruolo. Include sia le chiavi `_pending`
# del nuovo wizard sia le `addetto_*` del vecchio mapping `extra:addetto_*`.
LEGACY_DATO_KEYS: dict[str, str] = {
    "referente_contabilita_pending": RuoloReferenteStudio.REFERENTE_CONTABILITA,
    "referente_consulenza_pending": RuoloReferenteStudio.REFERENTE_CONSULENZA,
    "addetto_contabilita": RuoloReferenteStudio.REFERENTE_CONTABILITA,
    "addetto_consulenza": RuoloReferenteStudio.REFERENTE_CONSULENZA,
}


class Command(BaseCommand):
    help = (
        "Risolve i referenti studio rimasti pending: collega utenti reali "
        "alle righe AnagraficaReferenteStudio non agganciate (utente=NULL) "
        "e converte i vecchi DatoImportato legacy in altrettante righe referente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Non scrive nulla. Mostra solo il riepilogo.",
        )
        parser.add_argument(
            "--alias-file", type=str, default=None,
            help='JSON {"nome": "username_o_id"} per casi non risolvibili automaticamente.',
        )
        parser.add_argument(
            "--rimuovi-risolti", action="store_true",
            help="Elimina i DatoImportato risolti. Default: rinomina chiave a `_risolto`.",
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        rimuovi = opts["rimuovi_risolti"]
        alias_path = opts["alias_file"]

        alias_map = _load_alias_map(alias_path) if alias_path else {}

        stats: Counter = Counter()
        non_risolti: list[str] = []

        self._risolvi_referenti_raw(alias_map, dry, stats, non_risolti)
        self._risolvi_dato_importato_legacy(alias_map, dry, rimuovi, stats, non_risolti)

        if not stats and not non_risolti:
            self.stdout.write(self.style.WARNING("Nessun referente pending trovato."))
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Riepilogo:"))
        for k in ("associati", "creati_da_legacy", "gia_presenti",
                  "risolvibili", "non_risolti", "vuoti", "errori"):
            if stats[k]:
                self.stdout.write(f"  {k}: {stats[k]}")

        if non_risolti:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"Non risolti ({len(non_risolti)}). Esempi:"
            ))
            for desc in non_risolti[:20]:
                self.stdout.write(f"  {desc}")
            if len(non_risolti) > 20:
                self.stdout.write(f"  … e altri {len(non_risolti) - 20}.")
            self.stdout.write(
                "Crea gli utenti in admin o passa --alias-file per mapparli."
            )

    # ----------------------------------------------------------------------

    def _risolvi_referenti_raw(self, alias_map, dry, stats, non_risolti):
        """Processa AnagraficaReferenteStudio con utente=NULL: aggancia
        l'utente reale, svuota `nome_grezzo` e lascia la riga in vita."""
        qs = (
            AnagraficaReferenteStudio.objects
            .filter(utente__isnull=True, data_fine__isnull=True)
            .select_related("anagrafica")
        )
        for ref in qs.iterator():
            nome = (ref.nome_grezzo or "").strip()
            if not nome:
                stats["vuoti"] += 1
                continue

            utente = alias_map.get(nome.lower()) or _match_utente(nome)
            if utente is None:
                stats["non_risolti"] += 1
                non_risolti.append(
                    f"Ref#{ref.pk} [{ref.get_ruolo_display()}] '{nome}' "
                    f"({ref.anagrafica.denominazione})"
                )
                continue

            if dry:
                stats["risolvibili"] += 1
                continue

            try:
                with transaction.atomic():
                    duplicato = (
                        AnagraficaReferenteStudio.objects
                        .filter(
                            anagrafica=ref.anagrafica, utente=utente,
                            ruolo=ref.ruolo, data_fine__isnull=True,
                        )
                        .exclude(pk=ref.pk).exists()
                    )
                    if duplicato:
                        # Esiste gia' un referente attivo con quell'utente:
                        # chiudo la riga raw per non duplicare.
                        ref.data_fine = timezone.now().date()
                        ref.save(update_fields=["data_fine"])
                        stats["gia_presenti"] += 1
                    else:
                        ref.utente = utente
                        ref.nome_grezzo = ""
                        ref.save(update_fields=["utente", "nome_grezzo"])
                        stats["associati"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["errori"] += 1
                self.stderr.write(f"Errore su Ref#{ref.pk}: {exc}")

    def _risolvi_dato_importato_legacy(
        self, alias_map, dry, rimuovi, stats, non_risolti,
    ):
        """Processa i DatoImportato legacy (chiavi note in LEGACY_DATO_KEYS).
        Crea un referente per ognuno: con utente reale se il nome matcha,
        altrimenti con `nome_grezzo` valorizzato (come fa la 0015)."""
        dati = (
            DatoImportato.objects.filter(chiave__in=LEGACY_DATO_KEYS.keys())
            .select_related("anagrafica")
        )
        oggi = timezone.now().date()
        for d in dati.iterator():
            ruolo = LEGACY_DATO_KEYS[d.chiave]
            valore = (d.valore or "").strip()
            if not valore:
                stats["vuoti"] += 1
                continue

            utente = alias_map.get(valore.lower()) or _match_utente(valore)

            if dry:
                if utente is not None:
                    stats["risolvibili"] += 1
                else:
                    stats["non_risolti"] += 1
                    non_risolti.append(
                        f"DatoImportato#{d.pk} [{d.chiave}] '{valore}' "
                        f"({d.anagrafica.denominazione})"
                    )
                continue

            try:
                with transaction.atomic():
                    if utente is not None:
                        gia_presente = AnagraficaReferenteStudio.objects.filter(
                            anagrafica=d.anagrafica, utente=utente, ruolo=ruolo,
                            data_fine__isnull=True,
                        ).exists()
                        if not gia_presente:
                            AnagraficaReferenteStudio.objects.create(
                                anagrafica=d.anagrafica, utente=utente,
                                ruolo=ruolo, data_inizio=oggi,
                            )
                            stats["associati"] += 1
                        else:
                            stats["gia_presenti"] += 1
                    else:
                        gia_presente = AnagraficaReferenteStudio.objects.filter(
                            anagrafica=d.anagrafica, utente__isnull=True,
                            ruolo=ruolo, nome_grezzo__iexact=valore,
                            data_fine__isnull=True,
                        ).exists()
                        if not gia_presente:
                            AnagraficaReferenteStudio.objects.create(
                                anagrafica=d.anagrafica, utente=None,
                                nome_grezzo=valore, ruolo=ruolo, data_inizio=oggi,
                            )
                            stats["creati_da_legacy"] += 1
                        else:
                            stats["gia_presenti"] += 1

                    if rimuovi:
                        d.delete()
                    else:
                        d.chiave = f"{d.chiave}_risolto"
                        d.save(update_fields=["chiave", "updated_at"])
            except Exception as exc:  # noqa: BLE001
                stats["errori"] += 1
                self.stderr.write(f"Errore su DatoImportato#{d.pk}: {exc}")


def _load_alias_map(path: str) -> dict[str, object]:
    """Carica un JSON {nome_grezzo: username|id}. Le chiavi sono normalizzate
    a lowercase per match case-insensitive con il valore in DatoImportato."""
    p = Path(path)
    if not p.exists():
        raise CommandError(f"Alias file non trovato: {path}")
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise CommandError(f"Alias file non valido: {exc}")
    if not isinstance(raw, dict):
        raise CommandError("Alias file deve essere un oggetto JSON {nome: utente}.")

    User = get_user_model()
    out: dict[str, object] = {}
    not_found: list[str] = []
    for nome, ident in raw.items():
        if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
            u = User.objects.filter(pk=int(ident), is_active=True).first()
        else:
            u = User.objects.filter(username__iexact=str(ident), is_active=True).first()
        if u is None:
            not_found.append(f"{nome} -> {ident}")
        else:
            out[str(nome).strip().lower()] = u
    if not_found:
        raise CommandError(
            "Utenti non trovati per: " + ", ".join(not_found)
        )
    return out
