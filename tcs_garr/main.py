#!/usr/bin/env python

import argparse
import importlib
import inspect
import os
import pkgutil
from packaging import version

from tcs_garr.commands.base import BaseCommand
from tcs_garr.logger import setup_logger
from tcs_garr.utils import check_pypi_version, get_current_version, HaricaClientConfig

logger = setup_logger()


def discover_commands(args: argparse.Namespace, harica_config: HaricaClientConfig):
    command_classes = {}
    package = "tcs_garr"
    package_dir = os.path.join(os.path.dirname(__file__), "commands")

    # Iterate over modules in the commands package
    for _, name, is_pkg in pkgutil.iter_modules([package_dir]):
        if not is_pkg and not name.startswith("_") and name != "base" and name != "main" and name != "utils":
            # Import the module
            module = importlib.import_module(f"{package}.commands.{name}")
            # Find all classes that inherit from BaseCommand
            for item_name, item in module.__dict__.items():
                if inspect.isclass(item) and issubclass(item, BaseCommand) and item is not BaseCommand:
                    # Create an instance of the command class
                    cmd_instance = item(args, harica_config)
                    cmd_name = cmd_instance.command_name or item.__name__.replace("Command", "").lower()
                    command_classes[cmd_name] = cmd_instance

    return command_classes


def get_arguments_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI application."""
    parser = argparse.ArgumentParser(description="Harica Certificate Manager")

    parser.add_argument("--debug", action="store_true", default=False, help="Enable DEBUG logging.")
    parser.add_argument(
        "--version",
        action="version",
        version=get_current_version(),
    )
    parser.add_argument(
        "--no-check-release",
        action="store_true",
        help="Skip checking for a new release",
    )
    parser.add_argument(
        "--environment",
        choices=["production", "stg"],
        default="production",
        help="Specify the environment to use (default: production)",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help=(
            "Alternative path to the configuration file (note: this will override the "
            "default path and will not use environment variables)"
        ),
    )
    return parser


def main(argv: list[str] = None):
    """
    Main function to handle command line arguments and initiate the certificate issuance or listing process.

    :param argv: Command line arguments.
    """
    parser = get_arguments_parser()

    # Parse know arguments and read/load the configuration once
    args, _ = parser.parse_known_args()
    harica_config = HaricaClientConfig(
        environment=args.environment,
        alt_config_path=args.config,
    )

    # Add subparsers and dynamically load commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    command_instances = discover_commands(args, harica_config)

    for cmd_name, cmd_instance in command_instances.items():
        # Create a subparser for this command
        command_parser = subparsers.add_parser(cmd_name, help=cmd_instance.help_text)
        # Let the command instance configure its parser
        cmd_instance.configure_parser(command_parser)

    # Parse arguments
    args = parser.parse_args()

    # Now, pass the args to command discovery and update command instances
    command_instances = discover_commands(args, harica_config)

    # Check for new release unless --no-check-release is specified
    if not args.no_check_release:
        # Get the current version of the application
        current_version = get_current_version()

        # Check the latest version available on PyPI
        latest_version = check_pypi_version()

        # Compare the current version to the latest version
        if version.parse(latest_version) > version.parse(current_version):
            logger.info(f"New version available: {latest_version}. Please consider updating with command tcs-garr upgrade.")

    # Execute the selected command
    if args.command in command_instances:
        command_instance = command_instances[args.command]
        command_instance.execute()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
