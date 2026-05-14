# Crea il modello TextChoiceLabel e popola con i 21 valori canonici
# delle TextChoices del modello Anagrafica. Da quel momento le label
# sono modificabili da admin.

from django.db import migrations, models


# (field, codice, label_default, ordine)
SEED = [
    # tipo_soggetto (9)
    ("tipo_soggetto", "PF",     "Persona fisica",    1),
    ("tipo_soggetto", "PROFEX", "Professionista",    2),
    ("tipo_soggetto", "DI",     "Ditta individuale", 3),
    ("tipo_soggetto", "SNC",    "SNC",               10),
    ("tipo_soggetto", "SAS",    "SAS",               11),
    ("tipo_soggetto", "SRL",    "SRL",               12),
    ("tipo_soggetto", "SPA",    "SPA",               13),
    ("tipo_soggetto", "ASS",    "Associazione",      20),
    ("tipo_soggetto", "FALL",   "Fallimento",        30),
    # stato (3)
    ("stato", "attivo",  "Attivo",  1),
    ("stato", "sospeso", "Sospeso", 2),
    ("stato", "cessato", "Cessato", 3),
    # regime_contabile (4)
    ("regime_contabile", "ordinario",       "Ordinario",       1),
    ("regime_contabile", "semplificato",    "Semplificato",    2),
    ("regime_contabile", "forfettario",     "Forfettario",     3),
    ("regime_contabile", "non_applicabile", "Non applicabile", 9),
    # periodicita_iva (3)
    ("periodicita_iva", "mensile",      "Mensile",      1),
    ("periodicita_iva", "trimestrale",  "Trimestrale",  2),
    ("periodicita_iva", "non_soggetto", "Non soggetto", 3),
    # contabilita (2)
    ("contabilita", "interna", "Interna (tenuta dallo studio)", 1),
    ("contabilita", "esterna", "Esterna",                       2),
]


def seed(apps, schema_editor):
    Model = apps.get_model("anagrafica", "TextChoiceLabel")
    for field, codice, label, ordine in SEED:
        Model.objects.update_or_create(
            field=field, codice=codice,
            defaults={"label": label, "ordine": ordine},
        )


def unseed(apps, schema_editor):
    apps.get_model("anagrafica", "TextChoiceLabel").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0007_rename_anagrafica_progr_log_idx_anagrafica__anagraf_a1b1c6_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="TextChoiceLabel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field", models.CharField(
                    max_length=30, db_index=True,
                    choices=[
                        ("tipo_soggetto", "Tipo soggetto"),
                        ("stato", "Stato anagrafica"),
                        ("regime_contabile", "Regime contabile"),
                        ("periodicita_iva", "Periodicità IVA"),
                        ("contabilita", "Tenuta contabilità"),
                    ],
                    help_text="Campo dell'anagrafica a cui si applica l'override.",
                )),
                ("codice", models.CharField(
                    max_length=30, db_index=True,
                    help_text="Codice del valore (es. 'PF', 'attivo'). Stabile, non rinominare.",
                )),
                ("label", models.CharField(
                    max_length=80,
                    help_text="Etichetta mostrata all'utente (modificabile liberamente).",
                )),
                ("descrizione", models.CharField(blank=True, max_length=200)),
                ("ordine", models.PositiveSmallIntegerField(
                    default=0,
                    help_text="Ordine di visualizzazione nei dropdown (asc).",
                )),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Etichetta valore (override)",
                "verbose_name_plural": "Etichette valori (override)",
                "ordering": ("field", "ordine", "label"),
            },
        ),
        migrations.AddConstraint(
            model_name="textchoicelabel",
            constraint=models.UniqueConstraint(
                fields=("field", "codice"),
                name="uniq_textchoicelabel_field_codice",
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]
