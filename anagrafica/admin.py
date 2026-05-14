from django.contrib import admin

from .models import (
    Anagrafica,
    AnagraficaLegame,
    AnagraficaReferenteStudio,
    Categoria,
)


class ReferenteStudioInline(admin.TabularInline):
    model = AnagraficaReferenteStudio
    extra = 0
    autocomplete_fields = ("utente",)


class LegameInline(admin.TabularInline):
    model = AnagraficaLegame
    fk_name = "anagrafica"
    extra = 0
    autocomplete_fields = ("anagrafica_collegata",)


@admin.register(Anagrafica)
class AnagraficaAdmin(admin.ModelAdmin):
    list_display = (
        "codice_interno",
        "denominazione",
        "tipo_soggetto",
        "codice_fiscale",
        "partita_iva",
        "stato",
    )
    list_filter = ("tipo_soggetto", "stato", "regime_contabile", "periodicita_iva")
    search_fields = (
        "codice_interno",
        "denominazione",
        "codice_fiscale",
        "partita_iva",
        "cognome",
        "nome",
    )
    inlines = [ReferenteStudioInline, LegameInline]
    filter_horizontal = ("categorie",)
    fieldsets = (
        (
            "Identificazione",
            {
                "fields": (
                    "codice_interno",
                    "tipo_soggetto",
                    "denominazione",
                    "codice_fiscale",
                    "partita_iva",
                    "stato",
                    "data_inizio_mandato",
                    "data_fine_mandato",
                    "note",
                )
            },
        ),
        (
            "Dati persona fisica",
            {"fields": ("cognome", "nome"), "classes": ("collapse",)},
        ),
        (
            "Contatto",
            {
                "fields": (
                    "email",
                    "indirizzo_via",
                    "indirizzo_civico",
                    "indirizzo_cap",
                    "indirizzo_comune",
                    "indirizzo_provincia",
                    "indirizzo_nazione",
                )
            },
        ),
        (
            "Fiscale operativo",
            {"fields": ("regime_contabile", "periodicita_iva")},
        ),
        (
            "Profilo fiscale arricchito",
            {
                "fields": (
                    "contabilita",
                    "peso_contabilita",
                    "sostituto_imposta",
                    "iscritto_cciaa",
                    "data_fine_esercizio",
                    "categoria_professione",
                    "categorie",
                ),
            },
        ),
    )


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("slug", "denominazione", "attiva", "colore", "created_at")
    list_filter = ("attiva",)
    search_fields = ("slug", "denominazione", "descrizione")
    prepopulated_fields = {"slug": ("denominazione",)}


@admin.register(AnagraficaReferenteStudio)
class ReferenteStudioAdmin(admin.ModelAdmin):
    list_display = (
        "anagrafica",
        "utente",
        "ruolo",
        "principale",
        "data_inizio",
        "data_fine",
    )
    list_filter = ("ruolo", "principale")
    search_fields = ("anagrafica__denominazione", "utente__username")
    autocomplete_fields = ("anagrafica", "utente")


@admin.register(AnagraficaLegame)
class LegameAdmin(admin.ModelAdmin):
    list_display = ("anagrafica", "anagrafica_collegata", "tipo_legame")
    list_filter = ("tipo_legame",)
    search_fields = (
        "anagrafica__denominazione",
        "anagrafica_collegata__denominazione",
    )
    autocomplete_fields = ("anagrafica", "anagrafica_collegata")
