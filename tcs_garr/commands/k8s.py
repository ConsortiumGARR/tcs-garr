import base64
import os

from colorama import Fore, Style

from tcs_garr.commands.base import BaseCommand


class K8sCommand(BaseCommand):
    """
    Command to generate a Kubernetes TLS secret YAML file from a certificate and key.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    def __init__(self, args):
        """
        Initializes the K8sCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "k8s"
        self.help_text = "Generate Kubernetes TLS resource file"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the command.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Argument for the certificate file path
        parser.add_argument("--cert", required=True, help="Path to the certificate file.")
        # Argument for the key file path
        parser.add_argument("--key", required=True, help="Path to the key file.")
        # Argument for the Kubernetes namespace where the secret will be created
        parser.add_argument("--namespace", required=True, help="Kubernetes namespace for the secret.")
        # Argument for the secret name optional. Default is the name of the key file
        # without the extension and appended with "-tls"
        parser.add_argument(
            "--secret-name",
            default=None,
            help="Name for the secret (optional).",
        )
        # Argument for the yaml file name optional. Default is the name of the key file
        parser.add_argument(
            "--file-name",
            default=None,
            help="Name for the yaml file without the extension (optional).",
        )

    def get_output_folder(self):
        """
        Retrieve the default output folder from the configuration.

        Returns:
            str: The output folder path from the configuration.
        """
        # Load environment-specific configuration to get the output folder
        return self.harica_config.output_folder

    def execute(self):
        """
        Executes the command to generate a Kubernetes TLS secret YAML file.

        The file is created based on the provided certificate and key files, and the generated YAML is saved to the output folder.
        """
        key_filename = os.path.splitext(os.path.basename(self.args.key))[0]
        secret_name = f"{key_filename}-tls" if self.args.secret_name is None else self.args.secret_name
        file_name = secret_name if self.args.file_name is None else self.args.file_name

        # Read and encode the certificate file in base64
        with open(self.args.cert, "r") as cert_file:
            cert_b64 = base64.b64encode(cert_file.read().encode("utf-8")).decode("utf-8")

        # Read and encode the key file in base64
        with open(self.args.key, "r") as key_file:
            key_b64 = base64.b64encode(key_file.read().encode("utf-8")).decode("utf-8")

        # Generate the Kubernetes secret YAML content
        secret_yaml = f"""---
apiVersion: v1
kind: Secret
type: kubernetes.io/tls
metadata:
    name: {secret_name}
    namespace: {self.args.namespace}
data:
    tls.crt: >-
        {cert_b64}
    tls.key: >-
        {key_b64}
"""

        # Define the output file path where the secret YAML will be saved
        output_file = os.path.join(self.get_output_folder(), f"{file_name}.yml")

        # Write the generated YAML content to the output file
        with open(output_file, "w") as f:
            f.write(secret_yaml)

        # Log the completion of the secret YAML generation
        self.logger.info(f"{Fore.GREEN}Kubernetes secret YAML generated at {output_file}{Style.RESET_ALL}")
