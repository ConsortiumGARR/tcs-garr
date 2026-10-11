from datetime import datetime, timezone

from colorama import Fore, Style
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.harica_client import DEFAULT_REVOCATION_REASON
from tcs_garr.utils import UserRole


class RevokeCommand(BaseCommand):
    """
    Command to revoke a certificate.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
        harica_config (HaricaClientConfig): The harica client configuration instance.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args, harica_config):
        """
        Initializes the CancelCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args, harica_config)
        self.command_name = "revoke"
        self.help_text = "Revoke a certificate by ID"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the command.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        action_group = parser.add_mutually_exclusive_group(required=True)
        # Argument for the certificate ID that will be canceled
        action_group.add_argument(
            "--id",
            help="ID of the certificate to revoke.",
        )
        action_group.add_argument(
            "--list-reasons",
            action="store_true",
            help="List the revocation reason codes accepted by --reason.",
        )
        parser.add_argument(
            "--reason",
            help=f"Revocation reason code. Default: {DEFAULT_REVOCATION_REASON} (unspecified).",
        )

    def is_certificate_valid_for_revocation(self, cert) -> bool:
        """Checks if a certificate is eligible for revocation."""
        if not cert:
            self.logger.error("Certificate not found.")
            return False

        if "acmeEntryId" in cert:
            self.logger.error("ACME certificates must be revoked with 'tcs-garr acme revoke'.")
            return False

        if cert.get("isRevoked"):
            self.logger.error("Certificate is already revoked.")
            return False

        valid_from = datetime.fromisoformat(cert["validFrom"]).replace(tzinfo=timezone.utc)
        valid_to = datetime.fromisoformat(cert["validTo"]).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        if not (valid_from <= now <= valid_to):
            self.logger.error("Certificate is not currently valid.")
            return False

        return True

    def execute(self):
        """
        Executes the command to revoke a certificate using the provided ID.
        """
        is_user_only = self.harica_client.has_role(UserRole.USER) and len(self.harica_client.roles) == 1

        reasons_scope = "user" if is_user_only else "ssl"

        if self.args.list_reasons:
            self._list_reasons(reasons_scope)
            return

        reason = self.args.reason or DEFAULT_REVOCATION_REASON
        if self.args.reason and not self._is_valid_reason(self.args.reason, reasons_scope):
            self.logger.error(f"Invalid revocation reason '{self.args.reason}'. Use --list-reasons to see the valid codes.")
            exit(1)

        id = self.args.id
        if is_user_only:
            cert = self.harica_client.get_user_certificate(id)
        else:
            cert = self.harica_client.get_certificate(id)

        if not self.is_certificate_valid_for_revocation(cert):
            exit(1)

        # Use sANS for confirmation
        dns_names = [dns_name.replace("DNS Name=", "") for dns_name in cert["sANS"].split(", ")]

        valid_from = datetime.fromisoformat(cert["validFrom"])
        valid_to = datetime.fromisoformat(cert["validTo"])

        self.logger.info(f"You are going to {Fore.RED}revoke{Style.RESET_ALL} a certificate with the following details:\n")
        self.logger.info(f"Friendly name: {cert['friendlyName']}")
        self.logger.info(f"Valid from: {valid_from.strftime('%d %B %Y %H:%M:%S')}")
        self.logger.info(f"Valid to: {valid_to.strftime('%d %B %Y %H:%M:%S')}")
        self.logger.info(f"DNS names: {', '.join(dns_names)}")
        self.logger.info(f"Reason: {reason}")

        dns_name = input(
            "\nPlease enter one of the following DNS names "
            "to confirm the revocation: "
            f"{Fore.YELLOW}{', '.join(dns_names)}{Style.RESET_ALL}: "
        )
        if dns_name not in dns_names:
            self.logger.error("Invalid DNS name. Revocation operation cancelled.")
            exit(1)

        confirm = input(f"{Fore.RED}Are you sure you want to revoke certificate with ID '{id}'? (Y/n): {Style.RESET_ALL}")
        if confirm != "Y":
            self.logger.error("Revoke operation cancelled.")
            exit(1)

        revoke_methods = {
            True: self.harica_client.revoke_user_certificate,
            False: self.harica_client.revoke_certificate,
        }

        # Pick the appropriate revoke function
        revoke_func = revoke_methods[is_user_only]

        if revoke_func(id, reason):
            self.logger.info(f"Certificate with ID '{id}' has been revoked.")
        else:
            self.logger.error(f"Failed to revoke certificate with ID '{id}'.")

    def _list_reasons(self, scope: str):
        """Prints the revocation reasons accepted by HARICA."""
        reasons = self.harica_client.get_revocation_reasons(scope)
        data = [[r.get("name"), r.get("revocationMessage")] for r in reasons]
        self.logger.info(tabulate(data, headers=[Fore.BLUE + "Code", "Reason" + Style.RESET_ALL]))

    def _is_valid_reason(self, reason: str, scope: str) -> bool:
        """Checks that the reason code is one of those accepted by HARICA."""
        reasons = self.harica_client.get_revocation_reasons(scope)
        return any(r.get("name") == reason for r in reasons)
