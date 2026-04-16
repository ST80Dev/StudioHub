from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("accounts", "0002_seed_aree_aziendali")]

    operations = [
        migrations.AddField(
            model_name="utentestudio",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text=(
                    "True per utenti creati dal seed di test. "
                    "Mai True per utenti reali."
                ),
            ),
        ),
    ]
