"""
This module defines the core Patient model — the foundation of the
entire system. Every clinical analysis, visit record, and PDF report
traces back to a Patient instance.
 
Design decisions:
 
    Auto-generated patient IDs (CA-2026-00001)
        Uganda's health centres do not have a unified national patient
        identifier system. ClinAssist generates its own readable IDs
        in the format CA-{year}-{sequence}. These are human-readable
        (a clinical officer can say "patient CA-2026-00142" over the
        phone), year-scoped (prevents collisions across deployments),
        and zero-dependency (no external ID service required).
 
    Dual age fields (date_of_birth + age_years)
        Many patients at rural health centres do not know their exact
        date of birth. age_years accepts an approximate age when DOB
        is unknown. get_age_group() uses whichever is available,
        falling back to "Adult (18+)" when neither is recorded.
 
    Medical background fields (known_conditions, allergies, medications)
        These are stored as free text rather than structured codes
        (ICD-10, SNOMED) deliberately. Clinical officers at HC IIIs
        are not trained in clinical coding. Free text is entered
        once at registration and injected into every subsequent AI
        analysis as history context — no coding required.
 
    registered_by FK with SET_NULL
        If a clinical officer account is deleted, their patients are
        not deleted with them. SET_NULL preserves the patient record
        and allows an admin to reassign ownership.
"""
import uuid
from django.db import models
from django.conf import settings


def generate_patient_id():
    """
    Generate a human-readable, year-scoped patient ID.
 
    Format: CA-{year}-{5-digit-sequence}
    Example: CA-2026-00142
 
    The sequence resets each year (counted per calendar year, not
    globally). This means IDs stay short and readable — a 5-digit
    sequence supports up to 99,999 new patients per year per
    deployment, well above the capacity of any single health centre.
 
    Note: This function is called inside Patient.save() only when
    patient_id is not yet set (i.e. on first save only). It is not
    called on subsequent saves, so IDs are immutable once assigned.
 
    Race condition note: In a high-concurrency environment, two
    simultaneous registrations could theoretically receive the same
    count. For a health centre with one or two clinical officers,
    this is not a practical risk. A production deployment serving
    multiple facilities simultaneously should use a database sequence
    instead.
    """
    from django.utils import timezone
    year = timezone.now().year
    # Get count of patients this year
    count = Patient.objects.filter(created_at__year=year).count() + 1
    return f"CA-{year}-{count:05d}"


class Patient(models.Model):
    """
    Core patient record.
 
    Stores identity, contact, location, and medical background.
    All clinical analysis (visits, diagnoses) is linked to this model
    via the Visit FK in diagnoses/models.py.
 
    The patient_id field is the primary human-facing identifier.
    The Django pk (integer) is used internally for URL routing and
    database relationships.
    """
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

    # ── Medical background ────────────────────────────────────────────────
    # Stored as free text — clinical officers at HC IIIs are not trained
    # in ICD coding. These fields are injected into AI analysis context
    # verbatim, so plain language ("hypertension, on amlodipine") works
    # better than coded values for Gemma 4's natural language reasoning.
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
        """
        Auto-assign patient_id on first save.
 
        The ID is only generated once — subsequent saves preserve the
        existing ID. This makes patient_id effectively immutable after
        registration, which is important for paper records, referral
        letters, and audit trails that may reference it externally.
        """
        if not self.patient_id:
            self.patient_id = generate_patient_id()
        super().save(*args, **kwargs)

    def get_full_name(self):
        """Return first + last name. Used in UI display and AI history context."""
        return f"{self.first_name} {self.last_name}"

    def get_age_display(self):
        """
        Return a human-readable age string for UI display.
 
        Calculates exact age from date_of_birth when available.
        Falls back to the approximate age_years value.
        Returns "Unknown" when neither is recorded — this is common
        at health centres where elderly patients may not know their age.
        """
        if self.date_of_birth:
            from django.utils import timezone
            today = timezone.now().date()
            years = (today - self.date_of_birth).days // 365
            return f"{years} yrs"
        if self.age_years:
            return f"{self.age_years} yrs"
        return "Unknown"

    def get_age_group(self):
        """
        Map the patient's age to the AI engine's age group selector.
 
        The engine uses age group strings — not raw ages — because
        its retrieval profiles and prompt instructions are calibrated
        to these five clinical categories:
 
            Under 5       → IMCI protocols, mg/kg paediatric dosing
            Child (5–17)  → school-age paediatric protocols
            Adult (18+)   → standard adult dosing
            Elderly (60+) → comorbidity-aware adult protocols
            Pregnant woman → antenatal safety-aware protocols
                             (set manually by the clinical officer
                              — cannot be auto-detected from age alone)
 
        "Pregnant woman" is never returned here — it must be selected
        manually by the clinical officer, since pregnancy cannot be
        inferred from demographic data alone.
 
        Falls back to "Adult (18+)" when age is unknown — the safest
        default for an unverified adult presentation.
        """
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