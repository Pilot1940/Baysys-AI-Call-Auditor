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
  category_data: Record<string, unknown>[] | null;
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

export interface DashboardSummary {
  total_recordings: number;
  completed: number;
  pending: number;
  failed: number;
  avg_compliance_score: number | null;
  total_compliance_flags: number;
  critical_flags: number;
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
