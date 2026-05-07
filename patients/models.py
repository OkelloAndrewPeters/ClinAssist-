import uuid
from django.db import models
from django.conf import settings


def generate_patient_id():
    """Generates a readable patient ID like CA-2026-00142"""
    from django.utils import timezone
    year = timezone.now().year
    # Get count of patients this year
    count = Patient.objects.filter(created_at__year=year).count() + 1
    return f"CA-{year}-{count:05d}"


class Patient(models.Model):
    SEX_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other / Unknown"),
    ]

    # Identity
    patient_id   = models.CharField(max_length=20, unique=True, editable=False)
    first_name   = models.CharField(max_length=60)
    last_name    = models.CharField(max_length=60)
    sex          = models.CharField(max_length=1, choices=SEX_CHOICES, default="O")
    date_of_birth= models.DateField(null=True, blank=True)
    age_years    = models.PositiveIntegerField(null=True, blank=True,
                    help_text="Enter if date of birth unknown")

    # Contact / location
    phone        = models.CharField(max_length=20,  blank=True)
    village      = models.CharField(max_length=100, blank=True)
    district     = models.CharField(max_length=100, blank=True)
    next_of_kin  = models.CharField(max_length=100, blank=True)
    nok_phone    = models.CharField(max_length=20,  blank=True, verbose_name="Next of kin phone")

    # Medical background
    known_conditions = models.TextField(blank=True,
        help_text="e.g. Hypertension, Diabetes, HIV positive")
    allergies        = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)

    # System
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True,
        related_name="registered_patients",
    )
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = generate_patient_id()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_age_display(self):
        if self.date_of_birth:
            from django.utils import timezone
            today = timezone.now().date()
            years = (today - self.date_of_birth).days // 365
            return f"{years} yrs"
        if self.age_years:
            return f"{self.age_years} yrs"
        return "Unknown"

    def get_age_group(self):
        """Map age to the AI engine's age group selector."""
        age = None
        if self.date_of_birth:
            from django.utils import timezone
            age = (timezone.now().date() - self.date_of_birth).days // 365
        elif self.age_years:
            age = self.age_years

        if age is None:
            return "Adult (18+)"
        if age < 5:
            return "Under 5"
        if age < 18:
            return "Child (5–17)"
        if age >= 60:
            return "Elderly (60+)"
        return "Adult (18+)"

    def __str__(self):
        return f"{self.patient_id} — {self.get_full_name()}"