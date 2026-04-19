/** API client — typed wrappers around the Call Audit API. */

import { request } from "./Request";
import type {
  CallDetail,
  CallRecording,
  ComplianceFlag,
  DashboardSummary,
  OpsResult,
  PaginatedResponse,
  SignedUrlResponse,
} from "../types/audit";

export const api = {
  getRecordings(params?: Record<string, string>): Promise<PaginatedResponse<CallRecording>> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/recordings/${qs}`);
  },

  getRecordingDetail(id: number): Promise<CallDetail> {
    return request(`/recordings/${id}/`);
  },

  getDashboardSummary(params?: Record<string, string>): Promise<DashboardSummary> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/dashboard/summary/${qs}`);
  },

  getComplianceFlags(params?: Record<string, string>): Promise<PaginatedResponse<ComplianceFlag>> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request(`/compliance-flags/${qs}`);
  },

  getSignedUrl(recordingId: number): Promise<SignedUrlResponse> {
    return request(`/recordings/${recordingId}/signed-url/`);
  },

  retryRecording(recordingId: number): Promise<{ status: string; retry_count: number }> {
    return request(`/recordings/${recordingId}/retry/`, { method: "POST" });
  },

  reviewFlag(
    recordingId: number,
    flagId: number,
    reviewed: boolean
  ): Promise<ComplianceFlag> {
    return request(`/recordings/${recordingId}/flags/${flagId}/review/`, {
      method: "PATCH",
      body: { reviewed },
    });
  },

  syncCallLogs(params: { date?: string; dry_run?: boolean }): Promise<OpsResult> {
    return request(`/recordings/sync/`, { method: "POST", body: params });
  },

  submitRecordings(params: { batch_size?: number }): Promise<OpsResult> {
    return request(`/recordings/submit/`, { method: "POST", body: params });
  },

  pollStuckRecordings(params: { batch_size?: number; dry_run?: boolean }): Promise<OpsResult> {
    return request(`/recordings/poll/`, { method: "POST", body: params });
  },
};
