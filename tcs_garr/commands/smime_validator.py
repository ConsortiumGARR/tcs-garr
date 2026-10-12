from tcs_garr.commands import _enterprise_validator


class SmimeValidatorCommand(_enterprise_validator.EnterpriseValidatorCommand):
    """
    Command to review S/MIME requests and certificates as enterprise approver.
    """

    AREA = "smime"
    COMMAND_NAME = "smime-validator"
    LABEL = "S/MIME"
