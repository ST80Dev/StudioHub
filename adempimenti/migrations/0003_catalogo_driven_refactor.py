"""Refactoring completo da architettura tabella-per-tipo a catalogo-driven.

Rimuove AdempimentoBilancioUE. Crea TipoAdempimentoCatalogo, ScadenzaPeriodo,
ChecklistStep, RegolaApplicabilita, StepCompletato. Riscrive Adempimento
con FK al catalogo, periodo, data_scadenza, stato flat.

ATTENZIONE: questa migrazione svuota la tabella Adempimento esistente
(dati pre-produzione / demo). Non applicare su un DB con adempimenti reali.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def flush_old_adempimenti(apps, schema_editor):
    """Svuota adempimenti e figlie prima del refactoring schema."""
    apps.get_model("adempimenti", "AdempimentoBilancioUE").objects.all().delete()
    apps.get_model("adempimenti", "Adempimento").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0002_adempimento_is_demo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -- 1. Svuota i vecchi dati (pre-produzione) -------------------
        migrations.RunPython(flush_old_adempimenti, migrations.RunPython.noop),

        # -- 2. Rimuovi il vecchio modello figlia 1:1 ------------------
        migrations.DeleteModel(name="AdempimentoBilancioUE"),

        # -- 3. Crea TipoAdempimentoCatalogo ----------------------------
        migrations.CreateModel(
            name="TipoAdempimentoCatalogo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice", models.SlugField(max_length=40, unique=True)),
                ("denominazione", models.CharField(max_length=120)),
                ("periodicita", models.CharField(
                    choices=[("annuale", "Annuale"), ("trimestrale", "Trimestrale"), ("mensile", "Mensile"), ("una_tantum", "Una tantum")],
                    default="annuale", max_length=20,
                )),
                ("colore", models.CharField(blank=True, help_text="Colore CSS per badge/sidebar (es. '#3b82f6', 'blue').", max_length=20)),
                ("attivo", models.BooleanField(db_index=True, default=True)),
                ("note_regole", models.TextField(blank=True, help_text="Appunti interni sulla regola di scadenza.")),
                ("ordine", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Tipo adempimento",
                "verbose_name_plural": "Tipi adempimento",
                "ordering": ("ordine", "denominazione"),
            },
        ),

        # -- 4. Crea ScadenzaPeriodo ------------------------------------
        migrations.CreateModel(
            name="ScadenzaPeriodo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("periodo", models.PositiveSmallIntegerField(help_text="1 per annuale, 1-4 per trimestrale, 1-12 per mensile.")),
                ("mese_scadenza", models.PositiveSmallIntegerField(help_text="Mese dell'anno in cui cade la scadenza (1-12).")),
                ("giorno_scadenza", models.PositiveSmallIntegerField(help_text="Giorno del mese di scadenza (1-31).")),
                ("anno_offset", models.SmallIntegerField(default=0, help_text="0 = stesso anno fiscale, 1 = anno successivo.")),
                ("etichetta", models.CharField(help_text="Es: 'Q1', 'Gennaio', 'Annuale'.", max_length=30)),
                ("tipo_adempimento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="scadenze",
                    to="adempimenti.tipoadempimentocatalogo",
                )),
            ],
            options={
                "verbose_name": "Scadenza periodo",
                "verbose_name_plural": "Scadenze periodo",
                "ordering": ("tipo_adempimento", "periodo"),
            },
        ),
        migrations.AddConstraint(
            model_name="scadenzaperiodo",
            constraint=models.UniqueConstraint(
                fields=["tipo_adempimento", "periodo"],
                name="uniq_scadenza_tipo_periodo",
            ),
        ),

        # -- 5. Crea ChecklistStep --------------------------------------
        migrations.CreateModel(
            name="ChecklistStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ordine", models.PositiveSmallIntegerField(default=0)),
                ("denominazione", models.CharField(max_length=200)),
                ("tipo_adempimento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="checklist_steps",
                    to="adempimenti.tipoadempimentocatalogo",
                )),
            ],
            options={
                "verbose_name": "Step checklist",
                "verbose_name_plural": "Step checklist",
                "ordering": ("tipo_adempimento", "ordine"),
            },
        ),

        # -- 6. Crea RegolaApplicabilita --------------------------------
        migrations.CreateModel(
            name="RegolaApplicabilita",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("campo_condizione", models.CharField(
                    choices=[
                        ("tipo_soggetto", "Tipo soggetto"),
                        ("regime_contabile", "Regime contabile"),
                        ("periodicita_iva", "Periodicità IVA"),
                        ("sostituto_imposta", "Sostituto d'imposta"),
                        ("iscritto_cciaa", "Iscritto CCIAA"),
                        ("contabilita", "Contabilità (interna/esterna)"),
                        ("categoria_professione", "Categoria professione"),
                    ],
                    max_length=30,
                )),
                ("operatore", models.CharField(
                    choices=[
                        ("uguale", "Uguale a"),
                        ("in_lista", "In lista (valori separati da virgola)"),
                        ("vero", "Vero (campo booleano)"),
                        ("falso", "Falso (campo booleano)"),
                    ],
                    max_length=20,
                )),
                ("valore", models.CharField(blank=True, help_text="Valore di confronto. Per 'in_lista' separare con virgola (es. 'SRL,SPA').", max_length=200)),
                ("attiva", models.BooleanField(default=True)),
                ("ordine", models.PositiveSmallIntegerField(default=0)),
                ("tipo_adempimento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="regole",
                    to="adempimenti.tipoadempimentocatalogo",
                )),
            ],
            options={
                "verbose_name": "Regola di applicabilità",
                "verbose_name_plural": "Regole di applicabilità",
                "ordering": ("tipo_adempimento", "ordine"),
            },
        ),

        # -- 7. Ristruttura Adempimento ---------------------------------

        # Rimuovi vecchio constraint e indici
        migrations.RemoveConstraint(
            model_name="adempimento",
            name="uniq_adempimento_cliente_tipo_anno_fiscale",
        ),
        migrations.RemoveIndex(
            model_name="adempimento",
            name="adempimenti_tipo_156804_idx",
        ),
        migrations.RemoveIndex(
            model_name="adempimento",
            name="adempimenti_tipo_8010d5_idx",
        ),

        # Rimuovi campi vecchi
        migrations.RemoveField(model_name="adempimento", name="tipo"),
        migrations.RemoveField(model_name="adempimento", name="anno_esecuzione"),

        # Aggiungi nuovi campi
        migrations.AddField(
            model_name="adempimento",
            name="tipo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="adempimenti",
                to="adempimenti.tipoadempimentocatalogo",
                default=1,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="adempimento",
            name="periodo",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                help_text="Null per annuale. 1-4 per trimestrale, 1-12 per mensile.",
            ),
        ),
        migrations.AddField(
            model_name="adempimento",
            name="data_scadenza",
            field=models.DateField(
                blank=True, null=True,
                help_text="Calcolata da ScadenzaPeriodo, sovrascrivibile dall'utente.",
            ),
        ),
        migrations.AddField(
            model_name="adempimento",
            name="stato",
            field=models.CharField(
                choices=[
                    ("da_fare", "Da fare"),
                    ("in_corso", "In corso"),
                    ("controllato", "Controllato"),
                    ("inviato", "Inviato"),
                ],
                db_index=True, default="da_fare", max_length=15,
            ),
        ),

        # Altera responsabile: PROTECT → SET_NULL
        migrations.AlterField(
            model_name="adempimento",
            name="responsabile",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="adempimenti_eseguiti",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # Altera ordering
        migrations.AlterModelOptions(
            name="adempimento",
            options={
                "ordering": ("data_scadenza", "anagrafica__denominazione"),
                "verbose_name": "Adempimento",
                "verbose_name_plural": "Adempimenti",
            },
        ),

        # Nuovo constraint e indici
        migrations.AddConstraint(
            model_name="adempimento",
            constraint=models.UniqueConstraint(
                fields=["anagrafica", "tipo", "anno_fiscale", "periodo"],
                name="uniq_adempimento_cliente_tipo_anno_periodo",
            ),
        ),
        migrations.AddIndex(
            model_name="adempimento",
            index=models.Index(fields=["tipo", "anno_fiscale"], name="adempimenti_tipo_ad_anno_idx"),
        ),
        migrations.AddIndex(
            model_name="adempimento",
            index=models.Index(fields=["tipo", "stato"], name="adempimenti_tipo_ad_stato_idx"),
        ),
        migrations.AddIndex(
            model_name="adempimento",
            index=models.Index(fields=["data_scadenza", "stato"], name="adempimenti_scadenza_stato_idx"),
        ),

        # -- 8. Crea StepCompletato -------------------------------------
        migrations.CreateModel(
            name="StepCompletato",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completato", models.BooleanField(default=False)),
                ("data_completamento", models.DateField(blank=True, null=True)),
                ("adempimento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="steps_completati",
                    to="adempimenti.adempimento",
                )),
                ("step", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="completamenti",
                    to="adempimenti.checkliststep",
                )),
                ("completato_da", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Step completato",
                "verbose_name_plural": "Step completati",
            },
        ),
        migrations.AddConstraint(
            model_name="stepcompletato",
            constraint=models.UniqueConstraint(
                fields=["adempimento", "step"],
                name="uniq_step_per_adempimento",
            ),
        ),
    ]
