/** API client — typed wrappers around the Call Audit API. */

import { request } from "./Request";
import type {
  CallDetail,
  CallRecording,
  ComplianceFlag,
  DashboardSummary,
  PaginatedResponse,
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
};
