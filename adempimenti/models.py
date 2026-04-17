from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse


# ---------------------------------------------------------------------------
# Catalogo tipi adempimento (configurabile da UI)
# ---------------------------------------------------------------------------

class Periodicita(models.TextChoices):
    ANNUALE = "annuale", "Annuale"
    TRIMESTRALE = "trimestrale", "Trimestrale"
    MENSILE = "mensile", "Mensile"
    UNA_TANTUM = "una_tantum", "Una tantum"


class TipoAdempimentoCatalogo(models.Model):
    codice = models.SlugField(max_length=40, unique=True)
    denominazione = models.CharField(max_length=120)
    periodicita = models.CharField(
        max_length=20, choices=Periodicita.choices, default=Periodicita.ANNUALE
    )
    colore = models.CharField(
        max_length=20, blank=True,
        help_text="Colore CSS per badge/sidebar (es. '#3b82f6', 'blue').",
    )
    attivo = models.BooleanField(default=True, db_index=True)
    note_regole = models.TextField(
        blank=True,
        help_text="Appunti interni sulla regola di scadenza.",
    )
    ordine = models.PositiveSmallIntegerField(default=0)

    # Scadenza calcolata da un evento variabile sul singolo adempimento
    # (es. Bilancio UE: "30 giorni dalla data di approvazione assemblea").
    # Se entrambi questi campi sono valorizzati il tipo usa la modalità
    # "evento + offset" e le righe ScadenzaPeriodo vengono ignorate.
    etichetta_data_evento = models.CharField(
        max_length=100, blank=True,
        help_text=(
            "Nome dell'evento di riferimento (es. 'Data assemblea approvazione "
            "bilancio'). Lasciare vuoto se la scadenza è una data fissa."
        ),
    )
    giorni_offset_da_evento = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Giorni dopo l'evento entro cui scade l'adempimento.",
    )

    class Meta:
        ordering = ("ordine", "denominazione")
        verbose_name = "Tipo adempimento"
        verbose_name_plural = "Tipi adempimento"

    def __str__(self) -> str:
        return self.denominazione

    @property
    def usa_evento_variabile(self) -> bool:
        return bool(self.etichetta_data_evento) and self.giorni_offset_da_evento is not None


class ScadenzaPeriodo(models.Model):
    tipo_adempimento = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.CASCADE,
        related_name="scadenze",
    )
    periodo = models.PositiveSmallIntegerField(
        help_text="1 per annuale, 1-4 per trimestrale, 1-12 per mensile.",
    )
    mese_scadenza = models.PositiveSmallIntegerField(
        help_text="Mese dell'anno in cui cade la scadenza (1-12).",
    )
    giorno_scadenza = models.PositiveSmallIntegerField(
        help_text="Giorno del mese di scadenza (1-31).",
    )
    anno_offset = models.SmallIntegerField(
        default=0,
        help_text="0 = stesso anno fiscale, 1 = anno successivo.",
    )
    etichetta = models.CharField(
        max_length=30,
        help_text="Es: 'Q1', 'Gennaio', 'Annuale'.",
    )

    class Meta:
        ordering = ("tipo_adempimento", "periodo")
        verbose_name = "Scadenza periodo"
        verbose_name_plural = "Scadenze periodo"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_adempimento", "periodo"],
                name="uniq_scadenza_tipo_periodo",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tipo_adempimento} — {self.etichetta}"

    def calcola_data_scadenza(self, anno_fiscale: int) -> date:
        anno = anno_fiscale + self.anno_offset
        return date(anno, self.mese_scadenza, self.giorno_scadenza)


class ChecklistStep(models.Model):
    tipo_adempimento = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.CASCADE,
        related_name="checklist_steps",
    )
    ordine = models.PositiveSmallIntegerField(default=0)
    denominazione = models.CharField(max_length=200)

    class Meta:
        ordering = ("tipo_adempimento", "ordine")
        verbose_name = "Step checklist"
        verbose_name_plural = "Step checklist"

    def __str__(self) -> str:
        return f"{self.tipo_adempimento} — {self.ordine}. {self.denominazione}"


# ---------------------------------------------------------------------------
# Regole di applicabilità (motore regole semplice)
# ---------------------------------------------------------------------------

class CampoCondizione(models.TextChoices):
    TIPO_SOGGETTO = "tipo_soggetto", "Tipo soggetto"
    REGIME_CONTABILE = "regime_contabile", "Regime contabile"
    PERIODICITA_IVA = "periodicita_iva", "Periodicità IVA"
    SOSTITUTO_IMPOSTA = "sostituto_imposta", "Sostituto d'imposta"
    ISCRITTO_CCIAA = "iscritto_cciaa", "Iscritto CCIAA"
    CONTABILITA = "contabilita", "Contabilità (interna/esterna)"
    CATEGORIA_PROFESSIONE = "categoria_professione", "Categoria professione"


class OperatoreRegola(models.TextChoices):
    UGUALE = "uguale", "Uguale a"
    IN_LISTA = "in_lista", "In lista (valori separati da virgola)"
    VERO = "vero", "Vero (campo booleano)"
    FALSO = "falso", "Falso (campo booleano)"


class RegolaApplicabilita(models.Model):
    tipo_adempimento = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.CASCADE,
        related_name="regole",
    )
    campo_condizione = models.CharField(
        max_length=30, choices=CampoCondizione.choices
    )
    operatore = models.CharField(
        max_length=20, choices=OperatoreRegola.choices
    )
    valore = models.CharField(
        max_length=200, blank=True,
        help_text="Valore di confronto. Per 'in_lista' separare con virgola (es. 'SRL,SPA').",
    )
    attiva = models.BooleanField(default=True)
    ordine = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("tipo_adempimento", "ordine")
        verbose_name = "Regola di applicabilità"
        verbose_name_plural = "Regole di applicabilità"

    def __str__(self) -> str:
        return (
            f"{self.tipo_adempimento} — "
            f"{self.get_campo_condizione_display()} "
            f"{self.get_operatore_display()} {self.valore}"
        )

    def valuta(self, anagrafica) -> bool:
        val_cliente = self._leggi_campo(anagrafica)
        if self.operatore == OperatoreRegola.VERO:
            return bool(val_cliente)
        if self.operatore == OperatoreRegola.FALSO:
            return not bool(val_cliente)
        if self.operatore == OperatoreRegola.UGUALE:
            return str(val_cliente) == self.valore.strip()
        if self.operatore == OperatoreRegola.IN_LISTA:
            lista = [v.strip() for v in self.valore.split(",")]
            return str(val_cliente) in lista
        return False

    def _leggi_campo(self, anagrafica):
        mapping = {
            CampoCondizione.TIPO_SOGGETTO: "tipo_soggetto",
            CampoCondizione.REGIME_CONTABILE: "regime_contabile",
            CampoCondizione.PERIODICITA_IVA: "periodicita_iva",
            CampoCondizione.SOSTITUTO_IMPOSTA: "sostituto_imposta",
            CampoCondizione.ISCRITTO_CCIAA: "iscritto_cciaa",
            CampoCondizione.CONTABILITA: "contabilita",
            CampoCondizione.CATEGORIA_PROFESSIONE: "categoria_professione",
        }
        attr = mapping.get(self.campo_condizione, "")
        return getattr(anagrafica, attr, None)


def tipi_applicabili(anagrafica) -> list[TipoAdempimentoCatalogo]:
    """Restituisce i tipi adempimento applicabili a un'anagrafica
    in base alle regole di applicabilità configurate.

    Logica: per ogni tipo, TUTTE le regole attive devono essere soddisfatte (AND).
    Tipi con 0 regole non si applicano a nessuno automaticamente.
    """
    risultato = []
    for tipo in TipoAdempimentoCatalogo.objects.filter(attivo=True).prefetch_related("regole"):
        regole_attive = [r for r in tipo.regole.all() if r.attiva]
        if not regole_attive:
            continue
        if all(r.valuta(anagrafica) for r in regole_attive):
            risultato.append(tipo)
    return risultato


# ---------------------------------------------------------------------------
# Adempimento (record operativo)
# ---------------------------------------------------------------------------

class StatoAdempimento(models.TextChoices):
    DA_FARE = "da_fare", "Da fare"
    IN_CORSO = "in_corso", "In corso"
    CONTROLLATO = "controllato", "Controllato"
    INVIATO = "inviato", "Inviato"


class Adempimento(models.Model):
    anagrafica = models.ForeignKey(
        "anagrafica.Anagrafica",
        on_delete=models.PROTECT,
        related_name="adempimenti",
    )
    tipo = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.PROTECT,
        related_name="adempimenti",
    )
    anno_fiscale = models.IntegerField(db_index=True)
    periodo = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Null per annuale. 1-4 per trimestrale, 1-12 per mensile.",
    )
    data_evento_riferimento = models.DateField(
        null=True, blank=True,
        help_text=(
            "Data dell'evento di riferimento (es. data assemblea approvazione "
            "bilancio). Usata solo per tipi con scadenza a offset da evento."
        ),
    )
    data_scadenza = models.DateField(
        null=True, blank=True,
        help_text=(
            "Calcolata automaticamente (ScadenzaPeriodo o data_evento + offset), "
            "sovrascrivibile dall'utente."
        ),
    )
    stato = models.CharField(
        max_length=15,
        choices=StatoAdempimento.choices,
        default=StatoAdempimento.DA_FARE,
        db_index=True,
    )
    responsabile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adempimenti_eseguiti",
    )
    note = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    is_demo = models.BooleanField(
        default=False,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("data_scadenza", "anagrafica__denominazione")
        verbose_name = "Adempimento"
        verbose_name_plural = "Adempimenti"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "tipo", "anno_fiscale", "periodo"],
                name="uniq_adempimento_cliente_tipo_anno_periodo",
            ),
        ]
        indexes = [
            models.Index(fields=["tipo", "anno_fiscale"]),
            models.Index(fields=["tipo", "stato"]),
            models.Index(fields=["data_scadenza", "stato"]),
        ]

    def __str__(self) -> str:
        etichetta_periodo = ""
        if self.periodo is not None:
            etichetta_periodo = f" P{self.periodo}"
        return (
            f"{self.tipo} {self.anno_fiscale}{etichetta_periodo} — "
            f"{self.anagrafica}"
        )

    def get_absolute_url(self) -> str:
        return reverse("adempimenti:detail", args=[self.pk])

    def referenti_cliente_nel_periodo(self, ruolo: str):
        from anagrafica.models import RuoloReferenteStudio

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
        from anagrafica.models import RuoloReferenteStudio
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.ADDETTO_CONTABILITA
        )

    @property
    def responsabili_consulenza_cliente(self):
        from anagrafica.models import RuoloReferenteStudio
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.RESPONSABILE_CONSULENZA
        )

    @property
    def is_scaduto(self) -> bool:
        if self.data_scadenza and self.stato != StatoAdempimento.INVIATO:
            return date.today() > self.data_scadenza
        return False

    def calcola_data_scadenza(self):
        """Ritorna la data scadenza derivata dal tipo. Non persiste.

        - Se il tipo usa evento + offset: data_evento_riferimento + giorni_offset.
          Se l'evento non è ancora valorizzato ritorna None.
        - Altrimenti cerca la ScadenzaPeriodo corrispondente al periodo.
        """
        from datetime import timedelta

        if self.tipo.usa_evento_variabile:
            if not self.data_evento_riferimento:
                return None
            return self.data_evento_riferimento + timedelta(
                days=self.tipo.giorni_offset_da_evento
            )

        scadenza = self.tipo.scadenze.filter(periodo=self.periodo or 1).first()
        if not scadenza:
            return None
        return scadenza.calcola_data_scadenza(self.anno_fiscale)


class StepCompletato(models.Model):
    adempimento = models.ForeignKey(
        Adempimento,
        on_delete=models.CASCADE,
        related_name="steps_completati",
    )
    step = models.ForeignKey(
        ChecklistStep,
        on_delete=models.CASCADE,
        related_name="completamenti",
    )
    completato = models.BooleanField(default=False)
    data_completamento = models.DateField(null=True, blank=True)
    completato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Step completato"
        verbose_name_plural = "Step completati"
        constraints = [
            models.UniqueConstraint(
                fields=["adempimento", "step"],
                name="uniq_step_per_adempimento",
            ),
        ]

    def __str__(self) -> str:
        mark = "V" if self.completato else " "
        return f"[{mark}] {self.step.denominazione} — {self.adempimento}"
