from django.urls import path
from . import views

app_name = "diagnoses"

urlpatterns = [
    path("patient/<int:patient_pk>/new/",    views.new_visit,        name="new_visit"),
    path("patient/<int:patient_pk>/analyse/",views.run_analysis,     name="run_analysis"),
    path("visit/<int:pk>/",                  views.visit_detail,     name="visit_detail"),
    path("dx/<int:dx_pk>/notes/",            views.save_doctor_notes,name="save_notes"),
]
