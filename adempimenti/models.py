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
    codice = models.SlugField(
        max_length=40,
        unique=True,
        help_text=(
            "Identificativo tecnico stabile, usato dalle migration di seed "
            "e come opzione di default per il comando CLI "
            "`genera_adempimenti --tipo <codice>`. NON viene usato negli URL "
            "(le pagine dedicate referenziano il tipo per PK). "
            "Modificabile, ma se lo rinomini ricorda di aggiornare "
            "eventuali script/CLI che lo passano come argomento."
        ),
    )
    denominazione = models.CharField(max_length=120)
    abbreviazione = models.CharField(
        max_length=8,
        blank=True,
        help_text=(
            "Sigla breve mostrata in sidebar/badge/UI compatta "
            "(es. 'LIPE', 'BILUE', 'F24'). Liberamente modificabile. "
            "Se vuota, viene usato il fallback sulle prime lettere della denominazione."
        ),
    )
    periodicita = models.CharField(
        max_length=20, choices=Periodicita.choices, default=Periodicita.ANNUALE
    )
    colore = models.CharField(
        max_length=20, blank=True,
        help_text="Colore CSS per badge/sidebar (es. '#3b82f6', 'blue').",
    )
    attivo = models.BooleanField(default=True, db_index=True)
    ha_vista_dedicata = models.BooleanField(
        default=False,
        help_text=(
            "Se True, il tipo compare con un link diretto in sidebar e "
            "apre la pagina dedicata (layout per periodo). "
            "Al momento la vista dedicata supporta solo periodicità trimestrale."
        ),
    )
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

    @property
    def etichetta_breve(self) -> str:
        if self.abbreviazione:
            return self.abbreviazione
        return (self.denominazione[:8] or "").strip()


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
# Stati adempimento — catalogo configurabile da admin
# ---------------------------------------------------------------------------
#
# Sostituisce il vecchio `StatoAdempimento` TextChoices fisso. Ogni tipo
# adempimento ha il SUO set di stati (es. LIPE puo' avere "controllato" in
# piu' rispetto a F24); il set parte da uno "Standard" globale (editabile
# da admin Django) che viene copiato sul tipo alla creazione, e poi e'
# customizzabile per-tipo. Gli stati copiati dallo Standard sono marcati
# `e_predefinito=True` e non eliminabili (UI nega la cancellazione);
# l'utente puo' aggiungere stati custom (eliminabili).
#
# 3 attributi chiave per ogni stato:
#  - `lavorabile`: conta nel residuo "da fare"? (es. da_fare=True, inviato=False)
#  - `livello`: 0..100, progressione visiva (0=non in scope, 100=completato)
#  - `iniziale_default`: True su un solo stato del set — stato di partenza
#    per i nuovi adempimenti di quel tipo.

class ColoreStato(models.TextChoices):
    """Classi CSS predefinite per il badge dello stato.

    Mappano sulle classi `.sh-state-*` gia' definite nel CSS globale.
    """
    TODO = "todo", "Da fare (grigio)"
    WIP = "wip", "In corso (giallo)"
    REVIEW = "review", "In revisione (azzurro)"
    DONE = "done", "Completato (verde)"
    IDLE = "idle", "Riposo (slate)"


class StatoAdempimentoBase(models.Model):
    """Campi comuni fra `StatoAdempimentoStandard` e `StatoAdempimentoTipo`.

    Astratta: non genera tabella. Definita per evitare duplicazione di
    schema fra i due modelli quasi-identici.
    """
    codice = models.SlugField(
        max_length=30,
        help_text=(
            "Identificativo stabile (minuscolo, no spazi). Es. 'da_fare', "
            "'controllato'. Vedi convenzione codici TextChoices in CLAUDE.md."
        ),
    )
    denominazione = models.CharField(
        max_length=60,
        help_text="Etichetta estesa mostrata nei dropdown/form (es. 'Da fare').",
    )
    sigla = models.CharField(
        max_length=3, blank=True,
        help_text="Sigla 3 char per badge densi (es. 'FAR'). Vuoto = fallback automatico.",
    )
    colore = models.CharField(
        max_length=10,
        choices=ColoreStato.choices,
        default=ColoreStato.TODO,
        help_text="Classe colore del badge.",
    )
    lavorabile = models.BooleanField(
        default=True,
        help_text="Se True, conta nel 'lavoro residuo'. Se False, lo stato esce dai conteggi.",
    )
    livello = models.PositiveSmallIntegerField(
        default=10,
        help_text="0..100. Progressione: 0=non in scope, 100=completato. Anche sort.",
    )
    iniziale_default = models.BooleanField(
        default=False,
        help_text="Stato di partenza per nuovi adempimenti. Uno solo a True per set.",
    )
    attivo = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ("livello", "denominazione")

    def __str__(self) -> str:
        return f"{self.denominazione} ({self.codice})"


class StatoAdempimentoStandard(StatoAdempimentoBase):
    """Set predefinito globale degli stati.

    Editabile da admin Django (sezione "Stati standard"). Quando si crea un
    nuovo `TipoAdempimentoCatalogo`, ogni voce attiva di questo set viene
    copiata in `StatoAdempimentoTipo` con `e_predefinito=True`.

    NB: modificare lo Standard NON cambia gli stati dei tipi gia' esistenti
    (per evitare di sovrascrivere personalizzazioni). Lo Standard impatta
    solo le nuove copie alla creazione di un nuovo tipo.
    """

    class Meta(StatoAdempimentoBase.Meta):
        verbose_name = "Stato standard"
        verbose_name_plural = "Stati standard"
        constraints = [
            models.UniqueConstraint(
                fields=["codice"], name="uniq_statostd_codice",
            ),
        ]


class StatoAdempimentoTipo(StatoAdempimentoBase):
    """Stato concreto utilizzato da un `TipoAdempimentoCatalogo`.

    E' la fonte di verita' a runtime per la lista di stati validi del tipo:
    `Adempimento.stato` (CharField) deve essere uno dei `codice` di questo
    set per quel tipo.

    Voci con `e_predefinito=True` sono state copiate dallo Standard alla
    creazione del tipo e non sono cancellabili (UI/admin negano la
    cancellazione). L'utente puo' modificarne label/sigla/colore/livello.
    Voci con `e_predefinito=False` sono custom per il tipo e cancellabili.
    """
    tipo_adempimento = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.CASCADE,
        related_name="stati",
    )
    e_predefinito = models.BooleanField(
        default=False,
        help_text="Copiato dallo Standard. Non eliminabile (modifiche sono ammesse).",
    )

    class Meta(StatoAdempimentoBase.Meta):
        verbose_name = "Stato (per tipo)"
        verbose_name_plural = "Stati (per tipo)"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_adempimento", "codice"],
                name="uniq_statotipo_tipo_codice",
            ),
        ]


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
    CATEGORIA_PROFESSIONE = "categoria_professione", "Categoria professione (legacy)"
    CATEGORIE = "categorie", "Categorie (tag)"


class OperatoreRegola(models.TextChoices):
    UGUALE = "uguale", "Uguale a"
    DIVERSO_DA = "diverso_da", "Diverso da"
    IN_LISTA = "in_lista", "In lista (valori separati da virgola)"
    NON_IN_LISTA = "non_in_lista", "Non in lista (valori separati da virgola)"
    VERO = "vero", "Vero (campo booleano)"
    FALSO = "falso", "Falso (campo booleano)"
    HA_CATEGORIA = "ha_categoria", "Ha categoria (slug)"
    NON_HA_CATEGORIA = "non_ha_categoria", "Non ha categoria (slug)"


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
        # Operatori basati sulle categorie (M2M): leggono dalla relazione,
        # non da un singolo campo scalare.
        if self.operatore == OperatoreRegola.HA_CATEGORIA:
            return self._ha_categoria(anagrafica, self.valore.strip())
        if self.operatore == OperatoreRegola.NON_HA_CATEGORIA:
            return not self._ha_categoria(anagrafica, self.valore.strip())

        val_cliente = self._leggi_campo(anagrafica)
        if self.operatore == OperatoreRegola.VERO:
            return bool(val_cliente)
        if self.operatore == OperatoreRegola.FALSO:
            return not bool(val_cliente)
        if self.operatore == OperatoreRegola.UGUALE:
            return str(val_cliente) == self.valore.strip()
        if self.operatore == OperatoreRegola.DIVERSO_DA:
            return str(val_cliente) != self.valore.strip()
        if self.operatore == OperatoreRegola.IN_LISTA:
            lista = [v.strip() for v in self.valore.split(",")]
            return str(val_cliente) in lista
        if self.operatore == OperatoreRegola.NON_IN_LISTA:
            lista = [v.strip() for v in self.valore.split(",")]
            return str(val_cliente) not in lista
        return False

    @staticmethod
    def _ha_categoria(anagrafica, slug: str) -> bool:
        if not slug:
            return False
        # Anagrafica fittizia (matrice profili): espone gli slug come
        # iterable in `_categorie_slugs` per evitare i vincoli del manager M2M
        # su istanze non salvate.
        slugs = getattr(anagrafica, "_categorie_slugs", None)
        if slugs is not None:
            try:
                return slug in set(slugs)
            except TypeError:
                return False
        cats = getattr(anagrafica, "categorie", None)
        if cats is None:
            return False
        if hasattr(cats, "filter"):
            try:
                return cats.filter(slug=slug).exists()
            except ValueError:
                # Istanza senza pk: nessuna categoria reale.
                return False
        try:
            return slug in set(cats)
        except TypeError:
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
    """Codici canonici degli stati standard (seedati al primo deploy).

    NB: NON sono piu' le `choices` del field `Adempimento.stato`. La fonte
    di verita' a runtime e' la tabella `StatoAdempimentoTipo` (per-tipo).
    Questa enumeration sopravvive solo come *constants holder* per il
    codice applicativo che fa riferimento ai 6 codici canonici (es.
    `StatoAdempimento.INVIATO == "inviato"`). Aggiungere/rimuovere stati
    NON si fa qui ma da admin Django (vedi `StatoAdempimentoStandard` per
    il set di partenza condiviso, `StatoAdempimentoTipo` per il set
    concreto di ciascun tipo).
    """
    DA_FARE = "da_fare", "Da fare"
    IN_CORSO = "in_corso", "In corso"
    CHIUSA = "chiusa", "Chiusa (predisposta)"
    INVIATO = "inviato", "Inviato"
    FANNO_LORO = "fanno_loro", "Fanno loro"
    NO_DATI = "no_dati", "No dati"


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
        max_length=30,
        default="da_fare",
        db_index=True,
        help_text=(
            "Codice di uno stato in StatoAdempimentoTipo per `tipo`. "
            "I valori validi non sono hardcoded: si gestiscono da admin "
            "Django o da /configurazione/tipi/<id>/?tab=stati."
        ),
    )
    data_invio = models.DateField(null=True, blank=True)
    protocollo_invio = models.CharField(
        max_length=40, blank=True,
        help_text="Numero di protocollo telematico restituito dall'invio.",
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
    def referenti_contabilita_cliente(self):
        from anagrafica.models import RuoloReferenteStudio
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.REFERENTE_CONTABILITA
        )

    @property
    def referenti_consulenza_cliente(self):
        from anagrafica.models import RuoloReferenteStudio
        return self.referenti_cliente_nel_periodo(
            RuoloReferenteStudio.REFERENTE_CONSULENZA
        )

    @property
    def is_scaduto(self) -> bool:
        """Scaduto = oltre data_scadenza E stato ancora 'lavorabile'.

        Usa il flag `lavorabile` dello stato (per-tipo) anziche' un check
        sul codice 'inviato': cosi' un adempimento in stato 'fanno_loro' o
        'no_dati' non risulta scaduto anche se passa la data, e nuovi stati
        terminali aggiunti dall'utente (es. 'archiviato') sono gestiti senza
        modifiche al codice. Un adempimento puo' essere inviato anche oltre
        scadenza (con sanzioni), quindi 'inviato' termina il "lavoro residuo".
        """
        if not self.data_scadenza:
            return False
        from . import stati
        s = stati.stato_by_codice(self.tipo_id, self.stato)
        if s is None or not s.lavorabile:
            return False
        return date.today() > self.data_scadenza

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


# ---------------------------------------------------------------------------
# Configurazione colonne per le tabelle adempimenti (vedi `columns.py`)
# ---------------------------------------------------------------------------

class VistaAdempimentoColonne(models.Model):
    """Configura quali colonne mostrare per un `TipoAdempimentoCatalogo`.

    Una configurazione per coppia (tipo, vista). Se manca, le tabelle ricadono
    sul set di default definito in `adempimenti.columns.DEFAULT_COLUMN_CODES`.

    `colonne_codici` e' una lista ordinata di codici colonna (es.
    ["cliente", "codice_fiscale", "stato", "note"]). I codici sconosciuti
    vengono ignorati a runtime, quindi la configurazione e' tollerante a
    refactor delle colonne disponibili.
    """

    class Vista(models.TextChoices):
        SINGOLO = "singolo", "Singolo periodo"
        ANNO = "anno", "Anno aggregato"

    tipo = models.ForeignKey(
        TipoAdempimentoCatalogo,
        on_delete=models.CASCADE,
        related_name="viste_colonne",
    )
    vista = models.CharField(
        max_length=10,
        choices=Vista.choices,
        default=Vista.SINGOLO,
    )
    colonne_codici = models.JSONField(
        default=list,
        help_text=(
            "Lista ordinata di codici colonna. Vedi "
            "`adempimenti.columns.STANDARD_COLUMNS` per i codici disponibili."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configurazione colonne tabella"
        verbose_name_plural = "Configurazioni colonne tabelle"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "vista"],
                name="uniq_vista_colonne_per_tipo",
            ),
        ]

    def __str__(self) -> str:
        return f"Colonne {self.get_vista_display()} — {self.tipo}"
