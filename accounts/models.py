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