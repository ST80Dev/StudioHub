"""Seed del catalogo per la Liquidazione IVA Trimestrale (LIPE).

Crea (idempotente):
- TipoAdempimentoCatalogo `liquidazione-iva-trimestrale`
- 4 ScadenzaPeriodo (Q1=31/05, Q2=30/09, Q3=30/11, Q4=ultimo febbraio anno+1)
- 3 RegolaApplicabilita:
  * `periodicita_iva IN_LISTA "trimestrale,mensile"` (esclude i non soggetti)
  * `regime_contabile DIVERSO_DA "forfettario"`
  * `NON_HA_CATEGORIA "sanitaria-esente"`
- Categoria preconfigurata `sanitaria-esente`

NB: la scadenza Q2 storicamente "regola pura" sarebbe il 16/09; usiamo 30/09
perché è ciò che si applica di fatto (proroghe ricorrenti).
"""
from django.db import migrations


CODICE_TIPO = "liquidazione-iva-trimestrale"

SCADENZE = [
    # (periodo, mese, giorno, anno_offset, etichetta)
    (1, 5, 31, 0, "Q1"),
    (2, 9, 30, 0, "Q2"),
    (3, 11, 30, 0, "Q3"),
    (4, 2, 28, 1, "Q4"),
]

REGOLE = [
    # (campo, operatore, valore, ordine)
    ("periodicita_iva", "in_lista", "trimestrale,mensile", 10),
    ("regime_contabile", "diverso_da", "forfettario", 20),
    ("categorie", "non_ha_categoria", "sanitaria-esente", 30),
]


def seed_lipe(apps, schema_editor):
    TipoAdempimentoCatalogo = apps.get_model("adempimenti", "TipoAdempimentoCatalogo")
    ScadenzaPeriodo = apps.get_model("adempimenti", "ScadenzaPeriodo")
    RegolaApplicabilita = apps.get_model("adempimenti", "RegolaApplicabilita")
    Categoria = apps.get_model("anagrafica", "Categoria")

    Categoria.objects.get_or_create(
        slug="sanitaria-esente",
        defaults={
            "denominazione": "Sanitaria esente",
            "descrizione": (
                "Professionista sanitario in regime di esenzione IVA "
                "(non tenuto alla Liquidazione IVA Trimestrale)."
            ),
            "colore": "#10b981",
        },
    )

    tipo, _ = TipoAdempimentoCatalogo.objects.get_or_create(
        codice=CODICE_TIPO,
        defaults={
            "denominazione": "Liquidazione IVA Trimestrale",
            "periodicita": "trimestrale",
            "colore": "#0ea5e9",
            "attivo": True,
            "ordine": 50,
            "note_regole": (
                "LIPE - Comunicazione Liquidazioni Periodiche IVA. "
                "Si applica a soggetti IVA (mensili e trimestrali) "
                "esclusi i forfettari e i sanitari esenti."
            ),
        },
    )

    for periodo, mese, giorno, anno_offset, etichetta in SCADENZE:
        ScadenzaPeriodo.objects.update_or_create(
            tipo_adempimento=tipo,
            periodo=periodo,
            defaults={
                "mese_scadenza": mese,
                "giorno_scadenza": giorno,
                "anno_offset": anno_offset,
                "etichetta": etichetta,
            },
        )

    for campo, operatore, valore, ordine in REGOLE:
        RegolaApplicabilita.objects.update_or_create(
            tipo_adempimento=tipo,
            campo_condizione=campo,
            operatore=operatore,
            valore=valore,
            defaults={"attiva": True, "ordine": ordine},
        )


def unseed_lipe(apps, schema_editor):
    TipoAdempimentoCatalogo = apps.get_model("adempimenti", "TipoAdempimentoCatalogo")
    Categoria = apps.get_model("anagrafica", "Categoria")
    TipoAdempimentoCatalogo.objects.filter(codice=CODICE_TIPO).delete()
    Categoria.objects.filter(slug="sanitaria-esente").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("adempimenti", "0005_lipe_estensioni"),
    ]

    operations = [
        migrations.RunPython(seed_lipe, unseed_lipe),
    ]
