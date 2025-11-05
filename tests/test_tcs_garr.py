import pathlib
import unittest
import unittest.mock as mock
import io
import uuid
from argparse import Namespace
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr

from tcs_garr.utils import is_hostname_valid, OutputTemplate
from tcs_garr.main import main
from tcs_garr.commands.download import DownloadCommand


monday = datetime(year=1999, month=9, day=13)


def set_test_config(**kwargs):
    """
    Returns a patch __init__ for tests, use kwargs to override test defaults.

    TODO: It would be better to have a patch to simulate a configuration file.
    """

    def client_config_init(self, environment="production", alt_config_path=None):
        self.username = "dummy@tcs-garr.test"
        self.password = "****************"
        self.totp_seed = "otpauth://totp/TEST:dummy@tcs-garr.test?secret=JBSWY3DPEHPK3PXP&issuer=TEST"
        self.output_folder = "/home/dummy/harica_certificates"
        self.output_template = None
        self.http_proxy = None
        self.https_proxy = (None,)
        self.webhook_url = (None,)
        self.webhook_type = "generic"
        self.__dict__.update(kwargs)

    return client_config_init


class TestHelpers(unittest.TestCase):
    def test_is_hostname_valid(self):
        self.assertTrue(is_hostname_valid("foo.example.test"))
        self.assertFalse(is_hostname_valid("foo"))
        self.assertTrue(is_hostname_valid("foo.test"))


class TestOutputTemplate(unittest.TestCase):
    def test_initialization(self):
        template = OutputTemplate("$fqdn")
        self.assertEqual(template.get_identifiers(), ["fqdn"])

        template = OutputTemplate("${host}_${domain}")
        self.assertEqual(template.get_identifiers(), ["host", "domain"])

        with self.assertRaises(ValueError) as cm:
            OutputTemplate("${domain}")
        self.assertEqual(str(cm.exception), "Invalid template string '${domain}': missing both 'fqdn' and 'host' keys")

        with self.assertRaises(ValueError) as cm:
            OutputTemplate("${cn}.${ext}")
        self.assertEqual(str(cm.exception), "Invalid template string '${cn}.${ext}': missing both 'fqdn' and 'host' keys")

        template = OutputTemplate("${host}")
        self.assertEqual(template.get_identifiers(), ["host"])

        template = OutputTemplate("${host}/${fqdn}")
        self.assertEqual(template.get_identifiers(), ["host", "fqdn"])

    def test_substitution(self):
        template = OutputTemplate()
        self.assertEqual(template.get_filepath("foo.example.test"), "foo.example.test")

    @mock.patch("tcs_garr.utils.datetime")
    def test_hostname_mapping(self, mock_datetime):
        mock_datetime.today.return_value = monday

        template = OutputTemplate("$fqdn-${year}${month}${day}${suffix}")
        self.assertEqual(template.get_filepath("foo.example.test.key"), "foo.example.test-19990913.key")

        template = OutputTemplate("$domain/$host/$fqdn-${year}${month}${day}")
        self.assertEqual(
            template.get_filepath("foo.example.test.key", year="2000", month="01", day="01"),
            "example.test/foo/foo.example.test-20000101",
        )

        template = OutputTemplate("$fqdn/${year}${month}${day}/${fqdn}${suffix}")
        self.assertEqual(template.get_filepath("foo.example.test.pem"), "foo.example.test/19990913/foo.example.test.pem")


class TestCommandLineInterface(unittest.TestCase):
    def exec_main(self, argv=None, exc=None):
        """Execute main() function and returns stdout and stderr produced by the call."""
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


class TestDownloadCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = Namespace(
            debug=False,
            no_check_release=False,
            command="download",
            environment="production",
            config=None,
            id=str(uuid.uuid4()),
            save=False,
            output_filename=None,
            force=False,
            download_type="pemBundle",
        )

    @mock.patch("tcs_garr.utils.HaricaClientConfig.__init__", set_test_config())
    def test_get_output_folder(self):
        command = DownloadCommand(args=self.args)
        self.assertEqual(command.harica_config.username, "dummy@tcs-garr.test")
        self.assertEqual(command.get_output_folder(), "/home/dummy/harica_certificates")

    @mock.patch("tcs_garr.utils.HaricaClientConfig.__init__", set_test_config())
    def test_get_output_filepath(self):
        command = DownloadCommand(args=self.args)
        self.assertEqual(command.harica_config.username, "dummy@tcs-garr.test")

        self.assertEqual(
            command.get_output_filepath("foo.example.test.pem"),
            pathlib.Path("/home/dummy/harica_certificates/foo.example.test.pem"),
        )
        self.assertEqual(
            command.get_output_filepath("  foo.example.test.pem"),
            pathlib.Path("/home/dummy/harica_certificates/foo.example.test.pem"),
        )
        self.assertEqual(
            command.get_output_filepath("foo_bundle.pem"), pathlib.Path("/home/dummy/harica_certificates/foo_bundle.pem")
        )

    @mock.patch(
        "tcs_garr.utils.HaricaClientConfig.__init__",
        set_test_config(output_template="${host}/${year}${month}${day}/${fqdn}${suffix}"),
    )
    @mock.patch("tcs_garr.utils.datetime")
    def test_get_output_filepath_with_subpath(self, mock_datetime):
        mock_datetime.today.return_value = monday

        command = DownloadCommand(args=self.args)
        self.assertEqual(command.harica_config.username, "dummy@tcs-garr.test")

        self.assertEqual(
            command.get_output_filepath("foo.example.test.key"),
            pathlib.Path("/home/dummy/harica_certificates/foo/19990913/foo.example.test.key"),
        )


if __name__ == "__main__":
    unittest.main()
