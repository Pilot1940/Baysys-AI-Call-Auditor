# BaySys Call Audit AI — Test Guide

## Running tests

```bash
cd Baysys-AI-Call-Auditor/
source .venv/bin/activate

# Run all tests (SQLite in-memory, no Supabase needed)
python manage.py test --settings=settings_test -v 0

# Run with verbose output
python manage.py test --settings=settings_test -v 2

# Run a specific test file
python manage.py test --settings=settings_test baysys_call_audit.tests.test_models

# Run a specific test class
python manage.py test --settings=settings_test baysys_call_audit.tests.test_webhook.ProviderWebhookViewTests

# Run ruff linter
ruff check baysys_call_audit/
```

## Test files

| File | Tests | What it covers |
|------|-------|---------------|
| `test_models.py` | 18 | All 5 models: CRUD, constraints, str, compute_percentage |
| `test_speech_provider.py` | 12 | All 6 provider functions with mocked HTTP |
| `test_webhook.py` | 8 | Webhook receiver: success, idempotency, compliance flags |
| `test_services.py` | 13 | Ingestion pipeline, webhook processing, compliance checks |
| `test_views.py` | 14 | API views: list, detail, dashboard, flags, pagination |
| `test_crm_adapter.py` | 7 | All adapter functions in mock mode |

## Test gate

Before any commit or code review:
- 72 tests passing
- 0 ruff findings
