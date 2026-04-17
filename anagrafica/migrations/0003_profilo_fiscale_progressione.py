"""Profilo fiscale arricchito + ProgressioneContabilita.

Aggiunge campi su Anagrafica per il motore regole di applicabilità
e modelli per il tracciamento della progressione contabilità mensile.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0002_anagrafica_is_demo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -- Profilo fiscale arricchito su Anagrafica -------------------
        migrations.AddField(
            model_name="anagrafica",
            name="contabilita",
            field=models.CharField(
                choices=[("interna", "Interna (tenuta dallo studio)"), ("esterna", "Esterna")],
                default="esterna",
                help_text="Interna = tenuta dallo studio. Esterna = tenuta dal cliente o da terzi.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="peso_contabilita",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Indice di peso per il calcolo dell'aggiornamento ponderato. 0 = non considerato. Range consigliato 1-10.",
            ),
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="sostituto_imposta",
            field=models.BooleanField(default=False, help_text="Se True, al cliente competono CU e 770."),
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="iscritto_cciaa",
            field=models.BooleanField(default=False, help_text="Iscritto alla Camera di Commercio."),
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="data_fine_esercizio",
            field=models.CharField(
                default="12-31",
                help_text="Formato MM-DD. Default 31 dicembre (esercizio solare).",
                max_length=5,
            ),
        ),
        migrations.AddField(
            model_name="anagrafica",
            name="categoria_professione",
            field=models.CharField(
                blank=True, default="", max_length=60,
                help_text="Es: 'sanitaria'. Usato per regole tipo STS.",
            ),
        ),

        # -- ProgressioneContabilita ------------------------------------
        migrations.CreateModel(
            name="ProgressioneContabilita",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anno", models.IntegerField()),
                ("mese_ultimo_registrato", models.PositiveSmallIntegerField(
                    default=0,
                    help_text="0 = nessun mese registrato, 1-12 = ultimo mese completato.",
                )),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("anagrafica", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="progressione_contabilita",
                    to="anagrafica.anagrafica",
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Progressione contabilità",
                "verbose_name_plural": "Progressioni contabilità",
            },
        ),
        migrations.AddConstraint(
            model_name="progressionecontabilita",
            constraint=models.UniqueConstraint(
                fields=["anagrafica", "anno"],
                name="uniq_progressione_cliente_anno",
            ),
        ),

        # -- ProgressioneContabilitaLog ---------------------------------
        migrations.CreateModel(
            name="ProgressioneContabilitaLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anno", models.IntegerField()),
                ("mese_ultimo_registrato", models.PositiveSmallIntegerField()),
                ("rilevato_il", models.DateTimeField(auto_now_add=True)),
                ("anagrafica", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="progressione_log",
                    to="anagrafica.anagrafica",
                )),
                ("utente", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Log progressione contabilità",
                "verbose_name_plural": "Log progressioni contabilità",
                "ordering": ("-rilevato_il",),
            },
        ),
        migrations.AddIndex(
            model_name="progressionecontabilitalog",
            index=models.Index(
                fields=["anagrafica", "anno", "-rilevato_il"],
                name="anagrafica_progr_log_idx",
            ),
        ),
    ]
