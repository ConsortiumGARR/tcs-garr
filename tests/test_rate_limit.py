import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.exceptions import RateLimitError
from tcs_garr.harica_client import RATE_LIMIT_RETRIES, HaricaClient


def response(status, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return MagicMock(status_code=status, headers=headers, text="")


class TestRateLimit(unittest.TestCase):
    def setUp(self):
        with patch.object(HaricaClient, "prepare_client"):
            self.client = HaricaClient("user@example.org", "password")
        self.client._HaricaClient__get_request_verification_token = MagicMock()
        self.client.session = MagicMock()
        sleep_patcher = patch("tcs_garr.harica_client.time.sleep")
        self.sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def test_retries_after_429_then_succeeds(self):
        self.client.session.post.side_effect = [response(429), response(429), response(200)]
        self.assertEqual(self.client.api_post("/api/Test").status_code, 200)
        self.assertEqual(self.client.session.post.call_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [2, 4])

    def test_honours_retry_after_with_a_cap(self):
        self.client.session.post.side_effect = [response(429, "5"), response(429, "3600"), response(200)]
        self.client.api_post("/api/Test")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [5, 60])

    def test_raises_when_rate_limit_persists(self):
        self.client.session.post.return_value = response(429)
        with self.assertRaises(RateLimitError):
            self.client.api_post("/api/Test")
        self.assertEqual(self.client.session.post.call_count, RATE_LIMIT_RETRIES + 1)

    def test_no_retry_on_other_errors(self):
        self.client.session.post.return_value = response(500)
        self.assertEqual(self.client.api_post("/api/Test").status_code, 500)
        self.assertEqual(self.client.session.post.call_count, 1)
        self.sleep.assert_not_called()

    def test_acme_lookup_does_not_skip_rate_limited_accounts(self):
        self.client.session.post.return_value = response(429)
        with patch.object(self.client, "list_acme_accounts", return_value=[{"id": "acc", "userEmail": "u"}]):
            with self.assertRaises(RateLimitError):
                self.client.list_acme_certificates()

    def test_get_certificate_does_not_report_not_found_on_rate_limit(self):
        self.client.session.post.return_value = response(429)
        with patch.object(self.client, "list_certificates", return_value=[]):
            with self.assertRaises(RateLimitError):
                self.client.get_certificate("tx-1")


if __name__ == "__main__":
    unittest.main()
