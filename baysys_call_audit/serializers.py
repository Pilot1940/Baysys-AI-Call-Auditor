"""
DRF serializers for the Call Audit API.
"""
from rest_framework import serializers

from .models import (
    CallRecording,
    CallTranscript,
    ComplianceFlag,
    OwnLLMScore,
    ProviderScore,
)


class CallRecordingListSerializer(serializers.ModelSerializer):
    """Compact recording summary for list views."""
    compliance_flag_count = serializers.SerializerMethodField()

    class Meta:
        model = CallRecording
        fields = [
            "id", "agent_id", "agent_name", "customer_id", "portfolio_id",
            "agency_id", "bank_name", "product_type", "status",
            "recording_datetime", "completed_at", "compliance_flag_count",
        ]

    def get_compliance_flag_count(self, obj):
        return obj.compliance_flags.count()


class CallTranscriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallTranscript
        fields = [
            "id", "transcript_text", "detected_language",
            "total_call_duration", "total_non_speech_duration",
            "customer_talk_duration", "agent_talk_duration",
            "customer_sentiment", "agent_sentiment",
            "summary", "next_actionable", "created_at",
        ]


class ProviderScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderScore
        fields = [
            "id", "template_id", "template_name",
            "audit_compliance_score", "max_compliance_score", "score_percentage",
            "category_data", "detected_restricted_keyword", "restricted_keywords",
            "created_at",
        ]


class ComplianceFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceFlag
        fields = [
            "id", "flag_type", "severity", "description", "evidence",
            "auto_detected", "reviewed", "reviewed_by", "reviewed_at",
            "created_at",
        ]


class OwnLLMScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnLLMScore
        fields = [
            "id", "score_template_name", "total_score", "max_score",
            "score_percentage", "score_breakdown", "model_used", "created_at",
        ]


class CallDetailSerializer(serializers.ModelSerializer):
    """Full call detail with nested transcript, scores, and flags."""
    transcript = CallTranscriptSerializer(read_only=True)
    provider_scores = ProviderScoreSerializer(many=True, read_only=True)
    compliance_flags = ComplianceFlagSerializer(many=True, read_only=True)
    llm_scores = OwnLLMScoreSerializer(many=True, read_only=True)

    class Meta:
        model = CallRecording
        fields = [
            "id", "agent_id", "agent_name", "customer_id", "portfolio_id",
            "supervisor_id", "agency_id", "recording_url", "recording_datetime",
            "customer_phone", "product_type", "bank_name", "status",
            "provider_resource_id", "error_message", "retry_count",
            "created_at", "submitted_at", "completed_at",
            "transcript", "provider_scores", "compliance_flags", "llm_scores",
        ]


class DashboardSummarySerializer(serializers.Serializer):
    """Response for the dashboard summary endpoint."""
    total_recordings = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    failed = serializers.IntegerField()
    submitted = serializers.IntegerField()
    avg_compliance_score = serializers.FloatField(allow_null=True)
    total_compliance_flags = serializers.IntegerField()
    critical_flags = serializers.IntegerField()
    last_sync_at = serializers.DateTimeField(allow_null=True)
    last_completed_at = serializers.DateTimeField(allow_null=True)
    agent_summary = serializers.ListField(child=serializers.DictField())
