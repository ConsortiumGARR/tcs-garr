from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class WhoamiCommand(BaseCommand):
    """
    Command to get and display the currently logged-in user's profile information.

    This command interacts with the Harica API to retrieve the profile details
    of the user who is currently authenticated.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args):
        """
        Initialize the WhoamiCommand class.

        Sets the `command_name` and `help_text` attributes for this command.
        The command name is "whoami", and it will be used to get the current
        user's profile when executed.
        """
        super().__init__(args)
        self.command_name = "whoami"  # Set the command name to "whoami"
        self.help_text = "Get logged in user profile"  # Help text for the command

    def configure_parser(self, parser):
        """
        Configure the argument parser for the whoami command.

        This method is overridden from the BaseCommand class but is not used
        for the 'whoami' command as it does not require any additional arguments.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        pass  # No arguments needed for this command

    def execute(self):
        """
        Execute the whoami command to retrieve and display the logged-in user's profile.

        This method makes a call to the Harica client to fetch the current user's
        profile, including their full name and email address. It logs this
        information to the console in a formatted, colorized output.

        Args:
            args: Parsed command-line arguments (not used for this command).
        """

        # Log the user's full name and email in green-colored output
        self.logger.info(
            f"{Fore.GREEN}👤 Hi! You're logged in as {self.harica_client.full_name} ({self.harica_client.email}) on {self.args.environment} environment{Style.RESET_ALL}"
        )
        self.logger.info(
            f"{Fore.GREEN}🔒 You have the following roles: {self.harica_client.get_user_roles()}{Style.RESET_ALL}"
        )
