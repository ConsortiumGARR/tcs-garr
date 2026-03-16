from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand
from tcs_garr.commands.whoami import WhoamiCommand
from tcs_garr.utils import UserRole


class DummyCommand(BaseCommand):
    """
    Command to test adding user extra commands by config.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = "dummy"
        self.help_text = "Dummy user command for testing purposes."

    def configure_parser(self, parser):
        parser.add_argument("--dummy", action="store_true", help="Dummy option.")

    def execute(self):
        # Log the user's full name and email in green-colored output
        self.logger.info(f"{Fore.GREEN}👤 Hi! Your dummy option is {self.args.dummy}")


class InvalidWhoamiOverride(BaseCommand):
    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = "whoami"  # Set the command name to "whoami"
        self.help_text = "Get logged in user profile"  # Help text for the command

    def configure_parser(self, parser):
        pass  # No arguments needed for this command

    def execute(self):
        # Log the user's full name and email in green-colored output
        self.logger.info(
            f"{Fore.GREEN}👤 Hi! You're logged in as {self.harica_client.full_name} ({self.harica_client.email}) on {self.args.environment} environment{Style.RESET_ALL}"
        )
        self.logger.info(
            f"{Fore.GREEN}🔒 You have the following roles: {self.harica_client.get_user_roles()}{Style.RESET_ALL}"
        )


class WhoamiOverride(WhoamiCommand):
    def execute(self):
        # Log the user's full name and email in red-colored output
        self.logger.info(
            f"{Fore.RED}👤 Hi! You're logged in as {self.harica_client.full_name} ({self.harica_client.email}) on {self.args.environment} environment{Style.RESET_ALL}"
        )
        self.logger.info(f"{Fore.RED}🔒 You have the following roles: {self.harica_client.get_user_roles()}{Style.RESET_ALL}")
