from django import forms
from django.contrib import admin

from .columns import STANDARD_COLUMNS, available_column_choices
from .models import (
    Adempimento,
    ChecklistStep,
    RegolaApplicabilita,
    ScadenzaPeriodo,
    StatoAdempimentoStandard,
    StatoAdempimentoTipo,
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


class StatoAdempimentoTipoInline(admin.TabularInline):
    """Stati specifici del tipo adempimento.

    Sia le righe `e_predefinito=True` (copiate dallo Standard) che quelle
    custom sono modificabili ed eliminabili. La cancellazione di uno stato
    in uso da adempimenti viene bloccata da `StatoAdempimentoTipo.delete()`
    con un errore esplicito: per riassegnare prima gli adempimenti, usare
    la UI Configurazione → tab Stati (che offre un picker di rimpiazzo).
    """
    model = StatoAdempimentoTipo
    extra = 0
    fields = (
        "codice", "denominazione", "sigla", "colore",
        "lavorabile", "livello", "iniziale_default",
        "attivo", "e_predefinito",
    )
    readonly_fields = ("e_predefinito",)
    ordering = ("livello", "denominazione")


@admin.register(TipoAdempimentoCatalogo)
class TipoAdempimentoCatalogoAdmin(admin.ModelAdmin):
    list_display = (
        "codice", "denominazione", "abbreviazione", "periodicita",
        "ha_vista_dedicata", "attivo", "ordine",
    )
    list_filter = ("periodicita", "attivo", "ha_vista_dedicata")
    search_fields = ("codice", "denominazione", "abbreviazione")
    inlines = [
        ScadenzaPeriodoInline,
        StatoAdempimentoTipoInline,
        ChecklistStepInline,
        RegolaApplicabilitaInline,
    ]


@admin.register(StatoAdempimentoStandard)
class StatoAdempimentoStandardAdmin(admin.ModelAdmin):
    """Set predefinito globale degli stati.

    Modificando voci qui NON si tocca gli stati gia' assegnati ai tipi
    esistenti (per non sovrascrivere personalizzazioni). Lo Standard impatta
    solo le nuove copie alla creazione di un nuovo TipoAdempimentoCatalogo.
    """
    list_display = (
        "codice", "denominazione", "sigla", "colore",
        "lavorabile", "livello", "iniziale_default", "attivo",
    )
    list_filter = ("colore", "lavorabile", "attivo")
    list_editable = (
        "denominazione", "sigla", "colore",
        "lavorabile", "livello", "iniziale_default", "attivo",
    )
    search_fields = ("codice", "denominazione")
    ordering = ("livello", "denominazione")


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
        fields = ("tipo", "vista", "colonne", "colonne_ordinate", "larghezze_colonne")
        help_texts = {
            "larghezze_colonne": (
                "Override fine. Di norma si imposta dalla UI di pagina "
                "(\"Modifica vista\") con il drag del bordo destro delle "
                "colonne. Formato: {\"<codice>\": <px>}, con px in 40..800."
            ),
        }

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
