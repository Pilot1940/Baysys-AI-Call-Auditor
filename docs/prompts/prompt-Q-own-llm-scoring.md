# Prompt Q — OwnLLM Scoring Backend

**Repo:** `Baysys-AI-Call-Auditor/` (standalone)
**Branch:** `main`
**Goal:** Implement `run_own_llm_scoring()` using the Anthropic API, scoring each call against
the UVARCL 19-parameter scorecard. Wire it into the webhook flow before compliance checks,
and update the P2 compliance rule to check the LLM score instead of GreyLabs' internal score.
Also fix `_create_provider_score()` to read `category_data` from the correct location in the
GreyLabs payload (root level, not `insights`).

**Test gate:** All existing tests pass + new tests added. `ruff check .` → 0 findings.
**After completion:** Mirror `services.py`, `compliance.py`, `compliance_rules.yaml` to
`crm_apis/arc/baysys_call_audit/`. The new YAML config and test file stay in standalone only.

---

## Step 1 — Create `config/scoring_template_uvarcl_v2.yaml`

New file. Full content:

```yaml
# UVARCL Collections Call Quality Scorecard v2
# Used by run_own_llm_scoring() to score calls against this template.
template_name: "UVARCL Collections Call Quality v2"
version: "2.0"
max_total_score: 100

# Calls with these GreyLabs dispositions are not scoreable — store call_type=not_scoreable
not_scoreable_dispositions:
  - "Wrong Party Connect"
  - "No Answer"
  - "Voicemail"
  - "Switched Off"
  - "Not Connected"

parameters:
  - id: 1
    name: "Greeting"
    group: "Introduction Quality"
    max_score: 3
    fatal: false
    type: objective
    prompt: "Did the call open with a greeting (e.g. Good morning/afternoon/evening/namaste)? Score: 3=Yes, 0=No"

  - id: 2
    name: "Self-introduction (Name)"
    group: "Introduction Quality"
    max_score: 3
    fatal: false
    type: objective
    prompt: "Did the agent state their own name at any point? Score: 3=Stated, 0=Not stated"

  - id: 3
    name: "Bank / Original Lender context disclosed"
    group: "Introduction Quality"
    max_score: 3
    fatal: false
    type: objective
    prompt: "Did the agent mention the original bank or NBFC name? Score: 3=Yes, 0=No"

  - id: 4
    name: "UVARCL takeover / ARC identity disclosed"
    group: "Introduction Quality"
    max_score: 6
    fatal: false
    type: objective
    prompt: "Did the agent identify UVARCL as the current debt owner? Score: 6=Clear mention, 3=Partial/implied, 0=Not mentioned"

  - id: 5
    name: "Right Party Verification (RPV)"
    group: "Introduction Quality"
    max_score: 5
    fatal: true
    fatal_condition: "Debt details were discussed without verifying the identity of the person on the call"
    type: objective
    prompt: "FATAL if debt details were discussed without RPV. Did agent verify identity before discussing account? Score: 5=RPV done before any account discussion, 0=FATAL (discussed debt without RPV)"

  - id: 6
    name: "No fumble / fluent delivery"
    group: "Call Quality"
    max_score: 5
    fatal: false
    type: subjective
    prompt: "Assess agent fluency and confidence. Score: 5=Excellent (clear, confident, no hesitation), 3=Minor issues (occasional fumble), 0=Significant fumble (confusing, repetitive, incoherent)"

  - id: 7
    name: "No harsh / threatening / abusive language"
    group: "Call Quality"
    max_score: 10
    fatal: true
    fatal_condition: "Agent used any threatening, abusive, or coercive language"
    type: objective
    prompt: "FATAL if any threat or abuse by agent. Score: 10=None detected, 0=FATAL (any threat, abuse, or coercive language)"

  - id: 8
    name: "Objection handling / answered questions"
    group: "Call Quality"
    max_score: 8
    fatal: false
    type: objective
    prompt: "Did agent address customer questions and objections? Score: 8=All answered satisfactorily, 4=>50% answered, 0=<50% answered or ignored"

  - id: 9
    name: "Customer satisfied / de-escalated"
    group: "Call Quality"
    max_score: 5
    fatal: false
    type: subjective
    prompt: |
      Assess customer sentiment at end vs start. Score:
      5=De-escalated/satisfied (commitment signals: 'okay I will pay', 'theek hai', 'send me UPI',
        'kal tak kar deta hoon'; or acceptance: 'samajh gaya', 'noted', 'chalega')
      2=Neutral (deflection: 'baad mein', 'abhi nahi', 'mujhe time chahiye'; passive non-engagement)
      0=Escalated (threats: 'RBI mein jaaunga', 'consumer court'; abuse; customer angrier at end than start)

  - id: 10
    name: "Moved forward — PTP / next step secured"
    group: "Call Quality"
    max_score: 10
    fatal: false
    type: objective
    prompt: "Was a Promise-to-Pay or clear next action agreed? Score: 10=PTP with date/amount secured, 5=Next step agreed (callback, document, verification), 0=No movement"

  - id: 11
    name: "Closing remark and summary"
    group: "Call Quality"
    max_score: 4
    fatal: false
    type: objective
    prompt: "Did agent close with a thank-you and recap of next steps? Score: 4=Both done, 2=One done, 0=Neither"

  - id: 12
    name: "Regulatory concern"
    group: "Call Quality"
    max_score: 3
    fatal: false
    type: subjective
    prompt: "If customer raised a regulatory concern (RBI, harassment, complaint) — was it handled correctly? Score: 3=Handled correctly or not raised (N/A), 1=Partial handling, 0=Ignored or mishandled"

  - id: 13
    name: "Calling within permitted hours (8am–8pm IST)"
    group: "Compliance & RBI"
    max_score: 8
    fatal: true
    fatal_condition: "Evidence the call was placed outside 08:00–20:00 IST"
    type: objective
    prompt: "FATAL if call is outside permitted hours. Score: 8=Within window or cannot determine from transcript alone, 0=FATAL (transcript evidence of call outside hours)"

  - id: 14
    name: "Non-disclosure to third parties (TCP)"
    group: "Compliance & RBI"
    max_score: 5
    fatal: true
    fatal_condition: "Loan or account details shared with a third party without customer consent"
    type: objective
    prompt: "FATAL if loan details shared with unverified third party. Score: 5=Maintained confidentiality, 0=FATAL (details shared without consent)"

  - id: 15
    name: "Misrepresentation"
    group: "Compliance & RBI"
    max_score: 5
    fatal: true
    fatal_condition: "Agent claimed to be from the original bank/lender instead of UVARCL"
    type: objective
    prompt: "FATAL if agent misrepresented as original lender. Score: 5=Correctly identified as UVARCL, 3=Nothing mentioned (neutral), 0=FATAL (claimed to be from original bank)"

  - id: 16
    name: "Non-payment consequences communicated"
    group: "Compliance & RBI"
    max_score: 7
    fatal: false
    type: objective
    prompt: "Were legal or credit-bureau consequences of non-payment explained? Score: 7=Clearly explained, 3=Vaguely mentioned, 0=Not mentioned"

  - id: 17
    name: "Confirmed NO OTP / PIN requested"
    group: "Scam & Trust Handling"
    max_score: 4
    fatal: true
    fatal_condition: "Agent requested OTP, CVV, password, or PIN"
    type: objective
    prompt: "FATAL if agent asked for OTP/CVV/PIN/password. Score: 4=Not requested, 0=FATAL"

  - id: 18
    name: "Shared Personal Details for Payment"
    group: "Scam & Trust Handling"
    max_score: 4
    fatal: true
    fatal_condition: "Agent shared their personal phone number or UPI ID to collect payment"
    type: objective
    prompt: "FATAL if agent shared personal payment details. Score: 4=Not shared, 0=FATAL (agent gave personal number or UPI for payment)"

  - id: 19
    name: "Verification / dispute channel offered"
    group: "Scam & Trust Handling"
    max_score: 2
    fatal: false
    type: objective
    prompt: "Did agent mention official dispute or verification process? Score: 2=Yes, 0=No"
```

---

## Step 2 — `requirements.txt`

Add: `anthropic>=0.43.0`

---

## Step 3 — `baysys_call_audit/settings.py`

Add these settings (read from env using `env.bool` / `env.str` / `env.int`):

```python
OWN_LLM_ENABLED = env.bool("OWN_LLM_ENABLED", default=True)
OWN_LLM_API_KEY = env.str("OWN_LLM_API_KEY", default="")
OWN_LLM_MODEL = env.str("OWN_LLM_MODEL", default="claude-haiku-4-5-20251001")
OWN_LLM_MAX_TOKENS = env.int("OWN_LLM_MAX_TOKENS", default=4096)
OWN_LLM_SCORING_TEMPLATE = env.str("OWN_LLM_SCORING_TEMPLATE", default="scoring_template_uvarcl_v2")
```

---

## Step 4 — `.env.example`

Add section after the existing POLL_STUCK_AFTER_MINUTES block:

```
# Own-LLM scoring (UVARCL scorecard, runs synchronously after each completed webhook)
OWN_LLM_ENABLED=true
OWN_LLM_API_KEY=
OWN_LLM_MODEL=claude-haiku-4-5-20251001
OWN_LLM_MAX_TOKENS=4096
OWN_LLM_SCORING_TEMPLATE=scoring_template_uvarcl_v2
```

---

## Step 5 — `baysys_call_audit/services.py`

### 5a — Fix `_create_provider_score()`

GreyLabs sends `category_data` at the root of the payload, not inside a nested `insights` dict.
Also, GreyLabs returns `category_data` as a **list** of objects; `compute_fatal_level()` expects
a **dict** keyed by parameter name. Normalise on storage.

Replace the full function body of `_create_provider_score()`:

```python
def _create_provider_score(recording: CallRecording, payload: dict) -> ProviderScore | None:
    """Extract scoring data from provider payload and create ProviderScore."""
    template_id = settings.SPEECH_PROVIDER_TEMPLATE_ID
    if not template_id:
        return None

    # GreyLabs sends category_data as a list at root level (not nested in 'insights').
    # Normalise to {param_name: first_answer} dict so compute_fatal_level can look up by name.
    raw_category = payload.get("category_data") or []
    if isinstance(raw_category, list):
        category_data = {
            item["audit_parameter_name"]: (
                item["answer"][0]
                if isinstance(item.get("answer"), list) and item["answer"]
                else item.get("answer")
            )
            for item in raw_category
            if item.get("audit_parameter_name")
        }
    else:
        category_data = raw_category or None

    score = ProviderScore(
        recording=recording,
        template_id=template_id,
        audit_compliance_score=payload.get("audit_compliance_score"),
        max_compliance_score=payload.get("max_compliance_score"),
        category_data=category_data,
        detected_restricted_keyword=payload.get("detected_restricted_keyword", False),
        restricted_keywords=payload.get("restricted_keywords", []),
        raw_score_payload=payload,
    )
    score.compute_percentage()
    score.save()
    return score
```

### 5b — Implement `run_own_llm_scoring()`

Replace the entire placeholder function (currently returns None after a TODO comment) with:

```python
@newrelic.agent.background_task(name='run_own_llm_scoring')
def run_own_llm_scoring(recording_id: int, template_name: str | None = None) -> OwnLLMScore | None:
    """
    Score the call transcript against the UVARCL scorecard using the Anthropic API.

    Flow:
      1. Load scoring template YAML.
      2. If GreyLabs disposition is not-scoreable (WPC, voicemail, etc.) store
         call_type=not_scoreable and return — no LLM call.
      3. Otherwise, call the LLM with the transcript + 19-parameter prompt.
      4. Parse JSON response → OwnLLMScore.

    Returns OwnLLMScore instance, or None if LLM disabled / transcript missing / API error.
    """
    import json as _json
    import re
    from pathlib import Path

    import anthropic
    import yaml

    if not getattr(settings, "OWN_LLM_ENABLED", True):
        return None

    api_key = getattr(settings, "OWN_LLM_API_KEY", "")
    if not api_key:
        logger.warning(
            "OWN_LLM_API_KEY not set — skipping own-LLM scoring for recording %s", recording_id
        )
        return None

    try:
        recording = CallRecording.objects.get(pk=recording_id)
    except CallRecording.DoesNotExist:
        return None

    # Need transcript text
    try:
        transcript_text = recording.transcript.transcript_text or ""
    except Exception:
        logger.info("No transcript for recording %s — skipping own-LLM scoring", recording_id)
        return None

    if not transcript_text.strip():
        return None

    # Load scoring template
    tpl_name = template_name or getattr(settings, "OWN_LLM_SCORING_TEMPLATE", "scoring_template_uvarcl_v2")
    tpl_path = Path(settings.BASE_DIR) / "config" / f"{tpl_name}.yaml"
    try:
        tpl = yaml.safe_load(tpl_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Cannot load scoring template %s: %s", tpl_path, exc)
        return None

    # Check GreyLabs disposition — skip scoring for not-scoreable call types
    not_scoreable_lower = [d.lower() for d in tpl.get("not_scoreable_dispositions", [])]
    provider_score = ProviderScore.objects.filter(recording=recording).first()
    if provider_score and isinstance(provider_score.category_data, dict):
        disposition = str(provider_score.category_data.get("Disposition", "")).lower()
        if any(ns in disposition for ns in not_scoreable_lower):
            llm_score = OwnLLMScore(
                recording=recording,
                score_template_name=tpl.get("template_name", tpl_name),
                score_breakdown={
                    "call_type": "not_scoreable",
                    "disposition": provider_score.category_data.get("Disposition"),
                },
                model_used="classification_only",
            )
            llm_score.save()
            logger.info(
                "Recording %s classified as not_scoreable (disposition=%s)",
                recording_id,
                provider_score.category_data.get("Disposition"),
            )
            newrelic.agent.record_custom_metric("Custom/OwnLLM/NotScoreable", 1)
            return llm_score

    # Build parameter block for system prompt
    params = tpl.get("parameters", [])
    param_lines = []
    for p in params:
        fatal_note = " [FATAL]" if p.get("fatal") else ""
        param_lines.append(
            f"P{p['id']}{fatal_note} — {p['name']} (max {p['max_score']}): {p['prompt']}"
        )
    param_block = "\n".join(param_lines)

    system_prompt = f"""You are an expert call quality auditor for UVARCL, a debt recovery company in India.
Score the call transcript against the UVARCL Collections Call Quality Scorecard v2 (max {tpl['max_total_score']} points).

SCORING RULES:
- Score every parameter strictly based on evidence in the transcript
- For FATAL parameters: if the fatal condition is met, score = 0 AND set fatal_triggered = true
- If there is no evidence for a parameter, assume the minimum applicable score
- The agent and customer may speak in Hindi/English mix — Hindi signals matter
- If the call is a failed connection, voicemail, or wrong party, set call_type = "not_scoreable"

PARAMETERS:
{param_block}

Return ONLY valid JSON — no markdown fences, no explanation — in this exact format:
{{
  "call_type": "productive",
  "fatal_triggered": false,
  "fatal_parameter_id": null,
  "fatal_parameter_name": null,
  "parameters": [
    {{
      "id": 1,
      "name": "Greeting",
      "score": 3,
      "max_score": 3,
      "justification": "one sentence"
    }}
  ],
  "total_score": 45,
  "max_score": 100
}}"""

    model = getattr(settings, "OWN_LLM_MODEL", "claude-haiku-4-5-20251001")
    max_tokens = getattr(settings, "OWN_LLM_MAX_TOKENS", 4096)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": f"TRANSCRIPT:\n\n{transcript_text}"}],
        )
        raw_response = message.content[0].text.strip()
    except Exception as exc:
        logger.error("Anthropic API error for recording %s: %s", recording_id, exc)
        newrelic.agent.record_custom_metric("Custom/OwnLLM/Error", 1)
        return None

    # Parse JSON — strip markdown fences if present
    try:
        result = _json.loads(raw_response)
    except _json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            try:
                result = _json.loads(match.group())
            except _json.JSONDecodeError:
                logger.error(
                    "Cannot parse LLM response for recording %s: %r", recording_id, raw_response[:300]
                )
                return None
        else:
            logger.error(
                "No JSON in LLM response for recording %s: %r", recording_id, raw_response[:300]
            )
            return None

    score_breakdown = {
        "call_type": result.get("call_type", "productive"),
        "fatal_triggered": result.get("fatal_triggered", False),
        "fatal_parameter_id": result.get("fatal_parameter_id"),
        "fatal_parameter_name": result.get("fatal_parameter_name"),
        "parameters": result.get("parameters", []),
    }

    total_score = result.get("total_score")
    max_score = result.get("max_score", tpl["max_total_score"])

    # Any FATAL → total score forced to 0
    if result.get("fatal_triggered"):
        total_score = 0

    llm_score = OwnLLMScore(
        recording=recording,
        score_template_name=tpl.get("template_name", tpl_name),
        total_score=total_score,
        max_score=max_score,
        score_breakdown=score_breakdown,
        model_used=model,
    )
    llm_score.compute_percentage()
    llm_score.save()

    newrelic.agent.record_custom_metric("Custom/OwnLLM/Scored", 1)
    logger.info(
        "OwnLLM scored recording %s: %s/%s (%.1f%%)",
        recording_id,
        total_score,
        max_score,
        float(llm_score.score_percentage or 0),
    )
    return llm_score
```

### 5c — Wire into `process_provider_webhook()`

In `process_provider_webhook()`, after the `compute_fatal_level(recording, score)` line and
**before** `check_provider_compliance(recording, record)`, insert:

```python
    # Score transcript against UVARCL scorecard via own LLM.
    # Must run before check_provider_compliance so the P2 own_llm_score_threshold
    # rule can read the OwnLLMScore result.
    run_own_llm_scoring(recording.pk)
```

---

## Step 6 — `baysys_call_audit/compliance.py`

### 6a — Add `_check_own_llm_score_threshold()` handler

Add this function after `_check_provider_score_threshold()`:

```python
def _check_own_llm_score_threshold(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    """P2 variant: check own-LLM score (OwnLLMScore) instead of GreyLabs score."""
    from .models import OwnLLMScore  # noqa: PLC0415

    params = rule.get("params", {})
    threshold = params.get("threshold", 50)

    score = OwnLLMScore.objects.filter(recording=recording).order_by("-created_at").first()
    if score is None:
        return None

    # Not-scoreable calls (WPC, voicemail) — skip threshold check, not a compliance failure
    breakdown = score.score_breakdown or {}
    if breakdown.get("call_type") == "not_scoreable":
        return None

    value = score.score_percentage
    if value is None:
        return None

    if float(value) < threshold:
        desc = rule.get("description", "Low compliance score").format(
            score=value, threshold=threshold,
        )
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "rbi_coc_violation"),
            severity=rule.get("severity", "high"),
            description=desc,
            evidence=f"own_llm_score_percentage={value}",
        )
    return None
```

### 6b — Register in rule dispatch

In `check_provider_compliance()`, in the `RULE_HANDLERS` dict (or equivalent dispatch),
add `"own_llm_score_threshold": _check_own_llm_score_threshold` alongside the existing
`"provider_score_threshold"` entry.

---

## Step 7 — `config/compliance_rules.yaml`

Change the P2 rule `check_type` from `provider_score_threshold` to `own_llm_score_threshold`:

```yaml
  - id: P2
    name: Low compliance score
    enabled: true
    check_type: own_llm_score_threshold      # was: provider_score_threshold
    severity: high
    flag_type: rbi_coc_violation
    description: "Compliance score {score}% below threshold {threshold}%"
    params:
      threshold: 50
```

After making this change, recompute and update the `content_hash` line using the command
in the file header comment.

---

## Step 8 — Tests

Create `baysys_call_audit/tests/test_own_llm_scoring.py` with tests covering:

1. `run_own_llm_scoring()` returns `None` when `OWN_LLM_ENABLED=False`
2. Returns `None` when recording has no transcript
3. Returns `None` when `OWN_LLM_API_KEY` is empty string
4. Returns a `not_scoreable` `OwnLLMScore` when GreyLabs `category_data` has `Disposition = "Wrong Party Connect"`
5. Successfully parses a valid LLM JSON response into `OwnLLMScore` with correct `total_score`,
   `max_score`, `score_percentage`, and `score_breakdown` (mock `anthropic.Anthropic`)
6. Sets `total_score = 0` when LLM response has `fatal_triggered = true`
7. `_check_own_llm_score_threshold()` returns `None` for a `not_scoreable` OwnLLMScore
8. `_check_own_llm_score_threshold()` returns `None` when `OwnLLMScore.score_percentage >= threshold`
9. `_check_own_llm_score_threshold()` returns a `ComplianceFlag` when score < threshold

**Run test gate before committing:**
```bash
python -m pytest baysys_call_audit/tests/ -x -q
ruff check .
```

---

## Post-completion: Mirror to crm_apis

After all tests pass and commit is made on standalone, copy these three files to
`crm_apis/arc/baysys_call_audit/` and commit on the `call-auditor` branch:

- `baysys_call_audit/services.py`
- `baysys_call_audit/compliance.py`
- `config/compliance_rules.yaml`  → `crm_apis/arc/baysys_call_audit/` (check crm_apis config path)

The scoring template YAML (`config/scoring_template_uvarcl_v2.yaml`) and the new test file
stay in the standalone repo only.

Also add the five new `.env` variables to the production `.env` on the server:
```
OWN_LLM_ENABLED=true
OWN_LLM_API_KEY=<your-anthropic-api-key>
OWN_LLM_MODEL=claude-haiku-4-5-20251001
OWN_LLM_MAX_TOKENS=4096
OWN_LLM_SCORING_TEMPLATE=scoring_template_uvarcl_v2
```
