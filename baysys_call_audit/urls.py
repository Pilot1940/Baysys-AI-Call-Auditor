from django.urls import path

from .views import (
    ComplianceFlagListView,
    DashboardSummaryView,
    ProviderWebhookView,
    RecordingDetailView,
    RecordingImportView,
    RecordingListView,
)

app_name = "baysys_call_audit"

urlpatterns = [
    # Webhook (no auth — provider sends results here)
    path("webhook/provider/", ProviderWebhookView.as_view(), name="provider-webhook"),

    # Recordings
    path("recordings/", RecordingListView.as_view(), name="recording-list"),
    path("recordings/<int:recording_id>/", RecordingDetailView.as_view(), name="recording-detail"),
    path("recordings/import/", RecordingImportView.as_view(), name="recording-import"),

    # Dashboard
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),

    # Compliance
    path("compliance-flags/", ComplianceFlagListView.as_view(), name="compliance-flag-list"),
]
