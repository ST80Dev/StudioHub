from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("anagrafica", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="anagrafica",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="True per anagrafiche create dal seed di test.",
            ),
        ),
    ]
