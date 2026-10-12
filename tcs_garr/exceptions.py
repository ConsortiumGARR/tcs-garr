class CertificateNotApprovedException(Exception):
    """The requested certificated was not approved"""

    pass


class RateLimitError(Exception):
    """HARICA kept answering 429 Too Many Requests after all retries"""

    pass
