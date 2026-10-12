import argparse
import unittest
from unittest.mock import MagicMock, patch

from tcs_garr.commands.list_certificates import ListCertificatesCommand
from tcs_garr.harica_client import HaricaClient
from tcs_garr.utils import CertificateStatus


class TestFullInfo(unittest.TestCase):
    def setUp(self):
        with patch.object(HaricaClient, "prepare_client"):
            self.client = HaricaClient("user@example.org", "password")
        self.client.full_name = "User"
        # GetSSLCertificate of a revoked certificate
        self.info = {"transactionId": None, "isRevoked": False, "serial": "01"}

    def _post(self, entries):
        responses = [MagicMock(json=MagicMock(return_value=entries))]
        responses += [MagicMock(json=MagicMock(return_value=dict(self.info))) for _ in entries]
        self.client._HaricaClient__make_post_request = MagicMock(side_effect=responses)

    def test_list_certificates_keeps_list_fields(self):
        self._post([{"transactionId": "tx-1", "isRevoked": True}])
        cert = self.client.list_certificates(status=CertificateStatus.REVOKED, full_info=True)[0]
        self.assertEqual((cert["transactionId"], cert["isRevoked"], cert["serial"]), ("tx-1", True, "01"))

    def test_list_user_certificates_keeps_list_fields(self):
        self._post([{"transactionId": "tx-1", "transactionStatus": "Completed", "isRevoked": True}])
        cert = self.client.list_user_certificates(full_info=True)[0]
        self.assertEqual((cert["transactionId"], cert["status"], cert["serial"]), ("tx-1", "Revoked", "01"))


class TestAdminStatuses(unittest.TestCase):
    PAGES = {
        CertificateStatus.VALID: [{"transactionId": "tx-1"}],
        CertificateStatus.REVOKED: [{"transactionId": "tx-2"}],
        CertificateStatus.COMPLETED: [{"transactionId": "tx-1"}, {"transactionId": "tx-2"}],
    }

    def _list(self, statuses):
        def list_certificates(start_index, status, full_info):
            page = self.PAGES.get(status, []) if start_index == 0 else []
            return [dict(cert, status=status.value) for cert in page]

        args = argparse.Namespace(acme_account_id=None, fqdn=None, type=None)
        command = ListCertificatesCommand(args, None)
        command._harica_client = MagicMock(
            list_certificates=MagicMock(side_effect=list_certificates),
            list_acme_certificates=MagicMock(return_value=[]),
        )
        certificates, _ = command.list_certificates_as_admin(None, statuses)
        return {cert["transactionId"]: cert["status"] for cert in certificates}

    def test_completed_does_not_duplicate_certificates(self):
        statuses = [s for s in CertificateStatus if s != CertificateStatus.ALL]
        self.assertEqual(self._list(statuses), {"tx-1": "Valid", "tx-2": "Revoked"})

    def test_certificate_status_wins_over_completed_in_any_order(self):
        statuses = [CertificateStatus.COMPLETED, CertificateStatus.VALID]
        self.assertEqual(self._list(statuses), {"tx-1": "Valid", "tx-2": "Completed"})

    def test_completed_alone_lists_every_request(self):
        self.assertEqual(self._list([CertificateStatus.COMPLETED]), {"tx-1": "Completed", "tx-2": "Completed"})


if __name__ == "__main__":
    unittest.main()
