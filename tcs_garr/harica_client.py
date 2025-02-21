import json
import logging
import time
from threading import Lock

import jwt
import requests
from bs4 import BeautifulSoup

from .exceptions import NoHaricaAdminException, NoHaricaApproverException

from .utils import generate_otp

# Initialize logger
logger = logging.getLogger(__name__)


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
        environment (str): The environment of the CertManager ("dev", "stg", or "production").
        refresh_interval (int): Time in seconds before the JWT token needs to be refreshed.
    """

    def __init__(
        self, email: str, password: str, totp_seed: str = None, environment: str = "production", refresh_interval: int = 3600
    ):
        self.environment = environment
        self.email = email
        self.password = password
        self.totp_seed = totp_seed
        self.refresh_interval = refresh_interval
        self.login_lock = Lock()
        self.base_url = self.get_base_url()  # Set the base URL depending on the environment
        self.session = requests.Session()  # Reuse session for efficient requests
        self.token = None  # JWT token
        self.request_verification_token = None  # CSRF token
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

            self.login()  # Perform login

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
        login_payload = {"email": self.email, "password": self.password}

        # If TOTP seed is provided, generate OTP and add it to the payload
        if self.totp_seed:
            login_payload.update({"token": generate_otp(self.totp_seed)})
            login_response = self.__make_post_request("/api/User/Login2FA", data=login_payload)
        else:
            login_response = self.__make_post_request("/api/User/Login", data=login_payload)

        self.token = login_response.text
        if not self.token:
            raise Exception("Failed to retrieve JWT token.")

        # Update session headers with the JWT token for subsequent requests
        self.session.headers.update(
            {
                "Authorization": f"{self.token}",
            }
        )

        logger.debug("Login successful.")

        current_logged_in_user = self.get_logged_in_user_profile()
        if "Enterprise Admin" not in current_logged_in_user["role"]:
            raise NoHaricaAdminException
        if "SSL Enterprise Approver" not in current_logged_in_user["role"]:
            raise NoHaricaApproverException

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
        # response_data = self.__make_post_request("/api/Certificate/GetCertificate", data={"id": certificate_id}).json()
        response_data = self.__make_post_request(
            "/api/OrganizationAdmin/GetEnterpriseCertificate", data={"id": certificate_id}
        ).json()
        return response_data

    def list_certificates(self):
        """
        Retrieves a list of valid certificates.

        Returns:
            dict: List of certificates.
        """
        json_payload = {"startIndex": 0, "status": "Valid", "filterPostDTOs": []}
        data = self.__make_post_request("/api/OrganizationValidatorSSL/GetSSLTransactions", data=json_payload).json()
        return data

    def build_domains_list(self, domains):
        """
        Builds a list of domain information for the certificate request.

        Args:
            domains (list): List of domains.

        Returns:
            list: List of domain dictionaries with validation details.
        """
        domains_info = []
        processed_domains = set()

        for dom in domains:
            # Check if this is a 'www.' domain and skip if its non-www version has been processed
            base_domain = dom.replace("www.", "")

            if base_domain in processed_domains:
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

    def request_certificate(self, domains, csr):
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
            raise ValueError("Multiple organizations found. Specify one using '-O org'")

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
            "transactionType": (None, "OV"),
            "friendlyName": (None, domains[0]),
            "isManualCSR": (None, "true"),
            "consentSameKey": (None, "true"),
            "organizationDN": (None, orgDN),
        }
        data = self.__make_post_request(
            "/api/ServerCertificate/RequestServerCertificate", data=payload, content_type="multipart/form-data"
        )

        return data.json()["id"]

    def get_pending_transactions(self):
        """
        Retrieves a list of pending transactions.

        Returns:
            List: A list of pending transactions.
        """
        # Prepare the payload to retrieve SSL reviewable transactions
        json_payload = {"startIndex": 0, "status": "Pending", "filterPostDTOs": []}

        # Make a POST request to fetch the pending SSL transactions
        transactions = self.__make_post_request(
            "/api/OrganizationValidatorSSL/GetSSLReviewableTransactions", data=json_payload
        ).json()

        return transactions

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

    def validate_domains(self, domains=[]):
        """
        Create a validation token for the specified domains.

        This function performs the following steps:
        1. Searches for a group within the organization and retrieves its ID and associated domains.
        2. Fetches the domain validity information for the group.
        3. Creates a prevalidated validation token for each domain that needs validation.

        Args:
            domains (list): A list of domain names that need to be validated.

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

        # List to store IDs of domains that need to be validated
        domains_id_to_validate = []

        # Check each domain's validity and filter the ones that need validation
        for item in domain_validities:
            domain_id = item["organizationId"]
            domain_name = item["domain"]
            # domain_validity = datetime.fromisoformat(item["validity"])

            # If the domain is in the provided list, add its ID to the list for validation
            if domain_name in domains:
                domains_id_to_validate.append(domain_id)

        # Step 3: Create validation tokens for the domains that need validation
        for domain_id in domains_id_to_validate:
            # Make a request to create the validation token for each domain
            self.__make_post_request(
                "/api/OrganizationAdmin/CreatePrevalidatedValidation",
                data={
                    "usersEmail": self.get_logged_in_user_profile()["email"],  # Email of the currently logged-in user
                    "validationMethodName": "3.2.2.4.7",  # Fixed validation method name
                    "organizationId": domain_id,  # ID of the domain to validate
                    "whoisEmail": "",  # Empty WHOIS email, can be customized
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
            Exception: If the API request fails (non-200 status code).
        """
        # Ensure we have the necessary request verification token
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
        url = f"{self.base_url}{endpoint}"

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

        if response.status_code == 400 or response.status_code == 401:
            raise PermissionError(f"Permission Denied: {response.status_code}")
        elif response.status_code != 200:
            logging.error(f"API request failed with status code {response.status_code}: {response.text}")

        # Return the response object for further processing
        return response

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
