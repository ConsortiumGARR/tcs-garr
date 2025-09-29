import base64
import os
import time

from colorama import Fore, Style
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from cryptography.x509.extensions import ExtensionNotFound

from tcs_garr.commands.base import BaseCommand
from tcs_garr.exceptions import CertificateNotApprovedException
from tcs_garr.utils import UserRole


class RequestCommand(BaseCommand):
    """
    Command to request a new certificate by generating a CSR or submitting an existing one.

    This command allows the user to generate a Certificate Signing Request (CSR) or provide an existing CSR
    to request a new certificate from the Harica service. The user can choose between different certificate profiles
    (OV or DV), generate a CSR with a common name and alternative names, and submit the request for approval.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    HARICA_SAN_LIMIT = 100
    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args):
        """
        Initializes the RequestCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "request"
        self.help_text = "Request a new certificate"
        self.parser = None

    def configure_parser(self, parser):
        """
        Configures the argument parser for the request command.

        This method defines the arguments for requesting a new certificate:
        - --profile: Specifies the certificate profile (OV or DV).
        - --csr: Path to an existing CSR file.
        - --cn: Common Name for the certificate (used when no CSR is provided).
        - --alt_names: Comma-separated list of alternative names (used with --cn).
        - --wait: Wait for the certificate to be approved (polling).

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        self.parser = parser
        self.parser.add_argument(
            "--profile", default="OV", choices=["OV", "DV"], help="Profile to use between OV or DV. Default: OV"
        )

        self.parser.add_argument("--wait", action="store_true", help="Wait for the certificate to be approved")

        self.parser.add_argument(
            "--disable-webhook",
            action="store_true",
            help="Disable calling webhook after submit request. This works only if webhook_url has been configured",
        )

        # Create a mutually exclusive group for --csr and --cn (plus optional --alt_names)
        create_group = self.parser.add_mutually_exclusive_group(required=True)
        create_group.add_argument("--csr", type=str, help="Path to an existing CSR file.")

        # When no --csr is provided, user must provide --cn (with optional --alt_names)
        create_group.add_argument("--cn", help="Common name of the certificate.")
        self.parser.add_argument("--alt_names", default="", help="Comma-separated alternative names (only used with --cn).")

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
        Executes the command to generate a CSR or request a certificate.

        This method handles the logic to either generate a CSR and submit it or submit an existing CSR.
        It also ensures that the --alt_names argument is only used with the --cn argument.
        """
        # Additional logic to ensure --alt_names is only used with --cn and not with --csr
        if self.args.csr and self.args.alt_names:
            self.parser.error("--alt_names cannot be used with --csr.")
            exit(1)

        if self.args.cn:
            # Generate a CSR and request a certificate
            csr_path = self.__generate_key_csr(self.args.cn, self.args.alt_names, self.harica_config.output_folder)
            cn, certificate_id = self.__issue_certificate(csr_path, self.args.profile)
        else:
            # CSR has been provided, just issue the certificate
            cn, certificate_id = self.__issue_certificate(self.args.csr, self.args.profile)

        if self.args.wait:
            self.__wait_for_certificate_approval(cn, certificate_id)

        if not self.args.disable_webhook:
            self.call_webhook("TLS", cn, certificate_id)

    def __generate_key_csr(self, cn, alt_names, output_folder):
        """
        Generates a private key and CSR for the specified common name and alternative names.

        This method generates an RSA private key, creates a CSR with the provided common name (CN) and alternative
        names (SANs), and saves both the private key and CSR to the specified output folder.

        Args:
            cn (str): The Common Name for the certificate.
            alt_names (str): A comma-separated list of alternative names.
            output_folder (str): The folder where the private key and CSR will be saved.

        Returns:
            str: The file path to the generated CSR.
        """
        # Create the list of domains, including the CN and SANs
        domains = [cn]
        for alt_name in alt_names.split(","):
            if alt_name and alt_name not in domains:
                domains.append(alt_name)

        organizations = self.harica_client.get_matching_organizations(domains)

        if not organizations:
            self.logger.error("No available organization for this domain list")
            return

        if len(organizations) > 1:
            self.logger.error("Multiple orgs possible but no selection made (use -O org)")
            return

        organization = organizations[0]

        self.logger.info(
            f"{Fore.GREEN}Selected organization: {organization['organizationName']} ({organization['id']}){Style.RESET_ALL}"
        )

        # Generate the private key
        key = rsa.generate_private_key(public_exponent=65537, key_size=4096, backend=default_backend())

        # Write the private key to disk
        os.makedirs(output_folder, exist_ok=True)
        key_path = os.path.join(output_folder, f"{cn}.key")
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
        subject_alt_names = [cn]
        for item in alt_names.split(","):
            if item and item not in subject_alt_names:
                subject_alt_names.append(item)

        # Generate a CSR
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(
                x509.Name(
                    [
                        x509.NameAttribute(NameOID.COUNTRY_NAME, organization["country"].upper()),
                        x509.NameAttribute(NameOID.COMMON_NAME, cn),
                    ]
                )
            )
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(x) for x in subject_alt_names]),
                critical=False,
            )
            .sign(key, hashes.SHA512(), default_backend())
        )

        # Write the CSR to disk
        csr_path = os.path.join(output_folder, f"{cn}.csr")
        with open(csr_path, "wb") as f:
            f.write(csr.public_bytes(serialization.Encoding.PEM))
        self.logger.info(f"{Fore.BLUE}CSR created in {csr_path}{Style.RESET_ALL}")

        return csr_path

    def __issue_certificate(self, csr_file, profile):
        """
        Issues a certificate request by submitting a CSR to the Harica client.

        This method reads the provided CSR file, validates it, and submits it to the Harica client for certification.
        It also handles logging and outputs relevant information, including certificate IDs and download instructions.

        Args:
            csr_file (str): The path to the CSR file.
            profile (str): The certificate profile (OV or DV) to use for the request.
        """
        try:
            with open(csr_file, "rb") as f:
                csr = x509.load_pem_x509_csr(f.read(), default_backend())

                cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
                try:
                    alt_names = [x.value for x in csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value]
                except ExtensionNotFound:
                    alt_names = []

                # Check if the number of SANs is HARICA_SAN_LIMIT or more and print a warning
                if len(alt_names) >= self.HARICA_SAN_LIMIT:
                    self.logger.warning(
                        f"{Fore.RED}Warning: Certificates with more than {self.HARICA_SAN_LIMIT} SANs might be refused.{Style.RESET_ALL}"
                    )

                domains = [cn]
                for alt_name in alt_names:
                    if alt_name and alt_name not in domains:
                        domains.append(alt_name)

                self.logger.info(f"{Fore.YELLOW}Submitting CSR to Harica... Please wait...{Style.RESET_ALL}")

                cert_id = self.harica_client.request_certificate(
                    domains, csr.public_bytes(serialization.Encoding.PEM).decode(), profile
                )

                self.logger.info(f"{Fore.GREEN}CSR submitted with certificate ID {cert_id}.{Style.RESET_ALL}")

                id_file = f"{csr_file}.id"
                with open(id_file, "w") as id_f:
                    id_f.write(cert_id)
                self.logger.info(f"{Fore.GREEN}Certificate ID written to {id_file}.{Style.RESET_ALL}")

                self.logger.info(
                    f"Ask another administrator to approve the certificate, using command: \n\ttcs-garr approve --id {cert_id}"
                )
                self.logger.info(
                    f"After administrator approval, you will be able to download it using command: \n\tTo get fullchain: {Fore.BLUE}tcs-garr download --id {cert_id} --output-filename {cn.replace('*', 'wildcard')}_fullchain.pem{Style.RESET_ALL}\n\tTo get only certificate: {Fore.BLUE}tcs-garr download --id {cert_id} --output-filename {cn.replace('*', 'wildcard')}.pem --download-type certificate{Style.RESET_ALL}"
                )
                return cn, cert_id

        except FileNotFoundError:
            self.logger.error(f"{Fore.RED}CSR file {csr_file} not found.{Style.RESET_ALL}")
            exit(1)

    def __wait_for_certificate_approval(self, cn, certificate_id):
        """
        Waits for the certificate to be approved by polling the Harica service.

        This method keeps polling the Harica service until the certificate is approved, with increasing delays
        between retries. If approval is not received after several attempts, it raises an exception.

        Args:
            cn (str): The common name of the certificate.
            certificate_id (str): The ID of the certificate being requested.
        """
        retry_interval = 10  # Start with 10 seconds
        max_retries = 10
        retries = 0

        while retries < max_retries:
            try:
                self.logger.info(f"{Fore.YELLOW}Checking certificate status for ID {certificate_id}...{Style.RESET_ALL}")
                certificate = self.harica_client.get_certificate(certificate_id)

                data_to_write = certificate.get("pemBundle")

                # If no data is found for 'pemBundle', handle the PKCS7 format
                if not data_to_write:
                    # Get the PKCS7 encoded data and decode it
                    p7b_data_string = certificate.get("pKCS7")
                    p7b_base64 = (
                        p7b_data_string.replace("-----BEGIN PKCS7-----", "").replace("-----END PKCS7-----", "").strip()
                    )
                    p7b_data = base64.b64decode(p7b_base64)

                    # Load and extract the certificates from the PKCS7 data
                    if p7b_data:
                        pkcs7_cert = pkcs7.load_der_pkcs7_certificates(p7b_data)
                        if pkcs7_cert:
                            # Convert certificates to PEM format and join them into a single string
                            data_to_write = "".join(
                                cert.public_bytes(serialization.Encoding.PEM).decode("utf-8") for cert in pkcs7_cert
                            )

                if data_to_write:
                    # Determine the output folder from the config
                    output_folder = self.get_output_folder()

                    # If the output folder and filename are provided, save the certificate to a file
                    if output_folder:
                        output_path = os.path.join(output_folder, f"{cn}_fullchain.pem")

                        # Check if the file already exists, and handle the force flag for overwriting
                        if os.path.exists(output_path) and not self.args.force:
                            print(f"File {output_path} already exists. Use --force to overwrite.")
                        else:
                            # Write the certificate data to the file (binary or text based on data type)
                            with open(output_path, "wb" if isinstance(data_to_write, bytes) else "w") as cert_file:
                                cert_file.write(data_to_write)
                            print(f"Certificate saved to {output_path}")
                    else:
                        self.logger("Error saving certificate")
                return

            except CertificateNotApprovedException:
                self.logger.info(
                    f"{Fore.RED}Certificate not yet approved. Retrying in {retry_interval} seconds...{Style.RESET_ALL}"
                )
                retries += 1
                time.sleep(retry_interval)
                retry_interval = min(retry_interval * 2, 300)  # Exponentially increase sleep time up to 5 minutes

        self.logger.error(f"{Fore.RED}Certificate approval timed out after {max_retries} retries.{Style.RESET_ALL}")
        exit(1)
