from django import forms

from . import choices_labels as _choices_labels
from .models import Anagrafica


# Classi CSS riutilizzabili coerenti con il resto del sito (Tailwind).
_INPUT = (
    "w-full rounded border-slate-300 dark:bg-slate-800 dark:border-slate-700 "
    "text-sm px-2 py-1"
)
_SELECT = _INPUT
_TEXTAREA = _INPUT + " min-h-[80px]"


# Campi data-driven gestiti via TextChoiceLabel. I select del form sono
# popolati a `__init__` con le scelte attive correnti + l'eventuale valore
# corrente dell'istanza anche se disattivato (per non perderlo).
_DATA_DRIVEN_FIELDS = (
    "tipo_soggetto", "stato", "regime_contabile", "periodicita_iva", "contabilita",
)


class AnagraficaForm(forms.ModelForm):
    """Form di modifica completa di un'anagrafica.

    I 5 campi data-driven (`tipo_soggetto`, `stato`, `regime_contabile`,
    `periodicita_iva`, `contabilita`) usano `<select>` con i valori
    correnti da TextChoiceLabel. Modificabili da admin Django: vedi
    `anagrafica.choices_labels`.
    """

    class Meta:
        model = Anagrafica
        # Tutti i campi modificabili dall'utente. Escludiamo timestamp,
        # is_deleted e is_demo (gestiti altrove o dal sistema).
        fields = (
            "codice_interno",
            "tipo_soggetto",
            "denominazione",
            "cognome",
            "nome",
            "codice_fiscale",
            "partita_iva",
            "codice_cli",
            "codice_multi",
            "codice_gstudio",
            "stato",
            "data_inizio_mandato",
            "data_fine_mandato",
            "email",
            "indirizzo_via",
            "indirizzo_civico",
            "indirizzo_cap",
            "indirizzo_comune",
            "indirizzo_provincia",
            "indirizzo_nazione",
            "regime_contabile",
            "periodicita_iva",
            "contabilita",
            "categoria_professione",
            "data_fine_esercizio",
            "sostituto_imposta",
            "iscritto_cciaa",
            "peso_contabilita",
            "note",
        )
        widgets = {
            # Choices -> select (lista chiusa)
            "tipo_soggetto": forms.Select(attrs={"class": _SELECT}),
            "stato": forms.Select(attrs={"class": _SELECT}),
            "regime_contabile": forms.Select(attrs={"class": _SELECT}),
            "periodicita_iva": forms.Select(attrs={"class": _SELECT}),
            "contabilita": forms.Select(attrs={"class": _SELECT}),
            # Date
            "data_inizio_mandato": forms.DateInput(
                attrs={"class": _INPUT, "type": "date"}
            ),
            "data_fine_mandato": forms.DateInput(
                attrs={"class": _INPUT, "type": "date"}
            ),
            # Numeri / booleani
            "peso_contabilita": forms.NumberInput(
                attrs={"class": _INPUT, "min": 0, "max": 100}
            ),
            "sostituto_imposta": forms.CheckboxInput(),
            "iscritto_cciaa": forms.CheckboxInput(),
            # Textarea
            "note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            # Default per tutti gli altri text input
            "codice_interno": forms.TextInput(attrs={"class": _INPUT}),
            "denominazione": forms.TextInput(attrs={"class": _INPUT}),
            "cognome": forms.TextInput(attrs={"class": _INPUT}),
            "nome": forms.TextInput(attrs={"class": _INPUT}),
            "codice_fiscale": forms.TextInput(attrs={"class": _INPUT}),
            "partita_iva": forms.TextInput(attrs={"class": _INPUT}),
            "codice_cli": forms.TextInput(attrs={"class": _INPUT}),
            "codice_multi": forms.TextInput(attrs={"class": _INPUT}),
            "codice_gstudio": forms.TextInput(attrs={"class": _INPUT}),
            "email": forms.EmailInput(attrs={"class": _INPUT}),
            "indirizzo_via": forms.TextInput(attrs={"class": _INPUT}),
            "indirizzo_civico": forms.TextInput(attrs={"class": _INPUT}),
            "indirizzo_cap": forms.TextInput(attrs={"class": _INPUT}),
            "indirizzo_comune": forms.TextInput(attrs={"class": _INPUT}),
            "indirizzo_provincia": forms.TextInput(
                attrs={"class": _INPUT, "maxlength": 2}
            ),
            "indirizzo_nazione": forms.TextInput(attrs={"class": _INPUT}),
            "categoria_professione": forms.TextInput(attrs={"class": _INPUT}),
            "data_fine_esercizio": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "MM-DD", "maxlength": 5}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Popola dinamicamente i select dei 5 campi data-driven coi valori
        # attivi di TextChoiceLabel. Se l'istanza esistente ha un codice
        # disattivato lo includiamo comunque (per non perdere il valore
        # corrente al primo salvataggio).
        for f in _DATA_DRIVEN_FIELDS:
            choices = list(_choices_labels.get_choices(f))
            valid = {c for c, _ in choices}
            current = getattr(self.instance, f, "") if self.instance else ""
            if current and current not in valid:
                choices.append(
                    (current, _choices_labels.get_label(f, current) + " (disattivato)")
                )
            self.fields[f] = forms.ChoiceField(
                choices=[("", "—")] + choices,
                required=False,
                widget=forms.Select(attrs={"class": _SELECT}),
                label=self.fields[f].label if f in self.fields else f,
            )

    def clean_codice_fiscale(self):
        return (self.cleaned_data.get("codice_fiscale") or "").strip().upper()

    def clean_partita_iva(self):
        return (self.cleaned_data.get("partita_iva") or "").strip()
