"""Risolve i referenti studio rimasti "pending" da import passati.

Cerca tutte le righe `DatoImportato` con chiavi note (vedi `PENDING_KEYS`):
- `referente_contabilita_pending` / `referente_consulenza_pending`:
  prodotte dal nuovo wizard quando il nome dell'addetto non si risolve a un
  `UtenteStudio` (es. utenti non ancora popolati al momento dell'import).
- `addetto_contabilita` / `addetto_consulenza`:
  prodotte dal vecchio mapping `extra:addetto_*`. Backfill dello storico.

Per ogni riga: prova a risolvere il valore (free-text) a un `UtenteStudio`
con la stessa strategia dell'apply (vedi `importazione.apply._match_utente`),
ed eventualmente con una **mappa di alias** passata via --alias-file
(JSON `{"nome cosi'": "username"}`) per i casi sporchi.

Modalita':
  --dry-run            : non scrive, solo riepilogo.
  --alias-file PATH    : JSON {nome_grezzo: username_o_id_utente}.
  --rimuovi-risolti    : cancella il DatoImportato dopo aver creato il referente.
                         Default: marca la chiave come `<chiave>_risolto` per
                         tenere traccia dell'origine (audit).

Idempotente: una seconda esecuzione non duplica i referenti.
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


# Mappa chiave DatoImportato -> ruolo. Include le chiavi legacy del vecchio
# mapping (`extra:addetto_*`) per il backfill dello storico.
PENDING_KEYS: dict[str, str] = {
    "referente_contabilita_pending": RuoloReferenteStudio.REFERENTE_CONTABILITA,
    "referente_consulenza_pending": RuoloReferenteStudio.REFERENTE_CONSULENZA,
    "addetto_contabilita": RuoloReferenteStudio.REFERENTE_CONTABILITA,
    "addetto_consulenza": RuoloReferenteStudio.REFERENTE_CONSULENZA,
}


class Command(BaseCommand):
    help = (
        "Risolve i referenti studio salvati come DatoImportato "
        "(pending o legacy) creando le righe AnagraficaReferenteStudio."
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

        dati = DatoImportato.objects.filter(chiave__in=PENDING_KEYS.keys()).select_related("anagrafica")
        totale = dati.count()
        if totale == 0:
            self.stdout.write(self.style.WARNING("Nessun referente pending trovato."))
            return

        self.stdout.write(f"Trovate {totale} righe da processare.")
        if dry:
            self.stdout.write(self.style.NOTICE("Modalita' dry-run: niente scritture."))

        stats = Counter()
        non_risolti: list[tuple[int, str, str]] = []  # (riga.id, chiave, valore)

        for d in dati:
            ruolo = PENDING_KEYS[d.chiave]
            valore = (d.valore or "").strip()
            if not valore:
                stats["vuoti"] += 1
                continue

            utente = alias_map.get(valore.lower()) or _match_utente(valore)
            if utente is None:
                stats["non_risolti"] += 1
                non_risolti.append((d.pk, d.chiave, valore))
                continue

            if dry:
                stats["risolvibili"] += 1
                continue

            # Scrittura: idempotente, in transazione per singola riga.
            try:
                with transaction.atomic():
                    gia_attivo = AnagraficaReferenteStudio.objects.filter(
                        anagrafica=d.anagrafica,
                        utente=utente,
                        ruolo=ruolo,
                        data_fine__isnull=True,
                    ).exists()
                    if not gia_attivo:
                        AnagraficaReferenteStudio.objects.create(
                            anagrafica=d.anagrafica,
                            utente=utente,
                            ruolo=ruolo,
                            data_inizio=timezone.now().date(),
                        )
                        stats["creati"] += 1
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

        # Riepilogo
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Riepilogo:"))
        for k in ("creati", "gia_presenti", "risolvibili", "non_risolti",
                  "vuoti", "errori"):
            if stats[k]:
                self.stdout.write(f"  {k}: {stats[k]}")

        if non_risolti:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"Non risolti ({len(non_risolti)}). Esempi:"
            ))
            for pk, chiave, valore in non_risolti[:20]:
                self.stdout.write(f"  DatoImportato#{pk} [{chiave}]: {valore!r}")
            if len(non_risolti) > 20:
                self.stdout.write(f"  … e altri {len(non_risolti) - 20}.")
            self.stdout.write(
                "Crea gli utenti in admin o passa --alias-file per mapparli."
            )


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
