from django import forms

from .models import ImportSession


class ImportSessionUploadForm(forms.ModelForm):
    """Step 1 del wizard: upload file + metadata."""

    class Meta:
        model = ImportSession
        fields = ("nome", "file", "sheet_name", "header_row", "consente_creazione", "note")
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "class": "w-full rounded border-slate-300 dark:bg-slate-800 dark:border-slate-700",
                    "placeholder": "es. Master clienti 2026",
                    "autofocus": "autofocus",
                }
            ),
            "file": forms.ClearableFileInput(
                attrs={
                    "class": "block w-full text-sm",
                    "accept": ".xlsx,.xlsm",
                }
            ),
            "sheet_name": forms.TextInput(
                attrs={
                    "class": "w-full rounded border-slate-300 dark:bg-slate-800 dark:border-slate-700",
                    "placeholder": "vuoto = primo foglio",
                }
            ),
            "header_row": forms.NumberInput(
                attrs={
                    "class": "w-24 rounded border-slate-300 dark:bg-slate-800 dark:border-slate-700",
                    "min": 1,
                }
            ),
            "consente_creazione": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300"}
            ),
            "note": forms.Textarea(
                attrs={
                    "class": "w-full rounded border-slate-300 dark:bg-slate-800 dark:border-slate-700",
                    "rows": 2,
                }
            ),
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError(
                "Sono accettati solo file Excel (.xlsx, .xlsm)."
            )
        return f
