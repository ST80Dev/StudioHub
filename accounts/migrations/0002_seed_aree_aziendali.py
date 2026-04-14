from django.db import migrations


AREE_INIZIALI = [
    ("contabilita", "Contabilità", 10),
    ("consulenza", "Consulenza", 20),
    ("amministrazione", "Amministrazione", 30),
    ("informatica", "Informatica", 40),
]


def popola_aree(apps, schema_editor):
    Area = apps.get_model("accounts", "AreaAziendale")
    for codice, denominazione, ordine in AREE_INIZIALI:
        Area.objects.update_or_create(
            codice=codice,
            defaults={"denominazione": denominazione, "ordine": ordine, "attivo": True},
        )


def svuota_aree(apps, schema_editor):
    Area = apps.get_model("accounts", "AreaAziendale")
    Area.objects.filter(codice__in=[a[0] for a in AREE_INIZIALI]).delete()


class Migration(migrations.Migration):

    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(popola_aree, svuota_aree)]
