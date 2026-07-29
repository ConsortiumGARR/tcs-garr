import json
import os
import re
from datetime import datetime, timedelta

import pytz
from colorama import Fore, Style
from dateutil import parser
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand, requires_roles
from tcs_garr.utils import CertificateStatus, UserRole


class ListCertificatesCommand(BaseCommand):
    """
    Command to generate a report of certificates from the Harica service.

    This command lists certificates and optionally filters them based on
    expiration criteria provided by the user, such as certificates that have
    expired since a certain number of days or certificates expiring in the
    next few days.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
        harica_config (HaricaClientConfig): The harica client configuration instance.
    """

    REQUIRED_ROLE = UserRole.USER  # Base requirement for the whole command

    def __init__(self, args, harica_config):
        """
        Initialize the ListCertificates class.

        Sets the `command_name` and `help_text` attributes for this command.
        The command name is "list", and it is used to generate reports about
        certificates. The `help_text` provides a brief description of the command.
        """
        super().__init__(args, harica_config)
        self.command_name = "list"  # Set the command name to "list"
        self.help_text = "List and filter certificates"  # Help text for the command

    def configure_parser(self, parser):
        """
        Configure the argument parser for the list certificates command.

        This method adds optional arguments to filter certificates based on
        expiration dates. The user can specify certificates that have expired
        since a certain number of days or certificates that will expire in
        a certain number of days.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        # Add an optional argument to filter certificates that have expired since a given number of days
        parser.add_argument(
            "--expired-since",
            type=int,
            help="List certificates whose expiry date is X days before now.",
        )

        # Add an optional argument to filter certificates that will expire in a given number of days
        parser.add_argument(
            "--expiring-in",
            type=int,
            help="List certificates whose expiry date is X days after now.",
        )

        # Add an optional argument to filter certificates status. Default is valid.
        parser.add_argument(
            "--status",
            type=CertificateStatus,
            choices=list(CertificateStatus),
            action="append",
            help="Filter certificates by status. Default is valid.",
        )

        # Add an optional flag user to filter certificates by email
        parser.add_argument(
            "--user",
            nargs="?",
            const=True,
            default=None,
            help=(
                "Filter certificates owner by user. Without arg (--user only) will "
                "filter for the logged in user. "
                "Use this if you have Approver role or Admin role."
            ),
        )

        # Add an optional argument to filter certificates by FQDN
        parser.add_argument(
            "--fqdn",
            type=str,
            help="Filter certificates by a substring in their Fully Qualified Domain Name (FQDN).",
        )

        # Add full info flag
        parser.add_argument(
            "--full",
            action="store_true",
            help="Retrieve full certificate information.",
        )

        # Add export flag
        parser.add_argument(
            "--export",
            nargs="?",
            const=True,
            default=None,
            help=(
                "Export certificates to json file. Without arg uses default file, "
                "with arg specifies output file (e.g. --export output.json)."
            ),
        )

        # Add json flag as an alias for export
        parser.add_argument(
            "--json",
            nargs="?",
            const=True,
            default=None,
            help="Alias for --export. Export certificates to json file.",
        )

        # Add an optional flag type to filter certificates by type.
        parser.add_argument(
            "--type",
            type=str,
            choices=["ACME", "API"],
            help="Filter certificates by type.",
        )

        # Add an optional flag to filter certificates by acme account id
        parser.add_argument(
            "--acme-account-id",
            type=str,
            help="Filter certificates by acme account id.",
        )

    def _normalize_certificate(self, cert):
        """
        Normalize certificate data to have consistent field names for both API and ACME certificates.

        Args:
            cert (dict): Certificate data

        Returns:
            dict: Normalized certificate data
        """
        normalized = cert.copy()

        # Detect if this is an ACME certificate by checking for ACME-specific fields
        is_acme = "acmeEntryId" in cert or ("dn" in cert and "dN" not in cert)

        if is_acme:
            # Normalize ACME certificate fields
            normalized["certificateValidTo"] = cert.get("validTo", "")
            normalized["dN"] = cert.get("dn", "")
            normalized["status"] = cert.get("statusName", "")
            normalized["transactionId"] = cert.get("id", "")
            normalized["transactionStatusMessage"] = cert.get("statusName", "")
            normalized["user"] = cert.get("revokedByEmail", "ACME")  # ACME certs don't have user field
            normalized["userEmail"] = cert.get("userEmail", "")

            # Parse domains from SANS field for ACME certificates
            domains = []
            sans = cert.get("sans", "")
            if sans:
                # Extract DNS names from SANS string (format: "DNS Name=example.com")
                dns_matches = re.findall(r"DNS Name=([^,\s]+)", sans)
                for dns_name in dns_matches:
                    domains.append({"fqdn": dns_name})

            # If no SANS, try to extract from DN
            if not domains and normalized["dN"]:
                cn_match = re.search(r"CN=([^,]+)", normalized["dN"])
                if cn_match:
                    domains.append({"fqdn": cn_match.group(1)})

            normalized["domains"] = domains
            normalized["is_acme"] = True
        else:
            # API certificate - ensure all fields exist
            normalized["certificateValidTo"] = cert.get("certificateValidTo", "")
            normalized["dN"] = cert.get("dN", "")
            normalized["status"] = cert.get("status", "")
            normalized["transactionId"] = cert.get("transactionId", "")
            normalized["transactionStatusMessage"] = cert.get("transactionStatusMessage", "")
            normalized["user"] = cert.get("user", "")
            normalized["userEmail"] = cert.get("userEmail", "")
            normalized["domains"] = cert.get("domains", [])
            normalized["is_acme"] = False

        return normalized

    def _filter_certificates(self, certificates, statuses, username=None):
        """
        Apply filters to the list of certificates based on status, username, and FQDN.

        Args:
            certificates (list): List of certificate dictionaries.
            statuses (list): List of statuses to filter certificates by.
            username (str, optional): Username to filter certificates by.

        Returns:
            list: Filtered list of certificates.
            dict: Recap of filtered certificates.
        """
        # Normalize all certificates first
        normalized_certificates = [self._normalize_certificate(cert) for cert in certificates]

        # Filter by username
        if username:
            normalized_certificates = [cert for cert in normalized_certificates if cert["userEmail"] == username]

        # Filter by status
        normalized_certificates = [
            cert for cert in normalized_certificates if cert.get("status", "") in [status.value for status in statuses]
        ]

        # Filter by FQDN
        fqdn_filter = self.args.fqdn
        if fqdn_filter:
            normalized_certificates = [
                cert
                for cert in normalized_certificates
                if any(fqdn_filter in domain["fqdn"] for domain in cert.get("domains", []))
            ]

        # Filter by type. If an acme account id is provided, skip this filter.
        if self.args.type and not self.args.acme_account_id:
            normalized_certificates = [
                cert for cert in normalized_certificates if cert.get("is_acme") == (self.args.type == "ACME")
            ]

        # Build recap
        recap = {"count": len(normalized_certificates)}
        for cert in normalized_certificates:
            status_name = cert["status"]
            recap.setdefault(status_name, 0)
            recap[status_name] += 1

        return normalized_certificates, recap

    def _get_cn_value(self, item):
        """
        Determine the CN value for a certificate.

        Order of selection:

        1. Look for CN in dN
        2. If domains length is 1, return fqdn as CN
        3. Look in domains for fqdn that starts exactly with friendlyName + "."
        4. Find exact friendlyName in domains
        5. Otherwise, return friendlyName

        Args:
            item (dict): Data containing `dN`, `friendlyName`, and `domains`

        Returns:
            str: The selected Common Name value
        """
        friendly_name = item.get("friendlyName") or ""

        # 1. Look for CN in dN
        if item.get("dN"):
            match = re.search(r"CN=([^,]+)", item["dN"])
            if match:
                return match.group(1)

        # 2. If domains len is 1, return fqdn
        if item.get("domains") and len(item["domains"]) == 1:
            return item["domains"][0]["fqdn"]

        # 3. Look in domains for fqdn that starts with friendlyName + "."
        cn_value = next(
            (domain["fqdn"] for domain in item.get("domains", []) if domain["fqdn"].startswith(f"{friendly_name}.")),
            "",
        )

        # 4. If cn_value is empty, find exact friendlyName in domains
        if not cn_value:
            cn_value = next(
                (domain["fqdn"] for domain in item.get("domains", []) if domain["fqdn"] == friendly_name),
                "",
            )

        # Return cn_value or "CN not found"
        return cn_value if cn_value else "CN not found"

    @requires_roles(UserRole.ENTERPRISE_ADMIN, UserRole.SSL_ENTERPRISE_APPROVER, logic="AND")
    def list_certificates_as_admin(self, username, statuses, full_info=False):
        """
        List certificates as admin user

        Args:
            username (str): Username to filter certificates by
            statuses (list): List of certificate statuses to filter

        Returns:
            list: List of certificates
            dict: Recap
        """
        certificates = []

        for status in statuses:
            # If an acme account id is provided, do not retrieve api certificates
            if not self.args.acme_account_id:
                start_index = 0
                while True:
                    response = self.harica_client.list_certificates(
                        start_index=start_index, status=status, full_info=full_info
                    )

                    if not response:
                        break

                    certificates.extend(response)
                    start_index += len(response)

            # Add also acme certificates
            acme_certificates = self.harica_client.list_acme_certificates(
                id=self.args.acme_account_id,
                status=status,
            )
            certificates.extend(acme_certificates)

        return self._filter_certificates(certificates, statuses, username)

    def list_certificates_as_user(self, statuses, full_info=False):
        """
        List certificates as a regular user.

        Args:
            statuses (list): List of certificate statuses to filter.

        Returns:
            list: List of certificates.
            dict: Recap.
        """
        certificates = self.harica_client.list_user_certificates(full_info)
        return self._filter_certificates(certificates, statuses)

    def execute(self):
        """
        Execute the list certificates command to retrieve and display certificates.

        This method fetches certificates from the Harica client and optionally filters
        them based on expiration criteria (expired since a number of days or expiring
        in a number of days). The filtered certificates are then displayed in a tabular format.

        Args:
            args: Parsed command-line arguments that include optional filters for
                  certificate expiration dates.
        """
        # Load configs
        conf_user = self.harica_config.username
        output_folder = self.harica_config.output_folder

        # Get the current UTC date and time
        current_date = pytz.utc.localize(datetime.now())

        # Calculate the date range based on expired_since or expiring_in arguments, if provided
        from_date = current_date - timedelta(days=self.args.expired_since) if self.args.expired_since is not None else None
        to_date = current_date + timedelta(days=self.args.expiring_in) if self.args.expiring_in is not None else None

        # Get username if specified in args
        # True when --user without arg
        username = conf_user if self.args.user is True else self.args.user

        # Set default status to valid
        if not self.args.status:
            self.args.status = [CertificateStatus.VALID]

        # Build the list of statuses in case of ALL.
        # Otherwise, use the provided statuses
        statuses = (
            [s for s in CertificateStatus if s != CertificateStatus.ALL]
            if CertificateStatus.ALL in self.args.status
            else self.args.status
        )

        # Determine if we need to handle JSON output (either --export or --json is provided)
        export_setting = self.args.export if self.args.export is not None else self.args.json

        # Use full_info flag directly from args
        full_info = self.args.full

        # Retrieve the list of certificates from the Harica client
        # Handle pagination and statues if admin
        self.logger.info(f"{Fore.BLUE}Retrieving certificates...{Style.RESET_ALL}")

        # if user role is only USER and does not have any other role
        # get only user certificates
        if self.harica_client.has_role(UserRole.USER) and len(self.harica_client.roles) == 1:
            certificates, recap = self.list_certificates_as_user(statuses, full_info=full_info)
        else:
            certificates, recap = self.list_certificates_as_admin(username, statuses, full_info=full_info)

        # Replace None value with datemin and convert to string
        # This will facilitate sorting
        for cert in certificates:
            if not cert.get("certificateValidTo"):
                cert["certificateValidTo"] = datetime.min.replace(microsecond=0).isoformat()

        # Sort certificates by the 'certificateValidTo' field
        certificates.sort(key=lambda x: x["certificateValidTo"], reverse=True)

        # Handle JSON output if --export or --json is provided
        if export_setting is not None:
            # Filter certificates based on date range if specified
            filtered_certificates = []
            for cert in certificates:
                expire_date_str = cert.get("certificateValidTo", "")
                if not expire_date_str or expire_date_str == datetime.min.replace(microsecond=0).isoformat():
                    expire_date = datetime.min.replace(tzinfo=pytz.utc)
                else:
                    expire_date_naive = parser.isoparse(expire_date_str)
                    expire_date = (
                        pytz.utc.localize(expire_date_naive) if expire_date_naive.tzinfo is None else expire_date_naive
                    )

                if (from_date is None or expire_date <= from_date) and (to_date is None or expire_date < to_date):
                    filtered_certificates.append(cert)

            # Determine output file path
            if export_setting is True:  # No arg provided, use default file
                output_file = os.path.join(output_folder, "certificates.json")
            else:  # Use the provided filename
                output_file = export_setting

            # Save to file
            with open(output_file, "w") as f:
                json.dump(filtered_certificates, f, indent=4)
                self.logger.info(f"JSON data exported to {output_file}")

            # Only output the JSON to terminal if no filename specified (just --export or --json without args)
            if export_setting is True:
                print(json.dumps(filtered_certificates, indent=4))

            # Exit early as we don't need to show tabular output
            return

        # Initialize a list to store certificate data for tabular display
        data = []

        for item in certificates:
            # Parse the expiration date and convert to UTC - handle empty/None values
            expire_date_str = item.get("certificateValidTo", "")
            if not expire_date_str or expire_date_str == datetime.min.replace(microsecond=0).isoformat():
                expire_date = datetime.min.replace(tzinfo=pytz.utc)
            else:
                expire_date_naive = parser.isoparse(expire_date_str)
                expire_date = pytz.utc.localize(expire_date_naive) if expire_date_naive.tzinfo is None else expire_date_naive

            # Filter certificates based on the provided date range
            if (from_date is None or expire_date <= from_date) and (to_date is None or expire_date < to_date):
                # Determine the Common Name value
                cn_value = self._get_cn_value(item)

                # Ensure all values are properly converted to strings and handle None values
                transaction_id = str(item.get("transactionId", ""))
                expiration_date = str(item.get("certificateValidTo", ""))
                status = str(item.get("status", ""))
                status_info = str(item.get("transactionStatusMessage", ""))
                user = str(item.get("user") or item.get("userEmail") or "")

                # Add certificate type indicator
                cert_type = "ACME" if item.get("is_acme", False) else "API"

                alt_names = ";\n".join(domain.get("fqdn", "") for domain in item.get("domains", []) if domain.get("fqdn"))

                data.append([transaction_id, cn_value, expiration_date, status, status_info, alt_names, user, cert_type])

        # Log the results in a formatted table with headers, using color for column titles
        self.logger.info(
            tabulate(
                data,
                headers=[
                    Fore.BLUE + "ID",
                    "Common Name",
                    "Expire at",
                    "Status",
                    "Info",
                    "Alt Names",
                    "Requested by",
                    "Type" + Style.RESET_ALL,
                ],
                tablefmt="grid",
                maxcolwidths=[None, 32, None, None, 32, None, 20, None] if data else None,
            )
        )

        # Write a recap of certificate count by status
        self.logger.info(f"Total certificates: {recap['count']}")
        for status in CertificateStatus:
            if status.value in recap:
                self.logger.info(f"Certificates with status {status.name}: {recap[status.value]}")
