from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.urls import reverse


class TipoSoggetto(models.TextChoices):
    PF = "PF", "Persona fisica"
    PROFEX = "PROFEX", "Professionista"
    DI = "DI", "Ditta individuale"
    SNC = "SNC", "SNC"
    SAS = "SAS", "SAS"
    SRL = "SRL", "SRL"
    SPA = "SPA", "SPA"
    ASS = "ASS", "Associazione"
    FALL = "FALL", "Fallimento"


# Insiemi di tipo_soggetto (utili per logica applicativa)
TIPI_PERSONA_FISICA = {
    TipoSoggetto.PF,
    TipoSoggetto.PROFEX,
    TipoSoggetto.DI,
}
TIPI_ENTITA = {
    TipoSoggetto.SNC,
    TipoSoggetto.SAS,
    TipoSoggetto.SRL,
    TipoSoggetto.SPA,
    TipoSoggetto.ASS,
    TipoSoggetto.FALL,
}
# Tipi per i quali è dovuto il BILANCIO UE (bilancio d'esercizio telematico).
TIPI_BILANCIO_UE = {TipoSoggetto.SRL, TipoSoggetto.SPA}


class StatoAnagrafica(models.TextChoices):
    ATTIVO = "attivo", "Attivo"
    SOSPESO = "sospeso", "Sospeso"
    CESSATO = "cessato", "Cessato"


class RegimeContabile(models.TextChoices):
    ORDINARIO = "ordinario", "Ordinario"
    SEMPLIFICATO = "semplificato", "Semplificato"
    FORFETTARIO = "forfettario", "Forfettario"
    NON_APPLICABILE = "non_applicabile", "Non applicabile"


class PeriodicitaIVA(models.TextChoices):
    MENSILE = "mensile", "Mensile"
    TRIMESTRALE = "trimestrale", "Trimestrale"
    NON_SOGGETTO = "non_soggetto", "Non soggetto"


class Anagrafica(models.Model):
    """Anagrafica unica del cliente (PF / PG / Ente), discriminata da `tipo_soggetto`.

    Principio guida: contiene solo dati operativi cardine. Nessun dato camerale
    dettagliato, nessun dato antiriciclaggio: quelli si consultano su strumenti
    dedicati (visura, software AML).
    """

    codice_interno = models.CharField(max_length=16, unique=True)
    tipo_soggetto = models.CharField(
        max_length=8, choices=TipoSoggetto.choices, db_index=True
    )
    denominazione = models.CharField(max_length=255, db_index=True)

    codice_fiscale = models.CharField(max_length=16, blank=True, db_index=True)
    partita_iva = models.CharField(max_length=11, blank=True, db_index=True)

    stato = models.CharField(
        max_length=10,
        choices=StatoAnagrafica.choices,
        default=StatoAnagrafica.ATTIVO,
        db_index=True,
    )
    data_inizio_mandato = models.DateField(null=True, blank=True)
    data_fine_mandato = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    # Contatto
    email = models.EmailField(blank=True)

    # Indirizzo (sede legale / residenza)
    indirizzo_via = models.CharField(max_length=200, blank=True)
    indirizzo_civico = models.CharField(max_length=20, blank=True)
    indirizzo_cap = models.CharField(max_length=10, blank=True)
    indirizzo_comune = models.CharField(max_length=100, blank=True)
    indirizzo_provincia = models.CharField(max_length=2, blank=True)
    indirizzo_nazione = models.CharField(max_length=50, blank=True, default="Italia")

    # Fiscale operativo (pilota gli adempimenti)
    regime_contabile = models.CharField(
        max_length=20, choices=RegimeContabile.choices, blank=True
    )
    periodicita_iva = models.CharField(
        max_length=20, choices=PeriodicitaIVA.choices, blank=True
    )

    # Specifici PF (valorizzati solo se tipo in PF/PROFEX/DI)
    cognome = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100, blank=True)

    # Soft delete
    is_deleted = models.BooleanField(default=False)

    # Dati di test vs reali: cfr. ROADMAP.md — sezione "Policy dati demo vs reali"
    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True per anagrafiche create dal seed di test.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("denominazione",)
        verbose_name = "Anagrafica"
        verbose_name_plural = "Anagrafiche"

    def __str__(self) -> str:
        return f"{self.codice_interno} — {self.denominazione}"

    def get_absolute_url(self) -> str:
        return reverse("anagrafica:detail", args=[self.pk])

    @property
    def is_persona_fisica(self) -> bool:
        return self.tipo_soggetto in TIPI_PERSONA_FISICA

    @property
    def is_entita(self) -> bool:
        return self.tipo_soggetto in TIPI_ENTITA


class RuoloReferenteStudio(models.TextChoices):
    ADDETTO_CONTABILITA = "addetto_contabilita", "Addetto contabilità"
    RESPONSABILE_CONSULENZA = "responsabile_consulenza", "Responsabile consulenza"


class AnagraficaReferenteStudio(models.Model):
    """Referente interno dello studio per un cliente (storicizzato).

    Un cliente può avere 1-2 addetti contabilità e 1-2 responsabili consulenza.
    Le righe sono storicizzate: quando cambia il referente si chiude la riga
    esistente (`data_fine`) e si apre una nuova.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="referenti_studio"
    )
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="anagrafiche_seguite",
    )
    ruolo = models.CharField(max_length=30, choices=RuoloReferenteStudio.choices)
    principale = models.BooleanField(
        default=False,
        help_text="Quando ci sono più referenti dello stesso ruolo, "
        "indica quello principale / capo-pratica.",
    )
    data_inizio = models.DateField()
    data_fine = models.DateField(
        null=True,
        blank=True,
        help_text="Vuoto = ancora in carica.",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-data_inizio",)
        verbose_name = "Referente di studio"
        verbose_name_plural = "Referenti di studio"
        indexes = [
            models.Index(fields=["anagrafica", "ruolo", "data_inizio"]),
            models.Index(fields=["utente", "ruolo", "data_inizio"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(data_fine__isnull=True) | Q(data_fine__gte=F("data_inizio")),
                name="referente_data_fine_non_prima_di_inizio",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.utente} — {self.get_ruolo_display()} di {self.anagrafica}"


class TipoLegame(models.TextChoices):
    SOCIO = "socio", "Socio"
    AMMINISTRATORE = "amministratore", "Amministratore"
    LEGALE_RAPPR = "legale_rappr", "Legale rappresentante"
    CONIUGE = "coniuge", "Coniuge"
    GARANTE = "garante", "Garante"
    ALTRO = "altro", "Altro"


class AnagraficaLegame(models.Model):
    """Legame tra due anagrafiche (PF ↔ PG, tipicamente).

    Permette di annotare relazioni tipo: socio, amministratore, legale
    rappresentante, coniuge, garante, ecc. N legami per anagrafica.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="legami_da"
    )
    anagrafica_collegata = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="legami_a"
    )
    tipo_legame = models.CharField(max_length=20, choices=TipoLegame.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Legame anagrafico"
        verbose_name_plural = "Legami anagrafici"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "anagrafica_collegata", "tipo_legame"],
                name="uniq_legame_anagrafico",
            ),
            models.CheckConstraint(
                check=~Q(anagrafica=F("anagrafica_collegata")),
                name="legame_non_autoriferito",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.anagrafica} → {self.anagrafica_collegata} "
            f"({self.get_tipo_legame_display()})"
        )
