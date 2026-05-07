import sys
import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages

from patients.models import Patient
from .models import Visit, Diagnosis

# Add ai/ directory to path so we can import engine
AI_DIR = settings.BASE_DIR / "ai"
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))


def _patient_or_403(user, pk):
    from patients.views import _patient_queryset
    return get_object_or_404(_patient_queryset(user), pk=pk)


def _build_history_context(patient, current_visit_pk=None):
    """Build a text summary of the patient's previous visits for the AI prompt."""
    visits = patient.visits.exclude(pk=current_visit_pk).prefetch_related("diagnoses")[:5]
    if not visits:
        return ""

    lines = [f"PATIENT HISTORY for {patient.get_full_name()} ({patient.patient_id}):"]

    if patient.known_conditions:
        lines.append(f"Known conditions: {patient.known_conditions}")
    if patient.allergies:
        lines.append(f"Allergies: {patient.allergies}")
    if patient.current_medications:
        lines.append(f"Current medications: {patient.current_medications}")

    lines.append("\nPrevious visits:")
    for v in visits:
        lines.append(f"  - {v.created_at:%d %b %Y}: {v.symptoms[:100]}")
        for dx in v.diagnoses.all()[:1]:
            if dx.final_diagnosis:
                lines.append(f"    Final diagnosis: {dx.final_diagnosis}")
            elif dx.diagnoses_json:
                top = dx.diagnoses_json[0].get("name", "")
                lines.append(f"    AI suggestion: {top}")
            lines.append(f"    Triage: {dx.triage_level}")

    return "\n".join(lines)


@login_required
def new_visit(request, patient_pk):
    """Start a new visit / analysis for a patient."""
    patient = _patient_or_403(request.user, patient_pk)
    history = _build_history_context(patient)

    # Pre-fill age group from patient record
    age_group = patient.get_age_group()
    if patient.sex == "F":
        # Offer pregnant option for women of reproductive age
        age = None
        if patient.date_of_birth:
            from django.utils import timezone
            age = (timezone.now().date() - patient.date_of_birth).days // 365
        elif patient.age_years:
            age = patient.age_years
        if age and 15 <= age <= 49:
            age_group = age_group  # doctor can override in form

    return render(request, "diagnoses/new_visit.html", {
        "patient":   patient,
        "age_group": age_group,
        "history":   history,
        "settings_choices": Visit.SETTING_CHOICES,
        "duration_choices": [
            "Less than 24 hours", "1–3 days", "4–7 days", "More than 1 week"
        ],
        "age_choices": [
            "Adult (18+)", "Child (5–17)", "Under 5", "Elderly (60+)", "Pregnant woman"
        ],
    })


@login_required
@require_POST
def run_analysis(request, patient_pk):
    """AJAX endpoint: run AI analysis, save visit + diagnosis, return JSON."""
    patient = _patient_or_403(request.user, patient_pk)

    symptoms  = request.POST.get("symptoms", "").strip()
    age_group = request.POST.get("age_group", patient.get_age_group())
    duration  = request.POST.get("duration",  "1–3 days")
    setting   = request.POST.get("setting",   "outpatient")
    notes     = request.POST.get("notes",     "")

    if not symptoms:
        return JsonResponse({"error": "Symptoms are required."}, status=400)

    # Save the visit first
    setting_key = next(
        (k for k, v in Visit.SETTING_CHOICES if v.lower() == setting.lower()),
        "outpatient"
    )
    visit = Visit.objects.create(
        patient=patient,
        doctor=request.user,
        symptoms=symptoms,
        duration=duration,
        setting=setting_key,
        notes=notes,
    )

    # Run AI engine
    try:
        from engine import analyse_symptoms

        # Inject patient history into symptoms context
        history_ctx = _build_history_context(patient, current_visit_pk=visit.pk)
        enriched_symptoms = symptoms
        if history_ctx:
            enriched_symptoms = f"{symptoms}\n\n{history_ctx}"

        result = analyse_symptoms(
            symptoms=enriched_symptoms,
            age_group=age_group,
            duration=duration,
            setting=setting,
        )
    except Exception as e:
        visit.delete()  # rollback visit if AI fails
        return JsonResponse({"error": f"AI engine error: {str(e)}"}, status=500)

    # Save diagnosis
    triage = result.get("triage", {})
    meta   = result.get("_meta", {})

    dx = Diagnosis.objects.create(
        visit           = visit,
        triage_level    = triage.get("level",  "MODERATE"),
        triage_label    = triage.get("label",  ""),
        triage_reason   = triage.get("reason", ""),
        diagnoses_json  = result.get("diagnoses",  []),
        tests_json      = result.get("tests",      []),
        treatments_json = result.get("treatments", []),
        red_flags_json  = result.get("red_flags",  []),
        sources_json    = result.get("sources",    []),
        reasoning       = result.get("reasoning",  ""),
        disclaimer      = result.get("disclaimer", ""),
        llm_model       = meta.get("model",            ""),
        latency_s       = meta.get("latency_s",        None),
        chunks_used     = meta.get("chunks_retrieved", None),
    )

    result["visit_id"] = visit.pk
    result["diagnosis_id"] = dx.pk
    return JsonResponse(result)


@login_required
def visit_detail(request, pk):
    """View a saved visit and its diagnosis."""
    visit = get_object_or_404(
        Visit.objects.select_related("patient", "doctor").prefetch_related("diagnoses"),
        pk=pk,
        doctor=request.user if not request.user.is_facility_admin() else visit.doctor,
    )
    return render(request, "diagnoses/visit_detail.html", {"visit": visit})


@login_required
@require_POST
def save_doctor_notes(request, dx_pk):
    """Save doctor's annotations and confirmed diagnosis."""
    dx = get_object_or_404(Diagnosis, pk=dx_pk, visit__doctor=request.user)
    dx.doctor_notes    = request.POST.get("doctor_notes", "")
    dx.final_diagnosis = request.POST.get("final_diagnosis", "")
    dx.save()
    messages.success(request, "Notes saved.")
    return redirect("patients:detail", pk=dx.visit.patient.pk)