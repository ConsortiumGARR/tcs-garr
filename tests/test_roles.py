import itertools
import unittest
from unittest.mock import patch

from tcs_garr.harica_client import HaricaClient
from tcs_garr.utils import UserRole


def client():
    with patch.object(HaricaClient, "prepare_client"):
        return HaricaClient("user@example.org", "password")


class TestUsesUserEndpoints(unittest.TestCase):
    def test_same_result_as_the_previous_rule(self):
        known = [
            UserRole.USER,
            UserRole.ENTERPRISE_ADMIN,
            UserRole.SMIME_ENTERPRISE_APPROVER,
            UserRole.SSL_ENTERPRISE_APPROVER,
        ]
        c = client()
        for n in range(len(known) + 1):
            for combo in itertools.combinations(known, n):
                # Before CLIENT_AUTH_SMIME_ENTERPRISE_APPROVER existed, that role never reached self.roles
                previous = UserRole.USER in combo and len(combo) == 1
                for extra in ([], [UserRole.CLIENT_AUTH_SMIME_ENTERPRISE_APPROVER]):
                    c.roles = set(combo) | set(extra)
                    self.assertEqual(c.uses_user_endpoints(), previous, c.roles)


if __name__ == "__main__":
    unittest.main()
