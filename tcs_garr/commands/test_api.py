import json

from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class TestApiCommand(BaseCommand):
    """
    Command to test Harica API endpoints


    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = "test"
        self.help_text = "Test Harica API endpoints"

    def configure_parser(self, parser):
        """
        Configure the argument parser for the acme command.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        parser.add_argument("--endpoint", required=True, help="Endpoint to test")
        parser.add_argument(
            "--data",
            default=None,
            help=(
                'Data to send with the request in JSON format (e.g. \'--data {"id": "f3b2a6a8-5da6-46f1-8f1d-3f9d2a6f32ec"}\')'
            ),
        )
        parser.add_argument(
            "--foutput",
            default=None,
            help="File to output JSON response (e.g. --foutput test.json)",
        )

    def execute(self):
        """
        Executes the command to list ACME accounts from Harica.
        """
        try:
            data = {}
            if self.args.data:
                data = json.loads(self.args.data)

            res = self.harica_client.api_post(self.args.endpoint, data=data)
            res.raise_for_status()

            self.logger.info(f"{Fore.BLUE}\n🔍 API Response (code: {res.status_code}):")
            pp_json = json.dumps(res.json(), indent=4)
            self.logger.info(f"{pp_json}{Style.RESET_ALL}\n")

            if self.args.foutput:
                with open(self.args.foutput, "w") as f:
                    f.write(pp_json)
                self.logger.info(f"{Fore.GREEN}Wrote JSON response to {self.args.foutput}{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"{Fore.RED}❌ API test failed: {e}")
            self.logger.error(res.text if hasattr(res, "text") else f"No response text available.{Style.RESET_ALL}")
