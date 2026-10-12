from colorama import Fore, Style
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.harica_client import (
    DEFAULT_REVOCATION_REASON,
    ENTERPRISE_CERTIFICATE_STATUSES,
    ENTERPRISE_REQUEST_STATUSES,
)
from tcs_garr.utils import UserRole


class EnterpriseValidatorCommand(BaseCommand):
    """
    Shared implementation of the enterprise approver commands for S/MIME and
    Client Authentication. Subclasses set AREA, COMMAND_NAME and LABEL.

    The module name starts with "_" so that the command discovery skips this class.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
        harica_config (HaricaClientConfig): The harica client configuration instance.
    """

    # HARICA checks the approver roles, which tcs-garr does not track for every area
    REQUIRED_ROLE = UserRole.USER
    AREA = None
    COMMAND_NAME = None
    LABEL = None

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = self.COMMAND_NAME
        self.help_text = f"Review {self.LABEL} requests and certificates as enterprise approver"

    def configure_parser(self, parser):
        """
        Configure the argument parser for the command.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        subparsers = parser.add_subparsers(dest="action", required=True)

        requests_parser = subparsers.add_parser("requests", help=f"List {self.LABEL} requests")
        requests_parser.add_argument(
            "--status", choices=ENTERPRISE_REQUEST_STATUSES, default="Pending", help="Default: Pending."
        )

        certificates_parser = subparsers.add_parser("certificates", help=f"List {self.LABEL} certificates")
        certificates_parser.add_argument(
            "--status", choices=ENTERPRISE_CERTIFICATE_STATUSES, default="Valid", help="Default: Valid."
        )

        approve_parser = subparsers.add_parser("approve", help="Approve a pending request")
        approve_parser.add_argument("--id", required=True, help="ID of the pending request to approve.")

        cancel_parser = subparsers.add_parser("cancel", help="Cancel a request of another user")
        cancel_parser.add_argument("--id", required=True, help="ID of the request to cancel.")
        cancel_parser.add_argument("--message", required=True, help="Reason for the cancellation.")
        cancel_parser.add_argument(
            "--inform-applicant", action="store_true", help="Send the message to the applicant by email."
        )

        revoke_parser = subparsers.add_parser("revoke", help="Revoke a certificate")
        revoke_group = revoke_parser.add_mutually_exclusive_group(required=True)
        revoke_group.add_argument("--id", help="ID of the certificate to revoke (see 'certificates').")
        revoke_group.add_argument(
            "--list-reasons", action="store_true", help="List the revocation reason codes accepted by --reason."
        )
        revoke_parser.add_argument(
            "--reason", help=f"Revocation reason code. Default: {DEFAULT_REVOCATION_REASON} (unspecified)."
        )
        revoke_parser.add_argument("--message", default="", help="Message for the certificate owner.")

    def execute(self):
        """
        Executes the selected action.
        """
        try:
            if self.args.action == "requests":
                self._list_requests()
            elif self.args.action == "certificates":
                self._list_certificates()
            elif self.args.action == "approve":
                self._approve()
            elif self.args.action == "cancel":
                self._cancel()
            elif self.args.action == "revoke":
                self._revoke()
        except PermissionError as e:
            self.logger.error(f"{Fore.RED}HARICA refused the request: {e}{Style.RESET_ALL}")
            exit(1)

    def _confirm(self, question: str) -> bool:
        """Asks for a Y confirmation."""
        return input(f"{Fore.RED}{question} (Y/n): {Style.RESET_ALL}") == "Y"

    def _list_requests(self):
        """Prints the requests with the selected status."""
        requests = self.harica_client.list_enterprise_requests(self.AREA, self.args.status)
        data = [
            [
                r.get("transactionId"),
                r.get("transactionType"),
                r.get("transactionStatus"),
                r.get("userDescription"),
                r.get("createdAt"),
            ]
            for r in requests
        ]
        self.logger.info(
            tabulate(data, headers=[Fore.BLUE + "ID", "Type", "Status", "Requested by", "Created at" + Style.RESET_ALL])
        )

    def _list_certificates(self):
        """Prints the certificates with the selected status."""
        certificates = self.harica_client.list_enterprise_certificates(self.AREA, self.args.status)
        data = [
            [
                c.get("transactionId"),
                c.get("transactionTypeName") or c.get("transactionType"),
                c.get("userEmail") or c.get("userDescription"),
                c.get("dN"),
                c.get("certificateValidTo"),
            ]
            for c in certificates
        ]
        self.logger.info(tabulate(data, headers=[Fore.BLUE + "ID", "Type", "Owner", "DN", "Valid to" + Style.RESET_ALL]))

    def _find_request(self, transaction_id: str, status: str):
        """Returns the request with the given ID and status, or None."""
        requests = self.harica_client.list_enterprise_requests(self.AREA, status)
        return next((r for r in requests if r.get("transactionId") == transaction_id), None)

    def _approve(self):
        """Approves a pending request after confirmation."""
        request = self._find_request(self.args.id, "Pending")
        if not request:
            self.logger.error(f"No pending {self.LABEL} request found with ID {self.args.id}.")
            exit(1)

        self.logger.info(f"{request.get('transactionType')} requested by {request.get('userDescription')}")
        if not self._confirm(f"Are you sure you want to approve request '{self.args.id}'?"):
            self.logger.info("Operation cancelled.")
            return

        if self.harica_client.approve_enterprise_request(self.AREA, self.args.id):
            self.logger.info(f"{Fore.GREEN}Request with ID {self.args.id} has been approved.{Style.RESET_ALL}")
        else:
            self.logger.error(f"Failed to approve request with ID {self.args.id}.")
            exit(1)

    def _cancel(self):
        """Cancels a request after confirmation."""
        if not self._confirm(f"Are you sure you want to cancel request '{self.args.id}'?"):
            self.logger.info("Operation cancelled.")
            return

        if self.harica_client.cancel_enterprise_request(
            self.AREA, self.args.id, self.args.message, self.args.inform_applicant
        ):
            self.logger.info(f"{Fore.GREEN}Request with ID {self.args.id} has been cancelled.{Style.RESET_ALL}")
        else:
            self.logger.error(f"Failed to cancel request with ID {self.args.id}.")
            exit(1)

    def _revoke(self):
        """Revokes a valid certificate after confirmation, or lists the reasons."""
        reasons = None
        if self.args.list_reasons or self.args.reason:
            reasons = self.harica_client.get_revocation_reasons(self.AREA)

        if self.args.list_reasons:
            data = [[r.get("name"), r.get("revocationMessage")] for r in reasons]
            self.logger.info(tabulate(data, headers=[Fore.BLUE + "Code", "Reason" + Style.RESET_ALL]))
            return

        reason = self.args.reason or DEFAULT_REVOCATION_REASON
        if reasons is not None and not any(r.get("name") == reason for r in reasons):
            self.logger.error(f"Invalid revocation reason '{reason}'. Use --list-reasons to see the valid codes.")
            exit(1)

        certificates = self.harica_client.list_enterprise_certificates(self.AREA, "Valid")
        certificate = next((c for c in certificates if c.get("transactionId") == self.args.id), None)
        if not certificate:
            self.logger.error(f"No valid {self.LABEL} certificate found with ID {self.args.id}.")
            exit(1)

        self.logger.info(f"You are going to {Fore.RED}revoke{Style.RESET_ALL} a {self.LABEL} certificate:\n")
        self.logger.info(f"DN: {certificate.get('dN')}")
        self.logger.info(f"Owner: {certificate.get('userEmail') or certificate.get('userDescription')}")
        self.logger.info(f"Valid to: {certificate.get('certificateValidTo')}")
        self.logger.info(f"Reason: {reason}")
        if not self._confirm("Are you sure you want to revoke this certificate?"):
            self.logger.info("Operation cancelled.")
            return

        if self.harica_client.revoke_enterprise_certificate(self.AREA, self.args.id, reason, self.args.message):
            self.logger.info(f"{Fore.GREEN}Certificate with ID {self.args.id} has been revoked.{Style.RESET_ALL}")
        else:
            self.logger.error(f"Failed to revoke certificate with ID {self.args.id}.")
            exit(1)
