import unittest
import io
import logging
import pathlib
from unittest.mock import patch
from contextlib import contextmanager, redirect_stdout, redirect_stderr

from tcs_garr.commands.init import InitCommand
from tcs_garr.commands.whoami import WhoamiCommand
from tcs_garr.main import logger, main
import tcs_garr.main


class TestCommandLineInterface(unittest.TestCase):
    TEST_CONFIG_FILE = pathlib.Path(__file__).parent / "data" / "test-tcs-garr.conf"

    def exec_main(self, argv, exc=None):
        """Execute main() function and returns stdout and stderr produced by the call."""
        if "--config" not in argv:
            # Prepended because the subparser consumes everything after the command name
            argv = ["--config", str(self.TEST_CONFIG_FILE)] + argv

        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            if exc is None:
                main(argv)
            else:
                with self.assertRaises(exc):
                    main(argv)

        return out.getvalue().strip(), err.getvalue().strip()

    @contextmanager
    def assertNoLogsFrom(self, logger, level):
        """
        Substitute of TestCase.assertNoLogs(), that is available only from Python 3.10.
        A sentinel record is emitted because assertLogs() fails if nothing is logged.
        """
        with self.assertLogs(logger=logger, level=level) as cm:
            logger.log(logging.getLevelName(level), "sentinel record")
            yield
        self.assertListEqual(cm.output[1:], [])

    def test_help_option(self):
        out, err = self.exec_main(argv=["--help"], exc=SystemExit)
        self.assertIn("usage: tcs-garr [-h]", out)
        self.assertIn("whoami", out)
        self.assertEqual(err, "")

    def test_help_without_a_configuration(self):
        # The help message doesn't need the configuration, so it must not report its errors
        with self.assertNoLogsFrom(logger, "INFO"):
            out, _ = self.exec_main(argv=["--config", "unknown-file", "--help"], exc=SystemExit)
        self.assertIn("usage: tcs-garr [-h]", out)

    def test_no_command_prints_the_help(self):
        out, err = self.exec_main(argv=["--no-check-release"])
        self.assertIn("usage: tcs-garr [-h]", out)
        self.assertEqual(err, "")

    def test_version_option(self):
        # --version calls importlib.metadata.version() helper and then exit(0)
        out, err = self.exec_main(argv=["--version"], exc=SystemExit)
        self.assertRegex(out, r"\d+(\.\d+)*((a|b|rc)\d+)?")
        self.assertEqual(err, "")

    def test_invalid_environment(self):
        _, err = self.exec_main(argv=["--environment", "foo"], exc=SystemExit)
        self.assertIn("--environment: invalid choice: 'foo'", err)

    def test_release_check(self):
        with patch.object(WhoamiCommand, "execute"):
            with patch.object(tcs_garr.main, "get_current_version", return_value="0.1.0"):
                with patch.object(tcs_garr.main, "check_pypi_version", return_value="9.9.9"):
                    with self.assertLogs(logger=logger, level="INFO") as cm:
                        self.exec_main(argv=["whoami"])
                    self.assertEqual(len(cm.output), 1)
                    self.assertIn("New version available:", cm.output[0])

                    with self.assertNoLogsFrom(logger, "INFO"):
                        self.exec_main(argv=["--no-check-release", "whoami"])

    def test_command_is_executed(self):
        with patch.object(WhoamiCommand, "execute") as execute:
            self.exec_main(argv=["--no-check-release", "whoami"])
        execute.assert_called_once()

    def test_missing_config_file(self):
        with self.assertLogs(logger=logger, level="ERROR") as cm:
            self.exec_main(argv=["--config", "unknown-file", "whoami"], exc=SystemExit)
        self.assertEqual(len(cm.output), 1)
        self.assertIn("Alternative config file", cm.output[0])

    def test_init_runs_without_a_config_file(self):
        # 'init' creates the configuration, so it must run before the file exists
        with patch.object(InitCommand, "execute") as execute:
            self.exec_main(argv=["--no-check-release", "--config", "unknown-file", "init"])
        execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
