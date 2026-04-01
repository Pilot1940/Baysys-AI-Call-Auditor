"""
API views for the Call Audit system.

Views:
  - ProviderWebhookView — receives provider callbacks (no auth)
  - RecordingListView — paginated list of recordings (auth + RBAC)
  - RecordingDetailView — single recording detail (auth + RBAC)
  - DashboardSummaryView — aggregate stats (auth + RBAC)
  - ComplianceFlagListView — compliance flags filtered by recording (auth + RBAC)
"""
import logging

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
from .services import process_provider_webhook

logger = logging.getLogger(__name__)


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
