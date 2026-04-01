from django.contrib import admin

from .models import (
    CallRecording,
    CallTranscript,
    ComplianceFlag,
    OwnLLMScore,
    ProviderScore,
)


@admin.register(CallRecording)
class CallRecordingAdmin(admin.ModelAdmin):
    list_display = ("id", "agent_name", "status", "recording_datetime", "created_at")
    list_filter = ("status", "product_type", "bank_name")
    search_fields = ("agent_name", "agent_id", "customer_id")


@admin.register(CallTranscript)
class CallTranscriptAdmin(admin.ModelAdmin):
    list_display = ("id", "recording", "detected_language", "total_call_duration", "created_at")


@admin.register(ProviderScore)
class ProviderScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "recording", "template_id", "score_percentage", "created_at")


@admin.register(ComplianceFlag)
class ComplianceFlagAdmin(admin.ModelAdmin):
    list_display = ("id", "recording", "flag_type", "severity", "reviewed", "created_at")
    list_filter = ("flag_type", "severity", "reviewed")


@admin.register(OwnLLMScore)
class OwnLLMScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "recording", "score_template_name", "score_percentage", "created_at")
