from django import forms
from .models import Patient

# =============================================================================
# PATIENT SEARCH FORM
# =============================================================================
class PatientSearchForm(forms.Form):
    """
    Simple search form used to filter patients.

    Supports searching by:
        - name
        - patient ID
        - phone number

    This is used in the patient list view.
    """

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Search by name, patient ID, phone…",
            "class": "form-input",
            "autofocus": True,
        })
    )

# =============================================================================
# PATIENT CREATE / UPDATE FORM
# =============================================================================

class PatientForm(forms.ModelForm):
    """
    ModelForm for creating and updating Patient records.

    Responsibilities:
        - Collect patient demographic data
        - Capture medical history (conditions, allergies, meds)
        - Support flexible age entry (DOB OR age_years)
    """

    class Meta:
        model  = Patient

        # Fields exposed in the form (ordered intentionally for UI flow)
        fields = [
            "first_name", "last_name", "sex", "date_of_birth", "age_years",
            "phone", "village", "district", "next_of_kin", "nok_phone",
            "known_conditions", "allergies", "current_medications",
        ]

        # UI widgets (controls HTML rendering + UX behavior)
        widgets = {
            "date_of_birth":        forms.DateInput(attrs={"type": "date", "class": "form-input"}), # Date picker for birth date
            "known_conditions":     forms.Textarea(attrs={"rows": 2, "class": "form-input"}),       # Multi-line medical history fields
            "allergies":            forms.Textarea(attrs={"rows": 2, "class": "form-input"}),
            "current_medications":  forms.Textarea(attrs={"rows": 2, "class": "form-input"}),
        }

        # Human-friendly labels for UI display
        labels = {
            "age_years": "Age (years) — if date of birth unknown",
            "nok_phone": "Next of kin phone",
        }

    # =========================================================================
    # FORM INITIALIZATION CUSTOMIZATION
    # =========================================================================

    def __init__(self, *args, **kwargs):
        """
        Apply global styling and business logic adjustments
        after form fields are initialized.
        """

        super().__init__(*args, **kwargs)

        # Apply consistent CSS class to all fields (if not already set)
        for name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-input"
                
        # Business rule:
        # Allow flexible patient age entry:
        # Either date_of_birth OR age_years can be provided
        self.fields["date_of_birth"].required = False
        self.fields["age_years"].required     = False