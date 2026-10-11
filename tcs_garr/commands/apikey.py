from colorama import Fore, Style
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class ApiKeyCommand(BaseCommand):
    """
    Command to manage the HARICA API keys of the logged in user.

    HARICA allows API keys only to Enterprise Admins and Enterprise Approvers,
    with a maximum of 3 keys per user. The role check is left to HARICA.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
        harica_config (HaricaClientConfig): The harica client configuration instance.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = "apikey"
        self.help_text = "Manage your HARICA API keys"

    def configure_parser(self, parser):
        """
        Configure the argument parser for the apikey command.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        subparsers = parser.add_subparsers(dest="action", required=True)

        subparsers.add_parser("list", help="List your API keys")

        create_parser = subparsers.add_parser("create", help="Create a new API key")
        create_parser.add_argument("friendly_name", type=str, help="Friendly name for the new API key")

        disable_parser = subparsers.add_parser("disable", help="Disable an API key")
        disable_parser.add_argument("api_key_id", type=str, help="ID of the API key to disable")

    def execute(self):
        """
        Executes the selected apikey action.
        """
        try:
            if self.args.action == "list":
                self._list_keys()
            elif self.args.action == "create":
                self._create_key()
            elif self.args.action == "disable":
                self._disable_key()
        except PermissionError as e:
            self.logger.error(f"{Fore.RED}HARICA refused the request: {e}{Style.RESET_ALL}")
            exit(1)

    def _list_keys(self):
        """Prints the API keys of the logged in user."""
        keys = self.harica_client.list_api_keys()
        if not keys:
            self.logger.info(f"{Fore.YELLOW}No API keys found.{Style.RESET_ALL}")
            return

        data = [
            [
                key.get("apiKeyId"),
                key.get("friendlyName"),
                key.get("createdAt"),
                "ENABLED" if key.get("isActive") else f"DISABLED ({key.get('disabledAt')})",
            ]
            for key in keys
        ]
        self.logger.info(tabulate(data, headers=[Fore.BLUE + "ID", "Friendly name", "Created at", "Status" + Style.RESET_ALL]))

    def _create_key(self):
        """Creates an API key and prints its code."""
        code = self.harica_client.create_api_key(self.args.friendly_name)
        self.logger.info(f"{Fore.GREEN}API key '{self.args.friendly_name}' created.{Style.RESET_ALL}")
        self.logger.info(f"{Fore.YELLOW}This is the only time the key is shown, store it securely:{Style.RESET_ALL}")
        self.logger.info(code)

    def _disable_key(self):
        """Disables an API key after confirmation."""
        confirm = input(
            f"{Fore.RED}Are you sure you want to disable API key '{self.args.api_key_id}'? (Y/n): {Style.RESET_ALL}"
        )
        if confirm != "Y":
            self.logger.info("Operation cancelled.")
            return

        if self.harica_client.disable_api_key(self.args.api_key_id):
            self.logger.info(f"{Fore.GREEN}API key '{self.args.api_key_id}' has been disabled.{Style.RESET_ALL}")
        else:
            self.logger.error(f"{Fore.RED}Failed to disable API key '{self.args.api_key_id}'.{Style.RESET_ALL}")
