# Call Auditor — Project State

## Overview
Django backend voice analysis service for BaySys. Records Bolna call audio, transcribes via Deepgram, extracts disposition + persona match via GPT-4, stores in Supabase. Session 30 complete.

## Current State (2026-04-29)

**Last Commit:** `e56ecf7` — docs: Session 30 — collapsible agency accordion  
**Git Status:** Clean  
**Branch:** main  
**Test Files:** 17 test files covering models, API, CRM adapters, speech providers

## Core Architecture

**Django Stack:**
- **Runtime:** Python 3.10+
- **Framework:** Django 4.2 + DRF (Django REST Framework)
- **Database:** Supabase PostgreSQL (development) + AWS RDS (production)
- **ORM:** Django ORM
- **Task Queue:** Celery (optional, not currently used for critical paths)

**Key Modules:**
- `baysys_call_audit/` — core app with models, API, CRM adapters
- `baysys_call_audit_ui/` — frontend (React, minimal, supporting status page)
- `config/` — settings, environment config
- `tests/` — 17 test files (unit + integration)

## Critical Pattern: CRM Adapter

**File:** `baysys_call_audit/crmadapter.py`
**Rule:** ONLY file with mock/prod branching. Never add CRM logic elsewhere.
**Pattern:** Adapter wraps real CRM API calls. Tests use mocks via env var (`CRM_MODE=mock`).

```python
from baysys_call_audit.crm_adapter import CRMAdapter

adapter = CRMAdapter()
# Uses real/mock based on environment
adapter.fetch_customer(customer_id)
```

## Speech Provider Pattern

**File:** `baysys_call_audit/speech_provider.py`
**Provider:** GreyLabs (primary) + Deepgram (fallback)
**Invariant:** Provider selection at runtime via config. No hardcoding.

## Test Suite (17 files)

Located in `tests/`:
- `test_models.py` — Call, Disposition, Persona models
- `test_api.py` — DRF endpoints
- `test_crm_adapter.py` — CRM mocking pattern
- `test_speech_provider.py` — Deepgram/GreyLabs integration
- `test_disposition_extraction.py` — GPT-4 extraction logic
- `test_agency_accordion.py` — UI component logic (Session 30)
- [11 more tests covering auth, permissions, edge cases]

**Gate:** 17 tests passing, 0 ruff findings (enforced via CI)

## Session 30 Complete

**Feature:** Collapsible agency accordion in CRM  
**Files Modified:**
- `baysys_call_audit/models.py` — AgencyGroup model
- `baysys_call_audit_ui/components/AgencyAccordion.tsx` — React component
- `tests/test_agency_accordion.py` — New test file

**Commits:**
- Session 30 development (3 commits)
- Final: `e56ecf7` docs: Session 30 — collapsible agency accordion

## Documentation

- **CLAUDE.md** — Build rules, test gates, CRM adapter invariant
- **BUILD_LOG.md** — Detailed session history (62 KB, 30+ sessions)
- **MANIFEST.md** — API endpoints, models, configurations (24 KB)
- **docs/OPERATIONS.md** — Deployment, monitoring, troubleshooting

## Build & Deploy

```bash
# Install
pip install -r requirements.txt

# Dev server
python manage.py runserver

# Tests
pytest tests/ -v
ruff check .  # Linting

# Migrate
python manage.py migrate
```

**CI:** GitHub Actions runs pytest + ruff before merge.

## Known Constraints

- **CRM branching:** ONLY in crm_adapter.py, never elsewhere
- **Speech provider:** GreyLabs + Deepgram, configured via env
- **Database:** Supabase in dev, AWS RDS in prod
- **No test suite issues:** 17 tests, 0 ruff findings (consistently)

## .claude/ Tracking

**Status:** Untracked (not in .gitignore) — noted in code review  
**Resolution:** Pending: add .claude/ to .gitignore  
**Severity:** Low (session state, no impact on production)

## Next Steps

- Session 31: [pending — check build diary]
- Monitoring: Call quality metrics dashboard
- Scaling: Celery task optimization for high-volume call processing
