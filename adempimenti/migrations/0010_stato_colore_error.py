"""Aggiunge la choice `error` (rosso) al campo `colore` degli stati.

Cambio puramente formale (le choices del CharField): nessun dato esistente
viene toccato. Permette di marcare uno stato con badge rosso (per stati di
errore/blocco) ora che `todo` e' stato ricolorato in grigio reale.
"""

from django.db import migrations, models


COLORE_CHOICES = [
    ("todo", "Da fare (grigio)"),
    ("wip", "In corso (giallo)"),
    ("review", "In revisione (azzurro)"),
    ("done", "Completato (verde)"),
    ("idle", "Riposo (slate)"),
    ("error", "Errori (rosso)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0009_stati_catalogo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="statoadempimentostandard",
            name="colore",
            field=models.CharField(
                choices=COLORE_CHOICES,
                default="todo",
                max_length=10,
                help_text="Classe colore del badge.",
            ),
        ),
        migrations.AlterField(
            model_name="statoadempimentotipo",
            name="colore",
            field=models.CharField(
                choices=COLORE_CHOICES,
                default="todo",
                max_length=10,
                help_text="Classe colore del badge.",
            ),
        ),
    ]
