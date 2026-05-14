from django.db import migrations, models


def rename_ruoli_forward(apps, schema_editor):
    Ref = apps.get_model("anagrafica", "AnagraficaReferenteStudio")
    Ref.objects.filter(ruolo="addetto_contabilita").update(
        ruolo="referente_contabilita"
    )
    Ref.objects.filter(ruolo="responsabile_consulenza").update(
        ruolo="referente_consulenza"
    )


def rename_ruoli_backward(apps, schema_editor):
    Ref = apps.get_model("anagrafica", "AnagraficaReferenteStudio")
    Ref.objects.filter(ruolo="referente_contabilita").update(
        ruolo="addetto_contabilita"
    )
    Ref.objects.filter(ruolo="referente_consulenza").update(
        ruolo="responsabile_consulenza"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0012_extensible_choices"),
    ]

    operations = [
        migrations.RunPython(rename_ruoli_forward, rename_ruoli_backward),
        migrations.AlterField(
            model_name="anagraficareferentestudio",
            name="ruolo",
            field=models.CharField(
                choices=[
                    ("referente_contabilita", "Referente contabilità"),
                    ("referente_consulenza", "Referente consulenza"),
                ],
                max_length=30,
            ),
        ),
    ]
