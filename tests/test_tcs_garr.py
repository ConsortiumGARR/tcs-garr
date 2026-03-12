import unittest
import io
import pathlib
from contextlib import redirect_stdout, redirect_stderr

from tcs_garr.main import main


class TestCommandLineInterface(unittest.TestCase):
    TEST_CONFIG_FILE = pathlib.Path(__name__).parent / "data" / "test-tcs-garr.conf"

    def exec_main(self, argv, exc=None):
        """Execute main() function and returns stdout and stderr produced by the call."""
        if "--config" not in argv:
            argv = argv + ["--config", str(self.TEST_CONFIG_FILE)]

        print(argv)
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            if exc is None:
                main(argv)
            else:
                with self.assertRaises(exc):
                    main(argv)

        return out.getvalue().strip(), err.getvalue().strip()

    def test_main_options(self):
        out, err = self.exec_main(argv=["--help"], exc=SystemExit)
        self.assertTrue(out.lstrip().startswith("usage: tcs-garr [-h]"))
        self.assertEqual(err, "")

        out, err = self.exec_main(argv=["--version"], exc=SystemExit)
        self.assertRegex(out, r"\d+(\.\d+)*((a|b|rc)\d+)?")
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
