"""
API views for the Call Audit system.

Views:
  - ProviderWebhookView — receives provider callbacks (no auth)
  - RecordingListView — paginated list of recordings (auth + RBAC)
  - RecordingDetailView — single recording detail (auth + RBAC)
  - DashboardSummaryView — aggregate stats (auth + RBAC)
  - ComplianceFlagListView — compliance flags filtered by recording (auth + RBAC)
  - RecordingImportView — CSV/Excel upload (Admin/Manager)
  - SyncCallLogsView — failsafe sync trigger (Admin/Supervisor)
  - SubmitRecordingsView — trigger batch submission to provider (Admin/Manager)
  - PollStuckRecordingsView — poll provider for stuck recordings (Admin/Manager)
  - RecordingSignedUrlView — signed S3 URL for audio playback (all roles)
  - FlagReviewView — mark/unmark compliance flag reviewed (Admin/Manager/Supervisor)
  - RecordingRetryView — reset failed recording to pending (Admin/Manager)
  - SystemStatusView — read-only health snapshot, token-auth via ?token= query param
"""
import hmac
import json
import logging
import os
from datetime import date

import newrelic.agent
from django.conf import settings as django_settings
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import crm_adapter
from .auth import AuditPermissionMixin, get_auth_backend
from .models import CallRecording, ComplianceFlag, ProviderScore
from .serializers import (
    CallDetailSerializer,
    CallRecordingListSerializer,
    ComplianceFlagSerializer,
    DashboardSummarySerializer,
)
from .ingestion import create_recording_from_row, normalize_column_name, run_sync_for_date, validate_row
from .services import process_provider_webhook, run_poll_stuck_recordings, submit_pending_recordings

logger = logging.getLogger(__name__)

# Columns required in uploaded CSV/Excel files
_IMPORT_REQUIRED_COLUMNS = {"agent_id", "recording_url", "recording_datetime"}


class ProviderWebhookView(APIView):
    """
    Receives webhook callbacks from the speech analytics provider.
    No auth — provider sends results here after processing.

    Idempotent on provider_resource_id: if already completed, returns 200.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        newrelic.agent.add_custom_attributes({'webhook_source': 'provider'})
        allowed_ips_raw = getattr(django_settings, "SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS", "")
        if allowed_ips_raw:
            allowed_ips = {ip.strip() for ip in allowed_ips_raw.split(",") if ip.strip()}
            forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
            client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR", "")
            if client_ip not in allowed_ips:
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        if not payload:
            return Response(
                {"error": "Empty payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recording = process_provider_webhook(payload)
        if recording is None:
            return Response(
                {"error": "Recording not found for this resource_id"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"status": "ok", "recording_id": recording.pk})


class RecordingListView(AuditPermissionMixin, APIView):
    """
    GET /audit/recordings/
    Paginated list of recordings, filtered by user role (RBAC).
    Query params: status, agent_id, date_from, date_to, page, page_size
    """
    authentication_classes = [get_auth_backend()]

    def get(self, request):
        filters = self.get_user_filter(request)
        qs = CallRecording.objects.filter(**filters).order_by("-recording_datetime")

        # Optional query param filters
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("agent_id"):
            qs = qs.filter(agent_id=request.query_params["agent_id"])
        if request.query_params.get("date_from"):
            qs = qs.filter(recording_datetime__date__gte=request.query_params["date_from"])
        if request.query_params.get("date_to"):
            qs = qs.filter(recording_datetime__date__lte=request.query_params["date_to"])

        # Pagination
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(max(1, int(request.query_params.get("page_size", 25))), 100)
        except (ValueError, TypeError):
            page_size = 25
        start = (page - 1) * page_size
        end = start + page_size
        total = qs.count()

        serializer = CallRecordingListSerializer(qs[start:end], many=True)
        return Response({
            "results": serializer.data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        })


class RecordingDetailView(AuditPermissionMixin, APIView):
    """
    GET /audit/recordings/<id>/
    Full detail for a single recording including transcript, scores, and flags.
    """
    authentication_classes = [get_auth_backend()]

    def get(self, request, recording_id):
        filters = self.get_user_filter(request)
        try:
            recording = CallRecording.objects.get(pk=recording_id, **filters)
        except CallRecording.DoesNotExist:
            return Response(
                {"error": "Recording not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        newrelic.agent.add_custom_attributes({
            'recording_id': recording.pk,
            'agent_id': recording.agent_id,
        })
        serializer = CallDetailSerializer(recording)
        return Response(serializer.data)


class DashboardSummaryView(AuditPermissionMixin, APIView):
    """
    GET /audit/dashboard/summary/
    Aggregate statistics for the dashboard, filtered by user role.
    Query params: date_from, date_to, agent_id, agency_id
    """
    authentication_classes = [get_auth_backend()]

    def get(self, request):
        filters = self.get_user_filter(request)
        qs = CallRecording.objects.filter(**filters)

        # Optional filters
        if request.query_params.get("date_from"):
            qs = qs.filter(recording_datetime__date__gte=request.query_params["date_from"])
        if request.query_params.get("date_to"):
            qs = qs.filter(recording_datetime__date__lte=request.query_params["date_to"])
        if request.query_params.get("agent_id"):
            qs = qs.filter(agent_id=request.query_params["agent_id"])

        total = qs.count()
        completed_qs = qs.filter(status="completed")
        completed = completed_qs.count()

        avg_score = ProviderScore.objects.filter(
            recording__in=completed_qs,
        ).aggregate(avg=Avg("score_percentage"))["avg"]

        flags_qs = ComplianceFlag.objects.filter(recording__in=qs)

        last_sync_at = qs.order_by("-created_at").values_list("created_at", flat=True).first()
        last_completed_at = (
            qs.filter(status="completed")
            .order_by("-completed_at")
            .values_list("completed_at", flat=True)
            .first()
        )

        agent_summary = list(
            qs.filter(status="completed")
            .values("agent_id", "agent_name")
            .annotate(
                calls=Count("pk"),
                avg_score=Avg("provider_scores__score_percentage"),
                fatals=Count("pk", filter=Q(fatal_level__gte=3)),
            )
            .order_by("-avg_score")[:20]
        )

        data = {
            "total_recordings": total,
            "completed": completed,
            "pending": qs.filter(status="pending").count(),
            "failed": qs.filter(status="failed").count(),
            "submitted": qs.filter(status="submitted").count(),
            "avg_compliance_score": round(avg_score, 2) if avg_score else None,
            "total_compliance_flags": flags_qs.count(),
            "critical_flags": flags_qs.filter(severity="critical").count(),
            "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
            "last_completed_at": last_completed_at.isoformat() if last_completed_at else None,
            "agent_summary": agent_summary,
        }

        serializer = DashboardSummarySerializer(data)
        return Response(serializer.data)


class ComplianceFlagListView(AuditPermissionMixin, APIView):
    """
    GET /audit/compliance-flags/
    List compliance flags, filtered by user role.
    Query params: severity, flag_type, reviewed, recording_id, page, page_size
    """
    authentication_classes = [get_auth_backend()]

    def get(self, request):
        filters = self.get_user_filter(request)
        # ComplianceFlag filters go through recording's fields
        recording_filters = {f"recording__{k}": v for k, v in filters.items()}
        qs = ComplianceFlag.objects.filter(**recording_filters).order_by("-created_at")

        if request.query_params.get("severity"):
            qs = qs.filter(severity=request.query_params["severity"])
        if request.query_params.get("flag_type"):
            qs = qs.filter(flag_type=request.query_params["flag_type"])
        if request.query_params.get("reviewed") is not None:
            qs = qs.filter(reviewed=request.query_params["reviewed"].lower() == "true")
        if request.query_params.get("recording_id"):
            qs = qs.filter(recording_id=request.query_params["recording_id"])

        # Pagination
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(max(1, int(request.query_params.get("page_size", 25))), 100)
        except (ValueError, TypeError):
            page_size = 25
        start = (page - 1) * page_size
        end = start + page_size
        total = qs.count()

        serializer = ComplianceFlagSerializer(qs[start:end], many=True)
        return Response({
            "results": serializer.data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        })


class SyncCallLogsView(AuditPermissionMixin, APIView):
    """
    POST /audit/recordings/sync/
    Failsafe trigger for call_logs sync. Same logic as sync_call_logs management command.
    Restricted to Admin (role_id=1) and Supervisor (role_id=4).
    """
    authentication_classes = [get_auth_backend()]

    def post(self, request):
        allowed = getattr(django_settings, "SYNC_ALLOWED_ROLES", {1, 4})
        role = self.get_user_role(request)
        if role not in allowed:
            return Response(
                {"error": "Insufficient permissions. Admin or Supervisor required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data or {}

        # Parse date
        date_str = data.get("date")
        if date_str:
            # Truncate to date portion — JS date pickers often send full ISO datetime strings
            # e.g. "2026-04-07T00:00:00.000Z" → "2026-04-07"
            date_str = str(date_str)[:10]
            try:
                target_date = date.fromisoformat(date_str)
            except (ValueError, TypeError):
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = None  # run_sync_for_date defaults to yesterday

        batch_size = data.get("batch_size", 5000)
        dry_run = data.get("dry_run", False)
        newrelic.agent.add_custom_attributes({
            'sync_date': str(target_date),
            'dry_run': dry_run,
        })

        user_id = getattr(request.user, "user_id", None)
        logger.info("Sync triggered via API by user_id=%s for date=%s", user_id, target_date)

        counts = run_sync_for_date(
            target_date=target_date,
            batch_size=batch_size,
            dry_run=dry_run,
        )

        return Response({
            "status": "ok",
            "date": str(target_date or "yesterday"),
            "dry_run": dry_run,
            "total_fetched": counts["fetched"],
            "created": counts["created"],
            "skipped_dedup": counts["skipped_dedup"],
            "skipped_validation": counts["skipped_validation"],
            "unknown_agents": counts["unknown_agents"],
            "errors": counts["errors"],
            "duration_seconds": counts["duration_seconds"],
        })


class RecordingImportView(AuditPermissionMixin, APIView):
    """
    POST /audit/recordings/import/
    Upload a CSV or Excel file to create CallRecording rows.
    Restricted to Admin (role_id=1) and Manager/TL (role_id=2).

    Body: multipart/form-data with 'file' field.
    Query params: ?dry_run=true (optional)

    Response: {"total": N, "created": N, "skipped_dedup": N,
               "skipped_validation": N, "errors": [...]}
    """
    ALLOWED_ROLES = {1, 2}
    authentication_classes = [get_auth_backend()]

    def post(self, request):
        role = self.get_user_role(request)
        if role not in self.ALLOWED_ROLES:
            return Response(
                {"error": "Only Admin or Manager/TL can upload recordings."},
                status=status.HTTP_403_FORBIDDEN,
            )

        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response(
                {"error": "No file provided. Send a 'file' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dry_run = request.query_params.get("dry_run", "").lower() == "true"
        filename = uploaded.name.lower()

        try:
            if filename.endswith(".csv"):
                rows = self._parse_csv(uploaded)
            elif filename.endswith((".xlsx", ".xls")):
                rows = self._parse_excel(uploaded)
            else:
                return Response(
                    {"error": f"Unsupported file type: {uploaded.name}. Use .csv or .xlsx."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as exc:
            return Response(
                {"error": f"Failed to parse file: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not rows:
            return Response(
                {"error": "No data rows found in file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check required columns
        first_row_keys = set(rows[0].keys())
        missing = _IMPORT_REQUIRED_COLUMNS - first_row_keys
        if missing:
            return Response(
                {"error": f"Missing required columns: {', '.join(sorted(missing))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        counts = {"total": len(rows), "created": 0, "skipped_dedup": 0,
                  "skipped_validation": 0, "errors": []}

        for i, row in enumerate(rows, start=2):
            if dry_run:
                errors = validate_row(row)
                if errors:
                    counts["skipped_validation"] += 1
                    counts["errors"].append({"row": i, "messages": errors})
                else:
                    counts["created"] += 1
                continue

            try:
                recording, created = create_recording_from_row(row)
                if created:
                    counts["created"] += 1
                elif recording is None:
                    counts["skipped_validation"] += 1
                    counts["errors"].append({"row": i, "messages": validate_row(row)})
                else:
                    counts["skipped_dedup"] += 1
            except Exception as exc:
                counts["errors"].append({"row": i, "messages": [str(exc)]})

        return Response(counts)

    @staticmethod
    def _parse_csv(uploaded_file) -> list[dict]:
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        text = uploaded_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return []
        col_map = {n: normalize_column_name(n) for n in reader.fieldnames}
        rows = []
        for raw in reader:
            normalized = {}
            for orig, val in raw.items():
                normalized[col_map.get(orig, normalize_column_name(orig))] = val if val != "" else None
            rows.append(normalized)
        return rows

    @staticmethod
    def _parse_excel(uploaded_file) -> list[dict]:
        import openpyxl  # noqa: PLC0415

        wb = openpyxl.load_workbook(uploaded_file, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            wb.close()
            return []
        col_names = [normalize_column_name(str(h)) if h else f"col_{i}" for i, h in enumerate(header)]
        rows = []
        for data_row in rows_iter:
            row_dict = {}
            for col_name, value in zip(col_names, data_row):
                row_dict[col_name] = value if value is not None and str(value).strip() != "" else None
            rows.append(row_dict)
        wb.close()
        return rows


class SubmitRecordingsView(AuditPermissionMixin, APIView):
    """
    POST /audit/recordings/submit/
    Trigger batch submission of pending recordings to the speech provider.
    Restricted to Admin (role_id=1) and Manager/TL (role_id=2).

    Response: {"submitted": int, "failed": int}
    """
    ALLOWED_ROLES = {1, 2}
    authentication_classes = [get_auth_backend()]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        newrelic.agent.add_custom_attributes([("endpoint", "submit_recordings")])
        role = self.get_user_role(request)
        if role not in self.ALLOWED_ROLES:
            return Response(
                {"error": "Only Admin or Manager/TL can trigger submission."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            counts = submit_pending_recordings()
            return Response({"submitted": counts["submitted"], "failed": counts["failed"]})
        except Exception as exc:
            logger.exception("submit_recordings endpoint error")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PollStuckRecordingsView(AuditPermissionMixin, APIView):
    """
    POST /audit/recordings/poll/
    Poll the provider for recordings stuck in status=submitted.
    Restricted to Admin (role_id=1) and Manager/TL (role_id=2).

    Optional body: {"batch_size": int, "dry_run": bool}
    Response: summary dict from run_poll_stuck_recordings()
    """
    ALLOWED_ROLES = {1, 2}
    authentication_classes = [get_auth_backend()]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        newrelic.agent.add_custom_attributes([("endpoint", "poll_stuck_recordings")])
        role = self.get_user_role(request)
        if role not in self.ALLOWED_ROLES:
            return Response(
                {"error": "Only Admin or Manager/TL can trigger polling."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = request.data or {}
        batch_size = data.get("batch_size", 50)
        dry_run = data.get("dry_run", False)
        try:
            result = run_poll_stuck_recordings(batch_size=batch_size, dry_run=dry_run)
            return Response(result)
        except Exception as exc:
            logger.exception("poll_stuck_recordings endpoint error")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RecordingSignedUrlView(AuditPermissionMixin, APIView):
    """
    GET /audit/<S>/recordings/<recording_id>/signed-url/
    Returns a short-lived signed S3 URL for audio playback.
    All authenticated roles permitted.
    """
    authentication_classes = [get_auth_backend()]
    permission_classes = [IsAuthenticated]

    def get(self, request, recording_id):
        newrelic.agent.add_custom_attributes([("endpoint", "signed_url")])
        filters = self.get_user_filter(request)
        try:
            recording = CallRecording.objects.get(pk=recording_id, **filters)
        except CallRecording.DoesNotExist:
            return Response({"error": "Recording not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            signed_url = crm_adapter.get_signed_url(recording.recording_url)
        except Exception as exc:
            logger.error("get_signed_url failed for recording_id=%s: %s", recording_id, exc)
            return Response(
                {"error": "Failed to generate signed URL"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"signed_url": signed_url, "expires_in_seconds": 300})


class FlagReviewView(AuditPermissionMixin, APIView):
    """
    PATCH /audit/<S>/recordings/<recording_id>/flags/<flag_id>/review/
    Mark or unmark a compliance flag as reviewed.
    Restricted to Admin (1), Manager (2), Supervisor (4).
    """
    ALLOWED_ROLES = {1, 2, 4}
    authentication_classes = [get_auth_backend()]
    permission_classes = [IsAuthenticated]

    def patch(self, request, recording_id, flag_id):
        role = self.get_user_role(request)
        if role not in self.ALLOWED_ROLES:
            return Response(
                {"error": "Insufficient permissions. Admin, Manager, or Supervisor required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            flag = ComplianceFlag.objects.get(pk=flag_id)
        except ComplianceFlag.DoesNotExist:
            return Response({"error": "Flag not found"}, status=status.HTTP_404_NOT_FOUND)

        if flag.recording_id != recording_id:
            return Response({"error": "Flag not found"}, status=status.HTTP_404_NOT_FOUND)

        reviewed = request.data.get("reviewed")
        if reviewed:
            flag.reviewed = True
            flag.reviewed_by = str(request.user.user_id)
            flag.reviewed_at = timezone.now()
        else:
            flag.reviewed = False
            flag.reviewed_by = None
            flag.reviewed_at = None
        flag.save()

        from .serializers import ComplianceFlagSerializer  # noqa: PLC0415
        return Response(ComplianceFlagSerializer(flag).data)


class RecordingRetryView(AuditPermissionMixin, APIView):
    """
    POST /audit/<S>/recordings/<recording_id>/retry/
    Reset a failed recording back to pending for re-submission.
    Restricted to Admin (1) and Manager (2).
    """
    ALLOWED_ROLES = {1, 2}
    authentication_classes = [get_auth_backend()]
    permission_classes = [IsAuthenticated]

    def post(self, request, recording_id):
        role = self.get_user_role(request)
        if role not in self.ALLOWED_ROLES:
            return Response(
                {"error": "Insufficient permissions. Admin or Manager required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        filters = self.get_user_filter(request)
        try:
            recording = CallRecording.objects.get(pk=recording_id, **filters)
        except CallRecording.DoesNotExist:
            return Response({"error": "Recording not found"}, status=status.HTTP_404_NOT_FOUND)

        if recording.status != "failed":
            return Response(
                {"error": f"Recording is not in failed status (current: {recording.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recording.status = "pending"
        recording.error_message = None
        recording.save(update_fields=["status", "error_message"])

        return Response({"status": recording.status, "retry_count": recording.retry_count})


# ─────────────────────────────────────────────────────────────────────────────
# System status helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_recording_activity() -> dict:
    """Return recording activity metrics. Returns null values on DB error.

    Uses status=completed + completed_at (the field set when a recording
    finishes webhook processing / LLM scoring).
    """
    from django.db.models.functions import TruncHour  # noqa: PLC0415

    now = timezone.now()
    today = now.date()
    week_start = today - date.resolution * today.weekday()  # Monday
    try:
        completed = CallRecording.objects.filter(status="completed")
        recordings_today = completed.filter(completed_at__date=today).count()
        recordings_this_week = completed.filter(completed_at__date__gte=week_start).count()
        recordings_this_month = completed.filter(
            completed_at__year=today.year, completed_at__month=today.month
        ).count()
        last_ts = (
            completed.order_by("-completed_at")
            .values_list("completed_at", flat=True)
            .first()
        )
        last_scored = last_ts.isoformat() if last_ts else None
        pending_count = CallRecording.objects.filter(status="pending").count()
        submitted_count = CallRecording.objects.filter(status="submitted").count()
        hourly_qs = (
            completed.filter(completed_at__date=today)
            .annotate(hour=TruncHour("completed_at"))
            .values("hour")
            .annotate(cnt=Count("id"))
        )
        hourly: dict[str, int] = {f"{h:02d}": 0 for h in range(24)}
        for row in hourly_qs:
            if row["hour"] is not None:
                h_key = f"{row['hour'].hour:02d}"
                hourly[h_key] = row["cnt"]
    except Exception:  # noqa: BLE001
        logger.warning("SystemStatusView: recording_activity DB query failed", exc_info=True)
        recordings_today = None
        recordings_this_week = None
        recordings_this_month = None
        last_scored = None
        pending_count = None
        submitted_count = None
        hourly = None
    return {
        "recordings_today": recordings_today,
        "recordings_this_week": recordings_this_week,
        "recordings_this_month": recordings_this_month,
        "last_scored": last_scored,
        "pending": pending_count,
        "submitted": submitted_count,
        "hourly_today": hourly,
    }


_AUDIT_ENV_VAR_KEYS = [
    "AUDIT_AUTH_BACKEND",
    "AUDIT_URL_SECRET",
    "AUDIT_STATUS_SECRET",
    "SPEECH_PROVIDER_API_KEY",
    "SPEECH_PROVIDER_API_SECRET",
    "SPEECH_PROVIDER_TEMPLATE_ID",
    "SPEECH_PROVIDER_CALLBACK_URL",
    "NEW_RELIC_INSERT_KEY",
    "NEW_RELIC_LICENSE_KEY",
    "NEW_RELIC_ACCOUNT_ID",
    "GIT_COMMIT_HASH",
    "GIT_BRANCH",
    "DATABASE_URL",
    "SECRET_KEY",
]


def _fire_nr_audit_status_event(data: dict) -> None:
    """POST a BaySysAuditSystemStatus event to New Relic Insights API. Silent no-op on failure."""
    import requests as _requests  # noqa: PLC0415

    nr_key = os.environ.get("NEW_RELIC_INSERT_KEY") or os.environ.get("NEW_RELIC_LICENSE_KEY", "")
    nr_account = os.environ.get("NEW_RELIC_ACCOUNT_ID", "")
    if not nr_key or not nr_account:
        return
    ra = data["recording_activity"]
    event = {
        "eventType": "BaySysAuditSystemStatus",
        "git_commit": data["backend"]["git_commit"],
        "git_branch": data["backend"]["git_branch"],
        "frontend_build_hash": data["frontend"]["build_hash"],
        "latest_migration": data["migrations"]["latest_applied"],
        "pending_migrations": len(data["migrations"]["pending"]),
        "recordings_today": ra["recordings_today"],
        "recordings_this_week": ra["recordings_this_week"],
        "last_scored": ra["last_scored"],
        "pending": ra["pending"],
        "submitted": ra["submitted"],
    }
    url = f"https://insights-collector.newrelic.com/v1/accounts/{nr_account}/events"
    headers = {"Content-Type": "application/json", "X-Insert-Key": nr_key}
    try:
        _requests.post(url, json=[event], headers=headers, timeout=5)
    except Exception:  # noqa: BLE001
        logger.debug("NR audit status event failed", exc_info=True)


class SystemStatusView(View):
    """
    GET /audit/<URL_SECRET>/admin/status/?token=<AUDIT_STATUS_SECRET>

    Read-only system health snapshot. Token auth via query param so the
    endpoint is navigable directly in a browser or monitoring tool.
    Returns 403 if token is missing or wrong.
    """

    def get(self, request, *args, **kwargs):
        # ── Auth ──────────────────────────────────────────────────────────────
        expected = getattr(django_settings, "AUDIT_STATUS_SECRET", "")
        provided = request.GET.get("token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return JsonResponse({"error": "Forbidden"}, status=403)

        # ── Migrations ────────────────────────────────────────────────────────
        from django.db import connection  # noqa: PLC0415
        from django.db.migrations.executor import MigrationExecutor  # noqa: PLC0415

        executor = MigrationExecutor(connection)
        applied = executor.loader.applied_migrations
        audit_applied = sorted(name for app, name in applied if app == "baysys_call_audit")
        latest_applied = audit_applied[-1] if audit_applied else "unknown"
        total_applied = len(audit_applied)
        pending_plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending = [migration.name for migration, _ in pending_plan]

        # ── Backend ───────────────────────────────────────────────────────────
        git_commit = os.environ.get("GIT_COMMIT_HASH", "unknown")
        git_branch = os.environ.get("GIT_BRANCH", "unknown")

        # ── Frontend ──────────────────────────────────────────────────────────
        static_root = getattr(django_settings, "STATIC_ROOT", None)
        base_dir = getattr(django_settings, "BASE_DIR", "")
        version_path = os.path.join(static_root or base_dir, "version.json")
        try:
            with open(version_path) as fh:
                ver = json.load(fh)
            build_hash = ver.get("build_hash", "unknown")
            build_time = ver.get("build_time", "unknown")
        except Exception:  # noqa: BLE001
            build_hash = "unknown"
            build_time = "unknown"

        data = {
            "generated_at": timezone.now().isoformat(),
            "migrations": {
                "latest_applied": latest_applied,
                "total_applied": total_applied,
                "pending": pending,
            },
            "backend": {
                "git_commit": git_commit,
                "git_branch": git_branch,
            },
            "frontend": {
                "build_hash": build_hash,
                "build_time": build_time,
            },
            "recording_activity": _build_recording_activity(),
            "env_vars": {k: bool(os.environ.get(k, "")) for k in _AUDIT_ENV_VAR_KEYS},
        }

        _fire_nr_audit_status_event(data)

        return JsonResponse(data)
