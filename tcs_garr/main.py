#!/usr/bin/env python

import argparse
import importlib
import inspect
import os
import pkgutil
from packaging import version
from typing import Optional

from tcs_garr.commands.base import BaseCommand
from tcs_garr.logger import setup_logger
from tcs_garr.utils import check_pypi_version, get_current_version, HaricaClientConfig

logger = setup_logger()


def discover_commands(args: argparse.Namespace, harica_config: HaricaClientConfig) -> dict[str, BaseCommand]:
    """
    Returns a dictionary with instances of discovered commands.

    Args:
        args (Namespace): CLI arguments provided for testing purposes. It could be initially empty.
        harica_config (HaricaClientConfig): Harica client configuration to initialize the harica client.
    """
    command_instances = {}
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
                    command_instances[cmd_name] = cmd_instance

    return command_instances


def get_arguments_parser(commands: Optional[dict[str, BaseCommand]] = None) -> argparse.ArgumentParser:
    """
    Create argument parser for CLI application.

    Args:
        commands: Add subparsers for command instances. Defaults to None.
    """
    parser = argparse.ArgumentParser(prog="tcs-garr", add_help=bool(commands), description="Harica Certificate Manager")

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
    if commands:
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
        for cmd_name, cmd_instance in commands.items():
            # Create a subparser for this command
            command_parser = subparsers.add_parser(cmd_name, help=cmd_instance.help_text)
            # Let the command instance configure its parser
            cmd_instance.configure_parser(command_parser)

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


def main(argv: Optional[list[str]] = None):
    """
    Main function to handle command line arguments and initiate the certificate issuance or listing process.

    Args:
        argv (optional list of str): arguments provided for non CLI usage. For default argparse use sys.argv[1:].
    """
    # Parse known arguments in order to load configuration by --config option, if any.
    args, unknown = get_arguments_parser().parse_known_args(args=argv)
    harica_config = HaricaClientConfig(
        environment=args.environment,
        alt_config_path=args.config,
    )

    # Dynamically load commands and get the full argument parser
    commands_instances = discover_commands(args, harica_config)
    parser = get_arguments_parser(commands=commands_instances)

    # Parse the arguments updating args instance using all CLI arguments
    parser.parse_args(namespace=args)

    if args.command != "init":
        # Check configuration only if the invoked command is not 'init'
        try:
            harica_config.validate_config()
        except (OSError, TypeError, ValueError):
            exit(1)

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
    if args.command in commands_instances:
        command_instance = commands_instances[args.command]
        command_instance.execute()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
