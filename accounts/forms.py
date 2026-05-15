from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User

# =============================================================================
# USER REGISTRATION FORM
# =============================================================================
class RegisterForm(UserCreationForm):
    """
    Custom user registration form.

    Extends Django's UserCreationForm to include:
        - Personal details (name, email)
        - Health facility information
        - Role-based access (doctor, nurse, admin, etc.)
        - Optional phone number
    """

    first_name = forms.CharField(max_length=50, required=True, label="First name")
    last_name  = forms.CharField(max_length=50, required=True, label="Last name")
    email      = forms.EmailField(required=True)
    facility   = forms.CharField(max_length=120, required=True, label="Health facility")
    phone      = forms.CharField(max_length=20,  required=False, label="Phone (optional)")
    role       = forms.ChoiceField(choices=User.ROLE_CHOICES, initial="doctor")

    class Meta:
        model  = User
        fields = [
            "first_name", "last_name", "username", "email",
            "facility", "phone", "role", "password1", "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})

# =============================================================================
# USER LOGIN FORM
# =============================================================================
class LoginForm(AuthenticationForm):
    """
    Login form extending Django's AuthenticationForm.

    Enhancements:
        - Adds consistent styling
        - Adds user-friendly placeholders
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})
        self.fields["username"].widget.attrs["placeholder"] = "Username"
        self.fields["password"].widget.attrs["placeholder"] = "Password"

# =============================================================================
# USER PROFILE UPDATE FORM
# =============================================================================
class ProfileForm(forms.ModelForm):
    """
    Form for updating user profile information.

    Allows users to edit:
        - Name
        - Email
        - Facility
        - Phone number
    """
    
    class Meta:
        model  = User
        fields = ["first_name", "last_name", "email", "facility", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})