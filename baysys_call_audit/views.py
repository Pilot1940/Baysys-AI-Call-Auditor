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
"""
import logging
from datetime import date

from django.conf import settings as django_settings
from django.db.models import Avg
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import AuditPermissionMixin, get_auth_backend
from .models import CallRecording, ComplianceFlag, ProviderScore
from .serializers import (
    CallDetailSerializer,
    CallRecordingListSerializer,
    ComplianceFlagSerializer,
    DashboardSummarySerializer,
)
from .ingestion import create_recording_from_row, normalize_column_name, run_sync_for_date, validate_row
from .services import process_provider_webhook

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
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 25)), 100)
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

        data = {
            "total_recordings": total,
            "completed": completed,
            "pending": qs.filter(status="pending").count(),
            "failed": qs.filter(status="failed").count(),
            "avg_compliance_score": round(avg_score, 2) if avg_score else None,
            "total_compliance_flags": flags_qs.count(),
            "critical_flags": flags_qs.filter(severity="critical").count(),
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
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 25)), 100)
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
