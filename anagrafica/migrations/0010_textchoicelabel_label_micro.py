"""Aggiunge `label_micro` (sigla 3 char) a TextChoiceLabel.

3 livelli di etichetta complessivi:
- `codice`: identificativo stabile, minuscolo (vedi 0009)
- `label_micro`: sigla 3 char per celle dense ("INT", "EST", "PF", "SRL")
- `label`: estesa per form/dropdown ("Interna (tenuta dallo studio)")

Per i 21 valori canonici si popola un seed esplicito qui: il fallback
automatico (prime 3 lettere upper della label) andrebbe bene per alcuni
campi ma non per altri (es. tipo_soggetto: forme giuridiche hanno sigle
canoniche di 2-4 char). Per coerenza meglio seed esplicito.
"""

from django.db import migrations, models


# (field, codice_lower, label_micro)
SEED = [
    # tipo_soggetto: sigle giuridiche canoniche
    ("tipo_soggetto", "pf",     "PF"),
    ("tipo_soggetto", "profex", "PRF"),
    ("tipo_soggetto", "di",     "DI"),
    ("tipo_soggetto", "snc",    "SNC"),
    ("tipo_soggetto", "sas",    "SAS"),
    ("tipo_soggetto", "srl",    "SRL"),
    ("tipo_soggetto", "spa",    "SPA"),
    ("tipo_soggetto", "ass",    "ASS"),
    ("tipo_soggetto", "fall",   "FAL"),
    # stato
    ("stato", "attivo",  "ATT"),
    ("stato", "sospeso", "SOS"),
    ("stato", "cessato", "CES"),
    # regime_contabile
    ("regime_contabile", "ordinario",       "ORD"),
    ("regime_contabile", "semplificato",    "SEM"),
    ("regime_contabile", "forfettario",     "FOR"),
    ("regime_contabile", "non_applicabile", "N/A"),
    # periodicita_iva
    ("periodicita_iva", "mensile",      "MEN"),
    ("periodicita_iva", "trimestrale",  "TRI"),
    ("periodicita_iva", "non_soggetto", "N/S"),
    # contabilita
    ("contabilita", "interna", "INT"),
    ("contabilita", "esterna", "EST"),
]


def seed(apps, schema_editor):
    Model = apps.get_model("anagrafica", "TextChoiceLabel")
    for field, codice, micro in SEED:
        Model.objects.filter(field=field, codice=codice).update(
            label_micro=micro,
        )


def unseed(apps, schema_editor):
    # Reverse: svuota il campo (resetta al fallback automatico).
    apps.get_model("anagrafica", "TextChoiceLabel").objects.update(
        label_micro="",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0009_tipo_soggetto_lowercase"),
    ]

    operations = [
        migrations.AddField(
            model_name="textchoicelabel",
            name="label_micro",
            field=models.CharField(
                blank=True,
                max_length=3,
                help_text=(
                    "Sigla a 3 caratteri per badge e celle dense (es. 'INT', "
                    "'PF'). Se vuota viene generato un fallback dalle prime "
                    "3 lettere di `label`."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="textchoicelabel",
            name="label",
            field=models.CharField(
                max_length=80,
                help_text="Etichetta estesa (form, dropdown filtri).",
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]
