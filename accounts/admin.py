from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UtenteStudioCreationForm
from .models import AreaAziendale, UtenteStudio


@admin.register(AreaAziendale)
class AreaAziendaleAdmin(admin.ModelAdmin):
    list_display = ("denominazione", "codice", "ordine", "attivo")
    list_editable = ("ordine", "attivo")
    search_fields = ("denominazione", "codice")
    prepopulated_fields = {"codice": ("denominazione",)}


@admin.register(UtenteStudio)
class UtenteStudioAdmin(UserAdmin):
    add_form = UtenteStudioCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
                "description": (
                    "I campi password sono facoltativi: se lasciati vuoti, "
                    "l'utente viene creato con login disabilitato finché "
                    "non gli si imposta una password."
                ),
            },
        ),
    )
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
