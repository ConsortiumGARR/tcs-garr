import unittest
import io
import pathlib
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

from tcs_garr.main import logger, main
import tcs_garr.utils


class TestCommandLineInterface(unittest.TestCase):
    TEST_CONFIG_FILE = pathlib.Path(__file__).parent / "data" / "test-tcs-garr.conf"

    def exec_main(self, argv, exc=None):
        """Execute main() function and returns stdout and stderr produced by the call."""
        if "--config" not in argv:
            argv = argv + ["--config", str(self.TEST_CONFIG_FILE)]

        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            if exc is None:
                main(argv)
            else:
                with self.assertRaises(exc):
                    main(argv)

        return out.getvalue().strip(), err.getvalue().strip()

    def test_main_options(self):
        out, err = self.exec_main(argv=["--help"])
        self.assertTrue("usage: tcs-garr [-h]" in out)
        self.assertEqual(err, "")

        # --version calls importlib.metadata.version() helper and the exit(0)
        out, err = self.exec_main(argv=["--version"], exc=SystemExit)
        self.assertRegex(out, r"\d+(\.\d+)*((a|b|rc)\d+)?")
        self.assertEqual(err, "")

        with patch.object(tcs_garr.main, "get_current_version", return_value="0.1.0"):
            with self.assertLogs(logger=logger, level="INFO") as cm:
                self.exec_main(argv=["whoami"])
                self.assertEqual(len(cm.output), 1)
                self.assertIn("New version available:", cm.output[0])

            with self.assertNoLogs(logger=logger, level="INFO"):
                self.exec_main(argv=["whoami", "--no-check-release"])

        with self.assertLogs(logger=logger, level="ERROR") as cm:
            self.exec_main(argv=["--config", "unknown-file"], exc=OSError)
            self.assertEqual(len(cm.output), 1)
            self.assertIn("Alternative config file", cm.output[0])

        _, err = self.exec_main(argv=["--environment", "foo"], exc=SystemExit)
        self.assertIn("--environment: invalid choice: 'foo'", err)


if __name__ == "__main__":
    unittest.main()
