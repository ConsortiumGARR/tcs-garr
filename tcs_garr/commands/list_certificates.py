import json
import os
import re
from datetime import datetime, timedelta

import pytz
from colorama import Fore, Style
from dateutil import parser
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import CertificateStatus, UserRole


class ListCertificatesCommand(BaseCommand):
    """
    Command to generate a report of certificates from the Harica service.

    This command lists certificates and optionally filters them based on
    expiration criteria provided by the user, such as certificates that have
    expired since a certain number of days or certificates expiring in the
    next few days.
    """

    REQUIRED_ROLE = UserRole.USER

    def __init__(self, args):
        """
        Initialize the ListCertificates class.

        Sets the `command_name` and `help_text` attributes for this command.
        The command name is "list", and it is used to generate reports about
        certificates. The `help_text` provides a brief description of the command.
        """
        super().__init__(args)
        self.command_name = "list"  # Set the command name to "list"
        self.help_text = "Generate a report from Harica"  # Help text for the command

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

        # Add export flag
        parser.add_argument(
            "--export",
            action="store_true",
            help="Export certificates to json file.",
        )

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
        # Filter by username
        if username:
            certificates = [cert for cert in certificates if cert["userEmail"] == username]

        # Filter by status
        certificates = [cert for cert in certificates if cert.get("status", "") in [status.value for status in statuses]]

        # Filter by FQDN
        fqdn_filter = self.args.fqdn
        if fqdn_filter:
            certificates = [
                cert for cert in certificates if any(fqdn_filter in domain["fqdn"] for domain in cert.get("domains", []))
            ]

        # Build recap
        recap = {"count": len(certificates)}
        for cert in certificates:
            status_name = cert["status"]
            recap.setdefault(status_name, 0)
            recap[status_name] += 1

        return certificates, recap

    def get_cn_value(self, item):
        """
        Determine the CN value for a certificate.

        Order of selection:

        1. Look for CN in dN
        2. If domains length is 1, return fqdn as CN
        3. Look in domains for fqdn that starts exactly with friendlyName + "."
        4. Find exact friendlyName in domains
        4. Otherwise, return friendlyName

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

    def list_certificates_as_admin(self, username, statuses):
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
            start_index = 0
            while True:
                response = self.harica_client.list_certificates(
                    start_index=start_index,
                    status=status,
                )

                if not response:
                    break

                certificates.extend(response)
                start_index += len(response)

        return self._filter_certificates(certificates, statuses, username)

    def list_certificates_as_user(self, statuses):
        """
        List certificates as a regular user.

        Args:
            statuses (list): List of certificate statuses to filter.

        Returns:
            list: List of certificates.
            dict: Recap.
        """
        certificates = self.harica_client.list_user_certificates()
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

        # Retrieve the list of certificates from the Harica client
        # Handle pagination and statues if admin

        # if user role is only USER and does not have any other role
        # get only user certificates
        if self.harica_client.has_role(UserRole.USER) and len(self.harica_client.roles) == 1:
            certificates, recap = self.list_certificates_as_user(statuses)
        else:
            certificates, recap = self.list_certificates_as_admin(
                username,
                statuses,
            )

        # Replace None value with datemin and convert to string
        # This will facilitate sorting
        for cert in certificates:
            if not cert["certificateValidTo"]:
                cert["certificateValidTo"] = datetime.min.replace(microsecond=0).isoformat()

        # Sort certificates by the 'certificateValidTo' field
        certificates.sort(key=lambda x: x["certificateValidTo"], reverse=True)

        if self.args.export:
            with open(os.path.join(output_folder, "certificates.json"), "w") as f:
                json.dump(certificates, f, indent=4)

        # Initialize a list to store certificate data for tabular display
        data = []

        for item in certificates:
            # Parse the expiration date and convert to UTC
            expire_date_naive = parser.isoparse(item["certificateValidTo"])
            expire_date = pytz.utc.localize(expire_date_naive)

            # Filter certificates based on the provided date range
            if (from_date is None or expire_date <= from_date) and (to_date is None or expire_date < to_date):
                # Determine the Common Name value
                cn_value = self.get_cn_value(item)

                transaction_id = item["transactionId"]
                expiration_date = item["certificateValidTo"]
                status = item["status"]
                status_info = item["transactionStatusMessage"]
                user = item["user"]

                alt_names = ";\n".join(domain["fqdn"] for domain in item.get("domains", []))

                data.append([transaction_id, cn_value, expiration_date, status, status_info, alt_names, user])

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
                    "Requested by" + Style.RESET_ALL,
                ],
                tablefmt="grid",
                maxcolwidths=[None, 32, None, None, 32, None, 20] if data else None,
            )
        )

        # Write a recap of certificate count by status
        self.logger.info(f"Total certificates: {recap['count']}")
        for status in CertificateStatus:
            if status.value in recap:
                self.logger.info(f"Certificates with status {status.name}: {recap[status.value]}")
