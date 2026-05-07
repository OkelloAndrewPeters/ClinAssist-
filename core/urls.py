from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/",    admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("patients/", include("patients.urls")),
    path("diagnoses/",include("diagnoses.urls")),
    path("reports/",  include("reports.urls")),
    path("",          RedirectView.as_view(url="/patients/", permanent=False)),
]