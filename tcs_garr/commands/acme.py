from colorama import Fore, Style
from tabulate import tabulate

from tcs_garr.commands.base import BaseCommand
from tcs_garr.utils import UserRole, format_date_and_check_expiry


class AcmeAccountsCommand(BaseCommand):
    """
    Command to list available acme accounts and display their details.


    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    REQUIRED_ROLE = UserRole.ENTERPRISE_ADMIN

    def __init__(self, args, harica_config):
        super().__init__(args, harica_config)
        self.command_name = "acme"
        self.help_text = "List ACME accounts configured in Harica"

    def configure_parser(self, parser):
        """
        Configure the argument parser for the acme command.

        Args:
            parser: An argparse.ArgumentParser object used for parsing command-line arguments.
        """
        subparsers = parser.add_subparsers(dest="action")

        # Subcommand to list ACME accounts
        list_parser = subparsers.add_parser("list", help="List all ACME accounts")
        list_parser.add_argument("--show-disabled", action="store_true", help="Show also disabled ACME accounts")

        # Subcommand to get info on a specific ACME account
        info_parser = subparsers.add_parser("info", help="Get information on a specific ACME account including secrets")
        info_parser.add_argument("account_id", type=str, help="ID of the ACME account to retrieve information for")

        # Subcommand to create a new ACME account
        create_parser = subparsers.add_parser("create", help="Create a new ACME account")
        create_parser.add_argument("friendly_name", type=str, help="Friendly name for the new ACME account")
        create_parser.add_argument(
            "--transaction_type",
            type=str,
            default="SSL OV",
            choices=["SSL OV", "SSL DV"],
            help="Transaction type for the new ACME account",
        )

        # Subcommand to disable an ACME account
        disable_parser = subparsers.add_parser("disable", help="Disable an ACME account")
        disable_parser.add_argument("account_id", type=str, help="ID of the ACME account to disable")

        # Subcommand for domains
        domains_parser = subparsers.add_parser("domains", help="Perform actions on ACME account domains and rules")
        domains_parser.add_argument("account_id", type=str, help="ID of the ACME account to retrieve domains for")
        domains_parser.add_argument("--list", action="store_true", help="List available domains for the ACME account")
        domains_parser.add_argument("--active", action="store_true", help="List active rules for the ACME account")
        domains_parser.add_argument("--inactive", action="store_true", help="List inactive rules for the ACME account")

        # Subsubcommand for domain to add or remove rules
        domains_subparsers = domains_parser.add_subparsers(dest="domain_action")

        # Add
        add_parser = domains_subparsers.add_parser("add", help="Add a domain rule to an ACME account")
        add_parser.add_argument("domain", type=str, nargs="?", help="Domain to add to the ACME account (e.g., mydomain.tld)")
        add_parser.add_argument("--all", action="store_true", help="Add all domains to the ACME account")
        add_parser.add_argument(
            "--subdomain", type=str, help="Subdomain to add to the ACME account (e.g., subdomain.mydomain.tld)"
        )
        add_parser.add_argument(
            "--no-subdomains",
            action="store_false",
            help="Do NOT apply the domain to subdomains (default: applies to subdomains)",
        )

        add_parser.add_argument(
            "--not-allowed",
            action="store_false",
            help="Mark the domain as NOT allowed (default: allowed)",
        )

        # Remove
        remove_parser = domains_subparsers.add_parser("remove", help="Remove a domain rule from an ACME account")
        remove_parser.add_argument(
            "rule_id",
            type=str,
            help="Rule ID to remove from the ACME account. Use '--active' or '--inactive' to list rules to remove.",
        )

    def execute(self):
        """
        Executes the command to list ACME accounts from Harica.
        """
        action = self.args.action

        if action == "list":
            self._list_accounts(self.args.show_disabled)
        elif action == "info":
            self._account_info(self.args.account_id)
        elif action == "create":
            self._create_account(self.args.friendly_name, self.args.transaction_type)
        elif action == "disable":
            self.logger.info(f"{Fore.YELLOW}Disabling ACME account:{Style.RESET_ALL}\n")
            self._account_info(self.args.account_id)

            confirm = input(f"{Fore.RED}Are you sure you want to disable this ACME account? (Y/n): {Style.RESET_ALL}")
            if confirm == "Y":
                self._disable_account()
            else:
                self.logger.info("Operation cancelled.")
        elif action == "domains":
            domain_action = self.args.domain_action

            if not domain_action:
                if self.args.list:
                    self._list_available_domains()

                domains = []

                # Avoid calling the API twice if both --active and --inactive are
                # specified
                if self.args.active or self.args.inactive:
                    domains = self.harica_client.get_acme_domains(self.args.account_id)

                if self.args.active:
                    self._list_active_inactive_domains(domains, True)
                if self.args.inactive:
                    self._list_active_inactive_domains(domains, False)

            elif domain_action == "add":
                if not self.args.all and not self.args.domain:
                    self.logger.error("You must specify either a domain or --all when adding domains.")
                    return

                if self.args.all:
                    confirm = input(
                        f"{Fore.RED}Are you sure you want to add all domains to account ID '{self.args.account_id}'? (Y/n): {Style.RESET_ALL}"
                    )
                    if confirm == "Y":
                        self._add_all_domains()
                    else:
                        self.logger.info("Operation cancelled.")
                elif self.args.domain:
                    self._add_domain_rule()

            elif domain_action == "remove":
                if self.args.rule_id:
                    self._remove_domain_rule()

    def _list_available_domains(self):
        """List available domains for an ACME account."""
        self.logger.info(f"{Fore.BLUE}Listing available domains for account ID: {self.args.account_id}{Style.RESET_ALL}\n")
        domains = self.harica_client.get_acme_available_domains(self.args.account_id)
        table_data = []

        for domain in domains:
            domain_name = domain.get("domain")
            validity, expired = format_date_and_check_expiry(domain.get("validity"))
            expired_str = "Yes" if expired else "No"
            color = Fore.RED if expired else ""

            table_data.append(
                [
                    f"{color}{domain_name}{Style.RESET_ALL}",
                    f"{color}{validity}{Style.RESET_ALL}",
                    f"{color}{expired_str}{Style.RESET_ALL}",
                ]
            )

        self.logger.info(
            tabulate(
                table_data,
                headers=[
                    f"{Fore.BLUE}Domain",
                    "Validity",
                    f"Expired{Style.RESET_ALL}",
                ],
                tablefmt="grid",
            )
        )

    def _list_active_inactive_domains(self, domains: list[dict], active: bool):
        """List active or inactive domains for an ACME account.

        Parameters
        ----------
        domains : list[dict]
            List of active and inactive domains
        active : bool
            Whether to list active or inactive domains

        """
        self.logger.info(
            f"{Fore.BLUE}Listing {'active' if active else 'inactive'} domains for account ID: {self.args.account_id}{Style.RESET_ALL}\n"
        )
        table_data = []

        for domain in domains:
            enabled = domain.get("isEnabled")

            if active and not enabled:
                continue

            if not active and enabled:
                continue

            rule_id = domain.get("id")
            fqdn = domain.get("fqdn")
            allow_subdomains = "Yes" if domain.get("allowSubdomains") else "No"
            is_allowed = "Yes" if domain.get("isAllowed") else "No"

            table_data.append(
                [
                    rule_id,
                    fqdn,
                    is_allowed,
                    allow_subdomains,
                ]
            )

        self.logger.info(
            tabulate(
                table_data,
                headers=[
                    "Rule ID",
                    "Domain",
                    "Allowed",
                    "Rules applies to subdomains",
                ],
                tablefmt="grid",
            )
        )

    def _add_all_domains(self):
        """Add all available domains to an ACME account."""
        self.logger.info(f"Adding all available domains to account ID: {self.args.account_id}")
        res = self.harica_client.acme_allow_all_domains(self.args.account_id)

        if res:
            self.logger.info(
                f"{Fore.GREEN}Successfully added all available domains to account ID: {self.args.account_id}{Style.RESET_ALL}"
            )
            self.logger.info(f"Run 'tcs-garr acme domains {self.args.account_id} --active' to see the new domains")
        else:
            self.logger.error(
                f"{Fore.RED}Failed to add all available domains to account ID: {self.args.account_id}{Style.RESET_ALL}"
            )

    def _add_domain_rule(self):
        """Add a domain rule to an ACME account."""

        def is_subdomain_of(subdomain: str, domain: str) -> bool:
            """Check if subdomain is a subdomain of domain.

            Parameters
            ----------
            subdomain : str
                Subdomain
            domain : str
                Domain

            Returns
            -------
            bool
                True if subdomain is a subdomain of domain, False otherwise
            """
            # Quick sanity: domain must be non-empty and contain at least one dot
            if not domain or "." not in domain:
                return False

            # Also subdomain must contain at least one dot (not bare name)
            if "." not in subdomain:
                return False

            # Check if subdomain ends with "." + domain or equals domain
            # but to be subdomain it must be strictly longer and domain must be suffix after a dot
            if subdomain == domain:
                return False  # same domain is not a subdomain

            # Ensure subdomain ends with domain preceded by a dot
            if subdomain.endswith(f".{domain}"):
                return True

            return False

        self.logger.info(f"Adding domain '{self.args.domain}' to account ID: {self.args.account_id}")

        # Sanitize domains and check subdomains
        self.args.domain = self.args.domain.lower()

        if self.args.subdomain:
            self.args.subdomain = self.args.subdomain.lower()

            if not is_subdomain_of(self.args.subdomain, self.args.domain):
                self.logger.error(
                    f"{Fore.RED}Subdomain '{self.args.subdomain}' must be a subdomain of domain '{self.args.domain}'.{Style.RESET_ALL}"
                )
                return

        try:
            res = self.harica_client.create_acme_domain_rule(
                self.args.account_id,
                self.args.domain,
                subdomain=self.args.subdomain,
                applies_to_subdomains=self.args.no_subdomains,
                allowed=self.args.not_allowed,
            )

            target_domain = self.args.subdomain if self.args.subdomain else self.args.domain

            if res:
                self.logger.info(
                    f"{Fore.GREEN}Successfully added domain rule '{target_domain}' to account ID: {self.args.account_id}{Style.RESET_ALL}"
                )
                self.logger.info(f"Run 'tcs-garr acme domains {self.args.account_id} --active' to see the active domain rules")
            else:
                self.logger.error(
                    f"{Fore.RED}Failed to add domain rule '{target_domain}' to account ID: {self.args.account_id}{Style.RESET_ALL}"
                )
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to add domain rule: {e}{Style.RESET_ALL}")

    def _remove_domain_rule(self):
        """Remove a domain rule from an ACME account."""
        self.logger.info(f"Removing domain '{self.args.rule_id}' from account ID: {self.args.account_id}")

        try:
            res = self.harica_client.remove_acme_domain_rule(self.args.rule_id)

            if res:
                self.logger.info(
                    f"{Fore.GREEN}Successfully removed domain rule with ID: {self.args.rule_id} from account ID: {self.args.account_id}{Style.RESET_ALL}"
                )
                self.logger.info(
                    f"Run 'tcs-garr acme domains {self.args.account_id} --inactive' to see the inactive domain rules"
                )
            else:
                self.logger.error(
                    f"{Fore.RED}Failed to remove domain rule with ID: {self.args.rule_id} from account ID: {self.args.account_id}{Style.RESET_ALL}"
                )
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to remove domain rule: {e}{Style.RESET_ALL}")

    def _format_account_output(self, account, show_secrets=False) -> str:
        """Format an ACME account entry for display.

        Parameters
        ----------
        account : dict
            ACME account entry.
        show_secrets : bool, optional
            Whether to include secrets in the output, by default False

        Returns
        -------
        str
            Formatted output string.

        """
        id = account.get("id", "N/A")
        friendly_name = account.get("friendlyName", "N/A")
        email = account.get("userEmail", "N/A")
        entity = account.get("entityName", "N/A")
        acme_url = account.get("acmeServerUrl", "N/A")
        created_at = account.get("createdAt", "N/A")
        notes = account.get("notes", None)
        is_enabled = account.get("isEnabled", False)
        type = account.get("transactionTypeName", "N/A")
        last_time_used = account.get("lastTimeUsed", "N/A")

        try:
            created_str, _ = format_date_and_check_expiry(created_at)
        except ValueError:
            created_str = "Unknown"

        status_color = Fore.GREEN if is_enabled else Fore.RED
        status_str = "ENABLED" if is_enabled else "DISABLED"

        output = (
            f"{status_color}{friendly_name}{Style.RESET_ALL} "
            f"({entity}) - {email}\n"
            f"  ID: {id}\n"
            f"  Status: {status_color}{status_str}{Style.RESET_ALL}\n"
            f"  Type: {type}\n"
            f"  Created: {created_str}\n"
            f"  Last time used: {last_time_used}"
        )

        if notes:
            output += f"\n  Notes: {notes}"

        # Add acme url here
        output += f"\n  ACME URL: {acme_url}"

        if show_secrets:
            key_id = account.get("keyId", "N/A")
            hmac_key = account.get("hmacKey", "N/A")
            output += f"\n  Key ID: {key_id}\n  HMAC Key: {hmac_key}"

        return output

    def _list_accounts(self, show_disabled=False):
        """Lists all ACME accounts configured in Harica."""
        try:
            accounts = self.harica_client.list_acme_accounts()
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to retrieve ACME accounts: {e}{Style.RESET_ALL}")
            return

        if not accounts:
            self.logger.info(f"{Fore.YELLOW}No ACME accounts found.{Style.RESET_ALL}")
            return

        self.logger.info(f"{Fore.CYAN}ACME account(s):{Style.RESET_ALL}\n")

        count = {"enabled": 0, "disabled": 0}

        for account in accounts:
            enabled = account.get("isEnabled", False)
            count["disabled" if not enabled else "enabled"] += 1

            # Flag not provided and account is disabled
            if not show_disabled and not enabled:
                continue

            output = self._format_account_output(account)
            self.logger.info(f"{output}\n")

        self.logger.info(f"{Fore.CYAN}Summary:{Style.RESET_ALL}")
        self.logger.info(f"  Enabled: {Fore.GREEN}{count['enabled']}{Style.RESET_ALL}")
        self.logger.info(f"  Disabled: {Fore.RED}{count['disabled']}{Style.RESET_ALL}\n")

        self.logger.info(
            f"{Fore.CYAN}To see more details about an ACME account, use "
            f"the 'info' subcommand with the account ID.{Style.RESET_ALL}"
        )

        if not show_disabled:
            self.logger.info(
                f"{Fore.CYAN}To also display disabled ACME accounts, use "
                "the 'list' subcommand with the '--show-disabled' "
                f"flag.{Style.RESET_ALL}"
            )

    def _account_info(self, account_id: str):
        """Displays information about a specific ACME account.

        Parameters
        ----------
        account_id : str
            The ID of the ACME account.

        """
        try:
            accounts = self.harica_client.list_acme_accounts()
            account = next((a for a in accounts if a.get("id") == account_id), None)
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to retrieve ACME accounts: {e}{Style.RESET_ALL}")
            return

        if not account:
            self.logger.error(f"{Fore.RED}ACME account not found.{Style.RESET_ALL}")
            return

        output = self._format_account_output(account, show_secrets=True)
        self.logger.info(f"{output}\n")

    def _create_account(self, friendly_name: str, transaction_type: str):
        """Creates a new ACME account.

        Parameters
        ----------
        friendly_name : str
            Friendly name for the ACME account.
        transaction_type : str
            Type of ACME transaction (e.g., "SSL DV" or "SSL OV")

        """
        try:
            account = self.harica_client.create_acme_account(friendly_name=friendly_name, transaction_type=transaction_type)

            if not account:
                self.logger.error(f"{Fore.RED}Failed to create ACME account.{Style.RESET_ALL}")
                return

            self.logger.info(f"{Fore.GREEN}ACME account created successfully:{Style.RESET_ALL}\n")

            output = self._format_account_output(account, show_secrets=True)
            self.logger.info(f"{output}\n")
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to create ACME account: {e}{Style.RESET_ALL}")

    def _disable_account(self):
        """Disable an ACME account."""
        try:
            res = self.harica_client.disable_acme_account(self.args.account_id)

            if res:
                self.logger.info(
                    f"{Fore.GREEN}Successfully disabled ACME account with ID: {self.args.account_id}{Style.RESET_ALL}"
                )
            else:
                self.logger.error(f"{Fore.RED}Failed to disable ACME account with ID: {self.args.account_id}{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"{Fore.RED}Failed to disable ACME account: {e}{Style.RESET_ALL}")
