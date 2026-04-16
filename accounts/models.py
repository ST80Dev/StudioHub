from django.contrib.auth.models import AbstractUser
from django.db import models


class Tema(models.TextChoices):
    LIGHT = "light", "Chiaro"
    DARK = "dark", "Scuro"
    AUTO = "auto", "Auto (sistema)"


class DensitaUI(models.TextChoices):
    COMPATTA = "compatta", "Compatta"
    STANDARD = "standard", "Standard"


class AreaAziendale(models.Model):
    """Aree organizzative dello studio (Contabilità, Consulenza, ecc.).

    Un utente può appartenere a più aree (M2M via UtenteStudio.aree).
    """

    codice = models.SlugField(max_length=32, unique=True)
    denominazione = models.CharField(max_length=100)
    ordine = models.PositiveSmallIntegerField(default=0)
    attivo = models.BooleanField(default=True)

    class Meta:
        ordering = ("ordine", "denominazione")
        verbose_name = "Area aziendale"
        verbose_name_plural = "Aree aziendali"

    def __str__(self) -> str:
        return self.denominazione


class UtenteStudio(AbstractUser):
    """Utente interno dello studio.

    Estende AbstractUser di Django per poter aggiungere preferenze UI
    e l'appartenenza alle aree aziendali.
    """

    telefono = models.CharField(max_length=30, blank=True)
    tema = models.CharField(
        max_length=10, choices=Tema.choices, default=Tema.AUTO
    )
    densita_ui = models.CharField(
        max_length=10,
        choices=DensitaUI.choices,
        default=DensitaUI.COMPATTA,
    )
    aree = models.ManyToManyField(
        AreaAziendale, blank=True, related_name="utenti"
    )

    class Meta:
        ordering = ("last_name", "first_name", "username")
        verbose_name = "Utente studio"
        verbose_name_plural = "Utenti studio"

    def __str__(self) -> str:
        full = self.get_full_name()
        return full or self.username
