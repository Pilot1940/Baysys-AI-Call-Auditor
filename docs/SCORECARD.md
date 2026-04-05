# UVARCL Collections Call Quality Scorecard v2

> **Canonical scoring rubric for all Call Auditor systems.**
> Used by: GreyLabs configuration, own-LLM scoring (OwnLLMScore), hackathon evaluation, manual QA.
> Source: `Documentation/UVARCL_Scorecard_v2-sent by baysys.xlsx`

## Overview

- **19 parameters** across 5 groups
- **Maximum score: 100 points** (weighted by group)
- **7 FATAL parameters** — any single FATAL = automatic fail, regardless of total score
- **Score bands:** ≥85 Excellent | 70–84 Good | 55–69 Needs Improvement | <55 Critical
- **Documentation group removed** from scoring per updated weightage; tracked separately via CRM audit

## Group Weights

| Group | Weight | Parameters | Focus |
|---|---|---|---|
| Introduction Quality | 20% | 1–5 | Greeting, self-ID, bank context, ARC identity, RPV |
| Call Quality | 45% | 6–12 | Fluency, no abuse, objection handling, de-escalation, PTP, closing, regulatory |
| Compliance & RBI | 25% | 13–16 | Calling hours, TCP, misrepresentation, non-payment consequences |
| Scam & Trust Handling | 10% | 17–19 | No OTP/PIN requests, no personal detail sharing, dispute channel |

---

## Full Parameter Table

### Group 1: Introduction Quality (20%)

| # | Parameter | Max | Type | FATAL | Audit Prompt |
|---|---|---|---|---|---|
| 1 | **Greeting** | 3 | O | No | Did the call open with a greeting (e.g. Good morning/afternoon/evening/namaste)? 3=Yes, 0=No |
| 2 | **Self-introduction (Name)** | 3 | O | No | Agent states name. 3=Stated name, 0=Not stated |
| 3 | **Bank / Original Lender context disclosed** | 3 | O | No | Original bank/NBFC name mentioned? 3=Yes, 0=No |
| 4 | **UVARCL takeover / ARC identity disclosed** | 6 | O | No | UVARCL identified as current debt owner? 6=Clear, 3=Partial, 0=Not mentioned |
| 5 | **Right Party Verification (RPV)** | 5 | O | **FATAL** | FATAL if debt discussed without RPV. 5=RPV done, 0=FATAL |

### Group 2: Call Quality (45%)

| # | Parameter | Max | Type | FATAL | Audit Prompt |
|---|---|---|---|---|---|
| 6 | **No fumble / fluent delivery** | 5 | S | No | Auditor assesses fluency & confidence. 5=Excellent, 3=Minor issues, 0=Significant fumble |
| 7 | **No harsh / threatening / abusive language** | 10 | O | **FATAL** | FATAL. Any threat or abuse = auto-fail entire scorecard. 10=None, 0=FATAL |
| 8 | **Objection handling / answered questions** | 8 | O | No | Did agent address customer doubts satisfactorily? 8=All answered, 4=>50% answered, 0=<50% answered |
| 9 | **Customer satisfied / de-escalated** | 5 | O | No | See de-escalation signal taxonomy below |
| 10 | **Moved forward — PTP / next step secured** | 10 | O | No | Promise-to-Pay or clear next action agreed? 10=PTP secured, 5=Next step, 0=No movement |
| 11 | **Closing remark and summary** | 4 | O | No | Check for thank-you and agent recap. 4=Both done, 2=One done, 0=Neither |
| 12 | **Regulatory concern** | 3 | S | No | If raised by customer — was it handled correctly? 3=Handled/N/A, 1=Partial, 0=Ignored |

### Group 3: Compliance & RBI (25%)

| # | Parameter | Max | Type | FATAL | Audit Prompt |
|---|---|---|---|---|---|
| 13 | **Calling within permitted hours (8am–7pm IST)** | 8 | O | **FATAL** | FATAL if call placed outside 08:00–19:00 IST. 8=Within window, 0=FATAL |
| 14 | **Non-disclosure to third parties (TCP)** | 5 | O | **FATAL** | FATAL if loan details shared without customer consent. 5=Maintained, 0=FATAL |
| 15 | **Misrepresentation** | 5 | O | **FATAL** | Agent should clearly mention UVARCL, not misrepresent as original lender. 5=UVARCL mentioned, 3=Nothing mentioned, 0=Misrepresentation |
| 16 | **Non-payment consequences communicated** | 7 | O | No | Legal/credit-bureau consequences explained? 7=Clearly, 3=Vague, 0=Not mentioned |

### Group 4: Scam & Trust Handling (10%)

| # | Parameter | Max | Type | FATAL | Audit Prompt |
|---|---|---|---|---|---|
| 17 | **Confirmed NO OTP / PIN requested** | 4 | O | **FATAL** | FATAL if agent requests OTP, CVV, password. 4=Not requested, 0=FATAL |
| 18 | **Shared Personal Details for Payment** | 4 | O | **FATAL** | FATAL if agent shared their personal number / UPI ID to collect payment. 4=Not shared, 0=Shared |
| 19 | **Verification / dispute channel offered** | 2 | O | No | Official dispute/verification process mentioned? 2=Yes, 0=No |

---

## FATAL Parameters Summary

| FATAL # | Parameter | Group | What triggers it |
|---|---|---|---|
| F1 | Right Party Verification (RPV) | Introduction | Debt discussed without verifying identity |
| F2 | Harsh / threatening / abusive language | Call Quality | Any threat, abuse, or abusive language by agent |
| F3 | Calling outside permitted hours | Compliance | Call placed outside 08:00–19:00 IST |
| F4 | Non-disclosure to third parties (TCP) | Compliance | Loan details shared with unverified third party |
| F5 | Misrepresentation | Compliance | Agent claims to be from original lender, not UVARCL |
| F6 | OTP / PIN / CVV requested | Scam & Trust | Agent asks for OTP, CVV, password, or PIN |
| F7 | Agent shared personal payment details | Scam & Trust | Agent gives own phone number or UPI ID for payment |

---

## De-escalation Signal Taxonomy (Parameter 9)

### Score 5 — De-escalated / Satisfied
Customer uses agreement, commitment, or calm closure language.

**Commitment signals:** "okay I will pay", "theek hai karunga", "mujhe check karna hai", "I'll arrange it", "by this date I will", "kal tak kar deta hoon", "let me talk to my family", "send me the account details", "give me the UPI number", "kitna outstanding hai batao"

**Acceptance signals:** "understood", "samajh gaya", "fine", "alright", "noted", "okay okay", "haan theek hai", "I know I know", "I'll see what I can do", "chalega"

**Positive closing:** "thank you", "shukriya", "okay bhai", "acha", "theek hai band karo", "I'll call back", "you've been helpful"

### Score 2 — Neutral
Customer is neither hostile nor cooperative. Call ends without escalation but also without commitment.

**Deflection / delay:** "I'll think about it", "not right now", "baad mein dekhta hoon", "abhi nahi", "call me later", "busy hoon", "mujhe time chahiye", "will let you know", "pata nahi", "dekh lete hain"

**Passive non-engagement:** Long silences but no aggression, "hmm", "haan haan" without commitment, "okay" with flat tone, call ends with customer going quiet

### Score 0 — Escalated
Customer is angrier, more hostile, or more distressed at end than at start.

**Threat / aggression:** "main complaint karunga", "RBI mein jaaunga", "consumer court", "lawyer bhejunga", "media ko bata dunga", "ye sab illegal hai", "harassment hai ye", "band karo nahi to", "police bulaunga"

**Abuse / hostility:** Any abusive language, raised tone throughout, "mat karo call dobara", "number block kar raha hoon", "bakwaas band karo"

**Distress signals (handle carefully):** "kuch nahi kar sakta", "ghar bikna padega", "bahut takleef hai", "rona aa raha hai", "bohot bura ho gaya hai"

---

## Scoring Type Legend

- **O** = Objective — deterministic from transcript content (binary or rules-based)
- **S** = Subjective — requires auditor/LLM judgement (fluency, regulatory handling)

---

## RBI COC Compliance (outside scorecard)

The following RBI Code of Conduct requirements are enforced at the **system level** (metadata compliance checks in `compliance.py`) and are not part of the per-call scorecard:

- **Calling hours:** 08:00–19:00 IST (also FATAL in scorecard param 13 — double-enforced)
- **Max calls per customer per day:** configurable via `config/compliance_rules.yaml`
- **Min gap between calls to same customer:** configurable
- **Call duration thresholds:** configurable

These are checked at ingestion time and flagged before any scoring occurs. A call that violates calling hours is both a metadata compliance failure AND a scorecard FATAL.

---

## Usage

### With GreyLabs
GreyLabs configures their speech analytics platform against this scorecard. Their `template_id` maps to these 19 parameters. Results are stored in `ScoredRecording` via the provider webhook.

### With own-LLM scoring (OwnLLMScore)
When scoring via our own LLM (Claude Sonnet / GPT-4o-mini), the audit prompts in this document become the basis for the LLM system prompt. Each parameter's audit prompt is a ready-made instruction. The de-escalation signal taxonomy for parameter 9 is designed to be copy-pasted into an LLM prompt.

### For hackathon evaluation
The hackathon document (`Documentation/baysys-call-auditor-vendor-eval-v7.html`) references this scorecard directly. All combos are evaluated against these 19 parameters.

---

*Last updated: 2 April 2026. Source: UVARCL_Scorecard_v2-sent by baysys.xlsx*
