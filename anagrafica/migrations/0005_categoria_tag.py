"""Categorie come tag M2M sull'anagrafica.

Crea il modello `Categoria` e il M2M `Anagrafica.categorie`. Migra i valori
storici di `categoria_professione` (CharField libero) in righe `Categoria` e
li collega alle anagrafiche corrispondenti, così le regole costruite sui tag
funzionano subito anche sui dati pre-esistenti. Il vecchio CharField resta
per ora (deprecato): verrà rimosso in una migrazione successiva.
"""
from django.db import migrations, models
from django.utils.text import slugify


def migra_categoria_professione_in_tag(apps, schema_editor):
    Anagrafica = apps.get_model("anagrafica", "Anagrafica")
    Categoria = apps.get_model("anagrafica", "Categoria")

    cache_per_slug = {}
    qs = Anagrafica.objects.exclude(categoria_professione="").exclude(
        categoria_professione__isnull=True
    )
    for anag in qs:
        valore = (anag.categoria_professione or "").strip()
        if not valore:
            continue
        slug = slugify(valore)[:40] or "categoria"
        cat = cache_per_slug.get(slug)
        if cat is None:
            cat, _created = Categoria.objects.get_or_create(
                slug=slug,
                defaults={"denominazione": valore.capitalize()},
            )
            cache_per_slug[slug] = cat
        anag.categorie.add(cat)


def noop_reverse(apps, schema_editor):
    # Reverse: rimuoviamo solo le associazioni, le Categorie create restano
    # (vengono cancellate dal DeleteModel del rollback schema).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0004_add_codici_gestionali"),
    ]

    operations = [
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("denominazione", models.CharField(max_length=80)),
                ("colore", models.CharField(blank=True, max_length=20)),
                ("descrizione", models.CharField(blank=True, max_length=200)),
                ("attiva", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Categoria anagrafica",
                "verbose_name_plural": "Categorie anagrafica",
                "ordering": ("denominazione",),
            },
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="categorie",
            field=models.ManyToManyField(
                blank=True,
                help_text="Tag categoriali per marcare specificità del soggetto.",
                related_name="anagrafiche",
                to="anagrafica.categoria",
            ),
        ),
        migrations.AlterField(
            model_name="anagrafica",
            name="categoria_professione",
            field=models.CharField(
                blank=True,
                help_text=(
                    "DEPRECATO: usare il M2M `categorie`. Mantenuto per "
                    "compatibilità con regole legacy. La data-migration "
                    "0005 popola `categorie` dai valori storici."
                ),
                max_length=60,
            ),
        ),
        migrations.RunPython(
            migra_categoria_professione_in_tag,
            noop_reverse,
        ),
    ]
