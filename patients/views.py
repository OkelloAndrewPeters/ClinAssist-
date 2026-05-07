from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from .models import Patient
from .forms  import PatientForm, PatientSearchForm


def _patient_queryset(user):
    """Admins see all patients; others see only their own."""
    if user.is_facility_admin():
        return Patient.objects.all()
    return Patient.objects.filter(registered_by=user)


@login_required
def patient_list(request):
    form = PatientSearchForm(request.GET)
    qs   = _patient_queryset(request.user)

    if form.is_valid() and form.cleaned_data["q"]:
        q = form.cleaned_data["q"]
        qs = qs.filter(
            Q(first_name__icontains=q)  |
            Q(last_name__icontains=q)   |
            Q(patient_id__icontains=q)  |
            Q(phone__icontains=q)       |
            Q(village__icontains=q)
        )

    qs = qs.prefetch_related("visits")
    return render(request, "patients/list.html", {
        "patients": qs,
        "form":     form,
        "total":    qs.count(),
    })


@login_required
def patient_create(request):
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.registered_by = request.user
            patient.save()
            messages.success(request, f"Patient {patient.patient_id} registered.")
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientForm()
    return render(request, "patients/form.html", {"form": form, "title": "Register new patient"})


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(_patient_queryset(request.user), pk=pk)
    visits  = patient.visits.select_related("doctor").prefetch_related("diagnoses").order_by("-created_at")
    return render(request, "patients/detail.html", {
        "patient": patient,
        "visits":  visits,
    })


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(_patient_queryset(request.user), pk=pk)
    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Patient record updated.")
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, "patients/form.html", {
        "form": form, "patient": patient, "title": "Edit patient"
    })