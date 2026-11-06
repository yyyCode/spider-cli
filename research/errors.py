"""Errors shared by the DeepSeek search/fetch feature."""


class ResearchError(Exception):
    """An error that can be shown directly to the web UI."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ResearchConfigError(ResearchError):
    """Missing or invalid local configuration."""

    def __init__(self, message):
        super().__init__(message, 503)


class ResearchValidationError(ResearchError):
    """A request value rejected before it reaches DeepSeek."""

    def __init__(self, message):
        super().__init__(message, 400)
