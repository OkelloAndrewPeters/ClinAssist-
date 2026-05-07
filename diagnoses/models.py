from django.db import models
from django.conf import settings
from patients.models import Patient


class Visit(models.Model):
    """One visit = one encounter at the facility."""
    SETTING_CHOICES = [
        ("outpatient",   "Outpatient"),
        ("emergency",    "Emergency"),
        ("inpatient",    "Inpatient ward"),
        ("community",    "Community / Village"),
        ("hcii",         "Health Centre II/III"),
    ]

    patient  = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="visits")
    doctor   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, related_name="visits")
    setting  = models.CharField(max_length=20, choices=SETTING_CHOICES, default="outpatient")
    symptoms = models.TextField()
    duration = models.CharField(max_length=40, default="1–3 days")
    notes    = models.TextField(blank=True, help_text="Doctor's additional notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Visit {self.pk} — {self.patient.patient_id} on {self.created_at:%d %b %Y}"


class Diagnosis(models.Model):
    """AI-generated diagnosis result for a visit."""
    TRIAGE_CHOICES = [
        ("URGENT",   "Urgent"),
        ("MODERATE", "Moderate"),
        ("LOW",      "Low"),
    ]

    visit         = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name="diagnoses")

    # Triage
    triage_level  = models.CharField(max_length=10, choices=TRIAGE_CHOICES, default="MODERATE")
    triage_label  = models.CharField(max_length=120, blank=True)
    triage_reason = models.TextField(blank=True)

    # Structured results (stored as JSON)
    diagnoses_json   = models.JSONField(default=list)  # [{name, confidence, icd10, reasoning}]
    tests_json       = models.JSONField(default=list)  # [{name, priority, rationale}]
    treatments_json  = models.JSONField(default=list)  # [{step, action, notes}]
    red_flags_json   = models.JSONField(default=list)  # [str, ...]
    sources_json     = models.JSONField(default=list)  # [{document, chapter, page}]

    # Full reasoning
    reasoning    = models.TextField(blank=True)
    disclaimer   = models.TextField(blank=True)

    # Meta
    llm_model    = models.CharField(max_length=40, blank=True)
    latency_s    = models.FloatField(null=True, blank=True)
    chunks_used  = models.IntegerField(null=True, blank=True)

    # Doctor can override/annotate
    doctor_notes      = models.TextField(blank=True, help_text="Doctor's annotations on this result")
    final_diagnosis   = models.CharField(max_length=200, blank=True,
                        help_text="Doctor's confirmed final diagnosis")

    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def top_diagnosis(self):
        if self.diagnoses_json:
            return self.diagnoses_json[0].get("name", "Unknown")
        return "No diagnosis"

    def __str__(self):
        return f"Dx for {self.visit} — {self.top_diagnosis()}"