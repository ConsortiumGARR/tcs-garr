from abc import ABC, abstractmethod
from colorama import Fore, Style

from tcs_garr.harica_client import HaricaClient
from tcs_garr.logger import setup_logger
from tcs_garr.utils import HaricaClientConfig


class BaseCommand(ABC):
    """Base class that all command implementations should inherit from."""

    REQUIRED_ROLE = None

    def __init__(self, args):
        # Default command name (can be overridden by subclasses)
        self.command_name = None

        self.args = args

        self.logger = setup_logger()

        # Default help text (should be overridden by subclasses)
        self.help_text = "No description available"

        self._harica_client = None

        self._harica_config = None

    @abstractmethod
    def configure_parser(self, parser):
        """
        Configure the argument parser for this command.

        Args:
            parser: The argparse parser for this command
        """
        pass

    @property
    def harica_client(self):
        if not self._harica_client:
            self._harica_client = HaricaClient(
                self.harica_config.username,
                self.harica_config.password,
                self.harica_config.totp_seed,
                http_proxy=self.harica_config.http_proxy,
                https_proxy=self.harica_config.https_proxy,
                environment=self.args.environment,
            )
        self.check_required_role(self._harica_client)

        return self._harica_client

    @property
    def harica_config(self):
        if not self._harica_config:
            self._harica_config = HaricaClientConfig(environment=self.args.environment)
        return self._harica_config

    def check_required_role(self, client: HaricaClient):
        """Check if the user has the required role for the command."""
        if self.REQUIRED_ROLE and not client.has_role(self.REQUIRED_ROLE):
            self.logger.error(
                f"{Fore.RED}User {client.email} lacks required role: {self.REQUIRED_ROLE.value}{Style.RESET_ALL}"
            )
            exit(1)

    @abstractmethod
    def execute(self, args):
        """
        Execute the command with the parsed arguments.

        Args:
            args: The parsed command arguments
        """
        pass
