from django.urls import path
from . import views
app_name = "reports"
urlpatterns = [
    path("",       views.report_index, name="index"),
    path("pdf/",   views.download_pdf, name="pdf"),
]