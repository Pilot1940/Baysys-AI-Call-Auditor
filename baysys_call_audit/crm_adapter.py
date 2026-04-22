"""
CRM Adapter — the ONLY file that contains conditional CRM vs mock logic.

All CRM-specific imports are inside functions (not at module level) so that
this file can be imported in dev mode without the CRM codebase present.

AUDIT_AUTH_BACKEND='mock' in dev, 'crm' in production.
"""
from django.conf import settings


def get_auth_backend_name() -> str:
    """Returns 'mock' or 'crm'."""
    return getattr(settings, "AUDIT_AUTH_BACKEND", "mock")


def get_user_portfolio(user_id: int) -> dict:
    """
    Returns {portfolio_id, bank_name, product_type} for this user.
    Mock: returns fixed Axis Bank / Personal Loan.
    """
    if get_auth_backend_name() == "mock":
        return {
            "portfolio_id": "1",
            "bank_name": "Axis Bank",
            "product_type": "Personal Loan",
        }

    from arc.crm.models.user_model import User  # noqa: PLC0415, F401
    # TODO: wire to real CRM allocation query at go-live
    return {
        "portfolio_id": "1",
        "bank_name": "Axis Bank",
        "product_type": "Personal Loan",
    }


def get_team_users(agency_id: int) -> list[dict]:
    """
    Returns list of {user_id, first_name, last_name} for agents in this agency.
    """
    if get_auth_backend_name() == "mock":
        return [
            {"user_id": 1, "first_name": "Test", "last_name": "Agent"},
            {"user_id": 2, "first_name": "Demo", "last_name": "Agent"},
        ]

    from arc.crm.models.user_model import User  # noqa: PLC0415
    return list(
        User.objects
        .filter(agency_id=agency_id, role_id=3, is_active=True)
        .values("user_id", "first_name", "last_name"),
    )


def get_user_agency_id(user_id: int) -> int | None:
    """
    Returns the agency_id for a given user.
    Mock: returns 1 (all dev users are in agency 1).
    """
    if get_auth_backend_name() == "mock":
        return 1

    from arc.crm.models.user_model import User  # noqa: PLC0415
    try:
        return User.objects.get(user_id=user_id).agency_id
    except User.DoesNotExist:
        return None


def get_agency_list() -> list[dict]:
    """
    Returns list of {agency_id, agency_name} for all active agencies.
    """
    if get_auth_backend_name() == "mock":
        return [
            {"agency_id": 1, "agency_name": "BaySys Collections"},
            {"agency_id": 2, "agency_name": "Metro Recovery"},
            {"agency_id": 3, "agency_name": "National ARC"},
        ]

    from arc.crm.models.user_model import User  # noqa: PLC0415
    from arc.crm.models.agency_model import Agency  # noqa: PLC0415

    active_agency_ids = (
        User.objects.filter(is_active=True)
        .values_list("agency_id", flat=True)
        .distinct()
    )
    return list(
        Agency.objects
        .filter(agency_id__in=active_agency_ids)
        .values("agency_id", "agency_name")
        .order_by("agency_name")
    )


def get_signed_url(s3_path: str) -> str:
    """
    Return a fresh pre-signed URL for the given S3 path.
    Mock: returns s3_path unchanged (safe for dev/test).
    Prod: calls arc.s3.service.s3_download() to generate a short-lived signed URL.

    Called immediately before each provider submission — never stored.
    """
    if get_auth_backend_name() == "mock":
        return s3_path

    from arc.s3.service import s3_download  # noqa: PLC0415
    return s3_download(s3_path)


def get_agency_name_map(agency_ids) -> dict[str, str]:
    """
    Map agency_ids -> agency_name. Accepts any iterable of agency_ids.
    Keys in the returned dict are always stringified agency_ids so callers can
    look up regardless of how the ID is stored (CallRecording.agency_id is CharField).

    Mock: returns a fixed fixture covering the dev agency IDs used elsewhere.
    Prod: a single Agency.objects.filter(id__in=...) query.
    Unknown agency_ids are simply absent from the returned map — callers should
    treat a missing key as "name unknown".
    """
    ids = {str(a) for a in agency_ids if a is not None and str(a).strip() != ""}
    if not ids:
        return {}

    if get_auth_backend_name() == "mock":
        mock_map = {
            "1": "BaySys Collections",
            "2": "Metro Recovery",
            "3": "National ARC",
        }
        return {aid: mock_map[aid] for aid in ids if aid in mock_map}

    from arc.crm.models.agency_model import Agency  # noqa: PLC0415
    # Agency ids in CRM are integers; coerce defensively and skip non-numeric.
    numeric_ids: list[int] = []
    for aid in ids:
        try:
            numeric_ids.append(int(aid))
        except (TypeError, ValueError):
            continue
    if not numeric_ids:
        return {}
    return {
        str(row["agency_id"]): row["agency_name"]
        for row in Agency.objects.filter(agency_id__in=numeric_ids).values(
            "agency_id", "agency_name",
        )
    }


def get_user_names(user_ids: list[int]) -> dict[int, str]:
    """
    Map user_ids -> display name ('First Last').
    Mock: returns 'User {id}' for each ID.
    """
    if not user_ids:
        return {}

    if get_auth_backend_name() == "mock":
        return {uid: f"User {uid}" for uid in user_ids}

    from arc.crm.models.user_model import User  # noqa: PLC0415
    return {
        u["user_id"]: f'{u["first_name"]} {u["last_name"]}'.strip()
        for u in User.objects.filter(
            user_id__in=user_ids,
        ).values("user_id", "first_name", "last_name")
    }
