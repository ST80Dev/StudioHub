from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm

from .models import UtenteStudio


class UtenteStudioCreationForm(UserCreationForm):
    """Form di creazione utente con password opzionale.

    Se entrambi i campi password vengono lasciati vuoti, l'utente viene
    salvato con `set_unusable_password()`: il login resta disabilitato
    finché un admin non imposta una password (o l'utente non usa il flusso
    di reset).
    """

    password1 = forms.CharField(
        label="Password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=(
            "Facoltativa. Se lasciata vuota, l'utente viene creato senza "
            "password (login disabilitato finché non viene impostata)."
        ),
    )
    password2 = forms.CharField(
        label="Conferma password",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Ripetere la password per conferma.",
    )

    class Meta(UserCreationForm.Meta):
        model = UtenteStudio
        fields = ("username",)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if (password1 or password2) and password1 != password2:
            raise forms.ValidationError(
                "Le due password non corrispondono.", code="password_mismatch"
            )
        return password2

    def _post_clean(self):
        # Skip UserCreationForm._post_clean (would validate password presence)
        # and run the ModelForm-level cleaning instead.
        super(UserCreationForm, self)._post_clean()
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password2", error)

    def save(self, commit=True):
        user = super(UserCreationForm, self).save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
            if hasattr(self, "save_m2m"):
                self.save_m2m()
        return user
