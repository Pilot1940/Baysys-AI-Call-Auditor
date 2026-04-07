from django.urls import path

from .views import (
    ComplianceFlagListView,
    DashboardSummaryView,
    FlagReviewView,
    PollStuckRecordingsView,
    ProviderWebhookView,
    RecordingDetailView,
    RecordingImportView,
    RecordingListView,
    RecordingRetryView,
    RecordingSignedUrlView,
    SubmitRecordingsView,
    SyncCallLogsView,
    SystemStatusView,
)

app_name = "baysys_call_audit"

urlpatterns = [
    # Webhook (no auth — provider sends results here)
    path("webhook/provider/", ProviderWebhookView.as_view(), name="provider-webhook"),

    # Recordings
    path("recordings/", RecordingListView.as_view(), name="recording-list"),
    path("recordings/<int:recording_id>/", RecordingDetailView.as_view(), name="recording-detail"),
    path("recordings/<int:recording_id>/signed-url/", RecordingSignedUrlView.as_view(), name="recording-signed-url"),
    path("recordings/<int:recording_id>/retry/", RecordingRetryView.as_view(), name="recording-retry"),
    path("recordings/<int:recording_id>/flags/<int:flag_id>/review/", FlagReviewView.as_view(), name="flag-review"),
    path("recordings/import/", RecordingImportView.as_view(), name="recording-import"),
    path("recordings/submit/", SubmitRecordingsView.as_view(), name="submit-recordings"),
    path("recordings/poll/", PollStuckRecordingsView.as_view(), name="poll-stuck-recordings"),
    path("recordings/sync/", SyncCallLogsView.as_view(), name="sync-call-logs"),

    # Dashboard
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),

    # Compliance
    path("compliance-flags/", ComplianceFlagListView.as_view(), name="compliance-flag-list"),

    # Admin / ops
    path("admin/status/", SystemStatusView.as_view(), name="system-status"),
]
