from django.apps import AppConfig


class AdempimentiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "adempimenti"
    verbose_name = "Adempimenti"

    def ready(self) -> None:
        # Registra i signal del modulo stati (auto-copia Standard → Tipo
        # alla creazione di un TipoAdempimentoCatalogo, invalidazione cache
        # in-memory degli stati su save/delete).
        from . import stati  # noqa: F401
        stati._connect_signals()
