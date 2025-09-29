from abc import ABC, abstractmethod
from functools import wraps

from colorama import Fore, Style

from tcs_garr.harica_client import HaricaClient
from tcs_garr.logger import setup_logger
from tcs_garr.notifications import NotificationManager
from tcs_garr.utils import HaricaClientConfig


def requires_any_role(*roles):
    """
    Decorator to restrict function access based on user roles using OR logic.

    Args:
        *roles: One or more UserRole values. User must have AT LEAST ONE of these roles.

    Example:
        @requires_any_role(UserRole.ENTERPRISE_ADMIN, UserRole.SSL_ENTERPRISE_APPROVER)
        def admin_or_approver_function(self):
            # Users with either ENTERPRISE_ADMIN or SSL_ENTERPRISE_APPROVER role can call this
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Ensure we have a client with valid authentication
            client = self.harica_client

            # Check if the user has at least one of the required roles (OR logic)
            has_required_role = any(client.has_role(role) for role in roles)

            if not has_required_role:
                role_names = [role.value for role in roles]
                self.logger.error(
                    f"{Fore.RED}User {client.email} lacks required role(s): {' or '.join(role_names)}{Style.RESET_ALL}"
                )
                exit(1)

            # User has the required role, proceed with the function call
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def requires_all_roles(*roles):
    """
    Decorator to restrict function access based on user roles using AND logic.

    Args:
        *roles: One or more UserRole values. User must have ALL of these roles.

    Example:
        @requires_all_roles(UserRole.ENTERPRISE_ADMIN, UserRole.SSL_ENTERPRISE_APPROVER)
        def admin_and_approver_function(self):
            # Only users with BOTH ENTERPRISE_ADMIN and SSL_ENTERPRISE_APPROVER roles can call this
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Ensure we have a client with valid authentication
            client = self.harica_client

            # Check if the user has all of the required roles (AND logic)
            has_all_required_roles = all(client.has_role(role) for role in roles)

            if not has_all_required_roles:
                role_names = [role.value for role in roles]
                self.logger.error(
                    f"{Fore.RED}User {client.email} lacks required role(s): {' and '.join(role_names)}{Style.RESET_ALL}"
                )
                exit(1)

            # User has all required roles, proceed with the function call
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


# For backward compatibility and cleaner API
def requires_roles(*roles, logic="OR"):
    """
    Decorator to restrict function access based on user roles.

    Args:
        *roles: One or more UserRole values that are required to execute the function.
        logic: "OR" (default) - user must have at least one of the roles
               "AND" - user must have all of the roles

    Example:
        @requires_roles(UserRole.ENTERPRISE_ADMIN)
        def admin_only_function(self):
            # Only users with ENTERPRISE_ADMIN role can call this

        @requires_roles(UserRole.ENTERPRISE_ADMIN, UserRole.SSL_ENTERPRISE_APPROVER)
        def admin_or_approver_function(self):
            # Users with either ENTERPRISE_ADMIN or SSL_ENTERPRISE_APPROVER role can call this

        @requires_roles(UserRole.ENTERPRISE_ADMIN, UserRole.SSL_ENTERPRISE_APPROVER, logic="AND")
        def admin_and_approver_function(self):
            # Only users with both ENTERPRISE_ADMIN and SSL_ENTERPRISE_APPROVER roles can call this
    """
    if logic.upper() == "AND":
        return requires_all_roles(*roles)
    else:  # Default to OR logic
        return requires_any_role(*roles)


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

        if not self._harica_client.token:
            self.logger.error("Terminating!")
            exit(1)

        self.check_required_role(self._harica_client)

        return self._harica_client

    @property
    def harica_config(self) -> HaricaClientConfig:
        if not self._harica_config:
            self._harica_config = HaricaClientConfig(
                environment=self.args.environment,
                alt_config_path=self.args.config,
            )
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

    def call_webhook(self, cert_type, cn, cert_id=None):
        webhook_url = self._harica_config.webhook_url
        webhook_type = self._harica_config.webhook_type
        if webhook_url:
            try:
                requestor = self._harica_client.email

                manager = NotificationManager(webhook_type=webhook_type, webhook_url=webhook_url)

                title = f"{cert_type} Certificate Request"
                message = f"{cert_type} Certificate for {cn} has been requested."

                if cert_id is not None:
                    details = {"id": cert_id, "username": requestor}
                else:
                    details = {"subject": cn, "username": requestor}

                manager.success(title=title, message=message, details=details)

            except Exception as e:
                self.logger.error(f"Error sending webhook via NotificationManager: {e}")
