import configparser
import os
import pathlib
import re
import shutil
import string
import subprocess
import sys
from datetime import datetime
from enum import Enum
from importlib.metadata import version as get_installed_version

import pyotp
import requests

import tcs_garr.settings as settings
from tcs_garr.logger import setup_logger

logger = setup_logger()


class UserRole(Enum):
    ENTERPRISE_ADMIN = "Enterprise Admin"
    USER = "User"
    SMIME_ENTERPRISE_APPROVER = "SMIME Enterprise Approver"
    SSL_ENTERPRISE_APPROVER = "SSL Enterprise Approver"

    def __str__(self):
        return self.value


class CertificateStatus(Enum):
    # GetSSLTransactions statuses
    VALID = "Valid"
    REVOKED = "Revoked"
    EXPIRED = "Expired"

    # GetSSLReviewableTransactions statuses
    PENDING = "Pending"
    READY = "Ready"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

    # Custom status
    ALL = "All"

    def __str__(self):
        return self.value


class HaricaClientConfig:
    """
    Configuration class for Harica client settings.
    Holds all configuration parameters needed for the Harica client.
    Loads configuration from files or environment variables.
    """

    def __init__(self, environment="production", alt_config_path=None):
        """
        Initialize the HaricaClientConfig by loading configuration for the specified environment.

        Args:
            environment (str): The environment to load configuration for. Defaults to "production".
            alt_config_path (str): An optional path to an alternative configuration file.
        """
        # Set default values
        self.username = None
        self.password = None
        self.totp_seed = None
        self.output_folder = None
        self.output_template = None
        self.http_proxy = None
        self.https_proxy = None
        self.webhook_url = None
        self.webhook_type = None

        # Load configuration
        self._load_config(environment, alt_config_path)

    def _load_config(self, environment="production", alt_config_path=None):
        """
        Load Harica configuration based on the environment.
        Includes optional HTTP and HTTPS proxy support.
        """
        bc_move_previous_config()

        # For backward compatibility set write permission
        config_path = settings.CONFIG_PATH
        if os.path.exists(config_path) and not os.access(config_path, os.W_OK):
            os.chmod(config_path, settings.CONFIG_FILE_PERMISSIONS)

        # Determine the section name based on the environment
        section_name = f"harica-{environment}" if environment != "production" else "harica"

        config_data = None

        # If a custom path is provided, only use that path
        if alt_config_path:
            config_paths_to_check = [alt_config_path]
        else:
            config_paths_to_check = settings.CONFIG_PATHS

        for path in config_paths_to_check:
            if os.path.exists(path):
                config = configparser.RawConfigParser()
                config.read(path)

                if config.has_section(section_name):
                    config_data = {
                        "username": config.get(section_name, "username"),
                        "password": config.get(section_name, "password"),
                        "totp_seed": config.get(section_name, "totp_seed", fallback=None),
                        "output_folder": config.get(section_name, "output_folder"),
                        "output_template": config.get(section_name, "output_template", fallback=None),
                        "http_proxy": config.get(section_name, "http_proxy", fallback=None),
                        "https_proxy": config.get(section_name, "https_proxy", fallback=None),
                        "webhook_url": config.get(section_name, "webhook_url", fallback=None),
                        "webhook_type": config.get(section_name, "webhook_type", fallback=settings.WEBHOOK_TYPE),
                    }
                    # Found config, no need to check further
                    break
                else:
                    logger.error(f"No configuration found for environment '{environment}' in {path}")
                    exit(1)

        # No fallback to env variables if alt_config_path is provided and config file is
        # not found
        if not config_data and alt_config_path:
            logger.error(f"Alternative config file '{alt_config_path}' not found.")
            exit(1)

        # Fallback to env variables if no config file
        if config_data is None:
            logger.info("No config file found. Falling back to environment variables.")
            config_data = {
                "username": os.getenv("HARICA_USERNAME"),
                "password": os.getenv("HARICA_PASSWORD"),
                "totp_seed": os.getenv("HARICA_TOTP_SEED"),
                "output_folder": os.getenv("HARICA_OUTPUT_FOLDER", settings.OUTPUT_PATH),
                "output_template": os.getenv("HARICA_OUTPUT_TEMPLATE"),
                "http_proxy": os.getenv("HARICA_HTTP_PROXY") or os.getenv("HTTP_PROXY"),
                "https_proxy": os.getenv("HARICA_HTTPS_PROXY") or os.getenv("HTTPS_PROXY"),
                "webhook_url": os.getenv("HARICA_WEBHOOK_URL") or os.getenv("WEBHOOK_URL"),
                "webhook_type": os.getenv("HARICA_WEBHOOK_TYPE") or os.getenv("WEBHOOK_TYPE"),
            }

            # Ensure all required environment variables are set
            if not all([config_data["username"], config_data["password"]]):
                logger.error(
                    "Configuration file or environment variables missing. "
                    "Generate config file with 'tcs-garr init' command or set "
                    "HARICA_USERNAME and HARICA_PASSWORD "
                    "environment variables."
                )
                exit(1)

        self._validate_config(config_data)

        # Set object attributes from config_data
        self.username = config_data["username"]
        self.password = config_data["password"]
        self.totp_seed = config_data["totp_seed"]
        self.output_folder = config_data["output_folder"]
        self.output_template = config_data["output_template"]
        self.http_proxy = config_data["http_proxy"]
        self.https_proxy = config_data["https_proxy"]
        self.webhook_url = config_data["webhook_url"]
        self.webhook_type = config_data["webhook_type"]

    @staticmethod
    def _validate_config(config_data):
        """
        Validate the configuration data.

        Args:
            config_data (dict): Configuration data to validate.
        """
        mandatory_fields = ["username", "password", "output_folder"]
        missing_fields = [key for key in mandatory_fields if not config_data.get(key)]
        if missing_fields:
            logger.error(f"❌ Missing mandatory configuration values for: {', '.join(missing_fields)}")
            exit(1)

        # Validate email
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        valid = re.match(pattern, config_data["username"])
        if not valid:
            logger.error(f"❌ Invalid email format for username: {config_data['username']}")
            exit(1)

        # Validate TOTP seed if provided
        totp_seed = config_data["totp_seed"]
        if totp_seed:
            try:
                generate_otp(totp_seed)
            except ValueError:
                logger.error(f"❌ Invalid TOTP seed: {totp_seed}")
                exit(1)

        # Validate the output folder path
        output_folder = config_data["output_folder"]
        if not pathlib.Path(output_folder).is_absolute():
            logger.error(f"x Invalid output_folder {output_folder!r}: must be an absolute path")
            exit(1)

        output_template = config_data["output_template"]
        if output_template:
            try:
                OutputTemplate(output_template)
            except ValueError as e:
                logger.error(f"❌ Invalid output_template: {e}")
                exit(1)


def generate_otp(totp_seed):
    totp = pyotp.parse_uri(totp_seed)
    return totp.now()


def check_pypi_version():
    """Get the latest version of the package from PyPI."""
    url = f"https://pypi.org/pypi/{settings.PACKAGE_NAME}/json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data["info"]["version"]
    else:
        raise Exception("Failed to fetch version from PyPI")


def get_current_version():
    """Get the currently installed version of the package."""
    return get_installed_version(settings.PACKAGE_NAME)


def is_installed_via_pipx():
    """Check if the current environment is pipx."""
    return shutil.which("pipx") is not None and "pipx" in sys.prefix


def upgrade_via_pip():
    """Upgrade the package using pip."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            settings.PACKAGE_NAME,
        ]
    )


def upgrade_via_pipx():
    """Upgrade the package using pipx."""
    subprocess.run(["pipx", "upgrade", settings.PACKAGE_NAME])


def upgrade_package():
    """Upgrade the package depending on whether it's installed via pip or pipx."""
    if is_installed_via_pipx():
        upgrade_via_pipx()
    else:
        upgrade_via_pip()


def bc_move_previous_config():
    """
    Move an existing config file from the home directory to the new CONFIG_PATH.

    This function must be removed in future releases.
    """
    import shutil

    old_config_path = os.path.join(os.path.expanduser("~"), settings.CONFIG_FILENAME)

    # Check if the old config file exists
    if os.path.exists(old_config_path):
        # Create directories that host config file
        os.makedirs(os.path.dirname(settings.CONFIG_PATH), exist_ok=True)

        # Move the config file
        try:
            shutil.move(old_config_path, settings.CONFIG_PATH)
            logger.debug("Moved existing config.")
        except Exception as e:
            logger.error(f"Failed to move config: {e}")
    else:
        logger.debug("No existing config file found to move.")


def format_date_and_check_expiry(date: str) -> tuple[str, bool]:
    """Format a iso 8601 date string and check if it has expired.

    Parameters
    ----------
    date : str
        Date in iso 8601 format

    Returns
    -------
    tuple[str, bool]
        Formatted date (%Y-%m-%d %H:%M) and a boolean indicating if it has expired

    """
    date = date.split(".")[0]  # Remove microseconds
    formatted_date = datetime.fromisoformat(date)
    expired = False

    if formatted_date < datetime.now():
        expired = True

    return formatted_date.strftime("%Y-%m-%d %H:%M"), expired


def is_hostname_valid(hostname: str) -> bool:
    """
    Check if a hostname is a valid Fully Qualified Domain Name. Does not resolve the name to an IP address.
    """
    return re.match(r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{4,}$", hostname, re.IGNORECASE) is not None


class OutputTemplate(string.Template):
    """
    A string template class for mapping a filename to a predefined filename/path.
    The template can be defined with any identifiers, but the following ones have
    a special meaning::

      - "fqdn": the Fully Qualified Domain Name.
      - "host": the host part of the FQDN, without the domain.
      - "domain": the domain part of the FQDN, if any.
      - "year": the current year as 4-digits integer value.
      - "month": the current month as zero-filled integer value with 2-digits.
      - "day": the current day as zero-filled integer value with 2-digits.
      - "suffix": the suffix part filename provided for translation, that could be a file extension.

    The template is valid if contains at least either "fqdn" or "host" identifiers.
    """

    def __init__(self, template: str = "${fqdn}${suffix}") -> None:
        super().__init__(template)
        try:
            self.substitute({k: k.upper() for k in self.get_identifiers()})
        except ValueError as e:
            raise ValueError(f"Invalid template string {template!r}: {e}") from None

        identifiers = self.get_identifiers()
        if "fqdn" not in identifiers and "host" not in identifiers:
            raise ValueError(f"Invalid template string {template!r}: missing both 'fqdn' and 'host' keys")

    def get_identifiers(self):
        return [t[1] or t[2] for t in self.pattern.findall(self.template)]

    def get_filepath(self, filename: str, **kwargs: str) -> str:
        """
        Apply the template substitution to a filename. The substitution can be applied if
        a *fqdn* identifier is provided using the keyword arguments. If *fqdn* is not
        provided the Fully Qualified Domain Name is extracted from the filename. If *fqdn* is
        missing returns the *filename* argument unchanged.

        Missing *host* and *domain* values are extracted from *fqdn*. Missing values for *year*,
        *month* and *day* ar filled using the current date. Missing additional identifiers are
        replaced with an empty string.

        Arguments
        ---------
        filename : str
            the source filename string to be processed by template.
        kwargs: str
            additional keyword arguments passed to template substitution.

        Returns
        -------
        str
            The resulting filepath by substitution.
        """
        filepath = pathlib.Path(filename)
        if "_" in filepath.name:
            fqdn, _, suffix = filepath.name.partition("_")
            suffix = _ + suffix
        else:
            fqdn = filepath.stem
            suffix = filepath.suffix

        if "fqdn" in kwargs:
            fqdn = kwargs.pop("fqdn")

        host, _, domain = fqdn.partition(".")
        today = datetime.today()

        mapping = {
            "fqdn": fqdn.lower(),
            "host": kwargs.pop("host", host).lower(),
            "domain": kwargs.pop("domain", domain).lower(),
            "year": kwargs.pop("year", str(today.year).zfill(4)),
            "month": kwargs.pop("month", str(today.month).zfill(2)),
            "day": kwargs.pop("day", str(today.day).zfill(2)),
            "suffix": kwargs.pop("suffix", suffix),
        }

        # Additional identifiers
        mapping.update(kwargs)
        for k in self.get_identifiers():
            if k not in mapping:
                mapping[k] = ""

        return self.substitute(mapping)
