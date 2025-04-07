from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class CancelCommand(BaseCommand):
    """
    Command to cancel a transaction or request by its ID.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args):
        """
        Initializes the CancelCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "cancel"
        self.help_text = "Cancel a request by ID"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the command.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Argument for the request ID that will be canceled
        parser.add_argument("--id", required=True, help="ID of the request to cancel.")

    def execute(self):
        """
        Executes the command to cancel a transaction or request using the provided ID.

        Uses the Harica client to send the cancellation request.
        Logs the result of the operation, indicating success or failure.
        """
        # Attempt to cancel the transaction using the provided ID
        if self.harica_client.cancel_transaction(self.args.id):
            # Log success message
            self.logger.info(f"Transaction with ID {self.args.id} has been canceled.")
        else:
            # Log error message in case of failure
            self.logger.error(f"Failed to cancel transaction with ID {self.args.id}.")
