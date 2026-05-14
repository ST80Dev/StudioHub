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

    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True per utenti creati dal seed di test. Mai True per utenti reali.",
    )

    # Etichetta usata nelle liste/elenchi UI dove il "Cognome Nome" può
    # creare omonimi. Default suggerito: "nome.c" (es. "mario.r" per Mario
    # Rossi). Modificabile a piacimento dagli admin via Django admin.
    etichetta_ui = models.CharField(
        max_length=40,
        blank=True,
        help_text="Etichetta breve usata nelle liste (es. 'mario.r'). "
        "Se vuoto, viene generata automaticamente da nome+cognome o "
        "in fallback dallo username.",
    )

    class Meta:
        ordering = ("last_name", "first_name", "username")
        verbose_name = "Utente studio"
        verbose_name_plural = "Utenti studio"

    def __str__(self) -> str:
        full = self.get_full_name()
        return full or self.username

    @property
    def etichetta_lista(self) -> str:
        """Etichetta breve da mostrare in tabelle/elenchi.

        Priorità: `etichetta_ui` se impostata; altrimenti `nome.c` (nome
        minuscolo + iniziale cognome); in ultimo fallback lo username.
        """
        if self.etichetta_ui:
            return self.etichetta_ui
        nome = (self.first_name or "").strip()
        cognome = (self.last_name or "").strip()
        if nome and cognome:
            return f"{nome.lower()}.{cognome[0].lower()}"
        if nome:
            return nome.lower()
        if cognome:
            return cognome.lower()
        return self.username
