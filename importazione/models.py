"""Modelli per l'import incrementale di dati da file Excel/CSV.

Flusso (vedi anche ROADMAP.md — Importazione dati):

1. L'utente carica un file → crea un `ImportSession` (stato=BOZZA).
2. Il file viene parsato in `ImportRow` (una riga = un record candidato).
3. Per ogni riga il sistema tenta un match con un'`Anagrafica` esistente
   (cascata: codice_cli → codice_multi → codice_gstudio → CF → P.IVA →
   denominazione esatta normalizzata → fuzzy → alias).
4. L'utente conferma/corregge i match nello step di preview.
5. All'apply: si aggiorna l'anagrafica matchata (campi configurati nel mapping),
   si scrivono i `DatoImportato` per i campi extra non promossi a colonna,
   e si registrano gli `AnagraficaAlias` confermati.

Solo il primo file (master) può creare nuove anagrafiche; per i successivi
le righe non matchate vengono saltate o richiedono conferma esplicita.
"""

from django.conf import settings
from django.db import models

from anagrafica.models import Anagrafica


class ImportSessionStato(models.TextChoices):
    BOZZA = "bozza", "Bozza"
    MAPPATA = "mappata", "Colonne mappate"
    REVISIONATA = "revisionata", "Match revisionato"
    APPLICATA = "applicata", "Applicata"
    ANNULLATA = "annullata", "Annullata"


class ImportSession(models.Model):
    """Una sessione di import = un upload di file da parte di un utente.

    Tiene traccia di file, mapping colonne, esito.
    """

    nome = models.CharField(
        max_length=120,
        help_text="Etichetta libera (es: 'Master clienti 2026', 'Scadenze IVA Q1').",
    )
    file = models.FileField(upload_to="importazione/%Y/%m/")
    sheet_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Nome foglio Excel (vuoto = primo foglio).",
    )
    stato = models.CharField(
        max_length=15,
        choices=ImportSessionStato.choices,
        default=ImportSessionStato.BOZZA,
        db_index=True,
    )
    consente_creazione = models.BooleanField(
        default=False,
        help_text="Se True, le righe non matchate creano nuove anagrafiche. "
        "Da usare solo per il file master iniziale.",
    )
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Mapping {nome_colonna_file: campo_target}. "
        "campo_target può essere un campo Anagrafica o 'extra:<chiave>' per DatoImportato.",
    )
    header_row = models.PositiveSmallIntegerField(
        default=1,
        help_text="Indice (1-based) della riga di intestazione nel foglio.",
    )
    riepilogo = models.JSONField(
        default=dict,
        blank=True,
        help_text="Statistiche finali (n. create, aggiornate, skip, errori).",
    )
    note = models.TextField(blank=True)

    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="import_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Sessione di import"
        verbose_name_plural = "Sessioni di import"

    def __str__(self) -> str:
        return f"{self.nome} ({self.get_stato_display()})"


class ImportRowDecisione(models.TextChoices):
    AUTO_MATCH = "auto_match", "Match automatico"
    CONFERMATO = "confermato", "Match confermato dall'utente"
    NUOVA = "nuova", "Crea nuova anagrafica"
    SKIP = "skip", "Riga ignorata"
    ERRORE = "errore", "Errore"
    PENDING = "pending", "Da revisionare"


class ImportRow(models.Model):
    """Una riga del file caricato, con esito match e decisione utente."""

    sessione = models.ForeignKey(
        ImportSession, on_delete=models.CASCADE, related_name="righe"
    )
    numero_riga = models.PositiveIntegerField(
        help_text="Indice (1-based) della riga nel foglio originale."
    )
    dati_grezzi = models.JSONField(
        help_text="Cella per cella: {nome_colonna: valore}."
    )
    contesto_sezione = models.JSONField(
        default=dict,
        blank=True,
        help_text="Contesto dedotto dalla riga-intestazione di sezione "
        "(es. tipo_soggetto, regime_contabile, contabilita).",
    )

    anagrafica_match = models.ForeignKey(
        Anagrafica,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_rows",
        help_text="Anagrafica associata (se match trovato o confermato).",
    )
    confidenza = models.FloatField(
        default=0.0,
        help_text="0.0-1.0. 1.0 = match esatto su codice univoco.",
    )
    metodo_match = models.CharField(
        max_length=30,
        blank=True,
        help_text="Es: 'codice_cli', 'codice_multi', 'codice_fiscale', "
        "'denominazione_esatta', 'fuzzy', 'alias', 'manuale'.",
    )
    decisione = models.CharField(
        max_length=15,
        choices=ImportRowDecisione.choices,
        default=ImportRowDecisione.PENDING,
        db_index=True,
    )
    messaggio_errore = models.TextField(blank=True)

    class Meta:
        ordering = ("sessione", "numero_riga")
        verbose_name = "Riga import"
        verbose_name_plural = "Righe import"
        indexes = [
            models.Index(fields=["sessione", "decisione"]),
        ]

    def __str__(self) -> str:
        return f"{self.sessione_id}#{self.numero_riga}"


class AnagraficaAlias(models.Model):
    """Denominazione alternativa di un'anagrafica.

    Si popola sia manualmente sia automaticamente: quando l'utente conferma
    un match fuzzy in fase di import, l'aliase viene salvato per match
    automatico nei file futuri.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="alias"
    )
    denominazione_alias = models.CharField(max_length=255, db_index=True)
    fonte = models.CharField(
        max_length=30,
        blank=True,
        help_text="Origine dell'alias: 'manuale', 'import:<id_sessione>', ecc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alias anagrafica"
        verbose_name_plural = "Alias anagrafiche"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "denominazione_alias"],
                name="uniq_alias_per_anagrafica",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.denominazione_alias} → {self.anagrafica}"


class DatoImportato(models.Model):
    """Coppia chiave-valore di dati extra importati per un'anagrafica.

    Usato per i campi presenti nei file Excel ma non promossi a colonna
    su `Anagrafica` (es. addetto consulenza, scadenze trimestrali, gruppo,
    note per anno fiscale ecc.). Quando un campo diventa "ufficiale", lo si
    promuove a colonna con una migration e si dismettono le righe relative.

    L'unicità su (anagrafica, chiave, fonte_session) consente di ricaricare
    lo stesso file (idempotente per sessione) senza duplicati.
    """

    anagrafica = models.ForeignKey(
        Anagrafica, on_delete=models.CASCADE, related_name="dati_importati"
    )
    chiave = models.CharField(max_length=80, db_index=True)
    valore = models.TextField(blank=True)
    fonte_session = models.ForeignKey(
        ImportSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dati_importati",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("anagrafica", "chiave")
        verbose_name = "Dato importato"
        verbose_name_plural = "Dati importati"
        constraints = [
            models.UniqueConstraint(
                fields=["anagrafica", "chiave", "fonte_session"],
                name="uniq_dato_importato_per_fonte",
            ),
        ]
        indexes = [
            models.Index(fields=["anagrafica", "chiave"]),
        ]

    def __str__(self) -> str:
        return f"{self.anagrafica}: {self.chiave}={self.valore[:40]}"
