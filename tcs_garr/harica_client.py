import csv
import io
import json
import logging
import time
import zipfile
from threading import Lock
from urllib.parse import urljoin, urlparse

import jwt
import requests
from bs4 import BeautifulSoup

from .exceptions import CertificateNotApprovedException, ErrorPageError, RateLimitError

from .utils import generate_otp, CertificateStatus, UserRole

# Initialize logger
logger = logging.getLogger(__name__)

# "Unspecified", used by tcs-garr before reasons were selectable
DEFAULT_REVOCATION_REASON = "4.9.1.1.1.1"

# CA/B Forum Baseline Requirements domain validation methods offered to enterprise admins
DOMAIN_VALIDATION_METHODS = {
    "dns": "3.2.2.4.7",  # DNS Change
    "email": "3.2.2.4.4",  # Constructed Email to Domain Contact
}
# Enterprise validator endpoints, same actions for S/MIME and Client Authentication
ENTERPRISE_VALIDATOR_ENDPOINTS = {
    "smime": {
        "requests": "/api/OrganizationValidatorSmime/GetEnterpriseTransactions",
        "certificates": "/api/OrganizationValidatorSmime/GetEnterpriseCertificates",
        "review": "/api/OrganizationValidatorSmime/UpdateEnterpriseReview",
        "cancel": "/api/OrganizationValidatorSmime/CancelTransaction",
        "revoke": "/api/OrganizationValidatorSmime/RevokeCertificate",
        "reasons": "/api/OrganizationValidatorSmime/GetRevocationReasons",
    },
    "clientauth": {
        "requests": "/api/OrganizationValidatorClientAuthentication/GetEnterpriseClientAuthenticationRequests",
        "certificates": "/api/OrganizationValidatorClientAuthentication/GetEnterpriseClientAuthenticationCertificates",
        "review": "/api/OrganizationValidatorClientAuthentication/UpdateEnterpriseReview",
        "cancel": "/api/OrganizationValidatorClientAuthentication/CancelEnterpriseTransaction",
        "revoke": "/api/OrganizationValidatorClientAuthentication/RevokeEnterpriseClientCertificate",
        "reasons": "/api/OrganizationValidatorClientAuthentication/GetRevocationReasons",
    },
}
# Status names of the enterprise validator requests, "Canceled" with one "l" unlike SSL
ENTERPRISE_REQUEST_STATUSES = ["Pending", "Ready", "Completed", "Canceled"]
ENTERPRISE_CERTIFICATE_STATUSES = ["Valid", "Revoked", "Expired"]

# Retries after a 429 Too Many Requests, waiting 2, 4, 8 and 16 seconds unless
# HARICA sends Retry-After
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_MAX_DELAY = 60

# Mailboxes accepted by 3.2.2.4.4, prepended to the domain being validated
CONSTRUCTED_EMAIL_USERS = ["admin", "administrator", "webmaster", "hostmaster", "postmaster"]


class HaricaClient:
    """
    Client for interacting with the Harica CertManager API.

    This client handles authentication (including TOTP-based 2FA),
    certificate management, and domain validation. It uses JWT tokens for authentication
    and automatically refreshes the token if needed.

    Attributes:
        email (str): The email of the user for login.
        password (str): The password of the user for login.
        totp_seed (str): Optional TOTP seed for 2FA.
        http_proxy (str): Optional proxy configuration for HTTP requests.
        https_proxy (str): Optional proxy configuration for HTTPS requests.
        environment (str): The environment of the CertManager ("dev", "stg", or "production").
        refresh_interval (int): Time in seconds before the JWT token needs to be refreshed.
    """

    def __init__(
        self,
        email: str,
        password: str,
        totp_seed: str = None,
        http_proxy: str = None,
        https_proxy: str = None,
        environment: str = "production",
        refresh_interval: int = 3600,
    ):
        self.environment = environment
        self.email = email
        self.password = password
        self.totp_seed = totp_seed
        self.refresh_interval = refresh_interval
        self.login_lock = Lock()
        self.base_url = self.get_base_url()  # Set the base URL depending on the environment
        self.session = requests.Session()  # Reuse session for efficient requests

        # Configure proxies if provided
        if any([http_proxy, https_proxy]):
            self.session.proxies.update({"http": http_proxy, "https": https_proxy})
            logger.info(f"Configured proxies: {self.session.proxies}")

        self.token = None  # JWT token
        self.request_verification_token = None  # CSRF token
        self.roles = set()
        self.full_name = None
        self.organization = None

        self.prepare_client(force=False)  # Prepare client on initialization

    def prepare_client(self, force=False):
        """
        Prepares the client by logging in and acquiring tokens.
        If the token is valid, login is skipped unless force is set to True.

        Args:
            force (bool): Force login even if token is valid.
        """
        with self.login_lock:  # Ensure thread safety
            logger.debug("Preparing client")
            if self.token_is_valid() and not force:
                return

            try:
                self.login()
            except requests.exceptions.ProxyError as ex:
                logger.error(f"❌ Proxy connection error: {ex}")
            except Exception as ex:
                logger.error(f"❌ Login failed: {ex}")

    def token_is_valid(self):
        """
        Validates if the current JWT token is still valid.

        Returns:
            bool: True if the token is valid, False otherwise.
        """
        if not self.token:
            return False
        try:
            token = jwt.decode(self.token, options={"verify_exp": False})
            exp = token.get("exp")
            if exp and exp > time.time() + self.refresh_interval:
                logger.info(f"Token valid until {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(exp))}")
                return True
        except Exception as e:
            logger.error(f"Error decoding token: {e}")
        logger.info("Token expired or invalid, refreshing.")
        return False

    def get_base_url(self):
        """
        Returns the appropriate base URL depending on the environment.

        Returns:
            str: Base URL for the selected environment.
        """
        environments = {
            "dev": "https://cm-dev.harica.gr",
            "stg": "https://cm-stg.harica.gr",
            "production": "https://cm.harica.gr",
        }
        if self.environment not in environments:
            raise ValueError("Invalid environment. Choose from 'dev', 'stg', or 'production'.")
        return environments[self.environment]

    def __get_request_verification_token(self):
        """
        Retrieves the RequestVerificationToken from the login page.

        Returns:
            str: The request verification token.
        """
        response = self.session.get(f"{self.base_url}/")
        if response.status_code != 200:
            raise Exception(f"Failed to access base URL: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        token_element = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_element:
            raise Exception("Failed to find RequestVerificationToken in the HTML.")

        self.request_verification_token = token_element["value"]
        return self.request_verification_token

    def login(self):
        """
        Logs in to CertManager and retrieves the necessary JWT token.
        If TOTP seed is provided, it uses 2FA during login.
        """

        def parse_roles(raw_roles: str) -> set[UserRole]:
            """Convert a comma-separated role string into a set of UserRole enums."""
            roles = set()

            for role in raw_roles.split(","):
                role = role.strip()
                # Validate if it's a valid enum value
                if role in UserRole._value2member_map_:
                    roles.add(UserRole(role))

            return roles

        login_payload = {"email": self.email, "password": self.password}

        # If TOTP seed is provided, generate OTP and add it to the payload
        if self.totp_seed:
            login_payload.update({"token": generate_otp(self.totp_seed)})
            login_response = self.__make_post_request("/api/User/Login2FA", data=login_payload)
        else:
            logger.debug("No TOTP seed provided. Using password-based login.")
            login_response = self.__make_post_request("/api/User/Login", data=login_payload)

        login_response.raise_for_status()

        self.token = login_response.text

        # The token read before the login belongs to the anonymous session
        self.request_verification_token = None
        if not self.token:
            if self.totp_seed:
                raise Exception("Failed to retrieve JWT token.")
            else:
                raise Exception(
                    "Failed to retrieve JWT token. You attempted to log in without "
                    "2FA, but it may be enabled on your account. If it is, please "
                    "provide the TOTP seed."
                )

        # Update session headers with the JWT token for subsequent requests
        self.session.headers.update(
            {
                "Authorization": f"{self.token}",
            }
        )

        logger.debug("Login successful.")

        current_logged_in_user = self.get_logged_in_user_profile()
        self.roles = parse_roles(current_logged_in_user["role"])
        self.full_name = current_logged_in_user["fullName"]
        self.organization = current_logged_in_user["organization"]

    def get_logged_in_user_profile(self):
        """
        Retrieves the profile of the logged-in user.

        Returns:
            dict: The user profile data.
        """
        response_data = self.__make_post_request("/api/User/GetCurrentUser").json()
        return response_data

    def get_certificate(self, certificate_id):
        """
        Retrieves a certificate by its ID.

        Args:
            certificate_id (str): The certificate ID.

        Returns:
            dict: The certificate details.
        """
        pending_status = CertificateStatus.PENDING

        pending_certs = self._fetch_all_pages(lambda start: self.list_certificates(start_index=start, status=pending_status))
        logger.debug(json.dumps(pending_certs))

        for pc in pending_certs:
            # Check also pc.get("transactionStatus"). Better safe than sorry.
            if pc.get("transactionId") == certificate_id and pc.get("transactionStatus") == pending_status.value:
                raise CertificateNotApprovedException

        # Step 2: Try the legacy endpoint
        try:
            res = self.__make_post_request("/api/OrganizationValidatorSSL/GetSSLCertificate", data={"id": certificate_id})
            if res.status_code == 404:
                return None

            data = res.json()

            if isinstance(data, dict) and not data.get("certificate", True):
                raise ValueError("Certificate not available via GetSSLCertificate")

            return data
        except RateLimitError:
            raise
        except Exception:
            pass

        # Step 3: Search ACME certificates if not available via main API
        try:
            for cert in self.list_acme_certificates(status=None):
                if cert.get("id") == certificate_id:
                    return cert
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve certificate from ACME list: {e}")

        return None

    def get_certificate_info(self, certificate_id):
        cert_info = self.__make_post_request("/api/OrganizationValidatorSSL/GetSSLCertificate", data={"id": certificate_id})

        return cert_info.json()

    def get_user_certificate(self, certificate_id):
        """
        Retrieves a user certificate by its ID.

        Args:
            certificate_id (str): The certificate ID.

        Returns:
            dict: The certificate details.
        """
        pending_status = CertificateStatus.PENDING

        user_certs = self.list_user_certificates()
        logger.debug(json.dumps(user_certs))

        for uc in user_certs:
            if uc.get("transactionId") == certificate_id and uc.get("status") == pending_status.value:
                raise CertificateNotApprovedException

        res = self.__make_post_request("/api/Certificate/GetCertificate", data={"id": certificate_id})

        if res.status_code == 404:
            return None

        return res.json()

    def list_certificates(
        self, start_index: int = 0, status: CertificateStatus = CertificateStatus.VALID, full_info: bool = False
    ):
        """
        Retrieves a list of certificates based on status and an optional email filter.

        Args:
            start_index (int): The starting index of the certificates to retrieve.
            status (CertificateStatus): The status of the certificates to retrieve.

        Returns:
            list[dict]: List of certificates.
        """

        status_mapping = {
            # On Harica GUI GetSSLTransactions are SSL Certificates
            CertificateStatus.VALID: "GetSSLTransactions",
            CertificateStatus.REVOKED: "GetSSLTransactions",
            CertificateStatus.EXPIRED: "GetSSLTransactions",
            # On Harica GUI GetSSLReviewableTransactions are SSL Requests
            CertificateStatus.PENDING: "GetSSLReviewableTransactions",
            CertificateStatus.READY: "GetSSLReviewableTransactions",
            CertificateStatus.COMPLETED: "GetSSLReviewableTransactions",
            CertificateStatus.CANCELLED: "GetSSLReviewableTransactions",
        }

        # Build the filters list only if an email is provided
        # 19/03/2025 Filters are not working via API
        # if a filter is specified API will ignore it and return all certificates
        # This remains as example
        # filters = [{
        #     "filterType": "Email",
        #     "filterTypeSelection": "Is",
        #     "filterValue": email,
        #     "isSeperator": False
        # }] if email else []

        json_payload = {"startIndex": start_index, "status": status.value, "filterPostDTOs": []}

        endpoint = f"/api/OrganizationValidatorSSL/{status_mapping[status]}"
        data = self.__make_post_request(endpoint, data=json_payload).json()

        # Add status to each certificate
        for cert in data:
            cert["status"] = status.value

            if full_info:
                cert_info = self.get_certificate_info(cert["transactionId"])

                for key, value in cert_info.items():
                    cert[key] = value
        return data

    def list_user_certificates(self, full_info: bool = False):
        """Retrieves a list of user certificates."""
        endpoint = "/api/ServerCertificate/GetMyTransactions"
        data = self.__make_post_request(endpoint).json()

        # Add status to each certificate based on transactionStatus
        # Set user because harica api will not return it
        for cert in data:
            # Fix harica mispelling of "transactionStatus" for cancelled status
            if cert["transactionStatus"] == "Canceled":
                cert["transactionStatus"] = "Cancelled"

            # Revoked certificates have "Completed" as status and is not possible to
            # retrieve only revoked user certs. Overwrite with "Revoked"
            if cert["isRevoked"]:
                cert["transactionStatus"] = CertificateStatus.REVOKED.value

            cert["status"] = cert["transactionStatus"]
            cert["user"] = self.full_name

            if full_info:
                cert_info = self.get_certificate_info(cert["transactionId"])

                for key, value in cert_info.items():
                    cert[key] = value

        return data

    def list_acme_certificates(self, id: str = None, status: CertificateStatus = CertificateStatus.VALID):
        """
        Retrieves all ACME certificates for all ACME accounts filtered by status,
        and annotates each certificate with the corresponding user.

        Args:
            id (str): The ID of the ACME account to retrieve certificates for.
            status (CertificateStatus): The status of certificates to retrieve, None for all.

        Returns:
            list[dict]: List of ACME certificates across all accounts filtered by status.
        """
        acme_certs = []
        accounts = self.list_acme_accounts()

        for account in accounts:
            # If an account id is provided, only retrieve certificates for that account
            if id and id != account.get("id"):
                continue

            account_id = account.get("id")
            user = account.get("userEmail")
            if not account_id:
                continue

            payload = {"id": account_id}
            endpoint = "/api/OrganizationAdmin/GetAcmeCertificatesOfEntry"

            try:
                response = self.__make_post_request(endpoint, data=payload)
                response.raise_for_status()
                certs = response.json()
            except RateLimitError:
                raise
            except Exception as e:
                logger.error(f"Failed to get ACME certificates for account {account_id}: {e}")
                continue

            for cert in certs:
                if status is None or cert.get("statusName") == status.value:
                    cert["userEmail"] = user
                    acme_certs.append(cert)

        return acme_certs

    def create_acme_account(self, friendly_name: str, transaction_type: str = "SSL OV"):
        """Creates an ACME account.

        Parameters
        ----------
        friendly_name : str
            Friendly name for the ACME account.
        transaction_type : str, optional
            Transaction type, by default "SSL OV". Available options: "SSL OV", "SSL DV"

        """

        def get_organization_id():
            endpoint = "/api/OrganizationAdmin/GetOrganizationsBulk"
            response = self.__make_post_request(endpoint)
            response.raise_for_status()
            orgs_bulk = response.json()

            for org in orgs_bulk:
                if org["organization"] == self.organization:
                    return org["organizationId"]

            # Fallback if organization not found using SearchGroups and
            # GetOrganizationsByGroupId
            endpoint = "/api/OrganizationAdmin/SearchGroups"
            payload = {"key": "", "value": ""}
            response = self.__make_post_request(endpoint, data=payload)
            response.raise_for_status()

            groups = response.json()
            group_id = ""

            for group in groups:
                if group["alias"] == self.organization:
                    group_id = group["id"]
                    break

            if not group_id:
                raise Exception(f"Group for {self.organization} not found")

            endpoint = "/api/OrganizationAdmin/GetOrganizationsByGroupId"
            payload = {"id": group_id}
            response = self.__make_post_request(endpoint, data=payload)
            response.raise_for_status()

            orgs = response.json()
            org_id = ""

            for org in orgs:
                if org["organization"] == self.organization:
                    org_id = org["organizationId"]
                    break

            if not org_id:
                raise Exception(f"Organization {self.organization} not found")

            return org_id

        payload = {
            "friendlyName": friendly_name,
            "transactionType": transaction_type,
            "id": get_organization_id(),
        }
        endpoint = "/api/OrganizationAdmin/CreateAcmeEntry"

        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        accounts = self.list_acme_accounts()

        for account in accounts:
            if account["friendlyName"] == friendly_name:
                return account

        return {}

    def disable_acme_account(self, id: str) -> bool:
        """Disable an ACME account.

        Parameters
        ----------
        id : str
            The ID of the ACME account.

        Returns
        -------
        bool
            True if successful, False otherwise.

        """
        endpoint = "/api/OrganizationAdmin/DisableAcmeEntry"
        payload = {"id": id}
        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        if response.status_code != 200:
            return False

        return True

    def get_acme_available_domains(self, id: str) -> list[dict]:
        """Get available domains for an ACME account.

        Parameters
        ----------
        id : str
            The ID of the ACME account.

        Returns
        -------
        list[dict]
            A list of available domains for the ACME account.

        """
        endpoint = "/api/OrganizationAdmin/GetGroupDomainsForAcme"
        payload = {"id": id}
        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        return response.json()

    def get_acme_domains(self, id: str) -> list[dict]:
        """Get domains for an ACME account.

        Parameters
        ----------
        id : str
            The ID of the ACME account.

        Returns
        -------
        list[dict]
            A list of active or inactive domains for the ACME account.

        """
        endpoint = "/api/OrganizationAdmin/GetAcmeDomainsOfEntry"
        payload = {"id": id}
        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        return response.json()

    def acme_allow_all_domains(self, id: str) -> bool:
        """Allow all domains for an ACME account.

        Parameters
        ----------
        id : str
            The ID of the ACME account.

        Returns
        -------
        bool
            True if successful, False otherwise.

        """
        endpoint = "/api/OrganizationAdmin/CreateAllowAcmeRulesForAllDomains"
        payload = {"id": id}
        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        if response.status_code != 200:
            return False

        return True

    def create_acme_domain_rule(
        self,
        id: str,
        domain: str,
        subdomain: str = "",
        allowed: bool = True,
        applies_to_subdomains: bool = True,
    ) -> bool:
        """Create a domain rule for an ACME account.

        Parameters
        ----------
        id : str
            The ID of the ACME account.
        domain : str
            The domain to create.
        subdomain : str, optional
            The subdomain to create, by default "".
        allowed : bool, optional
            Whether the domain is allowed, by default True.
        applies_to_subdomains : bool, optional
            Whether the domain applies to subdomains, by default True.

        Returns
        -------
        bool
            True if successful, False otherwise.

        """
        if not subdomain:
            subdomain = domain

        endpoint = "/api/OrganizationAdmin/CreateAcmeDomain"
        payload = {
            "acmeEntryId": id,
            "baseDomain": domain,
            "customDomain": subdomain,
            "isAllowed": allowed,
            "allowSubdomains": applies_to_subdomains,
        }

        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        if response.status_code != 200:
            return False

        return True

    def remove_acme_domain_rule(self, id: str) -> bool:
        """Remove a domain rule from an ACME account.

        Parameters
        ----------
        id : str
            The ID of the domain rule to remove.

        Returns
        -------
        bool
            True if successful, False otherwise.

        """
        endpoint = "/api/OrganizationAdmin/DisableDomainRule"
        payload = {"id": id}
        response = self.__make_post_request(endpoint, data=payload)
        response.raise_for_status()

        if response.status_code != 200:
            return False

        return True

    def build_domains_list(self, domains):
        """
        Builds a list of domain information for the certificate request.
        If a wildcard domain (*.domain.tld) exists alongside its base domain,
        only the wildcard domain is processed since it already covers the base domain.

        Args:
            domains (list): List of domains.

        Returns:
            list: List of domain dictionaries with validation details.
        """
        domains_info = []
        processed_domains = set()
        wildcard_bases = set()

        # First, identify all wildcard domains and their base parts
        for dom in domains:
            if "*" in dom:
                # Extract the base part of the wildcard domain (e.g., "mydomain.tld" from "*.mydomain.tld")
                wildcard_base = dom.replace("*.", "")
                wildcard_bases.add(wildcard_base)

        for dom in domains:
            # Check if this is a 'www.' domain and get the base domain
            base_domain = dom.replace("www.", "")

            # Skip if this domain has already been processed
            if base_domain in processed_domains:
                continue

            # Skip regular domains that are covered by wildcards
            if "*" not in dom and base_domain in wildcard_bases:
                continue

            domain_info = {
                "isWildcard": "*" in dom,
                "domain": base_domain,
                "includeWWW": f"www.{base_domain}" in domains,
                "isPrevalidated": True,
                "isValid": True,
                "isFreeDomain": True,
                "isFreeDomainDV": True,
                "isFreeDomainEV": False,
                "canRequestOV": True,
                "canRequestEV": False,
                "errorMessage": "",
                "warningMessage": "",
            }
            processed_domains.add(base_domain)
            domains_info.append(domain_info)

        return domains_info

    def get_matching_organizations(self, domains):
        """
        Retrieves matching organizations based on the domain list.

        Args:
            domains (list): List of domains.

        Returns:
            list: List of matching organizations.
        """
        domains_info = self.build_domains_list(domains)
        data = self.__make_post_request("/api/ServerCertificate/CheckMachingOrganization", data=domains_info).json()
        return data

    def request_certificate(self, domains, csr, transactionType="OV"):
        """
        Requests a new server certificate based on the provided domains and CSR.

        Args:
            domains (list): List of domains.
            csr (str): Certificate signing request.

        Returns:
            str: The certificate ID.
        """
        organizations = self.get_matching_organizations(domains)

        if not organizations:
            raise ValueError("No available organization for this domain list")

        if len(organizations) > 1:
            raise ValueError("Multiple organizations found.'")

        organization = organizations[0]

        # Build the organization DN (Distinguished Name)
        orgDN = f"OrganizationId:{organization.get('id')}"
        if organization.get("country"):
            orgDN += "&C:" + organization["country"]
        if organization.get("state"):
            orgDN += "&ST:" + organization["state"]
        if organization.get("locality"):
            orgDN += "&L:" + organization["locality"]
        if organization.get("organizationName"):
            orgDN += "&O:" + organization["organizationName"]
        if organization.get("organizationUnitName"):
            orgDN += "&OU:" + organization["organizationUnitName"]

        domains_info = self.build_domains_list(domains)

        # Prepare the payload for the certificate request
        payload = {
            "domains": (None, json.dumps(domains_info)),
            "domainsString": (None, json.dumps(domains_info)),
            "csr": (None, csr),
            "duration": (None, "1"),
            "transactionType": (None, transactionType),
            "friendlyName": (None, domains[0]),
            "isManualCSR": (None, "true"),
            "consentSameKey": (None, "true"),
        }
        if transactionType == "OV":
            payload["organizationDN"] = (None, orgDN)

        data = self.__make_post_request(
            "/api/ServerCertificate/RequestServerCertificate", data=payload, content_type="multipart/form-data"
        )

        return data.json()["id"]

    def request_single_smime_bulk_certificate(self, emails, gn, sn, csr, transactionType="MV"):
        """
        Requests a new S/MIME client certificate based on the provided emails and CSR.
        Supported validation profiles are Mailbox Validated and Sponsor Validated.
        Harica calls these "Email Only" and "IV+OV", respectively.

        Args:
            emails (list): List of Email Addresses.
            gn (str): Given Name of the Subject (optional).
            sn (str): Surname of the Subject (optional).
            csr (str): Certificate signing request.

        Returns:
            str: The certificate in pkcs7 DER format.
        """

        cert_type = "email_only" if transactionType == "MV" else "natural_legal_lcp"
        # ensure all three email fields are used or "" and extract domains:
        email = [""] * 3
        domains = []
        for i, e in enumerate(emails):
            email[i] = e
            _, _, domain = e.rpartition("@")
            domains.append(domain)

        organizations = self.get_matching_organizations(domains)

        if not organizations:
            raise ValueError("No available organization for this domain list")

        if len(organizations) > 1:
            raise ValueError("Multiple organizations found.'")

        organization = organizations[0].get("id")

        csvio = io.StringIO()
        writer = csv.writer(csvio)
        writer.writerow(
            ["FriendlyName", "Email", "Email2", "Email3", "GivenName", "Surname", "PickupPassword", "CertType", "CSR"]
        )  # header
        writer.writerow([email[0], email[0], email[1], email[2], gn, sn, "", cert_type, csr])  # cert data
        # Note: the example CSV supplied by Harica adds a trailing comma after the CSR (but not on the header line). seems to work without just fine.
        csvdata = csvio.getvalue()

        # Prepare the payload for the certificate request
        payload = {
            "groupId": (None, organization),
            "csv": ("request.csv", csvdata, "text/csv"),
        }

        data = self.__make_post_request(
            "/api/OrganizationAdmin/CreateBulkCertificatesSMIME", data=payload, content_type="multipart/form-data"
        )
        if data.history:  # empty if not redirected
            # if user is not authorized, we get redirected to login page (status codes 308->200)
            raise PermissionError("User is not authorized, must be an admin.")
        zipped_certificates = data.content

        # the signed certificate is returned immediately, but in a zipfile. extract it.
        try:
            zipio = io.BytesIO(zipped_certificates)
            zipf = zipfile.ZipFile(zipio, "r")
            p7b_data = next(zipf.read(name) for name in zipf.namelist())  # only contains 1 file, named "1.<FriendlyName>.p7b"
        except Exception as e:
            raise ValueError("could not extract certificate from response")

        return p7b_data

    def _fetch_all_pages(self, fetch_page):
        """
        Collects all the pages of a paginated HARICA list.

        Args:
            fetch_page (callable): Returns the page starting at the given index.

        Returns:
            list: The items of all pages, until HARICA returns an empty page.
        """
        items = []
        previous = None
        while True:
            page = fetch_page(len(items))
            # Also stop if HARICA ignores startIndex and repeats the same page
            if not page or page == previous:
                return items
            items.extend(page)
            previous = page

    def get_pending_transactions(self):
        """
        Retrieves a list of pending transactions.

        Returns:
            List: A list of pending transactions.
        """

        def fetch_page(start_index):
            json_payload = {
                "startIndex": start_index,
                "status": CertificateStatus.PENDING.value,
                "filterPostDTOs": [],
            }
            return self.__make_post_request(
                "/api/OrganizationValidatorSSL/GetSSLReviewableTransactions",
                data=json_payload,
            ).json()

        return self._fetch_all_pages(fetch_page)

    def approve_transaction(self, transaction_id):
        """
        Approves a pending certificate request based on the provided certificate ID.

        This method retrieves transactions for certificates that are pending review, filters for
        the certificate matching the provided certificate ID, and performs the review process
        by submitting the necessary review updates.

        Args:
            transaction_id (str): The certificate ID to approve.

        Returns:
            bool: True if the approval process was successful, False otherwise.

        Raises:
            Exception: If no reviews are found for the specified certificate or if the approval fails.
        """
        # Retrieve SSL reviewable transactions
        transactions = self.get_pending_transactions()

        # Initialize a list to store reviews to be processed
        reviews = []

        # Iterate through the transactions to find the matching certificate
        for transaction in transactions:
            if transaction.get("transactionId") == transaction_id:
                # Extract the reviews for the matching certificate transaction
                review_dtos = transaction.get("reviewGetDTOs", [])
                for rev in review_dtos:
                    if not rev.get("isReviewed") and rev.get("reviewId") and "reviewValue" in rev:
                        reviews.append((rev["reviewId"], rev["reviewValue"]))

        # Check if there are reviews to process
        if not reviews:
            logger.warning(f"No available reviews for transaction with ID {transaction_id}")
            return False

        # Perform the review process for each review found
        for review_id, review_value in reviews:
            # Prepare the payload for submitting the review
            review_payload = {
                "reviewId": (None, review_id),
                "isValid": (None, "true"),
                "informApplicant": (None, "true"),
                "reviewMessage": (None, "Automatic Review by IT-Portal"),
                "reviewValue": (None, review_value),
            }

            # Make the POST request to update the review status
            response = self.__make_post_request(
                "/api/OrganizationValidatorSSL/UpdateReviews", data=review_payload, content_type="multipart/form-data"
            )

            # Check if the review submission was successful
            if response.status_code != 200:
                logger.error(f"Failed to approve review {review_id} for transaction {transaction_id}")
                return False

        # Return True if all reviews were successfully processed
        return True

    def cancel_transaction(self, transaction_id):
        """
        Cancels a pending certificate request based on the provided certificate ID.

        Args:
            transaction_id (str): The certificate ID to cancel.

        Returns:
            bool: True if the cancellation was successful, False otherwise.

        """
        # Prepare the payload for cancelling the transaction
        cancel_payload = {"id": transaction_id}

        # Make the POST request to cancel the transaction
        response = self.__make_post_request("/api/Transaction/CancelTransaction", data=cancel_payload)

        # Check if the cancellation was successful
        return response.status_code == 200

    def get_revocation_reasons(self, scope: str = "ssl") -> list[dict]:
        """
        Retrieves the revocation reasons accepted by HARICA.

        Args:
            scope (str): "user" for users without enterprise roles, "ssl" for SSL
                approvers, "admin" for enterprise admins (e.g. ACME certificates),
                "smime" and "clientauth" for the enterprise approvers of those areas.

        Returns:
            list[dict]: Reasons with "name" (the code) and "revocationMessage".
        """
        endpoints = {
            "user": "/api/Certificate/GetRevocationReasons",
            "ssl": "/api/OrganizationValidatorSSL/GetRevocationReasons",
            "admin": "/api/OrganizationAdmin/GetRevocationReasons",
            **{area: endpoints["reasons"] for area, endpoints in ENTERPRISE_VALIDATOR_ENDPOINTS.items()},
        }

        response = self.__make_post_request(endpoints[scope])
        response.raise_for_status()
        return response.json()

    def revoke_certificate(self, cert_id: str, reason: str = DEFAULT_REVOCATION_REASON) -> bool:
        """
        Revokes a certificate based on the provided certificate ID.

        Args:
            cert_id (str): The certificate ID to revoke.
            reason (str): Revocation reason code.

        Returns:
            bool: True if the revocation was successful, False otherwise.

        """
        payload = {
            "transactionId": cert_id,
            "name": reason,
            "notes": f"Revoked via harica-cli by {self.email}",
            "message": "",
        }
        response = self.__make_post_request(
            "/api/OrganizationValidatorSSL/RevokeCertificate",
            data=payload,
        )

        return response.status_code == 200

    def revoke_user_certificate(self, cert_id: str, reason: str = DEFAULT_REVOCATION_REASON) -> bool:
        """
        Revokes a user certificate based on the provided certificate ID.

        Args:
            cert_id (str): The certificate ID to revoke.
            reason (str): Revocation reason code.

        Returns:
            bool: True if the revocation was successful, False otherwise.

        """
        payload = {
            "transactionId": cert_id,
            "name": reason,
            "notes": f"Revoked via harica-cli by {self.email}",
        }
        response = self.__make_post_request(
            "/api/Certificate/RevokeCertificate",
            data=payload,
        )

        return response.status_code == 200

    def revoke_acme_certificate(self, cert_id: str, reason: str = DEFAULT_REVOCATION_REASON, message: str = "") -> bool:
        """
        Revokes a certificate issued through an ACME account.

        Args:
            cert_id (str): The ACME certificate ID ("id" in GetAcmeCertificatesOfEntry).
            reason (str): Revocation reason code.
            message (str): Message for the certificate owner.

        Returns:
            bool: True if the revocation was successful, False otherwise.
        """
        payload = {"transactionId": cert_id, "name": reason, "message": message}
        response = self.__make_post_request("/api/OrganizationAdmin/RevokeAcmeCertificate", data=payload)

        return response.status_code == 200

    def list_enterprise_requests(self, area: str, status: str = "Pending") -> list[dict]:
        """
        Retrieves the requests that an enterprise approver can review.

        Args:
            area (str): "smime" or "clientauth".
            status (str): One of ENTERPRISE_REQUEST_STATUSES.

        Returns:
            list[dict]: Requests of all pages.
        """
        endpoint = ENTERPRISE_VALIDATOR_ENDPOINTS[area]["requests"]

        def fetch_page(start_index):
            payload = {"startIndex": start_index, "status": status, "filterPostDTOs": []}
            response = self.__make_post_request(endpoint, data=payload)
            # HARICA answers an unknown status with an empty body
            return response.json() if response.text else []

        return self._fetch_all_pages(fetch_page)

    def list_enterprise_certificates(self, area: str, status: str = "Valid") -> list[dict]:
        """
        Retrieves the certificates of the requests handled by enterprise approvers.

        Args:
            area (str): "smime" or "clientauth".
            status (str): One of ENTERPRISE_CERTIFICATE_STATUSES.

        Returns:
            list[dict]: Certificates of all pages.
        """
        endpoint = ENTERPRISE_VALIDATOR_ENDPOINTS[area]["certificates"]

        def fetch_page(start_index):
            payload = {"startIndex": start_index, "filterPostDTOs": []}
            if area == "clientauth":
                # Same defaults as the web frontend: from the epoch to now
                payload.update(
                    selectedList=status,
                    dateFrom="1970-01-01T00:00:00.000Z",
                    dateTo=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                )
            else:
                payload["status"] = status
            response = self.__make_post_request(endpoint, data=payload)
            return response.json() if response.text else []

        return self._fetch_all_pages(fetch_page)

    def approve_enterprise_request(self, area: str, transaction_id: str) -> bool:
        """
        Approves a pending request by submitting its open reviews, as approve does for SSL.

        Args:
            area (str): "smime" or "clientauth".
            transaction_id (str): The ID of the pending request.

        Returns:
            bool: True if all reviews were submitted, False if there was nothing to review
                or HARICA refused a review.
        """
        reviews = [
            (review["reviewId"], review["reviewValue"])
            for request in self.list_enterprise_requests(area, "Pending")
            if request.get("transactionId") == transaction_id
            for review in request.get("reviewGetDTOs") or []
            if not review.get("isReviewed") and review.get("reviewId") and "reviewValue" in review
        ]
        if not reviews:
            logger.warning(f"No available reviews for transaction with ID {transaction_id}")
            return False

        for review_id, review_value in reviews:
            payload = {
                "reviewId": (None, review_id),
                "isValid": (None, "true"),
                "informApplicant": (None, "true"),
                "reviewMessage": (None, f"Approved via harica-cli by {self.email}"),
                "reviewValue": (None, review_value),
            }
            response = self.__make_post_request(
                ENTERPRISE_VALIDATOR_ENDPOINTS[area]["review"], data=payload, content_type="multipart/form-data"
            )
            if response.status_code != 200:
                logger.error(f"Failed to approve review {review_id} for transaction {transaction_id}")
                return False

        return True

    def cancel_enterprise_request(self, area: str, transaction_id: str, message: str, inform_applicant: bool) -> bool:
        """
        Cancels a request of another user as enterprise approver.

        Args:
            area (str): "smime" or "clientauth".
            transaction_id (str): The ID of the request.
            message (str): Status message shown for the request.
            inform_applicant (bool): Send the message to the applicant by email.

        Returns:
            bool: True if the request was cancelled, False otherwise.
        """
        payload = {
            "transactionId": transaction_id,
            "notes": f"Cancelled via harica-cli by {self.email}",
            "statusMessage": message,
            "informApplicant": inform_applicant,
        }
        response = self.__make_post_request(ENTERPRISE_VALIDATOR_ENDPOINTS[area]["cancel"], data=payload)

        return response.status_code == 200

    def revoke_enterprise_certificate(
        self, area: str, transaction_id: str, reason: str = DEFAULT_REVOCATION_REASON, message: str = ""
    ) -> bool:
        """
        Revokes a certificate as enterprise approver.

        Args:
            area (str): "smime" or "clientauth".
            transaction_id (str): The transaction ID of the certificate.
            reason (str): Revocation reason code.
            message (str): Message for the certificate owner.

        Returns:
            bool: True if the revocation was successful, False otherwise.
        """
        payload = {
            "transactionId": transaction_id,
            "name": reason,
            "notes": f"Revoked via harica-cli by {self.email}",
            "message": message,
        }
        response = self.__make_post_request(ENTERPRISE_VALIDATOR_ENDPOINTS[area]["revoke"], data=payload)

        return response.status_code == 200

    def list_api_keys(self) -> list[dict]:
        """
        Retrieves the API keys of the logged in user.

        Returns:
            list[dict]: API keys with "apiKeyId", "friendlyName", "createdAt", "isActive" and "disabledAt".
        """
        response = self.__make_post_request("/api/User/GetMyAPIKeys")
        response.raise_for_status()
        return response.json()

    def create_api_key(self, friendly_name: str) -> str:
        """
        Creates an API key for the logged in user.

        Args:
            friendly_name (str): Label of the new key.

        Returns:
            str: The key code. HARICA shows it only once.
        """
        response = self.__make_post_request("/api/User/CreateAPIKey", data={"id": friendly_name})
        response.raise_for_status()
        return response.text.strip('"')

    def disable_api_key(self, api_key_id: str) -> bool:
        """
        Disables an API key of the logged in user.

        Args:
            api_key_id (str): The "apiKeyId" of the key.

        Returns:
            bool: True if the key was disabled, False otherwise.
        """
        response = self.__make_post_request("/api/User/DisableAPIKey", data={"id": api_key_id})

        return response.status_code == 200

    def list_domains(self):
        # Step 1: Search for the first available group in the organization
        groups = self.__make_post_request("/api/OrganizationAdmin/SearchGroups", data={"key": "", "value": ""}).json()

        # Ensure that there are groups available
        if not groups:
            raise Exception("No groups found.")

        group = groups[0]
        group_id = group["id"]

        # Step 2: Get the validity of the domains associated with the group
        domain_validities = self.__make_post_request(
            "/api/OrganizationAdmin/GetDomainsValidityByGroupId", data={"id": group_id}
        ).json()

        return domain_validities

    def list_acme_accounts(self):
        """
        Retrieve the list of ACME accounts from the Harica API.

        Returns:
            list: A list of ACME account entries.
        """

        return self.__make_post_request("/api/OrganizationAdmin/GetAcmeEntries", data={"key": "", "value": ""}).json()

    def validate_domains(self, domains=[], method="dns", email_user="admin"):
        """
        Create a validation token for the specified domains.

        This function performs the following steps:
        1. Searches for a group within the organization and retrieves its ID and associated domains.
        2. Fetches the domain validity information for the group.
        3. Creates a prevalidated validation token for each domain that needs validation.

        Args:
            domains (list): A list of domain names that need to be validated.
            method (str): "dns" (DNS change) or "email" (constructed email to domain contact).
            email_user (str): Mailbox for the "email" method, one of CONSTRUCTED_EMAIL_USERS.
                The token is sent to <email_user>@<domain>.

        Raises:
            Exception: If there are no groups available or if domain validity data is not available.
        """
        # Step 1: Search for the first available group in the organization
        groups = self.__make_post_request("/api/OrganizationAdmin/SearchGroups", data={"key": "", "value": ""}).json()

        # Ensure that there are groups available
        if not groups:
            raise Exception("No groups found.")

        group = groups[0]
        group_id = group["id"]
        # group_domains = group["domains"]  # Not used, but kept for potential future use

        # Step 2: Get the validity of the domains associated with the group
        domain_validities = self.__make_post_request(
            "/api/OrganizationAdmin/GetDomainsValidityByGroupId", data={"id": group_id}
        ).json()

        # Domains (ID and name) that need to be validated
        domains_to_validate = []

        # Check each domain's validity and filter the ones that need validation
        for item in domain_validities:
            domain_id = item["organizationId"]
            domain_name = item["domain"]
            # domain_validity = datetime.fromisoformat(item["validity"])

            # If the domain is in the provided list, add its ID to the list for validation
            if domain_name in domains:
                domains_to_validate.append((domain_id, domain_name))

        # Step 3: Create validation tokens for the domains that need validation
        for domain_id, domain_name in domains_to_validate:
            # Make a request to create the validation token for each domain
            self.__make_post_request(
                "/api/OrganizationAdmin/CreatePrevalidatedValidation",
                data={
                    "usersEmail": self.email,
                    "validationMethodName": DOMAIN_VALIDATION_METHODS[method],
                    "organizationId": domain_id,  # ID of the domain to validate
                    # Recipient of the token for the constructed email method
                    "whoisEmail": f"{email_user}@{domain_name}" if method == "email" else "",
                },
            )

    def __make_api_request(self, endpoint, method="GET", data=None, content_type="application/json"):
        """
        Makes an authenticated API request to the specified endpoint with the given method, data, and content type.

        Args:
            endpoint (str): The API endpoint to send the request to.
            method (str, optional): The HTTP method to use (either 'GET' or 'POST'). Defaults to "GET".
            data (dict, optional): The payload to send with the request, if applicable. Defaults to None.
            content_type (str, optional): The content type for the request. Defaults to "application/json".

        Returns:
            Response: The response object from the HTTP request.

        Raises:
            ValueError: If the HTTP method is unsupported.
            RateLimitError: If HARICA still answers 429 after RATE_LIMIT_RETRIES retries.
            ErrorPageError: If HARICA redirects the call to its /Error page.
            Exception: If the API request fails (non-200 status code).
        """
        # The token stays valid for the whole session, the web frontend reuses it too
        token_reused = bool(self.request_verification_token)
        if not token_reused:
            self.__get_request_verification_token()

        # Update headers for authentication and content type
        self.session.headers.update(
            {
                "RequestVerificationToken": self.request_verification_token,
                "Content-Type": content_type,
            }
        )

        # Handle 'multipart/form-data' special case where Content-Type header is automatically set by the library
        if content_type == "multipart/form-data":
            self.session.headers.update({"Content-Type": None})

        # Construct the full URL for the request
        url = urljoin(self.base_url, endpoint)

        try:
            for attempt in range(RATE_LIMIT_RETRIES + 1):
                # Send the request based on the chosen method (GET or POST)
                if method == "GET":
                    response = self.session.get(url)
                elif method == "POST":
                    # Handle different content types for POST requests
                    if content_type == "multipart/form-data":
                        response = self.session.post(url, files=data)
                    else:
                        response = self.session.post(url, json=data)
                else:
                    raise ValueError("Unsupported method. Use 'GET' or 'POST'.")

                if response.status_code != 429:
                    break
                if attempt == RATE_LIMIT_RETRIES:
                    raise RateLimitError(
                        f"HARICA rate limit (429 Too Many Requests) on {endpoint}, "
                        f"still failing after {RATE_LIMIT_RETRIES} retries. Retry later."
                    )

                # A 429 request was not processed, so sending it again is safe
                delay = self._rate_limit_delay(response, attempt)
                logger.warning(
                    f"HARICA rate limit (429) on {endpoint}, retrying in {delay}s ({attempt + 1}/{RATE_LIMIT_RETRIES})"
                )
                time.sleep(delay)

            # HARICA answers a rejected RequestVerificationToken with a redirect to /Error
            if response.history and urlparse(response.url).path == "/Error":
                self.request_verification_token = None
                # Only reads are sent again: a write may have been processed before the error
                if token_reused and endpoint.rsplit("/", 1)[-1].startswith(("Get", "Search", "Check")):
                    logger.debug(f"{endpoint} redirected to /Error, retrying with a new token")
                    return self.__make_api_request(endpoint, method=method, data=data, content_type=content_type)
                raise ErrorPageError(f"HARICA redirected {endpoint} to its error page. Retry later.")

            if response.status_code == 400 or response.status_code == 401:
                raise PermissionError(response.text or "Permission denied.")
            elif response.status_code != 200:
                logging.error(f"API request failed with status code {response.status_code}: {response.text}")

            # Return the response object for further processing
            return response

        except requests.exceptions.ProxyError as e:
            logger.error(f"Proxy error during {method} request to {url}: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during {method} request to {url}: {e}")
            raise

    @staticmethod
    def _rate_limit_delay(response, attempt):
        """
        Seconds to wait before retrying a 429 response.

        Args:
            response (Response): The 429 response.
            attempt (int): Number of retries already done.

        Returns:
            int: Retry-After when it is a number of seconds, otherwise 2, 4, 8, ...,
                capped at RATE_LIMIT_MAX_DELAY.
        """
        retry_after = response.headers.get("Retry-After", "")
        delay = int(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)
        return min(delay, RATE_LIMIT_MAX_DELAY)

    def __make_get_request(self, endpoint, content_type="application/json"):
        """
        Helper function to make GET requests to the API.

        Args:
            endpoint (str): The API endpoint to send the GET request to.
            content_type (str, optional): The content type for the request. Defaults to "application/json".

        Returns:
            Response: The response object from the GET request.
        """
        return self.__make_api_request(endpoint, method="GET", content_type=content_type)

    def __make_post_request(self, endpoint, data={}, content_type="application/json"):
        """
        Helper function to make POST requests to the API.

        Args:
            endpoint (str): The API endpoint to send the POST request to.
            data (dict, optional): The payload to send with the POST request. Defaults to an empty dictionary.
            content_type (str, optional): The content type for the request. Defaults to "application/json".

        Returns:
            Response: The response object from the POST request.
        """
        return self.__make_api_request(endpoint, method="POST", data=data, content_type=content_type)

    def api_post(self, endpoint, data={}, content_type="application/json"):
        """
        Helper function to make POST requests to the API.

        Args:
            endpoint (str): The API endpoint to send the POST request to.
            data (dict, optional): The payload to send with the POST request. Defaults to an empty dictionary.
            content_type (str, optional): The content type for the request. Defaults to "application/json".

        Returns:
            Response: The response object from the POST request.
        """
        return self.__make_post_request(endpoint, data=data, content_type=content_type)

    def has_role(self, role: UserRole) -> bool:
        """Check if the user has a specific role."""
        return role in self.roles

    def get_user_roles(self) -> str:
        """Get a comma-separated string of user roles."""
        return ", ".join(role.value for role in self.roles)
