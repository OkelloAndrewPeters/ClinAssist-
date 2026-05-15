"""
Extends Django's AbstractUser with three fields specific to the
clinical deployment context: role, facility, and phone.
 
Role hierarchy and data access:
 
    doctor / nurse  → see only their own registered patients
                      and their own visits and diagnoses
    admin           → see all patients, visits, and diagnoses
                      across the entire facility deployment
    superuser       → full Django admin access (treated as admin
                      by is_facility_admin())
 
Why extend AbstractUser instead of using a separate Profile model?
    A separate Profile model requires an extra JOIN on every request
    that checks role or facility. Extending AbstractUser keeps the
    role check (is_facility_admin()) as a single attribute lookup
    with no additional database query.
 
Why store facility as a plain string instead of a FK to a Facility model?
    ClinAssist is designed for single-facility deployment — one laptop,
    one health centre. A Facility FK would add complexity with no
    practical benefit in this context. If ClinAssist is ever deployed
    as a multi-facility SaaS product, this is the field to migrate first.
 
The facility field is displayed in PDF reports so clinical officers
can identify which facility produced a given report — important when
reports are shared with district health officers.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("doctor",  "Doctor / Clinical Officer"),
        ("nurse",   "Nurse"),
        ("admin",   "Facility Admin"),
    ]

    role         = models.CharField(max_length=20, choices=ROLE_CHOICES, default="doctor")
    facility     = models.CharField(max_length=120, blank=True, help_text="Health facility name")
    phone        = models.CharField(max_length=20,  blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def is_facility_admin(self):
        return self.role == "admin" or self.is_superuser

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"