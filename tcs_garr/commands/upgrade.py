from packaging import version

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import check_pypi_version, get_current_version, upgrade_package


class UpgradeCommand(BaseCommand):
    """
    Command to perform a self-upgrade of the application.

    This command checks the current version of the application and compares it
    to the latest version available on PyPI. If a newer version is available,
    the application is upgraded automatically.
    """

    def __init__(self, args, harica_config):
        """
        Initialize the UpgradeCommand class.

        Sets the `command_name` and `help_text` attributes for this command.
        The command name is "upgrade", and it is used to upgrade the current
        application to the latest version available on PyPI.
        """
        super().__init__(args, harica_config)
        self.command_name = "upgrade"  # Set the command name to "upgrade"
        self.help_text = "Self-upgrade command for the app."  # Help text for the command

    def configure_parser(self, parser):
        """
        Configure the argument parser for the upgrade command.

        This method is overridden from the BaseCommand class but is not used
        for the 'upgrade' command as it does not require any additional arguments.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        pass  # No additional arguments needed for this command

    def execute(self):
        """
        Execute the upgrade command to update the application to the latest version.

        This method checks the current version of the application and compares it
        to the latest version available on PyPI. If a newer version is available,
        it performs the upgrade process and logs the result.

        Args:
            args: Parsed command-line arguments (not used for this command).
        """
        # Get the current version of the application
        current_version = get_current_version()

        # Check the latest version available on PyPI
        latest_version = check_pypi_version()

        # Compare the current version to the latest version
        if version.parse(latest_version) > version.parse(current_version):
            # If a newer version is available, log the upgrade process
            self.logger.info(f"Upgrading from {current_version} to {latest_version}...")
            upgrade_package()  # Perform the package upgrade
            self.logger.info(f"Successfully upgraded to {latest_version}")  # Log the success
        else:
            # If already at the latest version, log that no upgrade is needed
            self.logger.info(f"Already at the latest version: {current_version}")
