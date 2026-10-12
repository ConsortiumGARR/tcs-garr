import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.harica_client import DEFAULT_REVOCATION_REASON, HaricaClient


class TestHaricaClientPayloads(unittest.TestCase):
    def setUp(self):
        with patch.object(HaricaClient, "prepare_client"):
            self.client = HaricaClient("user@example.org", "password")
        self.post = MagicMock(return_value=MagicMock(status_code=200))
        self.client._HaricaClient__make_post_request = self.post

    def test_revoke_certificate_default_payload(self):
        self.assertTrue(self.client.revoke_certificate("tx-1"))
        self.post.assert_called_once_with(
            "/api/OrganizationValidatorSSL/RevokeCertificate",
            data={
                "transactionId": "tx-1",
                "name": "4.9.1.1.1.1",
                "notes": "Revoked via harica-cli by user@example.org",
                "message": "",
            },
        )

    def test_revoke_user_certificate_default_payload(self):
        self.assertTrue(self.client.revoke_user_certificate("tx-1"))
        self.post.assert_called_once_with(
            "/api/Certificate/RevokeCertificate",
            data={
                "transactionId": "tx-1",
                "name": "4.9.1.1.1.1",
                "notes": "Revoked via harica-cli by user@example.org",
            },
        )

    def test_revoke_certificate_with_reason(self):
        self.client.revoke_certificate("tx-1", "4.9.1.1.1.17")
        self.assertEqual(self.post.call_args.kwargs["data"]["name"], "4.9.1.1.1.17")

    def test_default_reason_is_unspecified(self):
        self.assertEqual(DEFAULT_REVOCATION_REASON, "4.9.1.1.1.1")

    def test_revoke_acme_certificate_payload(self):
        self.client.revoke_acme_certificate("acme-1", message="replaced")
        self.post.assert_called_once_with(
            "/api/OrganizationAdmin/RevokeAcmeCertificate",
            data={"transactionId": "acme-1", "name": "4.9.1.1.1.1", "message": "replaced"},
        )

    def test_revocation_reasons_endpoints(self):
        self.post.return_value.json.return_value = []
        for scope, endpoint in [
            ("user", "/api/Certificate/GetRevocationReasons"),
            ("ssl", "/api/OrganizationValidatorSSL/GetRevocationReasons"),
            ("admin", "/api/OrganizationAdmin/GetRevocationReasons"),
        ]:
            self.client.get_revocation_reasons(scope)
            self.post.assert_called_with(endpoint)

    def test_create_api_key_returns_plain_code(self):
        self.post.return_value.text = '"abc123"'
        self.assertEqual(self.client.create_api_key("ci"), "abc123")
        self.post.assert_called_once_with("/api/User/CreateAPIKey", data={"id": "ci"})

    def _mock_domain_lookup(self):
        groups = MagicMock(json=MagicMock(return_value=[{"id": "group-1"}]))
        validities = MagicMock(
            json=MagicMock(
                return_value=[
                    {"organizationId": "dom-1", "domain": "example.org"},
                    {"organizationId": "dom-2", "domain": "other.org"},
                ]
            )
        )
        self.post.side_effect = [groups, validities, MagicMock(status_code=200)]

    def test_validate_domains_default_payload(self):
        self._mock_domain_lookup()
        self.client.validate_domains(["example.org"])
        self.post.assert_called_with(
            "/api/OrganizationAdmin/CreatePrevalidatedValidation",
            data={
                "usersEmail": "user@example.org",
                "validationMethodName": "3.2.2.4.7",
                "organizationId": "dom-1",
                "whoisEmail": "",
            },
        )

    def test_validate_domains_email_payload(self):
        self._mock_domain_lookup()
        self.client.validate_domains(["example.org"], method="email", email_user="hostmaster")
        self.post.assert_called_with(
            "/api/OrganizationAdmin/CreatePrevalidatedValidation",
            data={
                "usersEmail": "user@example.org",
                "validationMethodName": "3.2.2.4.4",
                "organizationId": "dom-1",
                "whoisEmail": "hostmaster@example.org",
            },
        )

    def _pages(self, *pages):
        self.post.side_effect = [MagicMock(json=MagicMock(return_value=page)) for page in pages]

    def test_pending_transactions_reads_all_pages(self):
        self._pages([{"transactionId": "a"}, {"transactionId": "b"}], [{"transactionId": "c"}], [])
        transactions = self.client.get_pending_transactions()
        self.assertEqual([t["transactionId"] for t in transactions], ["a", "b", "c"])
        self.assertEqual([c.kwargs["data"]["startIndex"] for c in self.post.call_args_list], [0, 2, 3])
        self.assertEqual(self.post.call_args.kwargs["data"]["status"], "Pending")

    def test_pending_transactions_single_page(self):
        self._pages([{"transactionId": "a"}], [])
        self.assertEqual(len(self.client.get_pending_transactions()), 1)
        self.assertEqual(self.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
