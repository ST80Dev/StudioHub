from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.urls import reverse


class TipoSoggetto(models.TextChoices):
    PF = "pf", "Persona fisica"
    PROFEX = "profex", "Professionista"
    DI = "di", "Ditta individuale"
    SNC = "snc", "SNC"
    SAS = "sas", "SAS"
    SRL = "srl", "SRL"
    SPA = "spa", "SPA"
    ASS = "ass", "Associazione"
    FALL = "fall", "Fallimento"


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


class GestioneContabilita(models.TextChoices):
    INTERNA = "interna", "Interna (tenuta dallo studio)"
    ESTERNA = "esterna", "Esterna"


class Categoria(models.Model):
    """Tag categoriale per anagrafica.

    Insieme di etichette riusabili (es. 'sanitaria-esente', 'agricolo',
    'ente-non-commerciale') per marcare specificità del soggetto utili
    al motore regole degli adempimenti e ai filtri di lista.
    """

    slug = models.SlugField(max_length=40, unique=True)
    denominazione = models.CharField(max_length=80)
    colore = models.CharField(max_length=20, blank=True)
    descrizione = models.CharField(max_length=200, blank=True)
    attiva = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("denominazione",)
        verbose_name = "Categoria anagrafica"
        verbose_name_plural = "Categorie anagrafica"

    def __str__(self) -> str:
        return self.denominazione


class Anagrafica(models.Model):
    """Anagrafica unica del cliente (PF / PG / Ente), discriminata da `tipo_soggetto`.

    Principio guida: contiene solo dati operativi cardine. Nessun dato camerale
    dettagliato, nessun dato antiriciclaggio: quelli si consultano su strumenti
    dedicati (visura, software AML).
    """

    codice_interno = models.CharField(max_length=16, unique=True)
    tipo_soggetto = models.CharField(
        max_length=8, choices=TipoSoggetto.choices, db_index=True, blank=True
    )
    denominazione = models.CharField(max_length=255, db_index=True)

    codice_fiscale = models.CharField(max_length=16, blank=True, db_index=True)
    partita_iva = models.CharField(max_length=11, blank=True, db_index=True)

    # Codici provenienti dai gestionali esterni. Usati come chiavi di match
    # negli import Excel. Tutti opzionali: non ogni anagrafica li ha tutti.
    codice_cli = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        unique=True,
        help_text="COD CLI ANA — progressivo anagrafica unica gestionale (id_oe002_cliente).",
    )
    codice_multi = models.CharField(
        max_length=16,
        blank=True,
        db_index=True,
        help_text="COD MULTI — progressivo ditta nel gestionale di contabilità.",
    )
    codice_gstudio = models.CharField(
        max_length=16,
        blank=True,
        db_index=True,
        help_text="COD GSTU — progressivo nel gestionale registrazione ore (id_bp004_cliente).",
    )

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

    # Profilo fiscale arricchito (usato dal motore regole per derivare
    # quali adempimenti competono al cliente)
    contabilita = models.CharField(
        max_length=10,
        choices=GestioneContabilita.choices,
        default=GestioneContabilita.ESTERNA,
        help_text="Interna = tenuta dallo studio. Esterna = tenuta dal cliente o da terzi.",
    )
    peso_contabilita = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Indice di peso per il calcolo dell'aggiornamento ponderato. "
            "0 = non considerato. Range consigliato 1-10."
        ),
    )
    sostituto_imposta = models.BooleanField(
        default=False,
        help_text="Se True, al cliente competono CU e 770.",
    )
    iscritto_cciaa = models.BooleanField(
        default=False,
        help_text="Iscritto alla Camera di Commercio.",
    )
    data_fine_esercizio = models.CharField(
        max_length=5, default="12-31",
        help_text="Formato MM-DD. Default 31 dicembre (esercizio solare).",
    )
    categoria_professione = models.CharField(
        max_length=60, blank=True,
        help_text=(
            "DEPRECATO: usare il M2M `categorie`. Mantenuto per compatibilità "
            "con regole legacy. La data-migration 0005 popola `categorie` dai "
            "valori storici."
        ),
    )
    categorie = models.ManyToManyField(
        Categoria,
        blank=True,
        related_name="anagrafiche",
        help_text="Tag categoriali per marcare specificità del soggetto.",
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

    # Override dei `get_<field>_display` per leggere le label override-aware
    # da TextChoiceLabel (Fase 1 refactor data-driven). Il codice del campo
    # resta CharField con choices fisse, ma l'etichetta visualizzata diventa
    # modificabile da admin.
    def get_tipo_soggetto_display(self) -> str:
        from .choices_labels import get_label
        return get_label("tipo_soggetto", self.tipo_soggetto)

    def get_stato_display(self) -> str:
        from .choices_labels import get_label
        return get_label("stato", self.stato)

    def get_regime_contabile_display(self) -> str:
        from .choices_labels import get_label
        return get_label("regime_contabile", self.regime_contabile)

    def get_periodicita_iva_display(self) -> str:
        from .choices_labels import get_label
        return get_label("periodicita_iva", self.periodicita_iva)

    def get_contabilita_display(self) -> str:
        from .choices_labels import get_label
        return get_label("contabilita", self.contabilita)


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


# ---------------------------------------------------------------------------
# Progressione contabilità mensile
# ---------------------------------------------------------------------------

class ProgressioneContabilita(models.Model):
    """Stato corrente della registrazione contabile mensile per cliente/anno.

    Solo clienti con contabilita = INTERNA.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="progressione_contabilita"
    )
    anno = models.IntegerField()
    mese_ultimo_registrato = models.PositiveSmallIntegerField(
        default=0,
        help_text="0 = nessun mese registrato, 1-12 = ultimo mese completato.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Progressione contabilità"
        verbose_name_plural = "Progressioni contabilità"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "anno"],
                name="uniq_progressione_cliente_anno",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.anagrafica} — {self.anno}: mese {self.mese_ultimo_registrato}/12"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        ProgressioneContabilitaLog.objects.create(
            anagrafica=self.anagrafica,
            anno=self.anno,
            mese_ultimo_registrato=self.mese_ultimo_registrato,
            utente=self.updated_by,
        )


class ProgressioneContabilitaLog(models.Model):
    """Log append-only per domande retrospettive.

    Ogni save di ProgressioneContabilita scrive una riga qui.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="progressione_log"
    )
    anno = models.IntegerField()
    mese_ultimo_registrato = models.PositiveSmallIntegerField()
    rilevato_il = models.DateTimeField(auto_now_add=True)
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-rilevato_il",)
        verbose_name = "Log progressione contabilità"
        verbose_name_plural = "Log progressioni contabilità"
        indexes = [
            models.Index(fields=["anagrafica", "anno", "-rilevato_il"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.anagrafica} — {self.anno}: "
            f"mese {self.mese_ultimo_registrato} al {self.rilevato_il}"
        )


# ---------------------------------------------------------------------------
# Override delle label dei TextChoices (Fase 1 del refactor data-driven)
# ---------------------------------------------------------------------------
#
# Tabella di "shadow" che permette di modificare le label visualizzate dei
# valori delle TextChoices (`TipoSoggetto`, `StatoAnagrafica`, etc.) da
# Django admin senza intervento programmatore. I valori (codici) restano
# stabili nel codice; cambia solo il testo mostrato all'utente.
#
# Un singolo modello gestisce tutti i 5 enum identificato dalla coppia
# `(field, codice)`. Lookup via helper cached in `anagrafica.choices_labels`.

class TextChoiceLabel(models.Model):
    FIELD_CHOICES = [
        ("tipo_soggetto",    "Tipo soggetto"),
        ("stato",            "Stato anagrafica"),
        ("regime_contabile", "Regime contabile"),
        ("periodicita_iva",  "Periodicità IVA"),
        ("contabilita",      "Tenuta contabilità"),
    ]
    field = models.CharField(
        max_length=30, choices=FIELD_CHOICES, db_index=True,
        help_text="Campo dell'anagrafica a cui si applica l'override.",
    )
    codice = models.CharField(
        max_length=30, db_index=True,
        help_text="Codice del valore (es. 'PF', 'attivo'). Stabile, non rinominare.",
    )
    label = models.CharField(
        max_length=80,
        help_text="Etichetta estesa (form, dropdown filtri).",
    )
    label_micro = models.CharField(
        max_length=3, blank=True,
        help_text=(
            "Sigla a 3 caratteri per badge e celle dense (es. 'INT', 'PF'). "
            "Se vuota viene generato un fallback dalle prime 3 lettere di "
            "`label`."
        ),
    )
    descrizione = models.CharField(max_length=200, blank=True)
    ordine = models.PositiveSmallIntegerField(
        default=0,
        help_text="Ordine di visualizzazione nei dropdown (asc).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("field", "ordine", "label")
        verbose_name = "Etichetta valore (override)"
        verbose_name_plural = "Etichette valori (override)"
        constraints = [
            models.UniqueConstraint(
                fields=["field", "codice"], name="uniq_textchoicelabel_field_codice"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_field_display()}: {self.codice} → {self.label}"
