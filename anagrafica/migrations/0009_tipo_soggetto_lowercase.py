"""Uniforma i codici di `tipo_soggetto` a minuscolo.

Prima erano misti: `PF`, `PROFEX`, `DI`, `SNC`, `SAS`, `SRL`, `SPA`, `ASS`,
`FALL`. Adottiamo la regola "codici DB sempre minuscoli" (vedi CLAUDE.md):
i codici sono identificatori semantici stabili, l'aspetto visivo si gestisce
con le label (label + label_micro) configurabili da admin.

Cambia il dato in tre punti:
- `anagrafica.Anagrafica.tipo_soggetto`
- `anagrafica.TextChoiceLabel.codice` (righe con field='tipo_soggetto')
- `adempimenti.RegolaApplicabilita.valore` (righe con campo_condizione=
  'tipo_soggetto'; gestisce anche il caso `in_lista` con valori separati
  da virgola).

Reversibile: rimette tutto in maiuscolo se si fa rollback.
"""

from django.db import migrations


# (old_upper, new_lower)
TIPO_SOGGETTO_MAP = [
    ("PF", "pf"),
    ("PROFEX", "profex"),
    ("DI", "di"),
    ("SNC", "snc"),
    ("SAS", "sas"),
    ("SRL", "srl"),
    ("SPA", "spa"),
    ("ASS", "ass"),
    ("FALL", "fall"),
]


def _remap_in_lista(valore: str, mapping: dict[str, str]) -> str:
    """Per operatore `in_lista`/`non_in_lista`: rimappa ogni token CSV.

    Conserva whitespace originale fra le virgole se possibile.
    """
    if not valore:
        return valore
    parti = [p.strip() for p in valore.split(",")]
    rimappate = [mapping.get(p, p) for p in parti]
    return ",".join(rimappate)


def _apply(apps, mapping: dict[str, str]):
    Anagrafica = apps.get_model("anagrafica", "Anagrafica")
    TextChoiceLabel = apps.get_model("anagrafica", "TextChoiceLabel")
    RegolaApplicabilita = apps.get_model("adempimenti", "RegolaApplicabilita")

    for vecchio, nuovo in mapping.items():
        Anagrafica.objects.filter(tipo_soggetto=vecchio).update(
            tipo_soggetto=nuovo,
        )
        TextChoiceLabel.objects.filter(
            field="tipo_soggetto", codice=vecchio,
        ).update(codice=nuovo)
        # Regole con operatori scalari (uguale/diverso_da): valore == sigla
        RegolaApplicabilita.objects.filter(
            campo_condizione="tipo_soggetto", valore=vecchio,
        ).update(valore=nuovo)

    # Regole con operatori in_lista/non_in_lista: il valore è un CSV.
    for r in RegolaApplicabilita.objects.filter(
        campo_condizione="tipo_soggetto",
        operatore__in=("in_lista", "non_in_lista"),
    ):
        nuovo_valore = _remap_in_lista(r.valore, mapping)
        if nuovo_valore != r.valore:
            r.valore = nuovo_valore
            r.save(update_fields=["valore"])


def forwards(apps, schema_editor):
    _apply(apps, dict(TIPO_SOGGETTO_MAP))


def backwards(apps, schema_editor):
    _apply(apps, {nuovo: vecchio for vecchio, nuovo in TIPO_SOGGETTO_MAP})


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0008_textchoicelabel"),
        # Dipendenza cross-app: tocchiamo RegolaApplicabilita.
        ("adempimenti", "0007_rename_adempimenti_tipo_ad_anno_idx_adempimenti_tipo_id_f82114_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
