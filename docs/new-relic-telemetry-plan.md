# New Relic Telemetry Plan — BaySys Call Audit AI

**Status:** Plan (not yet implemented)
**Target:** EC2 (current), Kubernetes-ready (future)
**Scope:** APM + custom business metrics + management command instrumentation

---

## Why

The Call Auditor processes ~18K calls/day through a pipeline with multiple external dependencies (S3, GreyLabs/STT provider, CRM database). Right now there's zero observability — `logger.info()` to stdout is it. When something breaks at 3 AM (a stuck webhook, a provider timeout, a compliance rule miscalculation), nobody knows until someone manually checks the dashboard.

New Relic gives us: request-level APM, external call tracing, database query visibility, custom business metrics (calls processed, FATALs flagged, provider latency), and alerting — all without rewriting the application.

---

## Phase 1 — Agent Install + Auto-Instrumentation

**Effort:** ~30 minutes. Zero code changes.

### What to do

1. `pip install newrelic` → add to `requirements.txt`
2. Generate config: `newrelic-admin generate-config <LICENSE_KEY> newrelic.ini`
3. Add to `.env.example`:
   ```
   NEW_RELIC_LICENSE_KEY=
   NEW_RELIC_APP_NAME=BaySys-CallAudit-{env}
   NEW_RELIC_ENVIRONMENT=development
   ```
4. Wrap gunicorn startup:
   ```bash
   NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program gunicorn settings:wsgi --bind 0.0.0.0:8000
   ```
5. Add `newrelic.ini` to `.gitignore` (contains licence key). Commit a `newrelic.ini.example` with placeholder.

### What you get for free (no code changes)

- **Django request tracing** — every DRF view auto-instrumented with response time, throughput, error rate
- **Database queries** — all ORM and raw SQL queries tracked (including the `SYNC_QUERY` join against `uvarcl_live`)
- **External HTTP calls** — `requests` library auto-instrumented, so every call to `speech_provider.py` (GreyLabs API) shows up with latency, status code, error rate
- **Middleware timing** — CORS, auth, DRF permission checks
- **Error tracking** — exceptions with full stack traces

### Kubernetes-ready note

When you move to K8s, switch from `newrelic.ini` to env vars exclusively (`NEW_RELIC_LICENSE_KEY`, `NEW_RELIC_APP_NAME`, etc.) — inject via ConfigMap/Secret. The agent respects env vars natively. No config file needed.

---

## Phase 2 — Management Command Instrumentation

**Effort:** ~1 hour. Light code changes.

The cron-scheduled management commands are where the actual pipeline work happens. Without instrumenting these, you're blind to the most critical path.

### Wrap each command

Each of the 5 commands needs the `newrelic-admin` wrapper in cron:

```bash
# crontab
# Daily sync (runs at 01:00 IST)
0 1 * * * NEW_RELIC_CONFIG_FILE=/path/to/newrelic.ini newrelic-admin run-program python manage.py sync_call_logs

# Submit pending recordings (runs every 5 min)
*/5 * * * * NEW_RELIC_CONFIG_FILE=/path/to/newrelic.ini newrelic-admin run-program python manage.py submit_recordings --tier immediate --batch-size 500

# Poll stuck recordings (runs every 15 min)
*/15 * * * * NEW_RELIC_CONFIG_FILE=/path/to/newrelic.ini newrelic-admin run-program python manage.py poll_stuck_recordings
```

### Add `@background_task` to service functions

The management commands call service functions — those should be marked as background tasks so New Relic groups them correctly:

```python
# services.py
import newrelic.agent

@newrelic.agent.background_task(name='submit_pending_recordings')
def submit_pending_recordings(batch_size=100, tiers=None):
    ...

@newrelic.agent.background_task(name='process_provider_webhook')
def process_provider_webhook(payload):
    ...
```

```python
# ingestion.py
import newrelic.agent

@newrelic.agent.background_task(name='run_sync_for_date')
def run_sync_for_date(target_date=None, batch_size=5000, dry_run=False):
    ...
```

### What you get

- Each management command run appears as a separate transaction in New Relic
- Sync duration, submission batch times, polling recovery times — all visible
- External calls (S3 re-signing, provider API) tracked within the command context
- Database queries within sync/submit tracked with timing

---

## Phase 3 — Custom Business Metrics

**Effort:** ~2 hours. Targeted code changes in 4 files.

This is where New Relic goes from "ops tool" to "business dashboard." These metrics tell you whether the system is doing its job, not just whether it's running.

### `services.py` — Submission + Webhook metrics

```python
import newrelic.agent

# In submit_pending_recordings(), after each submission:
newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/Submitted', 1)
newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/SubmitFailed', 1)  # on ProviderError

# In process_provider_webhook(), after processing:
newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/Processed', 1)
newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/IdempotencySkip', 1)  # already completed

# Add recording context as custom attributes:
newrelic.agent.add_custom_attributes({
    'recording_id': recording.pk,
    'agent_id': recording.agent_id,
    'submission_tier': recording.submission_tier,
    'fatal_level': recording.fatal_level,
})
```

### `compliance.py` — Compliance flag metrics

```python
# In check_metadata_compliance(), per flag created:
newrelic.agent.record_custom_metric(f'Custom/Compliance/MetadataFlags/{flag.flag_type}', 1)

# In check_provider_compliance(), per flag created:
newrelic.agent.record_custom_metric(f'Custom/Compliance/ProviderFlags/{flag.flag_type}', 1)

# In compute_fatal_level():
newrelic.agent.record_custom_metric('Custom/Compliance/FatalLevel', fatal_level)
```

### `ingestion.py` — Sync metrics

```python
# At end of run_sync_for_date():
newrelic.agent.record_custom_event('SyncCompleted', {
    'target_date': str(target_date),
    'fetched': result['fetched'],
    'created': result['created'],
    'skipped_dedup': result['skipped_dedup'],
    'skipped_validation': result['skipped_validation'],
    'duration_seconds': result['duration_seconds'],
})
```

### `speech_provider.py` — Provider latency + errors

```python
# In submit_recording(), wrap the requests.post:
newrelic.agent.add_custom_attributes({
    'provider_endpoint': 'submit_recording',
    'provider_resource_id': resource_id,
})

# On ProviderError:
newrelic.agent.record_custom_event('ProviderError', {
    'endpoint': endpoint,
    'status_code': exc.status_code,
    'message': str(exc),
})
```

### Key metrics summary

| Metric | Source | Why it matters |
|--------|--------|----------------|
| `Custom/Pipeline/Recordings/Submitted` | services.py | Throughput — are we keeping up with 18K/day? |
| `Custom/Pipeline/Recordings/SubmitFailed` | services.py | Provider reliability — failure rate trend |
| `Custom/Pipeline/Webhooks/Processed` | services.py | Completion rate — are results coming back? |
| `Custom/Compliance/MetadataFlags/*` | compliance.py | Compliance flag volume by type |
| `Custom/Compliance/FatalLevel` | compliance.py | Fatal level distribution — are agents improving? |
| `SyncCompleted` (event) | ingestion.py | Daily sync health — rows fetched, created, skipped |
| `ProviderError` (event) | speech_provider.py | Provider incident detection |

---

## Phase 4 — Alerts

**Effort:** ~30 minutes. New Relic UI only, no code.

Set up in the New Relic Alerts UI after Phases 1–3 are deployed:

| Alert | Condition | Threshold | Channel |
|-------|-----------|-----------|---------|
| **Provider down** | `ProviderError` event count | >10 in 5 min | Slack / Email |
| **Webhook backlog** | `status=submitted` age | Any recording >60 min old | Slack |
| **Sync failure** | `SyncCompleted` event absent | No event by 02:00 IST | Email |
| **FATAL spike** | `Custom/Compliance/FatalLevel` avg | >3.0 over 1 hour | Slack |
| **API error rate** | HTTP 5xx rate on `/audit/*` | >5% over 5 min | Slack |
| **Submit throughput drop** | `Custom/Pipeline/Recordings/Submitted` | <500/hour during business hours | Email |

---

## Implementation Order

| Phase | What | Effort | Prereq |
|-------|------|--------|--------|
| **1** | Agent install + auto-instrumentation | 30 min | New Relic licence key |
| **2** | Management command wrapping + `@background_task` | 1 hr | Phase 1 |
| **3** | Custom business metrics | 2 hrs | Phase 1 |
| **4** | Alerts | 30 min | Phase 3 deployed + 24h of data |

Phases 1 and 2 are the priority — they give you 80% of the value with minimal code change. Phase 3 is where it becomes a business tool. Phase 4 is configuration.

---

## Files Modified

| File | Changes |
|------|---------|
| `requirements.txt` | Add `newrelic` |
| `.env.example` | Add `NEW_RELIC_*` vars |
| `.gitignore` | Add `newrelic.ini` |
| `newrelic.ini.example` | New — template config |
| `services.py` | `@background_task` decorators + custom metrics |
| `ingestion.py` | `@background_task` + sync event |
| `compliance.py` | Custom metrics per flag type |
| `speech_provider.py` | Custom attributes + error events |
| `docs/OPERATIONS.md` | Add New Relic section (env vars, cron wrappers, dashboard links) |

---

## What NOT to do

- **Don't add New Relic middleware manually** — the agent auto-detects Django. Adding middleware doubles the instrumentation.
- **Don't instrument every function** — auto-instrumentation covers Django views, DB queries, and HTTP calls. Only add `@function_trace` if a specific function is a known bottleneck.
- **Don't log to New Relic AND stdout** — use New Relic's log forwarding if you want logs in the same place, but don't duplicate.
- **Don't put the licence key in code or git** — env var only.
- **Keep custom metric names under 2,000 unique** — don't create per-recording or per-agent metric names. Use custom attributes for that granularity.
