from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib import messages
from .models import Patient
from .forms  import PatientForm, PatientSearchForm

# =============================================================================
# QUERY HELPERS
# =============================================================================

def _patient_queryset(user):
    """
    Return a filtered Patient queryset based on user role.

    - Facility admins: can view all patients
    - Regular users: can only view patients they registered
    """
    if user.is_facility_admin():
        return Patient.objects.all()
    return Patient.objects.filter(registered_by=user)


# =============================================================================
# PATIENT LIST VIEW
# =============================================================================

@login_required
def patient_list(request):
    """
    Display a searchable list of patients.

    Features:
        - Role-based access control (via _patient_queryset)
        - Full-text-like search across multiple fields
        - Prefetch visits for performance optimization
    """

    # Bind search form with query parameters
    form = PatientSearchForm(request.GET)

    # Base queryset depending on user permissions
    qs   = _patient_queryset(request.user)

    # Apply search filtering if query is valid
    if form.is_valid() and form.cleaned_data["q"]:
        q = form.cleaned_data["q"]
        qs = qs.filter(
            Q(first_name__icontains=q)  |
            Q(last_name__icontains=q)   |
            Q(patient_id__icontains=q)  |
            Q(phone__icontains=q)       |
            Q(village__icontains=q)
        )

    # Optimize DB access by preloading related visits
    qs = qs.prefetch_related("visits")

    return render(request, "patients/list.html", {
        "patients": qs,
        "form":     form,
        "total":    qs.count(),
    })

# =============================================================================
# PATIENT CREATE VIEW
# =============================================================================

@login_required
def patient_create(request):
    """
    Create a new patient record.

    Workflow:
        - Validate form
        - Attach logged-in user as 'registered_by'
        - Save patient
        - Redirect to detail view
    """
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)

            # Assign ownership to current user
            patient.registered_by = request.user
            patient.save()

            messages.success(request, f"Patient {patient.patient_id} registered.")
            return redirect("patients:detail", pk=patient.pk)
        
    else:
        form = PatientForm()
    return render(request, "patients/form.html", {"form": form, "title": "Register new patient"})

# =============================================================================
# PATIENT DETAIL VIEW
# =============================================================================

@login_required
def patient_detail(request, pk):
    """
    Display a single patient record with visit history.

    Includes:
        - Patient information
        - Related visits (ordered newest first)
        - Doctor and diagnoses preloaded for performance
    """

    patient = get_object_or_404(_patient_queryset(request.user), pk=pk)

    # Optimized relational queries for performance
    visits  = patient.visits.select_related("doctor").prefetch_related("diagnoses").order_by("-created_at")
    return render(request, "patients/detail.html", {
        "patient": patient,
        "visits":  visits,
    })

# =============================================================================
# PATIENT EDIT VIEW
# =============================================================================

@login_required
def patient_edit(request, pk):
    """
    Edit an existing patient record.

    Security:
        - Uses role-based queryset filtering
        - Prevents unauthorized access via get_object_or_404

    Flow:
        - Load patient
        - Bind form (POST or GET)
        - Save updates if valid
    """

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