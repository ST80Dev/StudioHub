"""Estensioni per la Liquidazione IVA Trimestrale (LIPE) e affini.

- Nuovi stati: `chiusa` (rinomina di `controllato`), `fanno_loro`, `no_dati`.
- Nuovi campi su Adempimento: `data_invio`, `protocollo_invio`.
- Nuovi operatori regola: `diverso_da`, `non_in_lista`,
  `ha_categoria`, `non_ha_categoria`.
- Nuovo campo condizione: `categorie` (legge dal M2M).

Include data-migration che converte gli adempimenti con stato `controllato`
in `chiusa` (semantica equivalente: predisposto/pronto per invio).
"""
from django.db import migrations, models


NEW_STATI_CHOICES = [
    ("da_fare", "Da fare"),
    ("in_corso", "In corso"),
    ("chiusa", "Chiusa (predisposta)"),
    ("inviato", "Inviato"),
    ("fanno_loro", "Fanno loro"),
    ("no_dati", "No dati"),
]

NEW_OPERATORI_CHOICES = [
    ("uguale", "Uguale a"),
    ("diverso_da", "Diverso da"),
    ("in_lista", "In lista (valori separati da virgola)"),
    ("non_in_lista", "Non in lista (valori separati da virgola)"),
    ("vero", "Vero (campo booleano)"),
    ("falso", "Falso (campo booleano)"),
    ("ha_categoria", "Ha categoria (slug)"),
    ("non_ha_categoria", "Non ha categoria (slug)"),
]

NEW_CAMPI_CHOICES = [
    ("tipo_soggetto", "Tipo soggetto"),
    ("regime_contabile", "Regime contabile"),
    ("periodicita_iva", "Periodicità IVA"),
    ("sostituto_imposta", "Sostituto d'imposta"),
    ("iscritto_cciaa", "Iscritto CCIAA"),
    ("contabilita", "Contabilità (interna/esterna)"),
    ("categoria_professione", "Categoria professione (legacy)"),
    ("categorie", "Categorie (tag)"),
]


def rinomina_controllato_in_chiusa(apps, schema_editor):
    Adempimento = apps.get_model("adempimenti", "Adempimento")
    Adempimento.objects.filter(stato="controllato").update(stato="chiusa")


def rinomina_chiusa_in_controllato(apps, schema_editor):
    Adempimento = apps.get_model("adempimenti", "Adempimento")
    Adempimento.objects.filter(stato="chiusa").update(stato="controllato")


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0004_scadenza_evento_offset"),
        ("anagrafica", "0005_categoria_tag"),
    ]

    operations = [
        # Nuovi campi operativi su Adempimento
        migrations.AddField(
            model_name="adempimento",
            name="data_invio",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="adempimento",
            name="protocollo_invio",
            field=models.CharField(
                blank=True,
                help_text="Numero di protocollo telematico restituito dall'invio.",
                max_length=40,
            ),
        ),

        # Allarga stato a 15 char (è già 15) con i nuovi choices.
        migrations.AlterField(
            model_name="adempimento",
            name="stato",
            field=models.CharField(
                choices=NEW_STATI_CHOICES,
                db_index=True,
                default="da_fare",
                max_length=15,
            ),
        ),
        # Data-migration: controllato → chiusa (semantica preservata)
        migrations.RunPython(
            rinomina_controllato_in_chiusa,
            rinomina_chiusa_in_controllato,
        ),

        # Nuovi operatori e nuovo campo condizione su RegolaApplicabilita
        migrations.AlterField(
            model_name="regolaapplicabilita",
            name="operatore",
            field=models.CharField(
                choices=NEW_OPERATORI_CHOICES,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="regolaapplicabilita",
            name="campo_condizione",
            field=models.CharField(
                choices=NEW_CAMPI_CHOICES,
                max_length=30,
            ),
        ),
    ]
