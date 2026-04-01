"""
Config-driven compliance engine + fatal level computation.

Two rule categories:
  - Metadata rules — checked at ingestion time using CallRecording fields only.
  - Provider rules — checked after webhook, using provider-returned variables only.

Rule definitions live in config/compliance_rules.yaml.
Fatal level weights live in config/fatal_level_rules.yaml.

Public API:
  - check_metadata_compliance(recording)     -> list[ComplianceFlag]
  - check_provider_compliance(recording, payload) -> list[ComplianceFlag]
  - compute_fatal_level(recording, provider_score) -> int
  - load_compliance_rules()                  -> dict
  - load_fatal_level_rules()                 -> dict
  - load_gazette_holidays(holidays_file)     -> set[date]
"""
import hashlib
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings

from .models import CallRecording, ComplianceFlag

logger = logging.getLogger(__name__)

_BASE_DIR = Path(settings.BASE_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Config loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_compliance_rules() -> dict:
    """Load and return config/compliance_rules.yaml. Returns empty dict on error."""
    path = _BASE_DIR / "config" / "compliance_rules.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logger.warning("Compliance rules file not found: %s", path)
        return {}
    except yaml.YAMLError as exc:
        logger.warning("Malformed compliance rules YAML: %s", exc)
        return {}


def load_fatal_level_rules() -> dict:
    """Load config/fatal_level_rules.yaml, verify content hash. Returns empty dict on error."""
    path = _BASE_DIR / "config" / "fatal_level_rules.yaml"
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return {}
    except FileNotFoundError:
        logger.warning("Fatal level rules file not found: %s", path)
        return {}
    except yaml.YAMLError as exc:
        logger.warning("Malformed fatal level rules YAML: %s", exc)
        return {}

    # Verify content hash
    stored_hash = data.get("content_hash", "")
    if stored_hash:
        computed = compute_content_hash(raw)
        if computed != stored_hash:
            logger.warning(
                "fatal_level_rules.yaml content hash mismatch — "
                "file may have been modified outside version control"
            )

    return data


def compute_content_hash(raw_yaml: str) -> str:
    """Compute SHA-256 of YAML content excluding the content_hash line."""
    lines = raw_yaml.splitlines(keepends=True)
    filtered = [line for line in lines if not line.strip().startswith("content_hash:")]
    return hashlib.sha256("".join(filtered).encode("utf-8")).hexdigest()


@lru_cache(maxsize=4)
def load_gazette_holidays(holidays_file: str) -> frozenset[date]:
    """
    Load holiday dates from text file. One date per line, YYYY-MM-DD.
    Lines starting with # are comments. Returns frozenset for cacheability.
    """
    path = _BASE_DIR / holidays_file
    holidays = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                try:
                    holidays.add(date.fromisoformat(stripped))
                except ValueError:
                    logger.warning("Skipping malformed holiday date: %s", stripped)
    except FileNotFoundError:
        logger.warning("Gazette holidays file not found: %s", path)
    return frozenset(holidays)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata compliance (runs at ingestion time)
# ─────────────────────────────────────────────────────────────────────────────

def check_metadata_compliance(recording: CallRecording) -> list[ComplianceFlag]:
    """Run all enabled metadata rules against a recording."""
    rules_data = load_compliance_rules()
    metadata_rules = rules_data.get("metadata_rules", [])
    flags = []

    for rule in metadata_rules:
        if not rule.get("enabled", True):
            continue
        check_type = rule.get("check_type")
        handler = _METADATA_HANDLERS.get(check_type)
        if handler is None:
            logger.warning("Unknown metadata check_type: %s (rule %s)", check_type, rule.get("id"))
            continue
        flag = handler(recording, rule)
        if flag:
            flags.append(flag)

    return flags


def _check_call_window(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    params = rule.get("params", {})
    start_hour = getattr(settings, "COMPLIANCE_CALL_WINDOW_START_HOUR", params.get("start_hour", 8))
    end_hour = getattr(settings, "COMPLIANCE_CALL_WINDOW_END_HOUR", params.get("end_hour", 20))

    call_hour = recording.recording_datetime.hour
    if call_hour < start_hour or call_hour >= end_hour:
        desc = rule.get("description", "Call outside permitted hours").format(
            start_hour=start_hour, end_hour=end_hour,
        )
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "outside_hours"),
            severity=rule.get("severity", "critical"),
            description=desc,
            evidence=recording.recording_datetime.isoformat(),
        )
    return None


def _check_blocked_weekday(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    params = rule.get("params", {})
    blocked_day = params.get("weekday", 6)
    if recording.recording_datetime.weekday() == blocked_day:
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "rbi_coc_violation"),
            severity=rule.get("severity", "high"),
            description=rule.get("description", "Call on blocked weekday"),
            evidence=recording.recording_datetime.isoformat(),
        )
    return None


def _check_gazette_holiday(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    params = rule.get("params", {})
    holidays_file = params.get("holidays_file", "")
    if not holidays_file:
        return None
    holidays = load_gazette_holidays(holidays_file)
    call_date = recording.recording_datetime.date()
    if call_date in holidays:
        desc = rule.get("description", "Call on gazette holiday").format(
            holiday_date=call_date.isoformat(),
        )
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "rbi_coc_violation"),
            severity=rule.get("severity", "high"),
            description=desc,
            evidence=call_date.isoformat(),
        )
    return None


def _check_max_calls_per_customer(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    if not recording.customer_id:
        return None
    params = rule.get("params", {})
    max_calls = getattr(
        settings, "COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY",
        params.get("max_calls", 3),
    )
    call_date = recording.recording_datetime.date()
    call_count = CallRecording.objects.filter(
        customer_id=recording.customer_id,
        recording_datetime__date=call_date,
    ).count()
    if call_count > max_calls:
        desc = rule.get("description", "Excessive calls to customer").format(
            customer_id=recording.customer_id,
            call_count=call_count,
            date=call_date.isoformat(),
            max_calls=max_calls,
        )
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "rbi_coc_violation"),
            severity=rule.get("severity", "medium"),
            description=desc,
            evidence=f"count={call_count}, limit={max_calls}",
        )
    return None


_METADATA_HANDLERS = {
    "call_window": _check_call_window,
    "blocked_weekday": _check_blocked_weekday,
    "gazette_holiday": _check_gazette_holiday,
    "max_calls_per_customer": _check_max_calls_per_customer,
}


# ─────────────────────────────────────────────────────────────────────────────
# Provider compliance (runs after webhook processing)
# ─────────────────────────────────────────────────────────────────────────────

def check_provider_compliance(recording: CallRecording, payload: dict) -> list[ComplianceFlag]:
    """Run all enabled provider rules. Called after webhook processing."""
    rules_data = load_compliance_rules()
    provider_rules = rules_data.get("provider_rules", [])
    flags = []

    # Also check restricted keywords from payload (carried over from old engine)
    restricted = payload.get("restricted_keywords", [])
    if payload.get("detected_restricted_keyword") or restricted:
        flag = ComplianceFlag.objects.create(
            recording=recording,
            flag_type="restricted_keyword",
            severity="high",
            description=f"Restricted keywords detected: {', '.join(restricted)}",
            evidence=str(restricted),
        )
        flags.append(flag)

    for rule in provider_rules:
        if not rule.get("enabled", True):
            continue
        check_type = rule.get("check_type")
        handler = _PROVIDER_HANDLERS.get(check_type)
        if handler is None:
            logger.warning("Unknown provider check_type: %s (rule %s)", check_type, rule.get("id"))
            continue
        flag = handler(recording, rule)
        if flag:
            flags.append(flag)

    return flags


def _check_fatal_level_threshold(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    if recording.fatal_level == 0:
        return None
    params = rule.get("params", {})
    threshold = getattr(settings, "COMPLIANCE_FATAL_THRESHOLD", params.get("threshold", 3))
    if recording.fatal_level >= threshold:
        desc = rule.get("description", "Fatal level exceeds threshold").format(
            fatal_level=recording.fatal_level, threshold=threshold,
        )
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "rbi_coc_violation"),
            severity=rule.get("severity", "critical"),
            description=desc,
            evidence=f"fatal_level={recording.fatal_level}",
        )
    return None


def _check_provider_score_threshold(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    from .models import ProviderScore  # noqa: PLC0415

    params = rule.get("params", {})
    score_field = params.get("score_field", "score_percentage")
    threshold = params.get("threshold", 50)

    score = ProviderScore.objects.filter(recording=recording).first()
    if score is None:
        return None

    value = getattr(score, score_field, None)
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
            evidence=f"{score_field}={value}",
        )
    return None


def _check_provider_transcript_field(recording: CallRecording, rule: dict) -> ComplianceFlag | None:
    from .models import CallTranscript  # noqa: PLC0415

    params = rule.get("params", {})
    field_name = params.get("field", "")
    flagged_values = [v.lower() for v in params.get("flagged_values", [])]

    try:
        transcript = CallTranscript.objects.get(recording=recording)
    except CallTranscript.DoesNotExist:
        return None

    value = getattr(transcript, field_name, None)
    if value is None:
        return None

    if str(value).lower() in flagged_values:
        desc = rule.get("description", "Flagged transcript field").format(value=value)
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type=rule.get("flag_type", "other"),
            severity=rule.get("severity", "medium"),
            description=desc,
            evidence=f"{field_name}={value}",
        )
    return None


_PROVIDER_HANDLERS = {
    "fatal_level_threshold": _check_fatal_level_threshold,
    "provider_score_threshold": _check_provider_score_threshold,
    "provider_transcript_field": _check_provider_transcript_field,
}


# ─────────────────────────────────────────────────────────────────────────────
# Fatal level computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_fatal_level(recording: CallRecording, provider_score) -> int:
    """
    Compute fatal_level from provider boolean scores using config/fatal_level_rules.yaml.

    For each parameter in the config:
      - Look up the parameter name in provider_score.category_data (JSON dict)
      - If invert=true: triggered when value == 1
      - If invert=false: triggered when value == 0
      - If parameter not found: skip
    Sum triggered weights, cap at 5. Store on recording.fatal_level.
    """
    if provider_score is None:
        return 0

    rules = load_fatal_level_rules()
    parameters = rules.get("parameters", [])
    if not parameters:
        return 0

    category_data = provider_score.category_data
    if not isinstance(category_data, dict):
        return 0

    total_weight = 0
    for param in parameters:
        name = param.get("name")
        if name is None:
            continue
        if name not in category_data:
            logger.debug("Fatal level parameter '%s' not in category_data, skipping", name)
            continue

        value = category_data[name]
        invert = param.get("invert", False)
        weight = param.get("weight", 0)

        # Triggered: invert=true triggers on 1, invert=false triggers on 0
        triggered = (invert and value == 1) or (not invert and value == 0)
        if triggered:
            total_weight += weight

    fatal_level = min(total_weight, 5)
    recording.fatal_level = fatal_level
    recording.save(update_fields=["fatal_level"])
    return fatal_level
