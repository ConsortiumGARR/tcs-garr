from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand
from tcs_garr.harica_client import CONSTRUCTED_EMAIL_USERS, DOMAIN_VALIDATION_METHODS
from tcs_garr.utils import UserRole


class ValidateCommand(BaseCommand):
    """
    Command to create validation tokens for domains.

    This command submits domains for pre-validation by the Harica client.
    Once the domains are validated, an email with a token for DNS configuration is sent.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
        harica_config (HaricaClientConfig): The harica client configuration instance.
    """

    REQUIRED_ROLE = UserRole.ENTERPRISE_ADMIN

    def __init__(self, args, harica_config):
        """
        Initializes the ValidateCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args, harica_config)
        self.command_name = "validate"
        self.help_text = "Create validation token for domains"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the validate command.

        This method defines the required argument for specifying the list of domains
        that need to be validated.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Argument for the comma-separated list of domains to validate
        parser.add_argument("--domains", required=True, help="Comma separated list of domains.")
        parser.add_argument(
            "--method",
            choices=list(DOMAIN_VALIDATION_METHODS),
            default="dns",
            help="Validation method: 'dns' (DNS change, 3.2.2.4.7) or 'email' "
            "(constructed email to domain contact, 3.2.2.4.4). Default: dns.",
        )
        parser.add_argument(
            "--email-user",
            choices=CONSTRUCTED_EMAIL_USERS,
            default="admin",
            help="Mailbox that receives the token with --method email, as <email-user>@<domain>. Default: admin.",
        )

    def execute(self):
        """
        Executes the command to create validation tokens for the provided domains.

        This method splits the provided comma-separated list of domains, submits them for
        validation using the Harica client, and logs the result for each domain, indicating
        that prevalidation has been submitted and an email will be sent with the token.

        Logs the result for each domain:
        - Green check mark (✅) if the prevalidation has been submitted successfully.
        """
        # Split the comma-separated domains into a list
        domains = self.args.domains.split(",")

        # Submit the domains for validation via the Harica client
        self.harica_client.validate_domains(domains, method=self.args.method, email_user=self.args.email_user)

        # Log the result for each domain
        for domain in domains:
            if self.args.method == "email":
                next_step = f"{self.args.email_user}@{domain} will receive an email soon with the validation link."
            else:
                next_step = "You will receive an email soon with token to configure DNS."
            self.logger.info(f"{Fore.GREEN}✅ Domain {domain} prevalidation submitted. {next_step}{Style.RESET_ALL}")
