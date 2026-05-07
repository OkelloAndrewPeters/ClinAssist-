from django import forms
from .models import Patient


class PatientSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Search by name, patient ID, phone…",
            "class": "form-input",
            "autofocus": True,
        })
    )


class PatientForm(forms.ModelForm):
    class Meta:
        model  = Patient
        fields = [
            "first_name", "last_name", "sex", "date_of_birth", "age_years",
            "phone", "village", "district", "next_of_kin", "nok_phone",
            "known_conditions", "allergies", "current_medications",
        ]
        widgets = {
            "date_of_birth":        forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "known_conditions":     forms.Textarea(attrs={"rows": 2, "class": "form-input"}),
            "allergies":            forms.Textarea(attrs={"rows": 2, "class": "form-input"}),
            "current_medications":  forms.Textarea(attrs={"rows": 2, "class": "form-input"}),
        }
        labels = {
            "age_years": "Age (years) — if date of birth unknown",
            "nok_phone": "Next of kin phone",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-input"
        # Make DOB optional — they can use age_years instead
        self.fields["date_of_birth"].required = False
        self.fields["age_years"].required     = False