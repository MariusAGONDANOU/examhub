from django import forms
from django.contrib.auth.models import User
from allauth.account.forms import SignupForm

from .models import Profile

class PaymentForm(forms.Form):
    OP_CHOICES = [
        ('MTN', 'MTN'),
        ('MOOV', 'MOOV'),
        ('CELTIIS', 'Celtiis'),
    ]
    operator = forms.ChoiceField(choices=OP_CHOICES, label='Opérateur')
    phone = forms.CharField(max_length=30, label='Numéro Mobile Money')
    email = forms.EmailField(required=False, label='Email (reçu)')
    pack_id = forms.IntegerField(widget=forms.HiddenInput())

# ----- SIGNUP PERSONNALISÉ (ajout téléphone) -----
class CustomSignupForm(SignupForm):
    phone = forms.CharField(
        max_length=30,
        label="Téléphone",
        required=False,
        help_text="Votre numéro de contact."
    )

    def save(self, request):
        user = super().save(request)
        phone = self.cleaned_data.get("phone", "").strip()
        if hasattr(user, "profile"):
            user.profile.phone = phone
            user.profile.save()
        return user

# ----- FORMULAIRES PROFIL -----
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]
        labels = {"username": "Nom d’utilisateur", "email": "Adresse e-mail"}

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["phone", "avatar"]
        labels = {"phone": "Téléphone", "avatar": "Photo de profil"}
