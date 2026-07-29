import configparser
import os
import re
import shutil
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

    CONFIG_FIELDS = (
        "username",
        "password",
        "totp_seed",
        "output_folder",
        "http_proxy",
        "https_proxy",
        "webhook_url",
        "webhook_type",
    )

    def __init__(self, environment="production", alt_config_path=None, load=True):
        """
        Initialize the HaricaClientConfig by loading configuration for the specified environment.

        Args:
            environment (str): The environment to load configuration for. Defaults to "production".
            alt_config_path (str): An optional path to an alternative configuration file.
            load (bool): Read the configuration sources. Set to False to get an empty configuration.
        """
        # Set default values
        for name in self.CONFIG_FIELDS:
            setattr(self, name, None)

        # Error occurred while loading, if any. Kept instead of raised because the
        # 'init' command has to run without a valid configuration in order to create one.
        self.load_error = None

        # Load configuration
        if load:
            try:
                self._load_config(environment, alt_config_path)
            except OSError as err:
                self.load_error = err

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
                        "http_proxy": config.get(section_name, "http_proxy", fallback=None),
                        "https_proxy": config.get(section_name, "https_proxy", fallback=None),
                        "webhook_url": config.get(section_name, "webhook_url", fallback=None),
                        "webhook_type": config.get(section_name, "webhook_type", fallback=settings.WEBHOOK_TYPE),
                    }
                    # Found config, no need to check further
                    break
                else:
                    raise OSError(f"No configuration found for environment '{environment}' in {path}")

        # No fallback to env variables if alt_config_path is provided and config file is
        # not found
        if not config_data and alt_config_path:
            raise OSError(f"Alternative config file '{alt_config_path}' not found.")

        # Fallback to env variables if no config file
        if config_data is None:
            logger.info("⚠️ No config file found. Falling back to environment variables.")
            config_data = {
                "username": os.getenv("HARICA_USERNAME"),
                "password": os.getenv("HARICA_PASSWORD"),
                "totp_seed": os.getenv("HARICA_TOTP_SEED"),
                "output_folder": os.getenv("HARICA_OUTPUT_FOLDER", settings.OUTPUT_PATH),
                "http_proxy": os.getenv("HARICA_HTTP_PROXY") or os.getenv("HTTP_PROXY"),
                "https_proxy": os.getenv("HARICA_HTTPS_PROXY") or os.getenv("HTTPS_PROXY"),
                "webhook_url": os.getenv("HARICA_WEBHOOK_URL") or os.getenv("WEBHOOK_URL"),
                "webhook_type": os.getenv("HARICA_WEBHOOK_TYPE") or os.getenv("WEBHOOK_TYPE"),
            }

        # Set object attributes from config_data, checked later by validate_config().
        for name in self.CONFIG_FIELDS:
            setattr(self, name, config_data[name])

    def as_dict(self):
        """Return the configuration values, without the loading state."""
        return {name: getattr(self, name) for name in self.CONFIG_FIELDS}

    def validate_config(self, config_data=None):
        """
        Validate the configuration data. Raises an exception on the first error found.

        Args:
            config_data (dict): Configuration data to validate. If not provided validate instance.
        """
        if config_data is None:
            config_data = self.as_dict()

        # Ensure all required environment variables are set
        missing_fields = [
            k for k in ("username", "password", "output_folder") if not (v := config_data.get(k)) or not isinstance(v, str)
        ]
        if missing_fields:
            raise TypeError(
                "Configuration file or environment variables missing for "
                f"configuration fields {', '.join(missing_fields)}. \n"
                "Generate config file with 'tcs-garr init' command or set "
                "HARICA_USERNAME and HARICA_PASSWORD environment variables."
            )

        # Validate email
        username = config_data["username"]
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(pattern, username):
            raise ValueError(f"Invalid email format for username: {username}")

        # Validate TOTP seed if provided
        totp_seed = config_data["totp_seed"]
        if totp_seed:
            try:
                generate_otp(totp_seed)
            except ValueError:
                raise ValueError(f"Invalid TOTP seed: {totp_seed}")


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
