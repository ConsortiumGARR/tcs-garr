from datetime import datetime

from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand

from tcs_garr.utils import UserRole


class DomainsCommand(BaseCommand):
    """
    Command to list available domains and display their expiration status.

    This command retrieves the list of domains from the Harica client and logs their
    expiration status, including whether the domain has expired, is expiring soon, or
    is valid for more than 30 days.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.ENTERPRISE_ADMIN

    def __init__(self, args):
        """
        Initializes the DomainsCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "domains"
        self.help_text = "List available domains"

    def configure_parser(self, parser):
        """
        Configure the argument parser for the domains command.

        This method is overridden from the BaseCommand class but is not used
        for the 'domains' command as it does not require any additional arguments.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        pass  # No arguments needed for this command

    def execute(self):
        """
        Executes the command to list available domains and their expiration status.

        This method retrieves the list of domains from the Harica client, and for each domain,
        it calculates the remaining days until expiration. Depending on the remaining days,
        the domain's status is logged in different colors:
        - Red if expired
        - Yellow if expiring within 30 days
        - Green if valid for more than 30 days
        """
        # Get the current time
        current_time = datetime.now()

        # Iterate through the list of domains retrieved from the Harica client
        for item in self.harica_client.list_domains():
            domain = item["domain"]
            # Parse the validity date from the domain information
            validity = datetime.strptime(item["validity"], "%Y-%m-%dT%H:%M:%S.%f")
            # Calculate the number of remaining days until the domain expires
            remaining_days = (validity - current_time).days

            if remaining_days < 0:
                # If the domain has already expired, log the information in red
                self.logger.info(f"{Fore.RED}{domain} expired on {validity.date()}{Style.RESET_ALL}")
            elif remaining_days <= 30:
                # If the domain is expiring within the next 30 days, log in yellow
                self.logger.info(
                    f"{Fore.YELLOW}{domain} expiring on {validity.date()} ({remaining_days} days left){Style.RESET_ALL}"
                )
            else:
                # If the domain is valid for more than 30 days, log in green
                self.logger.info(
                    f"{Fore.GREEN}{domain} valid until {validity.date()} ({remaining_days} days left){Style.RESET_ALL}"
                )
