from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("adempimenti", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="adempimento",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="True per adempimenti creati dal seed di test.",
            ),
        ),
    ]
