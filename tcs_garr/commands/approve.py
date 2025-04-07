from colorama import Fore, Style
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class ApproveCommand(BaseCommand):
    """
    Command to approve certificates by their ID or list pending requests.

    This command allows you to approve certificates by ID, approve all pending requests,
    or list all the pending certificate requests.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.SSL_ENTERPRISE_APPROVER

    def __init__(self, args):
        """
        Initializes the ApproveCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "approve"
        self.help_text = "Approve a certificate by ID"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the approve command.

        This method defines the mutually exclusive arguments for approving certificates by ID,
        listing pending requests, or approving all pending requests.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Create a mutually exclusive group for the approval options
        approve_certificate_group = parser.add_mutually_exclusive_group(required=True)

        # Add mutually exclusive arguments for approving certificates by ID,
        # listing pending requests, or approving all requests
        approve_certificate_group.add_argument("--id", help="ID of the certificates (comma separated) to approve.")
        approve_certificate_group.add_argument("--list-pending", action="store_true", help="List all pending requests.")
        approve_certificate_group.add_argument("--all", action="store_true", help="Approve all pending requests.")

    def execute(self):
        """
        Executes the command based on the provided arguments.

        This method determines the action to take based on the arguments:
        - If --id is provided, it approves the specified certificates.
        - If --all is provided, it approves all pending certificates.
        - If --list-pending is provided, it lists all pending certificate requests.
        """

        if self.args.id:
            # Approve specific transactions by ID
            self.__approve_transactions(self.args.id.split(","))
        elif self.args.all:
            # Approve all pending transactions
            self.__approve_transactions()
        elif self.args.list_pending:
            # List all pending certificate requests
            self.__list_pending_certificates()

    def __approve_transactions(self, ids=None):
        """
        Approves transactions by ID or approves all pending transactions.

        This method handles the approval of transactions. If no IDs are provided, it will approve
        all pending transactions. For each transaction, the method attempts to approve it and logs
        the success or failure message.

        Args:
            ids (list, optional): A list of certificate transaction IDs to approve. Defaults to None.
        """
        if ids is None:
            # If no IDs are provided, retrieve the list of pending transactions
            transactions = self.harica_client.get_pending_transactions()
            ids = [transaction["transactionId"] for transaction in transactions]

        for id in ids:
            try:
                # Try to approve the certificate with the specified ID
                if self.harica_client.approve_transaction(id):
                    # Log success if the transaction is approved
                    self.logger.info(f"Certificate with ID {id} has been approved.")
                    self.logger.info(
                        f"Requestor can download it with command: tcs-garr download --id {id} --output-filename <filename>.pem"
                    )
                else:
                    # Log error if the approval failed
                    self.logger.error(f"Failed to approve certificate with ID {id}.")
            except PermissionError:
                # Log error if trying to approve a certificate that the user cannot approve (own request)
                self.logger.error(f"Failed to approve certificate with ID {id}. You cannot approve your own request.")

    def __list_pending_certificates(self):
        """
        Lists all pending certificate requests.

        This method retrieves all pending transactions and logs them in a tabular format,
        displaying the transaction ID, the domains associated with the request, the status,
        and the user who requested the certificate.
        """
        # Retrieve the list of pending transactions
        transactions = self.harica_client.get_pending_transactions()

        # Prepare the data to be displayed in a table
        data = []
        for item in transactions:
            data.append(
                [
                    item["transactionId"],
                    ",".join([domain["fqdn"] for domain in item["domains"]]),
                    item["transactionStatus"],
                    item["user"],
                ]
            )

        # Log the data in a tabular format using tabulate
        self.logger.info(
            tabulate(
                data,
                headers=[
                    Fore.BLUE + "ID",
                    "CN",
                    "Status",
                    "Requested by" + Style.RESET_ALL,
                ],
            )
        )
