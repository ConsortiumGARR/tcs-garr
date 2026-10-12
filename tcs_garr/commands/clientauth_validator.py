from tcs_garr.commands import _enterprise_validator


class ClientAuthValidatorCommand(_enterprise_validator.EnterpriseValidatorCommand):
    """
    Command to review Client Authentication requests and certificates as enterprise approver.
    """

    AREA = "clientauth"
    COMMAND_NAME = "clientauth-validator"
    LABEL = "Client Authentication"
