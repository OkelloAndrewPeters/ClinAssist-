from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User


class RegisterForm(UserCreationForm):
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


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})
        self.fields["username"].widget.attrs["placeholder"] = "Username"
        self.fields["password"].widget.attrs["placeholder"] = "Password"


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ["first_name", "last_name", "email", "facility", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})