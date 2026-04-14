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
        "email",
        "is_active",
        "is_staff",
    )
    filter_horizontal = ("aree", "groups", "user_permissions")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Studio",
            {
                "fields": (
                    "telefono",
                    "aree",
                    "tema",
                    "densita_ui",
                )
            },
        ),
    )
