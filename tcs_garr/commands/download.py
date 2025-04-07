import base64
import importlib.resources as pkg_resources
import os

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs7

from tcs_garr.commands.base import BaseCommand
from tcs_garr.exceptions import CertificateNotApprovedException
from tcs_garr.utils import UserRole


class DownloadCommand(BaseCommand):
    """
    Command to download a certificate by ID and save it to a specified file or print it.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args):
        super().__init__(args)
        self.command_name = "download"
        self.help_text = "Download a certificate by ID"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the command.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Add the argument to specify the certificate ID to download
        parser.add_argument("--id", required=True, help="ID of the certificate to download.")

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

    def get_trusted_intermediates(self):
        """
        Load all trusted intermediate certificates from the 'certs' folder.

        Returns:
            list: A list of x509.Certificate objects representing trusted intermediates.
        """
        trusted_intermediates = []

        # Use importlib.resources to access the package resource directory
        certs_folder = pkg_resources.files("tcs_garr").joinpath("chain")

        if not os.path.exists(certs_folder):
            print(f"Certificate chain folder does not exist: {certs_folder}")
            return trusted_intermediates
        # Loop through all files in the 'chain' folder
        for cert_file in os.listdir(certs_folder):
            cert_path = os.path.join(certs_folder, cert_file)

            # Open and read the PEM certificate
            with open(cert_path, "rb") as f:
                cert_data = f.read()
                # Load the certificate from the PEM file
                try:
                    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                    trusted_intermediates.append(cert)
                except Exception as e:
                    self.logger.error(f"Error loading certificate from {cert_file}: {e}")

        return trusted_intermediates

    def inspect_certificate_chain(self, certificates, trusted_intermediates):
        """
        Inspect the certificate chain to ensure it's complete and valid.

        Args:
            certificates (list): List of x509.Certificate objects.
            trusted_intermediates (list): List of trusted intermediate certificates (x509.Certificate).

        Returns:
            bool: True if the chain is valid and complete, False otherwise.
        """
        # Loop through the chain and check if each certificate is signed by the next one
        for i in range(len(certificates) - 1):
            cert = certificates[i]
            issuer_cert = certificates[i + 1]

            # Check if the issuer of the cert matches the subject of the next cert in the chain
            if cert.issuer != issuer_cert.subject:
                self.logger.error(f"Certificate chain is broken between {cert.subject} and {issuer_cert.subject}.")
                return False

            # Verify the certificate was signed by the next one in the chain
            try:
                issuer_cert.public_key().verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    # Add the correct padding for RSA signatures (PKCS1v15) and the hash algorithm
                    padding.PKCS1v15(),
                    cert.signature_hash_algorithm,
                )
            except Exception as e:
                self.logger.error(f"Certificate chain verification failed: {e}")
                return False

        # Check if the last certificate in the chain is either a trusted intermediate or a root
        last_cert = certificates[-1]
        if last_cert in trusted_intermediates:
            self.logger.debug("The chain terminates with a trusted intermediate.")
            return True
        else:
            self.logger.error("The chain does not terminate with a trusted intermediate or root.")
            return False

    def complete_chain(self, certificates, trusted_intermediates):
        """
        Completes the certificate chain by appending trusted intermediates if the chain is incomplete.

        Args:
            certificates (list): List of x509.Certificate objects (certificate chain from server).
            trusted_intermediates (list): List of trusted intermediate certificates (x509.Certificate).

        Returns:
            list: The completed chain of certificates.
        """
        completed_chain = certificates.copy()

        # Try to complete the chain by appending trusted intermediates
        last_cert = completed_chain[-1]
        while last_cert.issuer != last_cert.subject:
            # Find the matching intermediate whose subject matches the last cert's issuer
            for intermediate in trusted_intermediates:
                if last_cert.issuer == intermediate.subject:
                    self.logger.debug(f"Adding intermediate certificate: {intermediate.subject}")
                    completed_chain.append(intermediate)
                    last_cert = intermediate
                    break
            else:
                break

        return completed_chain

    def execute(self):
        """
        Executes the command to download the certificate by ID, inspect and complete the chain, and save or print the certificate.
        """
        try:
            # if user role is only USER and does not have any other role
            # do not use enterprise apis
            if self.harica_client.has_role(UserRole.USER) and len(self.harica_client.roles) == 1:
                certificate = self.harica_client.get_user_certificate(self.args.id)
            else:
                certificate = self.harica_client.get_certificate(self.args.id)

            if not certificate:
                self.logger.error("Certificate not found.")
                exit(1)

            # Get the data of the specified download type
            data_to_write = certificate.get(self.args.download_type)

            # If no data is found for 'pemBundle', handle the PKCS7 format
            if not data_to_write and self.args.download_type == "pemBundle":
                p7b_data_string = certificate.get("pKCS7")
                p7b_base64 = p7b_data_string.replace("-----BEGIN PKCS7-----", "").replace("-----END PKCS7-----", "").strip()
                p7b_data = base64.b64decode(p7b_base64)

                # Load and extract the certificates from the PKCS7 data
                if p7b_data:
                    pkcs7_cert = pkcs7.load_der_pkcs7_certificates(p7b_data)
                    if pkcs7_cert:
                        certificates = pkcs7_cert

                        # Load trusted intermediates
                        trusted_intermediates = self.get_trusted_intermediates()

                        # Complete the certificate chain with trusted intermediates
                        complete_chain = self.complete_chain(certificates, trusted_intermediates)

                        # Convert certificates to PEM format and join them into a single string
                        data_to_write = "".join(
                            cert.public_bytes(serialization.Encoding.PEM).decode("utf-8") for cert in complete_chain
                        )

                        # Optionally inspect the certificate chain
                        if not self.inspect_certificate_chain(complete_chain, trusted_intermediates):
                            self.logger.error("Certificate chain is not complete or valid.")
                            return

            if data_to_write:
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
                        with open(output_path, "wb" if isinstance(data_to_write, bytes) else "w") as cert_file:
                            cert_file.write(data_to_write)
                        self.logger.info(f"Certificate saved to {output_path}")
                else:
                    # If no filename is provided, print the certificate data
                    print(data_to_write)
            else:
                # Handle case where no data is found for the given certificate ID
                self.logger.error(f"No data found for certificate ID {self.args.id}.")
        except CertificateNotApprovedException:
            self.logger.error(f"Certificate with id {self.args.id} has not been approved yet. Retry later.")
