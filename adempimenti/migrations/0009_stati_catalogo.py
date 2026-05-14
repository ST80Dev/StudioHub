"""Catalogo stati adempimento (Standard + per-tipo).

Sostituisce il vecchio `StatoAdempimento` TextChoices fisso con due tabelle:
- `StatoAdempimentoStandard`: set globale editabile da admin Django, usato
  come template alla creazione di nuovi tipi.
- `StatoAdempimentoTipo`: stati concreti per-tipo. Inizialmente popolato
  copiando lo Standard sui tipi esistenti.

Effetti:
- crea le due tabelle e i constraint di unicita';
- seeda 6 stati standard canonici (da_fare/in_corso/chiusa/inviato/
  fanno_loro/no_dati) con `lavorabile`, `livello`, `iniziale_default`,
  `sigla` e `colore` come concordato;
- per ogni `TipoAdempimentoCatalogo` esistente copia gli Standard come
  StatoAdempimentoTipo marcati `e_predefinito=True`;
- toglie `choices=` da `Adempimento.stato` (la validazione passa al
  catalogo dinamico) e porta `max_length` a 30 per coerenza con SlugField.

Reversibile: drop delle 2 tabelle + ripristino choices/max_length sul field.
"""

import django.db.models.deletion
from django.db import migrations, models


# (codice, denominazione, sigla, colore, lavorabile, livello, iniziale_default)
SEED_STANDARD = [
    ("da_fare",    "Da fare",             "FAR", "todo",   True,  10,  True),
    ("in_corso",   "In corso",            "COR", "wip",    True,  40,  False),
    ("chiusa",     "Chiusa (predisposta)", "CHI", "review", True,  70,  False),
    ("inviato",    "Inviato",             "INV", "done",   False, 100, False),
    ("fanno_loro", "Fanno loro",          "LOR", "idle",   False, 0,   False),
    ("no_dati",    "No dati",             "NOD", "idle",   False, 0,   False),
]


def seed(apps, schema_editor):
    Standard = apps.get_model("adempimenti", "StatoAdempimentoStandard")
    Tipo = apps.get_model("adempimenti", "StatoAdempimentoTipo")
    TipoAdempimentoCatalogo = apps.get_model("adempimenti", "TipoAdempimentoCatalogo")

    # 1) Seed Standard (idempotente su `codice`)
    for cod, den, sig, col, lav, liv, iniz in SEED_STANDARD:
        Standard.objects.update_or_create(
            codice=cod,
            defaults={
                "denominazione": den,
                "sigla": sig,
                "colore": col,
                "lavorabile": lav,
                "livello": liv,
                "iniziale_default": iniz,
                "attivo": True,
            },
        )

    # 2) Copia gli Standard su ogni tipo esistente come `e_predefinito=True`.
    #    Idempotente: skip se il (tipo, codice) e' gia' presente.
    standards = list(Standard.objects.filter(attivo=True))
    for tipo in TipoAdempimentoCatalogo.objects.all():
        gia_presenti = set(
            Tipo.objects.filter(tipo_adempimento=tipo).values_list("codice", flat=True)
        )
        nuovi = []
        for std in standards:
            if std.codice in gia_presenti:
                continue
            nuovi.append(Tipo(
                tipo_adempimento=tipo,
                codice=std.codice,
                denominazione=std.denominazione,
                sigla=std.sigla,
                colore=std.colore,
                lavorabile=std.lavorabile,
                livello=std.livello,
                iniziale_default=std.iniziale_default,
                attivo=True,
                e_predefinito=True,
            ))
        if nuovi:
            Tipo.objects.bulk_create(nuovi)


def unseed(apps, schema_editor):
    # Reverse: il drop tabelle e' gestito da `migrations.DeleteModel`
    # generato automaticamente dal RunPython reverse. Qui solo no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0008_vista_adempimento_colonne"),
    ]

    operations = [
        migrations.CreateModel(
            name="StatoAdempimentoStandard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice", models.SlugField(max_length=30, help_text="Identificativo stabile (minuscolo, no spazi). Es. 'da_fare', 'controllato'. Vedi convenzione codici TextChoices in CLAUDE.md.")),
                ("denominazione", models.CharField(max_length=60, help_text="Etichetta estesa mostrata nei dropdown/form (es. 'Da fare').")),
                ("sigla", models.CharField(blank=True, max_length=3, help_text="Sigla 3 char per badge densi (es. 'FAR'). Vuoto = fallback automatico.")),
                ("colore", models.CharField(
                    choices=[
                        ("todo", "Da fare (grigio)"),
                        ("wip", "In corso (giallo)"),
                        ("review", "In revisione (azzurro)"),
                        ("done", "Completato (verde)"),
                        ("idle", "Riposo (slate)"),
                    ],
                    default="todo",
                    max_length=10,
                    help_text="Classe colore del badge.",
                )),
                ("lavorabile", models.BooleanField(default=True, help_text="Se True, conta nel 'lavoro residuo'. Se False, lo stato esce dai conteggi.")),
                ("livello", models.PositiveSmallIntegerField(default=10, help_text="0..100. Progressione: 0=non in scope, 100=completato. Anche sort.")),
                ("iniziale_default", models.BooleanField(default=False, help_text="Stato di partenza per nuovi adempimenti. Uno solo a True per set.")),
                ("attivo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Stato standard",
                "verbose_name_plural": "Stati standard",
                "ordering": ("livello", "denominazione"),
            },
        ),
        migrations.AddConstraint(
            model_name="statoadempimentostandard",
            constraint=models.UniqueConstraint(fields=("codice",), name="uniq_statostd_codice"),
        ),
        migrations.CreateModel(
            name="StatoAdempimentoTipo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice", models.SlugField(max_length=30, help_text="Identificativo stabile (minuscolo, no spazi). Es. 'da_fare', 'controllato'. Vedi convenzione codici TextChoices in CLAUDE.md.")),
                ("denominazione", models.CharField(max_length=60, help_text="Etichetta estesa mostrata nei dropdown/form (es. 'Da fare').")),
                ("sigla", models.CharField(blank=True, max_length=3, help_text="Sigla 3 char per badge densi (es. 'FAR'). Vuoto = fallback automatico.")),
                ("colore", models.CharField(
                    choices=[
                        ("todo", "Da fare (grigio)"),
                        ("wip", "In corso (giallo)"),
                        ("review", "In revisione (azzurro)"),
                        ("done", "Completato (verde)"),
                        ("idle", "Riposo (slate)"),
                    ],
                    default="todo",
                    max_length=10,
                    help_text="Classe colore del badge.",
                )),
                ("lavorabile", models.BooleanField(default=True, help_text="Se True, conta nel 'lavoro residuo'. Se False, lo stato esce dai conteggi.")),
                ("livello", models.PositiveSmallIntegerField(default=10, help_text="0..100. Progressione: 0=non in scope, 100=completato. Anche sort.")),
                ("iniziale_default", models.BooleanField(default=False, help_text="Stato di partenza per nuovi adempimenti. Uno solo a True per set.")),
                ("attivo", models.BooleanField(default=True)),
                ("e_predefinito", models.BooleanField(default=False, help_text="Copiato dallo Standard. Non eliminabile (modifiche sono ammesse).")),
                ("tipo_adempimento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="stati",
                    to="adempimenti.tipoadempimentocatalogo",
                )),
            ],
            options={
                "verbose_name": "Stato (per tipo)",
                "verbose_name_plural": "Stati (per tipo)",
                "ordering": ("livello", "denominazione"),
            },
        ),
        migrations.AddConstraint(
            model_name="statoadempimentotipo",
            constraint=models.UniqueConstraint(
                fields=("tipo_adempimento", "codice"),
                name="uniq_statotipo_tipo_codice",
            ),
        ),
        migrations.AlterField(
            model_name="adempimento",
            name="stato",
            field=models.CharField(
                db_index=True,
                default="da_fare",
                help_text=(
                    "Codice di uno stato in StatoAdempimentoTipo per `tipo`. "
                    "I valori validi non sono hardcoded: si gestiscono da admin "
                    "Django o da /configurazione/tipi/<id>/?tab=stati."
                ),
                max_length=30,
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]
