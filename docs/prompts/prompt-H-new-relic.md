# Prompt H — New Relic APM Instrumentation

**Scope:** Add New Relic telemetry to the Call Auditor. Auto-instrumentation is already handled by the agent (Django views, DB queries, outbound HTTP via `requests`). This prompt adds: `@background_task` decorators, custom business metrics, custom events, custom attributes, and a `newrelic.ini.example` config template.

**Prereq:** `newrelic>=10.0` already in `requirements.txt`. `newrelic.ini` already in `.gitignore`. `NEW_RELIC_*` env vars already in `.env.example`. Build rules already in `CLAUDE.md` under "Observability — New Relic APM".

**Read first:** `CLAUDE.md` (especially the New Relic section), `docs/new-relic-telemetry-plan.md` (full plan with rationale).

---

## Tasks

### 1. Create `newrelic.ini.example` at project root

Template config with placeholder licence key. Include:
- `app_name = BaySys-CallAudit-%(NEW_RELIC_ENVIRONMENT)s`
- `license_key = REPLACE_ME`
- Environment-specific sections: `[newrelic:development]`, `[newrelic:staging]`, `[newrelic:production]`
- `monitor_mode = false` in development section, `true` in production
- `log_file = stdout` (for EC2 and future K8s compatibility)
- `transaction_tracer.record_sql = obfuscated`
- `distributed_tracing.enabled = true`
- Comment explaining: "In production, prefer env vars over this file. When moving to K8s, use env vars exclusively."

### 2. Instrument `services.py`

Add `import newrelic.agent` at top.

**`submit_pending_recordings()`:**
- Add `@newrelic.agent.background_task(name='submit_pending_recordings')` decorator
- After each successful submission: `newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/Submitted', 1)`
- On each `ProviderError`: `newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/SubmitFailed', 1)`
- Add `newrelic.agent.add_custom_attributes({'recording_id': recording.pk, 'agent_id': recording.agent_id, 'submission_tier': recording.submission_tier})` inside the submission loop

**`process_provider_webhook()`:**
- Add `@newrelic.agent.background_task(name='process_provider_webhook')` decorator
- After successful processing: `newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/Processed', 1)`
- On idempotency skip (already completed): `newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/IdempotencySkip', 1)`
- Add `newrelic.agent.add_custom_attributes({'recording_id': recording.pk, 'agent_id': recording.agent_id, 'provider_resource_id': resource_id})` after lookup

**`run_own_llm_scoring()`:**
- Add `@newrelic.agent.background_task(name='run_own_llm_scoring')` decorator (even though it's a placeholder — ready for when it's implemented)

### 3. Instrument `ingestion.py`

Add `import newrelic.agent` at top.

**`run_sync_for_date()`:**
- Add `@newrelic.agent.background_task(name='run_sync_for_date')` decorator
- At the end of the function (after the result dict is built), add:
```python
newrelic.agent.record_custom_event('SyncCompleted', {
    'target_date': str(target_date),
    'fetched': result['fetched'],
    'created': result['created'],
    'skipped_dedup': result['skipped_dedup'],
    'skipped_validation': result['skipped_validation'],
    'duration_seconds': result.get('duration_seconds', 0),
})
```

### 4. Instrument `compliance.py`

Add `import newrelic.agent` at top.

**`check_metadata_compliance()`:**
- After each `ComplianceFlag` creation: `newrelic.agent.record_custom_metric(f'Custom/Compliance/MetadataFlags/{flag.flag_type}', 1)`

**`check_provider_compliance()`:**
- After each `ComplianceFlag` creation: `newrelic.agent.record_custom_metric(f'Custom/Compliance/ProviderFlags/{flag.flag_type}', 1)`

**`compute_fatal_level()`:**
- After computing the level: `newrelic.agent.record_custom_metric('Custom/Compliance/FatalLevel', fatal_level)`

### 5. Instrument `speech_provider.py`

Add `import newrelic.agent` at top.

**`submit_recording()`:**
- On `ProviderError`, record a custom event:
```python
newrelic.agent.record_custom_event('ProviderError', {
    'endpoint': 'submit_recording',
    'status_code': exc.status_code,
    'message': str(exc)[:500],
})
```

**`get_results()`:**
- On `ProviderError`, same pattern with `'endpoint': 'get_results'`

### 6. Instrument `views.py`

Add `import newrelic.agent` at top.

**`ProviderWebhookView.post()`:**
- At top of method: `newrelic.agent.add_custom_attributes({'webhook_source': 'provider'})`

**`RecordingDetailView.get()`:**
- After retrieving recording: `newrelic.agent.add_custom_attributes({'recording_id': recording.pk, 'agent_id': recording.agent_id})`

**`SyncCallLogsView.post()`:**
- After parsing request: `newrelic.agent.add_custom_attributes({'sync_date': target_date, 'dry_run': dry_run})`

### 7. Tests

Add tests to verify New Relic instrumentation doesn't break anything when the agent is not active (which is the case in test runs). The New Relic API calls are no-ops when no agent is initialized, so existing tests should pass unchanged. Verify this by running the full test suite.

**Add 1 new test file: `tests/test_newrelic_instrumentation.py`** with:
- Test that `services.submit_pending_recordings` has `__wrapped__` attribute (proves decorator is applied)
- Test that `services.process_provider_webhook` has `__wrapped__` attribute
- Test that `ingestion.run_sync_for_date` has `__wrapped__` attribute
- Test that `services.run_own_llm_scoring` has `__wrapped__` attribute
- Test that importing `newrelic.agent` doesn't raise
- Test that `newrelic.agent.record_custom_metric` is callable (no-op without agent)

### 8. Documentation updates

- Update `MANIFEST.md`: add `newrelic.ini.example` to root files table, add `docs/new-relic-telemetry-plan.md` and `docs/prompts/prompt-H-new-relic.md` to docs table
- Update `BUILD_LOG.md`: add Prompt H session entry with files modified, tests added
- Verify `docs/OPERATIONS.md` New Relic section is current (already added — just verify)

---

## Files to create

| File | Purpose |
|------|---------|
| `newrelic.ini.example` | Template config (committed to git, no secrets) |
| `tests/test_newrelic_instrumentation.py` | Verify decorators applied + no-op safety |

## Files to modify

| File | Changes |
|------|---------|
| `services.py` | `@background_task` decorators + custom metrics + custom attributes |
| `ingestion.py` | `@background_task` + `SyncCompleted` event |
| `compliance.py` | Custom metrics per flag type + fatal level |
| `speech_provider.py` | `ProviderError` custom events |
| `views.py` | Custom attributes on key endpoints |
| `MANIFEST.md` | Add new files |
| `BUILD_LOG.md` | Add Prompt H entry |

## Files NOT to modify

- `settings.py` — no Django LOGGING config changes needed; New Relic agent handles instrumentation via wrapper
- `models.py` — no model changes
- `crm_adapter.py` — outbound HTTP calls auto-instrumented by agent
- `urls.py` — no changes needed

---

## Acceptance criteria

1. All 275+ existing tests still pass
2. New instrumentation tests pass
3. 0 ruff findings
4. `newrelic.ini.example` committed (no secrets)
5. Every `@background_task` decorated function has a test verifying the decorator is applied
6. No `newrelic` imports in `models.py`, `crm_adapter.py`, `settings.py`, or `urls.py`
7. MANIFEST.md and BUILD_LOG.md updated
