"""
Dev mode  (AUDIT_USE_MOCK_AUTH=True):  MockCrmAuth — no JWT needed.
Prod mode (AUDIT_USE_MOCK_AUTH=False): CrmJWTAuthentication from CRM.

Role IDs (same as Trainer):
  1 = Admin (cross-agency)
  2 = Manager/TL (agency-scoped)
  3 = Agent (own only)
  4 = Supervisor (cross-agency)
  5 = Agency Admin (agency-scoped)
"""
from django.conf import settings
from rest_framework.authentication import BaseAuthentication


class MockUser:
    is_authenticated = True

    def __init__(self, user_id=1, role_id=2, agency_id=1,
                 phone_number="+9190000000", first_name="BaySys.AI",
                 last_name="Test User", email="connect@baysys.ai"):
        self.user_id = user_id
        self.role_id = role_id
        self.agency_id = agency_id
        self.phone_number = phone_number
        self.first_name = first_name
        self.last_name = last_name
        self.email = email


class MockCrmAuth(BaseAuthentication):
    """
    Returns a fixed test user by default (user_id=1, role_id=2).
    Tests can override by setting req.user = MockUser(...) before the view call.
    """
    def authenticate(self, request):
        underlying = getattr(request, "_request", request)
        existing = getattr(underlying, "user", None)
        if isinstance(existing, MockUser):
            return (existing, None)
        return (MockUser(), None)


def get_auth_backend():
    """Use in views as: authentication_classes = [get_auth_backend()]"""
    if getattr(settings, "AUDIT_USE_MOCK_AUTH", True):
        return MockCrmAuth
    from arc.crm.common.authentication import CrmJWTAuthentication  # noqa: PLC0415
    return CrmJWTAuthentication


class AuditPermissionMixin:
    MANAGER_ROLES = {1, 2, 4, 5}
    AGENT_ROLES = {3}
    CROSS_AGENCY_ROLES = {1, 4}
    AGENCY_SCOPED_ROLES = {2, 5}

    def get_user_role(self, request):
        return getattr(request.user, "role_id", None)

    def is_manager_or_admin(self, request):
        return self.get_user_role(request) in self.MANAGER_ROLES

    def get_agency_filter(self, request):
        if self.get_user_role(request) in self.CROSS_AGENCY_ROLES:
            return {}
        return {"agency_id": getattr(request.user, "agency_id", None)}

    def get_user_filter(self, request):
        """For agent-role users: filter to own records only."""
        if self.get_user_role(request) in self.AGENT_ROLES:
            return {"agent_id": str(getattr(request.user, "user_id", None))}
        return self.get_agency_filter(request)
