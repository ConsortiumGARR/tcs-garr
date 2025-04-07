from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class ValidateCommand(BaseCommand):
    """
    Command to create validation tokens for domains.

    This command submits domains for pre-validation by the Harica client.
    Once the domains are validated, an email with a token for DNS configuration is sent.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.ENTERPRISE_ADMIN

    def __init__(self, args):
        """
        Initializes the ValidateCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
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
        self.harica_client.validate_domains(domains)

        # Log the result for each domain
        for domain in domains:
            self.logger.info(
                f"{Fore.GREEN}✅ Domain {domain} prevalidation submitted. You will receive an email soon with token to configure DNS.{Style.RESET_ALL}"
            )
