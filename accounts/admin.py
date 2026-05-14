from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AreaAziendale, UtenteStudio


@admin.register(AreaAziendale)
class AreaAziendaleAdmin(admin.ModelAdmin):
    list_display = ("denominazione", "codice", "ordine", "attivo")
    list_editable = ("ordine", "attivo")
    search_fields = ("denominazione", "codice")
    prepopulated_fields = {"codice": ("denominazione",)}


@admin.register(UtenteStudio)
class UtenteStudioAdmin(UserAdmin):
    list_display = (
        "username",
        "last_name",
        "first_name",
        "etichetta_ui",
        "email",
        "is_active",
        "is_staff",
    )
    list_editable = ("etichetta_ui",)
    filter_horizontal = ("aree", "groups", "user_permissions")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Studio",
            {
                "fields": (
                    "telefono",
                    "etichetta_ui",
                    "aree",
                    "tema",
                    "densita_ui",
                )
            },
        ),
    )
