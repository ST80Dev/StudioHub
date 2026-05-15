from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import UtenteStudio


class UtenteStudioCreationForm(UserCreationForm):
    """Form di creazione utente con password facoltativa.

    In Django 5.1 `BaseUserCreationForm` usa `SetPasswordMixin.validate_passwords()`
    che impone i campi password come obbligatori indipendentemente da
    `field.required`. Qui sovrascriviamo `validate_passwords` per saltare il
    check quando entrambi i campi sono vuoti, e `set_password_and_save` per
    chiamare `set_unusable_password()` in quel caso.
    """

    class Meta(UserCreationForm.Meta):
        model = UtenteStudio

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = False
        self.fields["password2"].required = False
        self.fields["password1"].help_text = (
            "Facoltativa. Se lasciata vuota, l'utente viene creato senza "
            "password (login disabilitato finché non viene impostata)."
        )
        self.fields["password2"].help_text = (
            "Ripetere la password (solo se la stai impostando)."
        )

    def validate_passwords(
        self,
        password1_field_name="password1",
        password2_field_name="password2",
    ):
        password1 = self.cleaned_data.get(password1_field_name)
        password2 = self.cleaned_data.get(password2_field_name)

        if not password1 and not password2:
            # Entrambi vuoti: utente senza password, niente errori.
            return

        if password1 and password2 and password1 != password2:
            self.add_error(
                password2_field_name,
                forms.ValidationError(
                    self.error_messages["password_mismatch"],
                    code="password_mismatch",
                ),
            )
            return

        if not password1:
            self.add_error(
                password1_field_name,
                forms.ValidationError(
                    "Compila anche questo campo, oppure lascia entrambi vuoti.",
                    code="required",
                ),
            )
        elif not password2:
            self.add_error(
                password2_field_name,
                forms.ValidationError(
                    "Conferma la password ripetendola qui.",
                    code="required",
                ),
            )

    def set_password_and_save(
        self, user, password_field_name="password1", commit=True
    ):
        password = self.cleaned_data.get(password_field_name)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user
