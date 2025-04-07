import configparser
import getpass
import os

from colorama import Fore, Style

import tcs_garr.settings as settings
from tcs_garr.commands.base import BaseCommand


class InitCommand(BaseCommand):
    """
    Command to generate or update the Harica configuration file.

    This command prompts the user for necessary credentials (email, password, and TOTP seed)
    and generates or updates the Harica configuration file in the user's home directory for the specified environment.
    When using the --force option to overwrite an existing configuration, it shows existing values as defaults.

    Args:
        args (argparse.Namespace): The command-line arguments passed to the command.
    """

    def __init__(self, args):
        """
        Initializes the InitCommand class.

        Args:
            args (argparse.Namespace): The command-line arguments passed to the command.
        """
        super().__init__(args)
        self.command_name = "init"
        self.help_text = "Generate Harica config file"

    def configure_parser(self, parser):
        """
        Configures the argument parser for the init command.

        This method defines the optional argument for forcing the overwrite of the configuration file.
        When force is used, existing configuration values will be shown as suggestions.

        Args:
            parser (argparse.ArgumentParser): The argument parser to configure.
        """
        # Optional argument to force overwrite of the configuration file
        parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Force overwrite configuration file. Existing values will be shown as defaults.",
        )

    def execute(self):
        """
        Executes the command to create or update the Harica configuration file.

        This method calls the `_create_config_file` method with the provided environment and force options.
        """
        # Call the method to create or update the configuration file
        self._create_config_file(self.args.environment, self.args.force)

    def _create_config_file(self, environment="production", force=False):
        """
        Creates or updates the Harica configuration file in the user's home directory for the specified environment.
        Now includes optional HTTP and HTTPS proxy settings.
        When force is True, shows previous values as defaults in square brackets.

        This method reads the existing configuration file, checks if a configuration already exists for the specified
        environment, and prompts the user for necessary credentials if a new configuration is needed. The configuration
        is then saved to the specified path.

        Args:
            environment (str): The environment for which to create the configuration. Defaults to "production".
            force (bool): Whether to force overwrite an existing configuration file. Defaults to False.
        """
        # Create a RawConfigParser instance to handle the configuration file
        config = configparser.RawConfigParser()

        # Set the section name based on the environment, defaulting to 'harica' for production
        section_name = f"harica-{environment}" if environment != "production" else "harica"

        # Default values
        existing_values = {
            "username": "",
            "password": "",
            "totp_seed": "",
            "output_folder": settings.OUTPUT_PATH,
            "http_proxy": "",
            "https_proxy": "",
        }

        # Check if the configuration file already exists
        has_existing_config = False
        if os.path.exists(settings.CONFIG_PATH):
            # Read the existing configuration file if it exists
            config.read(settings.CONFIG_PATH)

            # If section exists and force is True, get existing values
            if config.has_section(section_name):
                has_existing_config = True
                if force:
                    for key in existing_values:
                        if config.has_option(section_name, key):
                            existing_values[key] = config.get(section_name, key)
                else:
                    # Warn the user if the configuration already exists and is not forced to be overwritten
                    self.logger.warning(
                        f"Configuration for '{environment}' environment already exists in {settings.CONFIG_PATH}. "
                        f"If you want to reinitialize the configuration, use the --force option."
                    )
                    return

        # Ensure the directory for the config file exists
        os.makedirs(os.path.dirname(settings.CONFIG_PATH), exist_ok=True)

        # Prompt the user for credentials and configuration details
        # For force with existing config, show existing values in square brackets as suggestions
        if force and has_existing_config and existing_values["username"]:
            username = (
                input(f"{Fore.GREEN}👤 Enter Harica email [{existing_values['username']}]: {Style.RESET_ALL}")
                or existing_values["username"]
            )
        else:
            username = input(f"{Fore.GREEN}👤 Enter Harica email: {Style.RESET_ALL}")

        # Never show existing passwords or TOTP seeds as defaults
        if force and has_existing_config and existing_values["password"]:
            password = (
                getpass.getpass(
                    f"{Fore.GREEN}🔒 Enter Harica password [Press Enter to keep existing value]: {Style.RESET_ALL}"
                )
                or existing_values["password"]
            )
        else:
            password = getpass.getpass(f"{Fore.GREEN}🔒 Enter Harica password: {Style.RESET_ALL}")

        if force and has_existing_config and existing_values["totp_seed"]:
            totp_seed = (
                getpass.getpass(
                    f"{Fore.GREEN}🔒 Enter Harica TOTP Seed [Press Enter to keep existing value]: {Style.RESET_ALL}"
                )
                or existing_values["totp_seed"]
            )
        else:
            totp_seed = getpass.getpass(f"{Fore.GREEN}🔒 Enter Harica TOTP Seed: {Style.RESET_ALL}")

        # Prompt for output folder with existing value in brackets if force with existing config
        output_folder_prompt = f"{Fore.GREEN}📂 Enter output folder"
        if force and has_existing_config and existing_values["output_folder"]:
            output_folder_prompt += f" [{existing_values['output_folder']}]"
        else:
            output_folder_prompt += f" (default is '{settings.OUTPUT_PATH}')"
        output_folder = input(f"{output_folder_prompt}: {Style.RESET_ALL}") or (
            existing_values["output_folder"] if force and has_existing_config else settings.OUTPUT_PATH
        )

        # Expand in case input was a relative path
        output_folder = os.path.abspath(os.path.expanduser(output_folder))

        # Prompt for optional proxy settings with existing values in brackets if force with existing config
        http_proxy_prompt = f"{Fore.GREEN}🌐 Enter HTTP proxy (optional)"
        if force and has_existing_config and existing_values["http_proxy"]:
            http_proxy_prompt += f" [{existing_values['http_proxy']}]"
        http_proxy = input(f"{http_proxy_prompt}: {Style.RESET_ALL}") or (
            existing_values["http_proxy"] if force and has_existing_config else ""
        )

        https_proxy_prompt = f"{Fore.GREEN}🌐 Enter HTTPS proxy (optional)"
        if force and has_existing_config and existing_values["https_proxy"]:
            https_proxy_prompt += f" [{existing_values['https_proxy']}]"
        https_proxy = input(f"{https_proxy_prompt}: {Style.RESET_ALL}") or (
            existing_values["https_proxy"] if force and has_existing_config else ""
        )

        # Update the configuration with the user inputs
        config[section_name] = {
            "username": username,
            "password": password,
            "totp_seed": totp_seed,
            "output_folder": output_folder,
        }

        # Add proxy settings only if they were provided
        if http_proxy:
            config[section_name]["http_proxy"] = http_proxy
        if https_proxy:
            config[section_name]["https_proxy"] = https_proxy

        # Write the configuration to the file
        with open(settings.CONFIG_PATH, "w") as configfile:
            config.write(configfile)

        # Set appropriate permissions for the configuration file
        os.chmod(settings.CONFIG_PATH, settings.CONFIG_FILE_PERMISSIONS)

        # Log success message
        self.logger.info(f"✨ Configuration for '{environment}' environment updated at {settings.CONFIG_PATH}")
