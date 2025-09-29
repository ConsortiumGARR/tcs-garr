import os
import sys

from colorama import Fore, Style
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from cryptography.x509.extensions import ExtensionNotFound

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole


class RequestCommand(BaseCommand):
    """
    Command to request a new S/MIME certificate by generating a CSR or submitting an existing one.

    This command allows the user to generate a Certificate Signing Request (CSR) or provide an existing CSR
    to request a new S/MIME certificate from the Harica service. The user can choose between different certificate profiles
    (MV, SV), generate a CSR with a common name, and submit the request for approval.
    Note that Harica uses different names for the standard validation options in their documentation:
    * MV (Mailbox Validated): "Email only"
    * OV (Organisation Validated): "OV" - not available via bulk
    * IV (Individual Validated): "IV" - not available via bulk
    * SV (Sponsor Validated): "OV and IV"

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    HARICA_BULK_EMAIL_LIMIT = 100
    REQUIRED_ROLE = UserRole.ENTERPRISE_ADMIN

    def __init__(self, args):
        """
        Initializes the RequestCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "smime"
        self.help_text = "Request a new S/MIME certificate"
        self.parser = None

    def configure_parser(self, parser):
        """
        Configures the argument parser for the request command.

        This method defines the arguments for requesting a new certificate:
        - --profile: Specifies the certificate profile (MV or SV).
        - --csr: Path to an existing CSR file.
        - --emails: Up to three email addresses to include in SAN (used when no CSR is provided).
        - --gn: Given Name of the Subject (used with --emails).
        - --sn: Surname of the Subject (used with --emails).

        Automatically downloads the certificate and saves it to a specified file or prints it.
        - --output-filename: Optional filename to save the certificate inside the default output folder.
        - --force: Force overwrite if the output file already exists.
        - --download-type: Type of download: 'pemBundle' or 'certificate'. Default is 'pemBundle'.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        self.parser = parser
        self.parser.add_argument(
            "--profile", default="SV", choices=["SV", "MV"], help="Profile to use between SV or MV. Default: SV"
        )

        self.parser.add_argument(
            "--disable-webhook",
            action="store_true",
            help="Disable calling webhook after submit request. This works only if webhook_url has been configured",
        )

        # Create a mutually exclusive group for --csr and --cn/--email (plus optional --alt_names)
        create_group = self.parser.add_mutually_exclusive_group(required=True)
        create_group.add_argument("--csr", type=str, help="Path to an existing CSR file.")

        # When no --csr is provided, user must provide --cn (with optional --alt_names)
        create_group.add_argument("--emails", help="Comma-separated email addresses of the certificate (up to three).")
        self.parser.add_argument("--gn", default="", help="Given Name of the Subject (only used with --email).")
        self.parser.add_argument("--sn", default="", help="Surname of the Subject (only used with --email).")

        # Optional output filename for saving the certificate
        parser.add_argument(
            "--output-filename",
            default=None,
            help="Optional filename to save the certificate inside the default output folder.",
        )
        # Add force flag to allow overwriting the file
        parser.add_argument("--force", "-f", action="store_true", help="Force overwrite if the output file already exists.")

        # Specify the type of download (either 'pemBundle' or 'certificate')
        parser.add_argument(
            "--download-type",
            choices=["pemBundle", "certificate"],
            default="pemBundle",
            help="Type of download: 'pemBundle' or 'certificate'. Default is 'pemBundle'.",
        )

    def get_output_folder(self):
        """
        Retrieve the default output folder from the configuration.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.

        Returns:
            str: The output folder path from the configuration.
        """
        # Load environment-specific configuration
        return self.harica_config.output_folder

    def execute(self):
        """
        Executes the command to generate a CSR or request a certificate and download it.

        This method handles the logic to either generate a CSR and submit it or submit an existing CSR.
        It also ensures that the --gn/--sn arguments are only used with the --emails argument.
        """
        # Additional logic to ensure --alt_names is only used with --cn and not with --csr
        if self.args.csr and self.args.emails:
            self.parser.error("--emails cannot be used with --csr.")
            exit(1)

        if self.args.emails:
            if len(self.args.emails.split(",")) > 3:
                self.parser.error("--emails takes at most 3 addresses.")
                exit(1)
            # Generate a CSR and request a certificate
            csr_path = self.__generate_key_csr(self.args.emails, self.args.gn, self.args.sn, self.harica_config.output_folder)
            email, p7b_data = self.__issue_bulk_certificate(csr_path, self.args.profile)
        else:
            # CSR has been provided, just issue the certificate
            email, p7b_data = self.__issue_bulk_certificate(self.args.csr, self.args.profile)

        # since this API returns the certificate immediately, we do something similar to tcs_garr.commands.download.execute here.
        if self.args.download_type == "pemBundle":
            # Load and extract the certificates from the PKCS7 data. contains the full chain.
            pkcs7_cert = pkcs7.load_der_pkcs7_certificates(p7b_data)
            data_to_write = b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in pkcs7_cert)
        else:
            data_to_write = p7b_data

        # Determine the output folder from the config
        output_folder = self.get_output_folder()

        # If the output folder and filename are provided, save the certificate to a file
        if output_folder and self.args.output_filename:
            output_path = os.path.join(output_folder, self.args.output_filename)

            # Check if the file already exists, and handle the force flag for overwriting
            if os.path.exists(output_path) and not self.args.force:
                self.logger.error(f"File {output_path} already exists. Use --force to overwrite.")
            else:
                # Write the certificate data to the file (binary or text based on data type)
                with open(output_path, "wb") as cert_file:
                    cert_file.write(data_to_write)
                self.logger.info(f"Certificate saved to {output_path}")
        else:
            # If no filename is provided, print the certificate data
            sys.stdout.buffer.write(data_to_write)

        if not self.args.disable_webhook:
            self.call_webhook("S/MIME", email)

    def __generate_key_csr(self, emails, gn, sn, output_folder):
        """
        Generates a private key and CSR for the specified common name and alternative names.

        This method generates an RSA private key, creates a CSR with the provided email address and alternative
        names (SANs), and saves both the private key and CSR to the specified output folder.

        Args:
            emails (str): A comma-separated list of the subject's Email Addresses.
            gn (str): Given Name of the subject
            sn (str): Surname of the subject
            output_folder (str): The folder where the private key and CSR will be saved.

        Returns:
            str: The file path to the generated CSR.
        """

        # take the first provided email as the primary one to be written into the DN
        email = emails.split(",")[0]

        # Generate the private key
        key = rsa.generate_private_key(public_exponent=65537, key_size=4096, backend=default_backend())

        # Write the private key to disk
        os.makedirs(output_folder, exist_ok=True)
        key_path = os.path.join(output_folder, f"{email}.key")
        with open(key_path, "wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        self.logger.info(f"{Fore.BLUE}Private key created in {key_path}{Style.RESET_ALL}")
        os.chmod(key_path, 0o600)

        # Prepare Subject Alternative Names
        subject_alt_names = []
        for item in emails.split(","):
            if item and item not in subject_alt_names:
                subject_alt_names.append(item)

        subject = [
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),  # must always be present
        ]
        if gn and sn:
            subject.extend(
                [
                    x509.NameAttribute(NameOID.GIVEN_NAME, gn),
                    x509.NameAttribute(NameOID.SURNAME, sn),
                ]
            )
        # Generate a CSR
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name(subject))
            .add_extension(
                x509.SubjectAlternativeName([x509.RFC822Name(x) for x in subject_alt_names]),
                critical=False,
            )
            .sign(key, hashes.SHA512(), default_backend())
        )

        # Write the CSR to disk
        csr_path = os.path.join(output_folder, f"{email}.csr")
        with open(csr_path, "wb") as f:
            f.write(csr.public_bytes(serialization.Encoding.PEM))
        self.logger.info(f"{Fore.BLUE}CSR created in {csr_path}{Style.RESET_ALL}")

        return csr_path

    def __issue_bulk_certificate(self, csr_file, profile):
        """
        Issues a certificate request by submitting a CSR to the Harica client.

        This method reads the provided CSR file, validates it, and submits it to the Harica client for certification.
        It also handles logging and outputs relevant information, including certificate IDs and download instructions.

        Args:
            csr_file (str): The path to the CSR file.
            profile (str): The certificate profile (SV or MV) to use for the request.
        """
        try:
            with open(csr_file, "rb") as f:
                csr = x509.load_pem_x509_csr(f.read(), default_backend())

                email = csr.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)[0].value
                try:
                    gn = csr.subject.get_attributes_for_oid(NameOID.GIVEN_NAME)[0].value
                except (x509.AttributeNotFound, IndexError):
                    gn = None
                try:
                    sn = csr.subject.get_attributes_for_oid(NameOID.SURNAME)[0].value
                except (x509.AttributeNotFound, IndexError):
                    sn = None
                try:
                    alt_names = [x.value for x in csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value]
                except ExtensionNotFound:
                    alt_names = []

                all_emails = [email]
                for alt_name in alt_names:
                    if alt_name and alt_name not in all_emails:
                        all_emails.append(alt_name)

                # Check if the number of Email Addresses is HARICA_BULK_EMAIL_LIMIT or more and abort with an error
                if len(alt_names) >= self.HARICA_BULK_EMAIL_LIMIT:
                    self.logger.error(
                        f"{Fore.RED}Warning: Certificates with more than {self.HARICA_BULK_EMAIL_LIMIT} Email addresses cannot be submitted.{Style.RESET_ALL}"
                    )
                    exit(1)

                self.logger.info(f"{Fore.YELLOW}Submitting CSR to Harica... Please wait...{Style.RESET_ALL}")

                certificates = self.harica_client.request_single_smime_bulk_certificate(
                    all_emails, gn, sn, csr.public_bytes(serialization.Encoding.PEM).decode(), profile
                )

                self.logger.info(f"{Fore.GREEN}CSR submitted.{Style.RESET_ALL}")

                return email, certificates

        except FileNotFoundError:
            self.logger.error(f"{Fore.RED}CSR file {csr_file} not found.{Style.RESET_ALL}")
            exit(1)
