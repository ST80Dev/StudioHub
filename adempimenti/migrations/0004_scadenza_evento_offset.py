"""Scadenze a offset da evento variabile.

Aggiunge sul catalogo tipi i campi che attivano la modalità 'scadenza =
data_evento + giorni_offset' (necessaria per tipi come Bilancio UE dove la
scadenza dipende da una data variabile per adempimento, es. data assemblea
approvazione). Aggiunge su Adempimento il campo data_evento_riferimento.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0003_catalogo_driven_refactor"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipoadempimentocatalogo",
            name="etichetta_data_evento",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Nome dell'evento di riferimento (es. 'Data assemblea "
                    "approvazione bilancio'). Lasciare vuoto se la scadenza "
                    "è una data fissa."
                ),
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="tipoadempimentocatalogo",
            name="giorni_offset_da_evento",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Giorni dopo l'evento entro cui scade l'adempimento.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="adempimento",
            name="data_evento_riferimento",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Data dell'evento di riferimento (es. data assemblea "
                    "approvazione bilancio). Usata solo per tipi con scadenza "
                    "a offset da evento."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="adempimento",
            name="data_scadenza",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Calcolata automaticamente (ScadenzaPeriodo o "
                    "data_evento + offset), sovrascrivibile dall'utente."
                ),
                null=True,
            ),
        ),
    ]
