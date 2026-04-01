from django.db import models


class CallRecording(models.Model):
    """
    Staging/ingestion table. One row per audio file to process.
    Source: uvarcl_live.call_logs → Redis (signed S3 URLs populated every minute).
    ~18K new recordings/day + 5K/day backfill.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("submitted", "Submitted"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    agent_id = models.CharField(max_length=50, db_index=True)
    agent_name = models.CharField(max_length=200)
    customer_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    portfolio_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    supervisor_id = models.CharField(max_length=50, null=True, blank=True)
    agency_id = models.CharField(max_length=50, null=True, blank=True)
    recording_url = models.URLField(max_length=2000)
    recording_datetime = models.DateTimeField(db_index=True)
    customer_phone = models.CharField(max_length=20, null=True, blank=True)
    product_type = models.CharField(max_length=50, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    fatal_level = models.IntegerField(
        default=0,
        help_text="Computed severity 0-5 from provider boolean scores. 0 = not yet scored.",
    )
    provider_resource_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "call_recordings"

    def __str__(self):
        return f"Recording #{self.pk} — {self.agent_name} — {self.status}"


class CallTranscript(models.Model):
    """
    Processed transcript + metadata. One row per completed transcription.
    """
    recording = models.OneToOneField(
        CallRecording,
        on_delete=models.CASCADE,
        related_name="transcript",
    )
    transcript_text = models.TextField()
    detected_language = models.CharField(max_length=10, null=True, blank=True)
    total_call_duration = models.IntegerField(null=True, blank=True)
    total_non_speech_duration = models.IntegerField(null=True, blank=True)
    customer_talk_duration = models.IntegerField(null=True, blank=True)
    agent_talk_duration = models.IntegerField(null=True, blank=True)
    customer_sentiment = models.CharField(max_length=20, null=True, blank=True)
    agent_sentiment = models.CharField(max_length=20, null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    next_actionable = models.TextField(null=True, blank=True)
    raw_provider_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "call_transcripts"

    def __str__(self):
        lang = self.detected_language or "?"
        return f"Transcript #{self.pk} — {lang} — {self.total_call_duration}s"


class ProviderScore(models.Model):
    """
    Provider template-based scores. One row per template scoring result.
    Multiple rows possible per recording (one per template_id).
    """
    recording = models.ForeignKey(
        CallRecording,
        on_delete=models.CASCADE,
        related_name="provider_scores",
    )
    template_id = models.CharField(max_length=50)
    template_name = models.CharField(max_length=200, null=True, blank=True)
    audit_compliance_score = models.IntegerField(null=True, blank=True)
    max_compliance_score = models.IntegerField(null=True, blank=True)
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    category_data = models.JSONField(null=True, blank=True)
    detected_restricted_keyword = models.BooleanField(default=False)
    restricted_keywords = models.JSONField(default=list)
    raw_score_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "provider_scores"

    def __str__(self):
        pct = self.score_percentage or "?"
        return f"ProviderScore #{self.pk} — template {self.template_id} — {pct}%"

    def compute_percentage(self):
        if self.audit_compliance_score is not None and self.max_compliance_score:
            self.score_percentage = round(
                (self.audit_compliance_score / self.max_compliance_score) * 100, 2
            )


class ComplianceFlag(models.Model):
    """
    Individual compliance violations. One row per violation detected.
    """
    FLAG_TYPE_CHOICES = [
        ("abusive_language", "Abusive Language"),
        ("outside_hours", "Outside Permitted Hours"),
        ("restricted_keyword", "Restricted Keyword"),
        ("rbi_coc_violation", "RBI COC Violation"),
        ("other", "Other"),
    ]
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    recording = models.ForeignKey(
        CallRecording,
        on_delete=models.CASCADE,
        related_name="compliance_flags",
    )
    flag_type = models.CharField(max_length=50, choices=FLAG_TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    description = models.TextField()
    evidence = models.TextField(null=True, blank=True)
    auto_detected = models.BooleanField(default=True)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.CharField(max_length=50, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "compliance_flags"

    def __str__(self):
        return f"Flag #{self.pk} — {self.flag_type} ({self.severity})"


class OwnLLMScore(models.Model):
    """
    Custom LLM scoring results. One row per scoring pass.
    Schema will evolve — start minimal.
    """
    recording = models.ForeignKey(
        CallRecording,
        on_delete=models.CASCADE,
        related_name="llm_scores",
    )
    score_template_name = models.CharField(max_length=100)
    total_score = models.IntegerField(null=True, blank=True)
    max_score = models.IntegerField(null=True, blank=True)
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    score_breakdown = models.JSONField(null=True, blank=True)
    model_used = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "own_llm_scores"

    def __str__(self):
        pct = self.score_percentage or "?"
        return f"LLMScore #{self.pk} — {self.score_template_name} — {pct}%"

    def compute_percentage(self):
        if self.total_score is not None and self.max_score:
            self.score_percentage = round(
                (self.total_score / self.max_score) * 100, 2
            )
