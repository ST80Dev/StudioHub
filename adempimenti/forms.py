"""Form della sezione Configurazione.

Presentano i campi del catalogo con label colloquiali e help text pensati
per utenti non tecnici. Derivano dai modelli ma nascondono o traducono
alcuni dettagli (es. anno_offset → checkbox 'anno successivo').
"""
from django import forms

from .models import (
    ChecklistStep,
    OperatoreRegola,
    RegolaApplicabilita,
    ScadenzaPeriodo,
    StatoAdempimentoTipo,
    TipoAdempimentoCatalogo,
)
from .regole_helpers import CAMPI_INFO, KIND_BOOL, KIND_ENUM, valori_validi


INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm "
    "focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 "
    "dark:border-slate-700 dark:bg-slate-800"
)
CHECKBOX_CLASSES = (
    "h-4 w-4 rounded border-slate-300 text-brand-600 "
    "focus:ring-brand-500 dark:border-slate-600"
)


def _style(field, extra=""):
    widget = field.widget
    current = widget.attrs.get("class", "")
    if isinstance(widget, forms.CheckboxInput):
        widget.attrs["class"] = (CHECKBOX_CLASSES + " " + extra).strip()
    else:
        widget.attrs["class"] = (INPUT_CLASSES + " " + current + " " + extra).strip()


# ---------------------------------------------------------------------------

class TipoAdempimentoCatalogoForm(forms.ModelForm):
    class Meta:
        model = TipoAdempimentoCatalogo
        fields = [
            "codice",
            "denominazione",
            "abbreviazione",
            "periodicita",
            "etichetta_data_evento",
            "giorni_offset_da_evento",
            "colore",
            "ordine",
            "attivo",
            "ha_vista_dedicata",
            "note_regole",
        ]
        labels = {
            "codice": "Codice interno",
            "denominazione": "Denominazione",
            "abbreviazione": "Abbreviazione (sigla)",
            "periodicita": "Periodicità",
            "etichetta_data_evento": "Nome evento di riferimento",
            "giorni_offset_da_evento": "Giorni dopo l'evento",
            "colore": "Colore UI",
            "ordine": "Ordine di visualizzazione",
            "attivo": "Attivo",
            "ha_vista_dedicata": "Mostra in sidebar con vista dedicata",
            "note_regole": "Note interne",
        }
        help_texts = {
            "codice": (
                "Identificativo tecnico univoco, senza spazi "
                "(es. bilancio-ue, liquidazione-iva-trimestrale, f24). "
                "Usato dalle migration di seed e come opzione del comando "
                "CLI `genera_adempimenti --tipo <codice>`. "
                "NON è usato negli URL: rinominarlo non rompe le pagine, "
                "ma se lo cambi aggiorna eventuali script che lo passano "
                "come argomento."
            ),
            "denominazione": "Nome visualizzato agli utenti (es. 'Bilancio UE').",
            "abbreviazione": (
                "Sigla breve usata in sidebar, badge e UI compatta "
                "(es. 'LIPE', 'BILUE', 'F24'). Liberamente modificabile. "
                "Se vuota, la sidebar mostra la denominazione."
            ),
            "ha_vista_dedicata": (
                "Se attivo, il tipo compare con un link diretto nella sidebar "
                "e apre la pagina dedicata con layout per periodo. "
                "Al momento la vista dedicata supporta solo periodicità "
                "trimestrale."
            ),
            "periodicita": (
                "Annuale = 1 scadenza/anno · Trimestrale = 4 · "
                "Mensile = 12 · Una tantum = senza ricorrenza."
            ),
            "etichetta_data_evento": (
                "Compilare SOLO se la scadenza dipende da una data variabile "
                "per singolo adempimento (es. 'Data assemblea approvazione "
                "bilancio'). Altrimenti lasciare vuoto e definire le scadenze "
                "dalla tab 'Scadenze'."
            ),
            "giorni_offset_da_evento": (
                "Numero di giorni tra la data dell'evento e la scadenza "
                "(es. 30 per Bilancio UE: deposito entro 30 gg dall'assemblea)."
            ),
            "colore": "Colore CSS per badge e sidebar (es. #3b82f6). Opzionale.",
            "ordine": (
                "Numero per ordinare i tipi negli elenchi. "
                "Minore = compare prima. Lasciare 0 se non rilevante."
            ),
            "note_regole": (
                "Appunti liberi per chi configura (riferimenti normativi, "
                "prassi interne, ecc.). Non visibile agli operatori."
            ),
        }
        widgets = {
            "note_regole": forms.Textarea(attrs={"rows": 3}),
            "colore": forms.TextInput(attrs={"placeholder": "#3b82f6"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _style(field)

    def clean(self):
        cleaned = super().clean()
        etichetta = (cleaned.get("etichetta_data_evento") or "").strip()
        offset = cleaned.get("giorni_offset_da_evento")
        if etichetta and offset is None:
            self.add_error(
                "giorni_offset_da_evento",
                "Obbligatorio quando l'evento è valorizzato.",
            )
        if offset is not None and not etichetta:
            self.add_error(
                "etichetta_data_evento",
                "Obbligatorio quando i giorni di offset sono valorizzati.",
            )
        return cleaned


# ---------------------------------------------------------------------------

MESI_SCELTE = [
    (1, "Gennaio"), (2, "Febbraio"), (3, "Marzo"), (4, "Aprile"),
    (5, "Maggio"), (6, "Giugno"), (7, "Luglio"), (8, "Agosto"),
    (9, "Settembre"), (10, "Ottobre"), (11, "Novembre"), (12, "Dicembre"),
]


class ScadenzaPeriodoForm(forms.ModelForm):
    anno_successivo = forms.BooleanField(
        required=False,
        label="Scadenza nell'anno successivo all'esercizio",
        help_text=(
            "Spunta se la scadenza cade nell'anno solare dopo quello "
            "dell'esercizio fiscale (es. Bilancio UE 2025 → deposito 2026)."
        ),
    )

    class Meta:
        model = ScadenzaPeriodo
        fields = ["etichetta", "periodo", "mese_scadenza", "giorno_scadenza"]
        labels = {
            "etichetta": "Etichetta",
            "periodo": "Numero periodo",
            "mese_scadenza": "Mese",
            "giorno_scadenza": "Giorno",
        }
        help_texts = {
            "etichetta": "Nome leggibile (es. 'Annuale', 'Q1', 'Gennaio').",
            "periodo": (
                "1 per annuale · 1-4 per trimestrale · "
                "1-12 per mensile."
            ),
            "mese_scadenza": "Mese di scadenza.",
            "giorno_scadenza": "Giorno del mese (1-31).",
        }
        widgets = {
            "mese_scadenza": forms.Select(choices=MESI_SCELTE),
            "giorno_scadenza": forms.NumberInput(attrs={"min": 1, "max": 31}),
            "periodo": forms.NumberInput(attrs={"min": 1, "max": 12}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["anno_successivo"].initial = self.instance.anno_offset == 1
        for field in self.fields.values():
            _style(field)

    def save(self, commit=True):
        self.instance.anno_offset = 1 if self.cleaned_data.get("anno_successivo") else 0
        return super().save(commit=commit)


# ---------------------------------------------------------------------------

class ChecklistStepForm(forms.ModelForm):
    class Meta:
        model = ChecklistStep
        fields = ["denominazione", "ordine"]
        labels = {
            "denominazione": "Descrizione dello step",
            "ordine": "Ordine",
        }
        help_texts = {
            "denominazione": "Cosa deve fare l'operatore (es. 'Deposito CCIAA').",
            "ordine": (
                "Numero per ordinare gli step. Consigliato a step di 10 "
                "(10, 20, 30…) per lasciare spazio a inserimenti futuri."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _style(field)


# ---------------------------------------------------------------------------

class StatoAdempimentoTipoForm(forms.ModelForm):
    """Form per la creazione di uno stato custom per un TipoAdempimento.

    NB: non si edita qui un `e_predefinito=True` (quello passa dall'inline
    admin Django, o dall'UI inline cella-per-cella). Questa form e' usata
    per aggiungere NUOVI stati custom dal tab `?tab=stati`.
    """

    class Meta:
        model = StatoAdempimentoTipo
        fields = [
            "codice", "denominazione", "sigla", "colore",
            "lavorabile", "livello", "iniziale_default", "attivo",
        ]
        labels = {
            "codice": "Codice (slug, stabile)",
            "denominazione": "Denominazione",
            "sigla": "Sigla (3 char)",
            "colore": "Colore badge",
            "lavorabile": "Conta nel 'lavoro residuo'",
            "livello": "Livello (0..100)",
            "iniziale_default": "Stato iniziale predefinito",
            "attivo": "Attivo",
        }
        help_texts = {
            "codice": (
                "Identificativo stabile, minuscolo, niente spazi "
                "(es. 'archiviato'). Non rinominare dopo l'uso."
            ),
            "denominazione": "Etichetta mostrata all'utente (es. 'Archiviato').",
            "sigla": "3 caratteri max per badge densi (es. 'ARC'). Opzionale.",
            "livello": (
                "Progressione: 0=non in scope, 100=completato. Usato anche "
                "per sort del set."
            ),
            "iniziale_default": (
                "Se True, e' lo stato di partenza per i nuovi adempimenti di "
                "questo tipo. Uno solo a True per set."
            ),
        }
        widgets = {
            "livello": forms.NumberInput(attrs={"min": 0, "max": 100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _style(field)


# ---------------------------------------------------------------------------

class RegolaApplicabilitaForm(forms.ModelForm):
    class Meta:
        model = RegolaApplicabilita
        fields = ["campo_condizione", "operatore", "valore", "ordine", "attiva"]
        labels = {
            "campo_condizione": "Campo del cliente",
            "operatore": "Condizione",
            "valore": "Valore",
            "ordine": "Ordine",
            "attiva": "Regola attiva",
        }
        help_texts = {
            "campo_condizione": "Quale campo del profilo fiscale del cliente guardare.",
            "operatore": (
                "Come confrontarlo. 'Vero/Falso' funziona solo con campi sì/no "
                "(es. Sostituto d'imposta). 'In lista' per confronti multipli."
            ),
            "valore": (
                "Per 'Uguale a': un singolo valore (es. SRL). "
                "Per 'In lista': valori separati da virgola (es. SRL,SPA,SAPA). "
                "Per 'Vero/Falso': lasciare vuoto."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _style(field)

    def clean(self):
        cleaned = super().clean()
        campo = cleaned.get("campo_condizione")
        op = cleaned.get("operatore")
        valore = (cleaned.get("valore") or "").strip()

        info = CAMPI_INFO.get(campo, {})
        kind = info.get("kind", "")

        # Coerenza operatore ↔ tipo campo
        if kind == KIND_BOOL and op not in (OperatoreRegola.VERO, OperatoreRegola.FALSO):
            self.add_error(
                "operatore",
                "Per un campo Sì/No usa solo 'Vero' o 'Falso'.",
            )
        if kind != KIND_BOOL and op in (OperatoreRegola.VERO, OperatoreRegola.FALSO):
            self.add_error(
                "operatore",
                "'Vero'/'Falso' sono validi solo per i campi Sì/No "
                "(Sostituto d'imposta, Iscritto CCIAA).",
            )

        # Valore richiesto / vietato
        if op in (OperatoreRegola.UGUALE, OperatoreRegola.IN_LISTA) and not valore:
            self.add_error("valore", "Obbligatorio per questo operatore.")
        if op in (OperatoreRegola.VERO, OperatoreRegola.FALSO):
            cleaned["valore"] = ""
            valore = ""

        # Valore deve essere nei choices per campi enum
        if kind == KIND_ENUM and valore:
            ammessi = valori_validi(campo)
            presenti = {v.strip() for v in valore.split(",") if v.strip()}
            non_validi = presenti - ammessi
            if non_validi:
                self.add_error(
                    "valore",
                    "Valori non riconosciuti: "
                    + ", ".join(sorted(non_validi))
                    + ". Ammessi: "
                    + ", ".join(sorted(ammessi)),
                )
            if op == OperatoreRegola.UGUALE and len(presenti) > 1:
                self.add_error(
                    "valore",
                    "Con 'Uguale a' specifica un solo valore. "
                    "Per confronti multipli usa 'In lista'.",
                )

        return cleaned
