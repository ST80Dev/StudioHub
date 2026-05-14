from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("accounts", "0003_utentestudio_is_demo")]

    operations = [
        migrations.AddField(
            model_name="utentestudio",
            name="etichetta_ui",
            field=models.CharField(
                max_length=40,
                blank=True,
                help_text=(
                    "Etichetta breve usata nelle liste (es. 'mario.r'). "
                    "Se vuoto, viene generata automaticamente da nome+cognome "
                    "o in fallback dallo username."
                ),
            ),
        ),
    ]
