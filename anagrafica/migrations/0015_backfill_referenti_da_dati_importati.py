"""Backfill referenti dai DatoImportato pending/legacy.

Converte le righe `importazione.DatoImportato` con chiavi note in righe
`anagrafica.AnagraficaReferenteStudio(utente=None, nome_grezzo=...)`:

- `referente_contabilita_pending` / `referente_consulenza_pending`: prodotte
  dal nuovo wizard quando il nome dell'addetto non si risolveva a un utente
  (versione pre-#41, prima di rendere `utente` nullable).
- `addetto_contabilita` / `addetto_consulenza`: prodotte dal vecchio mapping
  `extra:addetto_*`. Backfill dello storico.

Idempotente: non ricrea referenti se gia' presente uno con stesso
(anagrafica, ruolo, nome_grezzo, data_fine=NULL).

Dopo la conversione, le righe DatoImportato vengono rinominate a
`<chiave>_risolto` per audit (non vengono cancellate per non perdere la
fonte di sessione).
"""
from datetime import date

from django.db import migrations


PENDING_KEY_TO_RUOLO: dict[str, str] = {
    "referente_contabilita_pending": "referente_contabilita",
    "referente_consulenza_pending": "referente_consulenza",
    "addetto_contabilita": "referente_contabilita",
    "addetto_consulenza": "referente_consulenza",
}


def backfill(apps, schema_editor):
    DatoImportato = apps.get_model("importazione", "DatoImportato")
    Referente = apps.get_model("anagrafica", "AnagraficaReferenteStudio")

    dati = (
        DatoImportato.objects.filter(chiave__in=PENDING_KEY_TO_RUOLO.keys())
        .select_related("anagrafica")
    )
    oggi = date.today()
    for d in dati.iterator():
        valore = (d.valore or "").strip()
        if not valore:
            continue
        ruolo = PENDING_KEY_TO_RUOLO[d.chiave]
        gia_presente = Referente.objects.filter(
            anagrafica=d.anagrafica,
            ruolo=ruolo,
            nome_grezzo__iexact=valore,
            data_fine__isnull=True,
        ).exists()
        if not gia_presente:
            Referente.objects.create(
                anagrafica=d.anagrafica,
                utente=None,
                nome_grezzo=valore,
                ruolo=ruolo,
                data_inizio=oggi,
            )
        # Audit: rinomina la chiave invece di cancellare, cosi' resta
        # traccia della sessione di import.
        if not d.chiave.endswith("_risolto"):
            d.chiave = f"{d.chiave}_risolto"
            d.save(update_fields=["chiave", "updated_at"])


def unbackfill(apps, schema_editor):
    # Reverse: ripristina le chiavi dei DatoImportato + rimuove i referenti
    # creati senza utente. Best-effort: i referenti potrebbero essere stati
    # modificati a mano nel frattempo.
    DatoImportato = apps.get_model("importazione", "DatoImportato")
    Referente = apps.get_model("anagrafica", "AnagraficaReferenteStudio")

    for original, _ in PENDING_KEY_TO_RUOLO.items():
        risolta = f"{original}_risolto"
        DatoImportato.objects.filter(chiave=risolta).update(chiave=original)

    Referente.objects.filter(utente__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0014_referente_nome_grezzo"),
        ("importazione", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
