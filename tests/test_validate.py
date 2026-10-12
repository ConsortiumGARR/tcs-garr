import argparse
import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.commands.validate import ValidateCommand
from tcs_garr.harica_client import HaricaClient


def client():
    with patch.object(HaricaClient, "prepare_client"):
        return HaricaClient("user@example.org", "password")


class TestValidateDomains(unittest.TestCase):
    def setUp(self):
        self.client = client()
        groups = MagicMock(json=MagicMock(return_value=[{"id": "group-1"}]))
        validities = MagicMock(
            json=MagicMock(
                return_value=[
                    {"organizationId": "dom-1", "domain": "example.org"},
                    {"organizationId": "dom-2", "domain": "Other.org"},
                ]
            )
        )
        self.post = MagicMock(side_effect=[groups, validities, MagicMock(status_code=200), MagicMock(status_code=500)])
        self.client._HaricaClient__make_post_request = self.post

    def test_results_per_domain(self):
        results = self.client.validate_domains(["example.org", "other.org", "unknown.org"])
        self.assertEqual(results, {"example.org": True, "other.org": False, "unknown.org": None})

    def _run_command(self, domains, results):
        args = argparse.Namespace(domains=domains, method="dns", email_user="admin")
        command = ValidateCommand(args, None)
        command._harica_client = MagicMock(token="jwt", validate_domains=MagicMock(return_value=results))
        return command

    def test_command_strips_and_lowercases_domains(self):
        command = self._run_command(" Example.org, ,other.org ", {"example.org": True, "other.org": True})
        command.execute()
        command._harica_client.validate_domains.assert_called_once_with(
            ["example.org", "other.org"], method="dns", email_user="admin"
        )

    def test_command_fails_on_unknown_domain(self):
        command = self._run_command("example.org,unknown.org", {"example.org": True, "unknown.org": None})
        with self.assertLogs(level="ERROR") as cm, self.assertRaises(SystemExit):
            command.execute()
        self.assertIn("unknown.org is not a domain of your organization", cm.output[0])


if __name__ == "__main__":
    unittest.main()
