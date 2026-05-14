from django import forms
from django.contrib import admin

from .columns import STANDARD_COLUMNS, available_column_choices
from .models import (
    Adempimento,
    ChecklistStep,
    RegolaApplicabilita,
    ScadenzaPeriodo,
    StepCompletato,
    TipoAdempimentoCatalogo,
    VistaAdempimentoColonne,
)


# ---------------------------------------------------------------------------
# Catalogo tipi
# ---------------------------------------------------------------------------

class ScadenzaPeriodoInline(admin.TabularInline):
    model = ScadenzaPeriodo
    extra = 1


class ChecklistStepInline(admin.TabularInline):
    model = ChecklistStep
    extra = 1


class RegolaApplicabilitaInline(admin.TabularInline):
    model = RegolaApplicabilita
    extra = 1


@admin.register(TipoAdempimentoCatalogo)
class TipoAdempimentoCatalogoAdmin(admin.ModelAdmin):
    list_display = ("codice", "denominazione", "periodicita", "attivo", "ordine")
    list_filter = ("periodicita", "attivo")
    search_fields = ("codice", "denominazione")
    inlines = [ScadenzaPeriodoInline, ChecklistStepInline, RegolaApplicabilitaInline]


# ---------------------------------------------------------------------------
# Adempimento
# ---------------------------------------------------------------------------

class StepCompletatoInline(admin.TabularInline):
    model = StepCompletato
    extra = 0
    readonly_fields = ("step",)


class VistaAdempimentoColonneForm(forms.ModelForm):
    """Form admin con UI a checkbox + ordinamento per `colonne_codici`.

    Render: lista di checkbox (una per colonna disponibile, in ordine standard)
    + un campo nascosto `colonne_ordinate` che cattura l'ordine attuale
    (manipolato lato client via Sortable.js incluso da `admin/colonne.html`).

    Sul `clean()` ricostruiamo `colonne_codici` filtrando l'ordine sul
    sottoinsieme spuntato. In assenza di JS: si torna a ordinamento standard.
    """

    colonne = forms.MultipleChoiceField(
        choices=available_column_choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Colonne da mostrare",
        help_text=(
            "Spunta le colonne da includere nella tabella. Trascina per "
            "riordinare (richiede JavaScript). Se non riordini, l'ordine "
            "seguira' quello standard."
        ),
    )
    colonne_ordinate = forms.CharField(
        widget=forms.HiddenInput,
        required=False,
    )

    class Meta:
        model = VistaAdempimentoColonne
        fields = ("tipo", "vista", "colonne", "colonne_ordinate")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.colonne_codici:
            self.initial["colonne"] = list(self.instance.colonne_codici)
            self.initial["colonne_ordinate"] = ",".join(self.instance.colonne_codici)

    def clean(self):
        cleaned = super().clean()
        selezionate = set(cleaned.get("colonne") or [])
        ordinate_raw = (cleaned.get("colonne_ordinate") or "").strip()
        if ordinate_raw:
            ordine = [c for c in ordinate_raw.split(",") if c in selezionate]
            # Aggiunge eventuali codici spuntati ma assenti dall'ordine.
            for c in selezionate:
                if c not in ordine:
                    ordine.append(c)
        else:
            ordine = [c for c in STANDARD_COLUMNS if c in selezionate]
        cleaned["colonne_codici"] = ordine
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.colonne_codici = self.cleaned_data["colonne_codici"]
        if commit:
            instance.save()
        return instance


@admin.register(VistaAdempimentoColonne)
class VistaAdempimentoColonneAdmin(admin.ModelAdmin):
    form = VistaAdempimentoColonneForm
    list_display = ("tipo", "vista", "_colonne_preview", "updated_at")
    list_filter = ("vista", "tipo")
    autocomplete_fields = ("tipo",)

    class Media:
        # Sortable.js da CDN per il drag&drop tra le checkbox.
        js = (
            "https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js",
            "adempimenti/colonne_admin.js",
        )

    @admin.display(description="Colonne")
    def _colonne_preview(self, obj: VistaAdempimentoColonne) -> str:
        if not obj.colonne_codici:
            return "—"
        n = len(obj.colonne_codici)
        preview = ", ".join(obj.colonne_codici[:4])
        if n > 4:
            preview += f" (+{n - 4})"
        return preview


@admin.register(Adempimento)
class AdempimentoAdmin(admin.ModelAdmin):
    list_display = (
        "anagrafica",
        "tipo",
        "anno_fiscale",
        "periodo",
        "data_scadenza",
        "stato",
        "responsabile",
    )
    list_filter = ("tipo", "anno_fiscale", "stato")
    search_fields = (
        "anagrafica__denominazione",
        "anagrafica__codice_interno",
    )
    autocomplete_fields = ("anagrafica", "responsabile", "tipo")
    inlines = [StepCompletatoInline]
