"""Two models, one relationship:
 
    Visit      — records a single patient encounter (symptoms, setting, duration)
    Diagnosis  — stores the AI-generated assessment for that visit
 
Design decisions worth noting:
 
    Separate JSONFields instead of one blob
        diagnoses_json, tests_json, treatments_json, red_flags_json, and
        sources_json are stored as individual JSONField columns rather than
        a single large JSON blob. This allows the reports module to query
        specific fields independently — e.g. filtering all URGENT triage
        visits, or counting visits where a specific diagnosis appeared —
        without parsing a monolithic object in application code.
 
    Doctor annotation layer (doctor_notes + final_diagnosis)
        The AI output is never treated as ground truth. Two fields allow
        the clinical officer to annotate every result:
            final_diagnosis  — the confirmed diagnosis after examination
                               and investigation results
            doctor_notes     — free-text clinical notes and follow-up plan
 
        final_diagnosis is the most important field in the system.
        When a patient returns, diagnoses/views.py injects their history
        into the next AI analysis — and it always prefers final_diagnosis
        over the AI suggestion. A doctor confirming "Malaria (RDT positive)"
        means the next analysis receives ground truth, not a probability.
        This is the feedback loop that improves accuracy over time.
 
    LLM metadata fields (llm_model, latency_s, chunks_used)
        These are stored for auditability and performance monitoring.
        A clinician reviewing a past diagnosis can see exactly which model
        version produced it, how long it took, and how many guideline
        chunks were used — making every output fully traceable.
 
    Doctor FK with SET_NULL on Visit
        If a clinical officer account is deleted, their visits are not
        deleted with them. The patient record and clinical history are
        preserved. An admin can query orphaned visits via the Django admin.
"""

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