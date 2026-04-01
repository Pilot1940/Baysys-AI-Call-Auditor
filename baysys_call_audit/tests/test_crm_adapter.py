"""Tests for crm_adapter.py — mock backend only."""
from django.test import TestCase, override_settings

from baysys_call_audit.crm_adapter import (
    get_agency_list,
    get_auth_backend_name,
    get_team_users,
    get_user_agency_id,
    get_user_names,
    get_user_portfolio,
)


@override_settings(AUDIT_AUTH_BACKEND="mock")
class CrmAdapterMockTests(TestCase):
    def test_get_auth_backend_name(self):
        self.assertEqual(get_auth_backend_name(), "mock")

    def test_get_user_portfolio(self):
        result = get_user_portfolio(1)
        self.assertIn("portfolio_id", result)
        self.assertIn("bank_name", result)
        self.assertIn("product_type", result)

    def test_get_team_users(self):
        users = get_team_users(1)
        self.assertTrue(len(users) >= 1)
        self.assertIn("user_id", users[0])
        self.assertIn("first_name", users[0])

    def test_get_user_agency_id(self):
        self.assertEqual(get_user_agency_id(1), 1)

    def test_get_agency_list(self):
        agencies = get_agency_list()
        self.assertTrue(len(agencies) >= 1)
        self.assertIn("agency_id", agencies[0])
        self.assertIn("agency_name", agencies[0])

    def test_get_user_names(self):
        names = get_user_names([1, 2, 3])
        self.assertIn(1, names)
        self.assertEqual(names[1], "User 1")

    def test_get_user_names_empty(self):
        names = get_user_names([])
        self.assertEqual(names, {})
