import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.harica_client import HaricaClient


def page(items, text="x"):
    return MagicMock(status_code=200, text=text, json=MagicMock(return_value=items))


class TestEnterpriseValidatorPayloads(unittest.TestCase):
    def setUp(self):
        with patch.object(HaricaClient, "prepare_client"):
            self.client = HaricaClient("user@example.org", "password")
        self.post = MagicMock(return_value=MagicMock(status_code=200))
        self.client._HaricaClient__make_post_request = self.post

    def test_smime_requests_payload_and_pagination(self):
        self.post.side_effect = [page([{"transactionId": "a"}]), page([])]
        requests = self.client.list_enterprise_requests("smime", "Canceled")
        self.assertEqual(requests, [{"transactionId": "a"}])
        self.post.assert_any_call(
            "/api/OrganizationValidatorSmime/GetEnterpriseTransactions",
            data={"startIndex": 0, "status": "Canceled", "filterPostDTOs": []},
        )

    def test_requests_empty_body_is_an_empty_list(self):
        self.post.return_value = page(None, text="")
        self.assertEqual(self.client.list_enterprise_requests("smime", "Cancelled"), [])

    def test_repeated_page_stops_pagination(self):
        self.post.return_value = page([{"transactionId": "a"}])
        self.assertEqual(len(self.client.list_enterprise_requests("smime")), 1)
        self.assertEqual(self.post.call_count, 2)

    def test_clientauth_certificates_payload(self):
        self.post.side_effect = [page([])]
        self.client.list_enterprise_certificates("clientauth", "Revoked")
        endpoint = self.post.call_args.args[0]
        data = self.post.call_args.kwargs["data"]
        self.assertEqual(
            endpoint, "/api/OrganizationValidatorClientAuthentication/GetEnterpriseClientAuthenticationCertificates"
        )
        self.assertEqual(data["selectedList"], "Revoked")
        self.assertEqual(data["dateFrom"], "1970-01-01T00:00:00.000Z")
        self.assertNotIn("status", data)

    def test_smime_certificates_payload(self):
        self.post.side_effect = [page([])]
        self.client.list_enterprise_certificates("smime", "Expired")
        self.assertEqual(self.post.call_args.kwargs["data"], {"startIndex": 0, "filterPostDTOs": [], "status": "Expired"})

    def test_approve_submits_only_open_reviews(self):
        pending = [
            {
                "transactionId": "tx-1",
                "reviewGetDTOs": [
                    {"reviewId": "r1", "reviewValue": "v1", "isReviewed": False},
                    {"reviewId": "r2", "reviewValue": "v2", "isReviewed": True},
                ],
            }
        ]
        with patch.object(self.client, "list_enterprise_requests", return_value=pending):
            self.assertTrue(self.client.approve_enterprise_request("clientauth", "tx-1"))
        self.post.assert_called_once_with(
            "/api/OrganizationValidatorClientAuthentication/UpdateEnterpriseReview",
            data={
                "reviewId": (None, "r1"),
                "isValid": (None, "true"),
                "informApplicant": (None, "true"),
                "reviewMessage": (None, "Approved via harica-cli by user@example.org"),
                "reviewValue": (None, "v1"),
            },
            content_type="multipart/form-data",
        )

    def test_approve_without_reviews_fails(self):
        with patch.object(
            self.client, "list_enterprise_requests", return_value=[{"transactionId": "tx-1", "reviewGetDTOs": []}]
        ):
            self.assertFalse(self.client.approve_enterprise_request("smime", "tx-1"))
        self.post.assert_not_called()

    def test_cancel_payload(self):
        self.client.cancel_enterprise_request("smime", "tx-1", "duplicate", True)
        self.post.assert_called_once_with(
            "/api/OrganizationValidatorSmime/CancelTransaction",
            data={
                "transactionId": "tx-1",
                "notes": "Cancelled via harica-cli by user@example.org",
                "statusMessage": "duplicate",
                "informApplicant": True,
            },
        )

    def test_revoke_payload(self):
        self.client.revoke_enterprise_certificate("clientauth", "tx-1", "4.9.1.1.1.3", "key leaked")
        self.post.assert_called_once_with(
            "/api/OrganizationValidatorClientAuthentication/RevokeEnterpriseClientCertificate",
            data={
                "transactionId": "tx-1",
                "name": "4.9.1.1.1.3",
                "notes": "Revoked via harica-cli by user@example.org",
                "message": "key leaked",
            },
        )


if __name__ == "__main__":
    unittest.main()
