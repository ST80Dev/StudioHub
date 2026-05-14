from django.apps import AppConfig


class AnagraficaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "anagrafica"
    verbose_name = "Anagrafiche clienti"

    def ready(self):
        # Connette i signal di invalidazione cache delle label di TextChoiceLabel
        from . import choices_labels
        choices_labels._connect_signals()
