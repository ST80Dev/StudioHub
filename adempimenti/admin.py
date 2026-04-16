from django.contrib import admin

from .models import Adempimento, AdempimentoBilancioUE


class BilancioUEInline(admin.StackedInline):
    model = AdempimentoBilancioUE
    extra = 0
    can_delete = False


@admin.register(Adempimento)
class AdempimentoAdmin(admin.ModelAdmin):
    list_display = (
        "anagrafica",
        "tipo",
        "anno_fiscale",
        "anno_esecuzione",
        "responsabile",
        "stato",
    )
    list_filter = ("tipo", "anno_fiscale", "anno_esecuzione")
    search_fields = (
        "anagrafica__denominazione",
        "anagrafica__codice_interno",
    )
    autocomplete_fields = ("anagrafica", "responsabile")
    inlines = [BilancioUEInline]


@admin.register(AdempimentoBilancioUE)
class BilancioUEAdmin(admin.ModelAdmin):
    list_display = (
        "adempimento",
        "data_chiusura_bilancio",
        "data_compilazione",
        "data_invio_pratica",
        "stato_label",
    )
