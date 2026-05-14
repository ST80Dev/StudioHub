"""Aggiunge `abbreviazione` e `ha_vista_dedicata` a TipoAdempimentoCatalogo.

- `abbreviazione`: sigla breve per sidebar/badge (es. "LIPE", "BILUE", "F24"),
  liberamente modificabile dall'utente. Disaccoppia l'etichetta visiva dal
  `codice` (identificativo tecnico stabile).
- `ha_vista_dedicata`: flag che marca i tipi con una pagina dedicata (oggi:
  la lista trimestrale LIPE). I tipi con questo flag compaiono come link
  diretto in sidebar e sono raggiungibili via `/adempimenti/tipo/<pk>/`.

Backfill idempotente: la riga LIPE (qualunque sia il suo `codice` attuale —
"liquidazione-iva-trimestrale" o "LIPE" — perché in produzione potrebbe
essere stato rinominato a mano) riceve `abbreviazione="LIPE"` e
`ha_vista_dedicata=True`. Riconosciuta per periodicità trimestrale + presenza
delle scadenze seedate dalla 0006, in modo da non dipendere dal codice.
"""
from django.db import migrations, models


def backfill_lipe(apps, schema_editor):
    TipoAdempimentoCatalogo = apps.get_model("adempimenti", "TipoAdempimentoCatalogo")

    # Match resiliente al rename del codice: cerchiamo per codice canonico,
    # poi per codice "LIPE" (caso rinomina a mano), poi per fallback su
    # periodicità trimestrale (se in produzione l'utente ha rinominato in
    # qualcosa di diverso).
    candidati = list(
        TipoAdempimentoCatalogo.objects.filter(
            codice__in=["liquidazione-iva-trimestrale", "LIPE", "lipe"]
        )
    )
    if not candidati:
        candidati = list(
            TipoAdempimentoCatalogo.objects.filter(periodicita="trimestrale")
        )

    for tipo in candidati:
        changed = False
        if not tipo.abbreviazione:
            tipo.abbreviazione = "LIPE"
            changed = True
        if not tipo.ha_vista_dedicata:
            tipo.ha_vista_dedicata = True
            changed = True
        if changed:
            tipo.save(update_fields=["abbreviazione", "ha_vista_dedicata"])


def unbackfill_lipe(apps, schema_editor):
    # Reverse no-op: i campi vengono droppati comunque dall'AlterField inverso.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0009_stati_catalogo"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipoadempimentocatalogo",
            name="abbreviazione",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Sigla breve mostrata in sidebar/badge/UI compatta "
                    "(es. 'LIPE', 'BILUE', 'F24'). Liberamente modificabile. "
                    "Se vuota, viene usato il fallback sulle prime lettere "
                    "della denominazione."
                ),
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="tipoadempimentocatalogo",
            name="ha_vista_dedicata",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Se True, il tipo compare con un link diretto in sidebar "
                    "e apre la pagina dedicata (layout per periodo). "
                    "Al momento la vista dedicata supporta solo periodicità "
                    "trimestrale."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="tipoadempimentocatalogo",
            name="codice",
            field=models.SlugField(
                help_text=(
                    "Identificativo tecnico stabile, usato dalle migration di "
                    "seed e come opzione di default per il comando CLI "
                    "`genera_adempimenti --tipo <codice>`. NON viene usato "
                    "negli URL (le pagine dedicate referenziano il tipo per "
                    "PK). Modificabile, ma se lo rinomini ricorda di "
                    "aggiornare eventuali script/CLI che lo passano come "
                    "argomento."
                ),
                max_length=40,
                unique=True,
            ),
        ),
        migrations.RunPython(backfill_lipe, unbackfill_lipe),
    ]
