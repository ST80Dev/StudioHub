from django.contrib import admin

from .models import (
    AnagraficaAlias,
    DatoImportato,
    ImportRow,
    ImportSession,
)


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    fields = (
        "numero_riga",
        "anagrafica_match",
        "metodo_match",
        "confidenza",
        "decisione",
    )
    readonly_fields = ("numero_riga", "metodo_match", "confidenza")
    show_change_link = True


@admin.register(ImportSession)
class ImportSessionAdmin(admin.ModelAdmin):
    list_display = ("nome", "stato", "consente_creazione", "creato_da", "created_at")
    list_filter = ("stato", "consente_creazione")
    search_fields = ("nome",)
    readonly_fields = ("created_at", "updated_at", "applied_at", "riepilogo")
    inlines = [ImportRowInline]


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "sessione",
        "numero_riga",
        "anagrafica_match",
        "metodo_match",
        "confidenza",
        "decisione",
    )
    list_filter = ("decisione", "metodo_match")
    search_fields = ("dati_grezzi",)
    raw_id_fields = ("sessione", "anagrafica_match")


@admin.register(AnagraficaAlias)
class AnagraficaAliasAdmin(admin.ModelAdmin):
    list_display = ("denominazione_alias", "anagrafica", "fonte", "created_at")
    search_fields = ("denominazione_alias", "anagrafica__denominazione")
    raw_id_fields = ("anagrafica",)


@admin.register(DatoImportato)
class DatoImportatoAdmin(admin.ModelAdmin):
    list_display = ("anagrafica", "chiave", "valore", "fonte_session", "updated_at")
    list_filter = ("chiave",)
    search_fields = ("anagrafica__denominazione", "chiave", "valore")
    raw_id_fields = ("anagrafica", "fonte_session")
