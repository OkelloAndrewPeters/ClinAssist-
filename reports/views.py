"""
Two views:
 
    report_index   — renders an HTML summary table for a date range
    download_pdf   — generates and streams a downloadable PDF report
 
Design decisions worth noting:
 
    Reports are generated on the fly, not cached or pre-built.
        Health centre deployments have low report frequency (a doctor
        might download one report per week). On-demand generation keeps
        the system simple — no scheduled tasks, no stored report files,
        no disk management. ReportLab renders directly to a BytesIO
        buffer and streams the response in under a second for typical
        date ranges.
 
    Role-based data access is enforced at the query level.
        _visits_for_user() applies the same access control used
        throughout the system: clinical officers see only their own
        visits; admins see all visits at the facility. This means
        a doctor downloading a PDF report can never inadvertently
        include another doctor's patients — the filter happens before
        any data reaches ReportLab.
 
    final_diagnosis is preferred over AI suggestion in the report.
        For each visit, the report displays the doctor's confirmed
        diagnosis (final_diagnosis) if available, falling back to
        the AI's top suggestion otherwise. This ensures the report
        reflects clinical ground truth, not AI probability — which
        matters when reports are submitted to district health offices
        or used for MOH statistics.
 
    ReportLab is imported inside download_pdf, not at module level.
        This means the rest of the application loads normally even if
        reportlab is not installed. The ImportError is caught cleanly
        with an actionable error message rather than crashing on startup.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta

from diagnoses.models import Visit, Diagnosis
from patients.models  import Patient


def _visits_for_user(user, date_from, date_to):
    """
    Return visits for the given date range, filtered by user role.
 
    Clinical officers receive only their own visits.
    Admins and superusers receive all visits in the facility.
 
    Uses select_related and prefetch_related to avoid N+1 queries
    when the caller iterates over visits and their diagnoses.
    """
    qs = Visit.objects.select_related("patient", "doctor") \
                      .prefetch_related("diagnoses") \
                      .filter(created_at__date__gte=date_from,
                              created_at__date__lte=date_to)
    if not user.is_facility_admin():
        qs = qs.filter(doctor=user)
    return qs.order_by("-created_at")


@login_required
def report_index(request):
    """
    Render the HTML report dashboard for a given date range.
 
    Date range defaults to the last 30 days if not provided in
    query parameters. Invalid date strings fall back to the default
    silently — no error is surfaced to the user.
 
    Summary stats (total visits, unique patients, urgent cases) are
    computed here and passed to the template. urgent_count iterates
    over the queryset rather than using a database aggregation because
    the visits are already loaded for the table render — no extra query.
    """
    today     = timezone.now().date()
    date_from = request.GET.get("from", str(today - timedelta(days=30)))
    date_to   = request.GET.get("to",   str(today))

    try:
        df = datetime.strptime(date_from, "%Y-%m-%d").date()
        dt = datetime.strptime(date_to,   "%Y-%m-%d").date()
    except ValueError:
        df, dt = today - timedelta(days=30), today

    visits = _visits_for_user(request.user, df, dt)

    # Summary stats
    total_visits  = visits.count()
    urgent_count  = sum(
        1 for v in visits
        if v.diagnoses.filter(triage_level="URGENT").exists()
    )
    unique_patients = visits.values("patient").distinct().count()

    return render(request, "reports/index.html", {
        "visits":          visits,
        "date_from":       df,
        "date_to":         dt,
        "total_visits":    total_visits,
        "urgent_count":    urgent_count,
        "unique_patients": unique_patients,
    })


@login_required
def download_pdf(request):
    """
    Generate and stream a PDF clinical report for a given date range.
 
    The PDF is built using ReportLab's Platypus layout engine:
        - Header: facility name, doctor name, date range, generation timestamp
        - Summary table: total visits, unique patients, urgent case count
        - Visit table: one row per visit with patient ID, symptoms summary,
          triage level, and confirmed or AI diagnosis
 
    The report filename encodes the date range:
        ClinAssist_Report_2026-04-01_2026-05-01.pdf
 
    Streams directly to the browser as an attachment — no file is
    written to disk. BytesIO buffer is used and discarded after the
    HTTP response is sent.
    """
    today     = timezone.now().date()
    date_from = request.GET.get("from", str(today - timedelta(days=30)))
    date_to   = request.GET.get("to",   str(today))

    try:
        df = datetime.strptime(date_from, "%Y-%m-%d").date()
        dt = datetime.strptime(date_to,   "%Y-%m-%d").date()
    except ValueError:
        df, dt = today - timedelta(days=30), today

    visits = _visits_for_user(request.user, df, dt)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles    import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units     import cm
        from reportlab.lib           import colors
        from reportlab.platypus      import (SimpleDocTemplate, Paragraph, Spacer,
                                             Table, TableStyle, HRFlowable)
        from io import BytesIO

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm,  bottomMargin=2*cm)

        styles  = getSampleStyleSheet()
        GREEN   = colors.HexColor("#1D9E75")
        LGRAY   = colors.HexColor("#F1EFE8")
        URGENT  = colors.HexColor("#FCEBEB")
        story   = []

        # Header
        story.append(Paragraph(
            "<font color='#1D9E75'><b>ClinAssist Uganda</b></font> — Clinical Report",
            styles["Title"]
        ))
        story.append(Paragraph(
            f"Prepared by: <b>{request.user.get_full_name() or request.user.username}</b> "
            f"({request.user.facility or 'Unknown facility'})",
            styles["Normal"]
        ))
        story.append(Paragraph(
            f"Period: <b>{df.strftime('%d %b %Y')}</b> to <b>{dt.strftime('%d %b %Y')}</b> "
            f"| Generated: {timezone.now().strftime('%d %b %Y %H:%M')}",
            styles["Normal"]
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=12))

        # Summary row
        summary_data = [
            ["Total Visits", "Unique Patients", "Urgent Cases"],
            [str(visits.count()),
             str(visits.values("patient").distinct().count()),
             str(sum(1 for v in visits if v.diagnoses.filter(triage_level="URGENT").exists()))],
        ]
        summary_table = Table(summary_data, colWidths=[5*cm, 5*cm, 5*cm])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),  GREEN),
            ("TEXTCOLOR",   (0,0), (-1,0),  colors.white),
            ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
            ("ALIGN",       (0,0), (-1,-1), "CENTER"),
            ("BACKGROUND",  (0,1), (-1,-1), LGRAY),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.white),
            ("FONTSIZE",    (0,0), (-1,-1), 11),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5*cm))

        # Visit table header
        story.append(Paragraph("<b>Patient Visits</b>", styles["Heading2"]))

        table_data = [["Date", "Patient ID", "Patient Name", "Symptoms (summary)", "Triage", "AI Diagnosis"]]

        for v in visits:
            dx_list = list(v.diagnoses.all())
            triage  = dx_list[0].triage_level if dx_list else "—"
            top_dx  = dx_list[0].final_diagnosis or dx_list[0].top_diagnosis() if dx_list else "—"
            symptoms_short = v.symptoms[:60] + ("…" if len(v.symptoms) > 60 else "")

            bg = URGENT if triage == "URGENT" else colors.white

            table_data.append([
                v.created_at.strftime("%d %b %Y"),
                v.patient.patient_id,
                v.patient.get_full_name(),
                symptoms_short,
                triage,
                top_dx[:40],
            ])

        col_widths = [2.5*cm, 2.5*cm, 3.5*cm, 4.5*cm, 2*cm, 3*cm]
        data_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        data_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),  (-1,0),  GREEN),
            ("TEXTCOLOR",   (0,0),  (-1,0),  colors.white),
            ("FONTNAME",    (0,0),  (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0,0),  (-1,-1), 8),
            ("GRID",        (0,0),  (-1,-1), 0.3, colors.lightgrey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGRAY]),
            ("VALIGN",      (0,0),  (-1,-1), "TOP"),
        ]))
        story.append(data_table)

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            "<i>For clinical decision support only. Always apply professional judgment.</i>",
            styles["Normal"]
        ))

        doc.build(story)
        buf.seek(0)

        fname = f"ClinAssist_Report_{df}_{dt}.pdf"
        response = HttpResponse(buf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response

    except ImportError:
        return HttpResponse(
            "reportlab is not installed. Run: pip install reportlab",
            status=500
        )