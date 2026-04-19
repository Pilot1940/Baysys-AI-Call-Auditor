/** TypeScript interfaces for the Call Audit API */

export interface CallRecording {
  id: number;
  agent_id: string;
  agent_name: string;
  customer_id: string | null;
  portfolio_id: string | null;
  agency_id: string | null;
  bank_name: string | null;
  product_type: string | null;
  status: "pending" | "submitted" | "processing" | "completed" | "failed" | "skipped";
  recording_datetime: string;
  completed_at: string | null;
  compliance_flag_count: number;
  fatal_level?: number;
  submission_tier?: "immediate" | "normal" | "off_peak";
  retry_count?: number;
}

export interface CallTranscript {
  id: number;
  transcript_text: string;
  detected_language: string | null;
  total_call_duration: number | null;
  total_non_speech_duration: number | null;
  customer_talk_duration: number | null;
  agent_talk_duration: number | null;
  customer_sentiment: string | null;
  agent_sentiment: string | null;
  summary: string | null;
  next_actionable: string | null;
  created_at: string;
}

export interface ProviderScore {
  id: number;
  template_id: string;
  template_name: string | null;
  audit_compliance_score: number | null;
  max_compliance_score: number | null;
  score_percentage: number | null;
  category_data: Record<string, unknown> | null;
  detected_restricted_keyword: boolean;
  restricted_keywords: string[];
  created_at: string;
}

export interface ComplianceFlag {
  id: number;
  flag_type: string;
  severity: "critical" | "high" | "medium" | "low";
  description: string;
  evidence: string | null;
  auto_detected: boolean;
  reviewed: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface OwnLLMScore {
  id: number;
  score_template_name: string;
  total_score: number | null;
  max_score: number | null;
  score_percentage: number | null;
  score_breakdown: Record<string, unknown> | null;
  model_used: string | null;
  created_at: string;
}

export interface CallDetail extends CallRecording {
  recording_url: string;
  supervisor_id: string | null;
  customer_phone: string | null;
  provider_resource_id: string | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  submitted_at: string | null;
  transcript: CallTranscript | null;
  provider_scores: ProviderScore[];
  compliance_flags: ComplianceFlag[];
  llm_scores: OwnLLMScore[];
}

export interface AgentSummaryRow {
  agent_id: string;
  agent_name: string;
  calls: number;
  avg_score: number | null;
  fatals: number;
  unreviewed_flags?: number;
  agency_id?: string;
}

export interface DashboardSummary {
  total_recordings: number;
  completed: number;
  pending: number;
  failed: number;
  submitted: number;
  avg_compliance_score: number | null;
  total_compliance_flags: number;
  critical_flags: number;
  last_sync_at: string | null;
  last_completed_at: string | null;
  agent_summary: AgentSummaryRow[];
}

export interface PaginatedResponse<T> {
  results: T[];
  pagination: {
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
  };
}

export interface AuthUser {
  user_id: number;
  role_id: number;
  agency_id: number;
  first_name: string;
  last_name: string;
  email: string;
}

export interface OpsResult {
  status?: string;
  date?: string;
  dry_run?: boolean;
  total_fetched?: number;
  created?: number;
  skipped_dedup?: number;
  skipped_validation?: number;
  unknown_agents?: number;
  errors?: number;
  duration_seconds?: number;
  submitted?: number;
  failed?: number;
}

export interface SignedUrlResponse {
  signed_url: string;
  expires_in_seconds: number;
}

export type ScoreBand = "excellent" | "good" | "needs-improvement" | "critical" | null;

export function scoreBand(pct: number | null | undefined): ScoreBand {
  if (pct == null) return null;
  if (pct >= 85) return "excellent";
  if (pct >= 70) return "good";
  if (pct >= 55) return "needs-improvement";
  return "critical";
}

export function scoreBandLabel(band: ScoreBand): string {
  switch (band) {
    case "excellent":        return "Excellent";
    case "good":             return "Good";
    case "needs-improvement":return "Needs Improvement";
    case "critical":         return "Critical";
    default:                 return "—";
  }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "Asia/Kolkata",
  });
}
