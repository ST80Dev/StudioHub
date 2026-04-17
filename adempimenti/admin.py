from django.contrib import admin

from .models import (
    Adempimento,
    ChecklistStep,
    RegolaApplicabilita,
    ScadenzaPeriodo,
    StepCompletato,
    TipoAdempimentoCatalogo,
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
