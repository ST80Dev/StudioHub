from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse

from anagrafica.models import Anagrafica, RuoloReferenteStudio


class TipoAdempimento(models.TextChoices):
    """Catalogo dei tipi di adempimento gestiti dalla piattaforma.

    Estendere con nuovi valori quando si aggiungono nuove figlie
    (`adempimento_<tipo>`): il dispatcher applicativo mappa tipo → figlia.
    """

    BILANCIO_UE = "BILANCIO_UE", "Bilancio UE"


class Adempimento(models.Model):
    """Tabella padre. Contiene solo ciò che è comune a tutti i tipi.

    Le caratteristiche specifiche di un tipo stanno nella figlia 1:1
    (es. AdempimentoBilancioUE), collegata via `adempimento_id`.
    """

    anagrafica = models.ForeignKey(
        Anagrafica,
        on_delete=models.PROTECT,
        related_name="adempimenti",
    )
    tipo = models.CharField(
        max_length=30, choices=TipoAdempimento.choices, db_index=True
    )
    anno_fiscale = models.IntegerField(
        db_index=True,
        help_text=(
            "Anno fiscale di riferimento (es. 2025 per il bilancio "
            "d'esercizio 2025). Pivot per derivare i referenti del cliente."
        ),
    )
    anno_esecuzione = models.IntegerField(
        db_index=True,
        help_text="Anno in cui l'adempimento viene eseguito (es. 2026).",
    )
    responsabile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adempimenti_eseguiti",
        help_text="Esecutore concreto. Libero, non necessariamente un referente del cliente.",
    )
    note = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)

    # Dati di test vs reali: cfr. ROADMAP.md — sezione "Policy dati demo vs reali"
    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True per adempimenti creati dal seed di test.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-anno_esecuzione", "anagrafica__denominazione")
        verbose_name = "Adempimento"
        verbose_name_plural = "Adempimenti"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "tipo", "anno_fiscale"],
                name="uniq_adempimento_cliente_tipo_anno_fiscale",
            ),
        ]
        indexes = [
            models.Index(fields=["tipo", "anno_esecuzione"]),
            models.Index(fields=["tipo", "anno_fiscale"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_tipo_display()} {self.anno_fiscale} — {self.anagrafica}"
        )

    def get_absolute_url(self) -> str:
        return reverse("adempimenti:detail", args=[self.pk])

    # ------------------------------------------------------------------ helpers

    def referenti_cliente_nel_periodo(self, ruolo: str):
        """Derivazione opzione B: referenti validi durante l'anno fiscale."""
        inizio = date(self.anno_fiscale, 1, 1)
        fine = date(self.anno_fiscale, 12, 31)
        return self.anagrafica.referenti_studio.filter(
            ruolo=ruolo,
            data_inizio__lte=fine,
        ).filter(
            models.Q(data_fine__isnull=True) | models.Q(data_fine__gte=inizio)
        ).select_related("utente")

    @property
    def addetti_contabilita_cliente(self):
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.ADDETTO_CONTABILITA
        )

    @property
    def responsabili_consulenza_cliente(self):
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.RESPONSABILE_CONSULENZA
        )

    @property
    def dettaglio(self):
        """Restituisce la figlia 1:1 corrispondente al tipo."""
        if self.tipo == TipoAdempimento.BILANCIO_UE:
            return getattr(self, "bilancio_ue", None)
        return None

    @property
    def stato(self) -> str:
        dettaglio = self.dettaglio
        if dettaglio and hasattr(dettaglio, "stato"):
            return dettaglio.stato
        return "sconosciuto"


class StatoBilancioUE(models.TextChoices):
    DA_INIZIARE = "da_iniziare", "Da iniziare"
    DA_COMPILARE = "da_compilare", "Chiuso, da compilare"
    DA_INVIARE = "da_inviare", "Compilato, da inviare"
    COMPLETATO = "completato", "Completato"


class AdempimentoBilancioUE(models.Model):
    """Figlia 1:1 per il tipo BILANCIO_UE.

    Lo stato è DERIVATO dai tre timestamp, non memorizzato.
    """

    adempimento = models.OneToOneField(
        Adempimento,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="bilancio_ue",
    )
    data_chiusura_bilancio = models.DateField(null=True, blank=True)
    data_compilazione = models.DateField(null=True, blank=True)
    data_invio_pratica = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Bilancio UE"
        verbose_name_plural = "Bilanci UE"

    def __str__(self) -> str:
        return f"Bilancio UE — {self.adempimento}"

    @property
    def stato(self) -> str:
        if self.data_invio_pratica:
            return StatoBilancioUE.COMPLETATO
        if self.data_compilazione:
            return StatoBilancioUE.DA_INVIARE
        if self.data_chiusura_bilancio:
            return StatoBilancioUE.DA_COMPILARE
        return StatoBilancioUE.DA_INIZIARE

    @property
    def stato_label(self) -> str:
        return dict(StatoBilancioUE.choices).get(self.stato, "")
