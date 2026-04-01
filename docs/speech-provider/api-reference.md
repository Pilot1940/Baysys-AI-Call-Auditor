# Speech Analytics Provider API Reference

**Current provider:** GreyLabs
**Host:** `https://api.greylabs.ai`
**Auth:** `x-api-key` + `x-api-secret` headers on every request

> This document is for reference only. All provider interaction goes through `speech_provider.py`.

---

## Endpoints

### POST `/insights/resource/listen` — Submit audio for processing
**Payload (form-data):**
- `resource_url` — Signed S3 URL to the MP3 file
- `template_id` — Scoring template identifier
- `agent_id` — CRM agent identifier
- `agent_name` — Agent display name
- `recording_datetime` — ISO 8601 datetime
- `callback_url` — Webhook URL for results

**Response:** `{ "resource_insight_id": "..." }`

### POST `/insights/resource/insights` — Poll for results
**Payload (json):** `{ "resource_insight_id": "..." }`

**Response:** Full results including transcript, durations, sentiments, compliance score, category_data, subjective_data.

### POST `/insights/v1/resource/delete` — Delete a resource
**Payload (json):** `{ "resource_insight_id": "..." }`

### POST `/insights/v1/resource/ask` — Ask a question
**Payload (json):** `{ "resource_insight_id": "...", "question": "..." }`

### POST `/insights/transcript/listen` — Submit raw transcript
**Payload (json):** `{ "transcript": "...", "template_id": "...", "callback_url": "..." }`

### POST `/insights/resource/insights/update/metadata` — Update metadata
**Payload (json):** `{ "resource_insight_id": "...", ...metadata }`

### POST `/reports/batch/import` — Batch upload (Excel)
**Payload (form-data):** Excel file

---

## Key response fields

```json
{
  "resource_url": "...",
  "transcript": "...",
  "detected_language": "en",
  "total_call_duration": 203,
  "total_non_speech_duration": 49,
  "customer_talk_duration": 36,
  "agent_talk_duration": 110,
  "audit_compliance_score": 0,
  "max_compliance_score": 4,
  "customer_sentiment": "Neutral",
  "agent_sentiment": "Neutral",
  "detected_restricted_keyword": false,
  "restricted_keywords": [],
  "insights": {
    "category_data": [...],
    "subjective_data": [...]
  }
}
```

---

## Rate limits
- 200 requests/minute

## MONO recording caveat
All recordings are mono (single channel). Diarisation accuracy ~80% on mono (vs 90%+ on stereo). Objective parameters (binary yes/no) are reliable. Subjective parameters depending on speaker attribution are less reliable.
