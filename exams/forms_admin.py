from django import forms
from .models import validate_zip

class ImportZipForm(forms.Form):
    zip_file = forms.FileField(
        label="Fichier ZIP",
        validators=[validate_zip],
        help_text="Choisissez un fichier .zip contenant les épreuves et corrigés.",
    )
