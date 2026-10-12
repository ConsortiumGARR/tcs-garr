import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.exceptions import ErrorPageError, RateLimitError
from tcs_garr.harica_client import RATE_LIMIT_RETRIES, HaricaClient


def response(status, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return MagicMock(status_code=status, headers=headers, text="", history=[])


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


class TestRequestVerificationToken(unittest.TestCase):
    def setUp(self):
        with patch.object(HaricaClient, "prepare_client"):
            self.client = HaricaClient("user@example.org", "password")
        self.client.session = MagicMock()
        self.client.session.post.return_value = response(200)
        self.fetch = MagicMock(side_effect=lambda: setattr(self.client, "request_verification_token", "csrf"))
        self.client._HaricaClient__get_request_verification_token = self.fetch

    def test_token_is_fetched_once_per_session(self):
        for _ in range(3):
            self.client.api_post("/api/Test")
        self.fetch.assert_called_once()

    def test_token_is_fetched_again_after_login(self):
        self.client.session.post.return_value = MagicMock(status_code=200, text="jwt", history=[])
        with patch.object(
            self.client, "get_logged_in_user_profile", return_value={"role": "User", "fullName": "", "organization": ""}
        ):
            self.client.login()
        self.assertIsNone(self.client.request_verification_token)
        self.client.api_post("/api/Test")
        self.assertEqual(self.fetch.call_count, 2)

    def _error_page(self):
        return MagicMock(status_code=200, history=[MagicMock(status_code=302)], url="https://cm.harica.gr/Error")

    def test_read_redirected_to_error_retries_with_new_token(self):
        self.client.request_verification_token = "stale"
        self.client.session.post.side_effect = [self._error_page(), response(200)]
        self.assertEqual(self.client.api_post("/api/User/GetCurrentUser").status_code, 200)
        self.fetch.assert_called_once()
        self.assertEqual(self.client.session.post.call_count, 2)

    def test_write_redirected_to_error_is_not_sent_again(self):
        self.client.request_verification_token = "stale"
        self.client.session.post.return_value = self._error_page()
        with self.assertRaises(ErrorPageError):
            self.client.api_post("/api/OrganizationValidatorSSL/RevokeCertificate")
        self.assertEqual(self.client.session.post.call_count, 1)
        self.assertIsNone(self.client.request_verification_token)

    def test_error_page_with_fresh_token_is_not_retried(self):
        self.client.session.post.return_value = self._error_page()
        with self.assertRaises(ErrorPageError):
            self.client.api_post("/api/User/GetCurrentUser")
        self.assertEqual(self.client.session.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
