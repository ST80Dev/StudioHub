from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0012_alter_statoadempimentotipo_e_predefinito"),
    ]

    operations = [
        migrations.AddField(
            model_name="vistaadempimentocolonne",
            name="larghezze_colonne",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Larghezze colonne in pixel come dict {codice: int}. "
                    "Editabile da UI in pagina (\"Modifica vista\") o qui per "
                    "override fine. I codici assenti usano la larghezza Tailwind "
                    "di default definita in `columns.py`."
                ),
            ),
        ),
    ]
